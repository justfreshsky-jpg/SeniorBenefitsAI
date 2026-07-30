"""Smoke tests for Senior Benefits AI."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def client():
    os.environ.setdefault('SECRET_KEY', 'test-secret-key')
    os.environ.setdefault('SESSION_COOKIE_SECURE', 'false')
    from app import app
    app.testing = True
    return app.test_client()


def test_health(client):
    r = client.get('/health')
    assert r.status_code == 200
    body = r.get_json()
    assert body['status'] == 'ok'
    assert body['service'] == 'seniorbenefits'
    assert body['workspace_id'] == 'action_packs'
    assert body['required_subscription_tier'] == 'focus'
    assert body['subscription_price_cents'] == 999
    assert body['free_preview_limit'] == 3
    assert body['states'] == 51
    assert body['federal_benefits'] >= 20


def test_home_renders(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'Senior Benefits AI' in r.data
    assert b'California' in r.data
    assert b'Build my checklist' in r.data
    assert b'Focus \xc2\xb7 $9.99/month' in r.data
    assert b'No surprise overages' in r.data
    assert b'Do not include names, exact addresses' in r.data


def test_portfolio_checkout_and_status_contract(client):
    status = client.get('/api/user-status').get_json()
    assert status['workspace_id'] == 'action_packs'
    assert status['required_subscription_tier'] == 'focus'
    assert status['subscription_price_cents'] == 999
    assert status['free_preview_limit'] == 3
    assert (
        client.get('/subscribe').location
        == 'https://www.freshskyai.com/subscribe?workspace=action_packs'
    )
    assert (
        client.get('/subscribe/yearly').location
        == 'https://www.freshskyai.com/subscribe?workspace=action_packs'
    )
    assert client.get('/billing').location == 'https://www.freshskyai.com/billing'


def test_federal_index(client):
    r = client.get('/federal')
    assert r.status_code == 200
    assert b'Social Security Retirement' in r.data
    assert b'Medicare' in r.data


def test_federal_benefit_detail(client):
    r = client.get('/federal/medicare')
    assert r.status_code == 200
    assert b'Medicare' in r.data
    assert b'medicare.gov' in r.data


def test_2026_federal_figures_are_current_and_source_dated(client):
    from app import _FED_BY_KEY

    retirement = _FED_BY_KEY['ss-retirement']
    assert '$2,071' in retirement['what']
    assert '$4,152' in retirement['what']
    assert '$5,181' in retirement['what']
    assert '$4,018' not in retirement['what']

    ssi = _FED_BY_KEY['ssi']
    assert '$994' in ssi['what']
    assert '$1,491' in ssi['what']
    assert '$967' not in ssi['what']

    medicare = _FED_BY_KEY['medicare']
    assert '$202.90' in medicare['who']
    assert '$283' in medicare['who']

    extra_help = _FED_BY_KEY['extra-help']
    assert '$23,940' in extra_help['who']
    assert '$32,460' in extra_help['who']

    medicaid_ltc = _FED_BY_KEY['medicaid-ltc']
    assert '$4,066.50' in medicaid_ltc['tips']
    assert '$162,660' in medicaid_ltc['tips']

    for key in ('ss-retirement', 'ssi', 'ssdi', 'medicare', 'medicare-savings', 'extra-help', 'medicaid-ltc'):
        benefit = _FED_BY_KEY[key]
        assert benefit['figures_as_of'] == 'July 16, 2026'
        assert benefit['figure_sources']
        assert all(source['url'].startswith('https://') for source in benefit['figure_sources'])

    page = client.get('/federal/medicare').get_data(as_text=True)
    assert 'Federal figures verified July 16, 2026' in page
    assert 'CMS 2026 Medicare Parts A and B fact sheet' in page


def test_federal_unknown_benefit_404(client):
    r = client.get('/federal/this-does-not-exist')
    assert r.status_code == 404


def test_state_california(client):
    r = client.get('/state/CA')
    assert r.status_code == 200
    assert b'California' in r.data
    assert b'Property Tax Postponement' in r.data


def test_state_lowercase_ok(client):
    r = client.get('/state/tx')
    assert r.status_code == 200
    assert b'Texas' in r.data


def test_verified_state_link_repairs(client):
    from app import _STATES

    assert _STATES['AK']['dept_aging']['url'] == 'https://health.alaska.gov/en/senior-and-disabilities-services/'
    assert _STATES['AK']['medicaid_ltc'] == 'https://health.alaska.gov/en/senior-and-disabilities-services/'
    assert _STATES['AK']['spap'] is None
    assert _STATES['FL']['medicaid_ltc'].endswith('/long-term-care-program.html')
    assert _STATES['GA']['medicaid_ltc'].endswith('/waiver-programs')


def test_state_unknown_404(client):
    r = client.get('/state/XX')
    assert r.status_code == 404


def test_api_states(client):
    r = client.get('/api/states')
    assert r.status_code == 200
    body = r.get_json()
    assert len(body['states']) == 51
    codes = [s['code'] for s in body['states']]
    assert 'CA' in codes and 'NY' in codes and 'DC' in codes


def test_checklist_requires_age(client):
    r = client.post('/api/personalized-checklist', json={'state': 'CA'})
    assert r.status_code == 400
    assert b'age' in r.data.lower()


def test_checklist_api_is_private_even_on_validation_error(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, '_freemium_check', lambda: None)
    r = client.post('/api/personalized-checklist', json={'state': 'CA'})

    assert r.status_code == 400
    assert r.headers['Cache-Control'] == 'private, no-store, max-age=0'
    assert r.headers['Pragma'] == 'no-cache'
    assert r.headers['Expires'] == '0'
    assert r.headers['X-Robots-Tag'] == 'noindex, nofollow, noarchive'


@pytest.mark.parametrize('payload', [
    [],
    {'age': 65, 'state': 'CA', 'marital': 'not-a-real-option'},
    {'age': 65, 'state': 'CA', 'income': 'unbounded custom input'},
    {'age': 65, 'state': 'CA', 'veteran': 'false'},
    {'age': 65, 'state': 123},
])
def test_checklist_rejects_malformed_fields(client, monkeypatch, payload):
    import app as app_module

    monkeypatch.setattr(app_module, '_freemium_check', lambda: None)
    r = client.post('/api/personalized-checklist', json=payload)

    assert r.status_code == 400
    assert r.headers['Cache-Control'] == 'private, no-store, max-age=0'


def test_checklist_rejects_oversized_requests(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, '_freemium_check', lambda: None)
    r = client.post('/api/personalized-checklist', json={
        'age': 65,
        'state': 'CA',
        'situation': 'x' * (33 * 1024),
    })

    assert r.status_code == 413
    assert r.get_json()['error'] == 'Request is too large.'
    assert r.headers['Cache-Control'] == 'private, no-store, max-age=0'


def test_personalized_checklist_is_not_cached(client, monkeypatch):
    import app as app_module

    calls = []

    def provider(system, user):
        calls.append((system, user))
        return f'Checklist response {len(calls)}'

    monkeypatch.setattr(app_module, '_freemium_check', lambda: None)
    monkeypatch.setattr(app_module, '_PROVIDERS', [('test', provider)])
    payload = {
        'age': 70,
        'state': 'CA',
        'marital': 'single',
        'income': 'under $1,500',
        'situation': 'Need help lowering Medicare costs.',
    }

    first = client.post('/api/personalized-checklist', json=payload)
    second = client.post('/api/personalized-checklist', json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.get_json()['result'] == 'Checklist response 1'
    assert second.get_json()['result'] == 'Checklist response 2'
    assert len(calls) == 2
    assert first.headers['Cache-Control'] == 'private, no-store, max-age=0'


def test_personal_identifiers_are_rejected_with_422(client, monkeypatch):
    import app as app_module
    from freshsky_common.privacy import SensitiveDataError

    def reject(_system, _user):
        raise SensitiveDataError(('email',))

    monkeypatch.setattr(app_module, '_freemium_check', lambda: None)
    monkeypatch.setattr(app_module, '_PROVIDERS', [('test', reject)])
    response = client.post('/api/personalized-checklist', json={
        'age': 70,
        'state': 'CA',
        'situation': 'Contact me at person@example.com',
    })

    assert response.status_code == 422
    assert response.get_json()['code'] == 'sensitive_data_detected'
    assert response.get_json()['categories'] == ['email']
    assert response.headers['Cache-Control'] == 'private, no-store, max-age=0'


def test_personal_identifiers_are_rejected_before_provider(client, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, '_freemium_check', lambda: None)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError('Sensitive text reached the provider')

    monkeypatch.setattr(app_module, '_PROVIDERS', [('test', fail_if_called)])
    response = client.post('/api/personalized-checklist', json={
        'age': 70,
        'state': 'CA',
        'situation': 'Email me at senior@example.com with the result.',
    })

    assert response.status_code == 422
    assert response.get_json()['code'] == 'sensitive_data_detected'
    assert 'email' in response.get_json()['categories']


def test_candidate_mode_is_inert_in_a_fresh_process():
    script = """
import json
from app import app
app.config["TESTING"] = True
client = app.test_client()
health = client.get("/health")
root = client.get("/")
shared_css = client.get("/freshsky.css")
blocked = client.post(
    "/api/personalized-checklist",
    json={"age": 70, "state": "CA"},
)
print(json.dumps({
    "health": health.get_json(),
    "root_status": root.status_code,
    "shared_css_status": shared_css.status_code,
    "blocked_status": blocked.status_code,
    "blocked": blocked.get_json(),
}))
"""
    env = dict(os.environ)
    env['FRESHSKY_CANDIDATE_MODE'] = 'true'
    result = subprocess.run(
        [sys.executable, '-c', script],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    assert payload['health']['candidate_mode'] is True
    assert payload['health']['ai_requests_enabled'] is False
    assert payload['root_status'] == 200
    assert payload['shared_css_status'] == 200
    assert payload['blocked_status'] == 503
    assert payload['blocked']['code'] == 'candidate_mode'


def test_deploy_workflow_is_zero_traffic_secretless_and_exactly_priced():
    workflow = (
        Path(__file__).resolve().parents[1]
        / '.github'
        / 'workflows'
        / 'deploy.yml'
    ).read_text(encoding='utf-8')
    assert '--no-traffic' in workflow
    assert '--clear-secrets' in workflow
    assert 'FRESHSKY_CANDIDATE_MODE=true' in workflow
    assert 'FRESHSKY_WORKSPACE_ID=action_packs' in workflow
    assert 'FRESHSKY_SUBSCRIPTION_TIER=focus' in workflow
    assert (
        'FRESHSKY_SUBSCRIPTION_PRICE_ID='
        'price_1TwEqOCh3Z13FbXdyTubbeVF'
    ) in workflow
    assert 'FRESHSKY_SUBSCRIPTION_AMOUNT_CENTS=999' in workflow


def test_checklist_result_uses_safe_dom_rendering(client):
    page = client.get('/').get_data(as_text=True)

    assert 'innerHTML' not in page
    assert 'renderChecklist(out, data.result)' in page
    assert "url.protocol === 'https:'" in page
    assert "link.rel = 'noopener noreferrer'" in page
    assert 'document.createTextNode' in page


def test_checklist_requires_state(client):
    r = client.post('/api/personalized-checklist', json={'age': 65})
    assert r.status_code == 400
    assert b'state' in r.data.lower()


def test_checklist_age_bounds(client):
    r = client.post('/api/personalized-checklist', json={'age': 30, 'state': 'CA'})
    assert r.status_code == 400


def test_checklist_unknown_state(client):
    r = client.post('/api/personalized-checklist', json={'age': 65, 'state': 'ZZ'})
    assert r.status_code == 400
