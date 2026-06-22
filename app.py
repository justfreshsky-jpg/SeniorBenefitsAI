"""
Senior Benefits AI — Flask app.

Helps Americans 55+/65+ find federal and state benefits — Social Security, Medicare,
SNAP, Medicaid LTC, SSI, LIHEAP, senior housing, property tax relief, and state-specific
pharmacy + freeze programs. Forwards users to authoritative .gov resources rather than
duplicating them.

The personalized checklist tool uses an LLM fallback chain (US/EU providers only) gated
behind freshsky_common's freemium layer.
"""
import collections
import functools
import json
import logging
import os
import threading
import time

from flask import Flask, abort, jsonify, render_template, request, session

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32))
app.config.update(
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() == 'true',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger('seniorbenefits')


def _load_json(filename: str) -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


_FED = _load_json('federal_benefits.json')
_STATES = _load_json('states.json')

_FED_BY_KEY = {b['key']: b for b in _FED['benefits']}
_FED_BY_CATEGORY = collections.defaultdict(list)
for _b in _FED['benefits']:
    _FED_BY_CATEGORY[_b['category']].append(_b)
_CATEGORIES = _FED['categories']
_STATE_LIST = sorted(
    [{'code': code, 'name': data['name']} for code, data in _STATES.items()],
    key=lambda s: s['name'],
)


from freshsky_common.security import install_security_headers  # noqa: E402
install_security_headers(app)
from freshsky_common.caching import ResponseCache  # noqa: E402
from freshsky_common.revenue import install as _install_revenue  # noqa: E402
_install_revenue(
    app,
    slug='seniorbenefits',
    brand='Senior Benefits AI',
    primary_url='https://seniorbenefits.freshskyai.com/',
    category='benefits',
)

from freshsky_common.freemium import register_freemium  # noqa: E402

_freemium_check = register_freemium(
    app,
    google_client_id=os.environ.get('GOOGLE_CLIENT_ID', ''),
    google_client_secret=os.environ.get('GOOGLE_CLIENT_SECRET', ''),
    primary_url=os.environ.get('APP_URL', 'http://localhost:5000'),
)

_metrics = {'requests_total': 0, 'provider_success': collections.Counter(), 'provider_failure': collections.Counter()}
_metrics_lock = threading.Lock()


def _route_handler(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception:
            logger.exception('Unhandled exception in %s', f.__name__)
            return jsonify(error='Something went wrong. Please try again.'), 500
    return wrapper


# Provider calls are centralized in the privacy-restricted shared chain.

from freshsky_common.llm import LLMChain  # noqa: E402

_SHARED_LLM = LLMChain(privacy_profile="us_public")


def _llm_via_shared_chain(system, user):
    return _SHARED_LLM.complete(system=system, user=user) or None


_PROVIDERS = [('shared', _llm_via_shared_chain)]


_LLM_CACHE = ResponseCache(max_entries=500, ttl_seconds=3600)


def _llm(system: str, user: str) -> str:
    cache_key = ResponseCache.make_key(system, user)
    cached = _LLM_CACHE.get(cache_key)
    if cached is not None:
        with _metrics_lock:
            _metrics['provider_success']['cache'] += 1
        return cached

    last_err = None
    for name, fn in _PROVIDERS:
        try:
            out = fn(system, user)
            if out:
                with _metrics_lock:
                    _metrics['provider_success'][name] += 1
                result = out.strip()
                _LLM_CACHE.set(cache_key, result)
                return result
        except Exception as e:
            last_err = e
            with _metrics_lock:
                _metrics['provider_failure'][name] += 1
            logger.warning('Provider %s failed: %s', name, e)
    raise RuntimeError(f'All LLM providers failed: {last_err}')


_CHECKLIST_SYSTEM = """You are a benefits navigator for older Americans. Given a user's age, state, marital status, monthly income, and a brief description of their situation, you produce a PRIORITIZED, PERSONALIZED CHECKLIST of federal and state benefit programs they should investigate.

For each suggested program:
1. **Name** the program plainly (e.g., "Medicare Savings Program (QMB)").
2. State the **likely fit** ("strong fit," "worth checking," or "borderline — check eligibility carefully").
3. In ONE plain sentence, explain WHY based on what they told you.
4. Include the **single best official URL** to apply or learn more (.gov preferred, then BenefitsCheckUp.org or shiphelp.org).
5. State the **first concrete action** ("Call your state SHIP at 1-877-839-2675," "Apply online at ssa.gov/ssi," etc.).

Order programs from highest-impact to lowest. Group by category if you suggest more than 5 programs. End with one short paragraph titled "Where to start" that names the SINGLE most important call or application to make first based on their specific situation.

Do not invent programs. Stick to programs in widespread use and well-documented at federal or state level. If their state has a noteworthy state-specific program (pharmacy assistance, senior freeze, etc.) and it appears in your context data, include it.

Speak warmly, in plain English at an 8th-grade reading level. Address the reader as "you." End with a one-line disclaimer: "This is general guidance, not legal advice. Eligibility depends on your specific situation — confirm with the agency before relying on these numbers."
"""


@app.route('/')
def index():
    return render_template(
        'index.html',
        states=_STATE_LIST,
        categories=_CATEGORIES,
        federal_count=len(_FED['benefits']),
    )


@app.route('/federal')
def federal():
    benefits_by_cat = {cat['id']: _FED_BY_CATEGORY.get(cat['id'], []) for cat in _CATEGORIES}
    return render_template(
        'federal.html',
        categories=_CATEGORIES,
        benefits_by_cat=benefits_by_cat,
        states=_STATE_LIST,
    )


@app.route('/federal/<benefit_key>')
def federal_benefit(benefit_key):
    benefit = _FED_BY_KEY.get(benefit_key)
    if not benefit:
        abort(404)
    cat = next((c for c in _CATEGORIES if c['id'] == benefit['category']), None)
    return render_template(
        'benefit.html',
        benefit=benefit,
        category=cat,
        states=_STATE_LIST,
    )


@app.route('/state/<code>')
def state(code):
    code = code.upper()
    state_data = _STATES.get(code)
    if not state_data:
        abort(404)
    return render_template(
        'state.html',
        code=code,
        state=state_data,
        states=_STATE_LIST,
        categories=_CATEGORIES,
        federal_benefits=_FED['benefits'],
    )


@app.route('/api/states')
def api_states():
    return jsonify(states=_STATE_LIST)


@app.route('/api/personalized-checklist', methods=['POST'])
@_route_handler
def personalized_checklist():
    gate = _freemium_check()
    if gate is not None:
        return gate

    data = request.get_json(silent=True) or {}
    age_raw = data.get('age')
    state_code = (data.get('state') or '').strip().upper()
    marital = (data.get('marital') or '').strip().lower()
    income = (data.get('income') or '').strip()
    situation = (data.get('situation') or '').strip()
    veteran = bool(data.get('veteran'))

    try:
        age = int(age_raw)
    except (TypeError, ValueError):
        return jsonify(error='Please tell us your age.'), 400
    if age < 50 or age > 110:
        return jsonify(error='Age must be between 50 and 110.'), 400
    if state_code not in _STATES:
        return jsonify(error='Please select a state.'), 400
    if len(situation) > 1500:
        return jsonify(error='Situation description is too long (max 1500 characters).'), 400

    state_info = _STATES[state_code]
    state_summary = (
        f"State: {state_info['name']}. "
        f"State Department of Aging: {state_info['dept_aging']['name']} ({state_info['dept_aging']['url']}). "
        f"State Medicaid LTC info: {state_info['medicaid_ltc']}. "
    )
    if state_info.get('spap'):
        state_summary += f"State Pharmacy Assistance: {state_info['spap']['name']} ({state_info['spap']['url']}). "
    if state_info.get('property_tax'):
        pt = state_info['property_tax']
        state_summary += f"State Property Tax Relief: {pt['name']} — {pt['blurb']} ({pt['url']}). "
    if state_info.get('highlights'):
        state_summary += "State highlights: " + ' | '.join(state_info['highlights'])

    fed_summary = "FEDERAL PROGRAMS AVAILABLE NATIONWIDE:\n" + "\n".join(
        f"- {b['name']} (age {b['age_start'] or 'any'}+): {b['who']} | Apply: {b['url']}"
        for b in _FED['benefits']
    )

    user_profile = (
        f"AGE: {age}\n"
        f"STATE: {state_info['name']} ({state_code})\n"
        f"MARITAL STATUS: {marital or 'not specified'}\n"
        f"MONTHLY INCOME: {income or 'not specified'}\n"
        f"VETERAN OR SURVIVING SPOUSE OF VETERAN: {'yes' if veteran else 'no'}\n"
        f"SITUATION / GOAL: {situation or 'not specified'}\n\n"
        f"{state_summary}\n\n{fed_summary}"
    )

    with _metrics_lock:
        _metrics['requests_total'] += 1
    out = _llm(_CHECKLIST_SYSTEM, user_profile)
    return jsonify(result=out, state=state_info['name'])


@app.route('/health')
@app.route('/healthz')
def health():
    return jsonify(status='ok', federal_benefits=len(_FED['benefits']), states=len(_STATES))


@app.route('/metrics')
def metrics():
    with _metrics_lock:
        return jsonify({
            'requests_total': _metrics['requests_total'],
            'provider_success': dict(_metrics['provider_success']),
            'provider_failure': dict(_metrics['provider_failure']),
        })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
