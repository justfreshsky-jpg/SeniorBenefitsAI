"""Smoke tests for Senior Benefits AI."""
import json
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
