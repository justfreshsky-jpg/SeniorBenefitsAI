"""Smoke tests for Senior Benefits AI."""
import os
import sys

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
    assert body['states'] == 51
    assert body['federal_benefits'] >= 20


def test_home_renders(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'Senior Benefits AI' in r.data
    assert b'California' in r.data
    assert b'Build my checklist' in r.data
    assert b'Three previews are included' in r.data
    assert b'Focus is $9.99 per month' in r.data
    assert b'no automatic overage charges' in r.data.lower()


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
