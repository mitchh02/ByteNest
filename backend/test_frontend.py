"""The frontend and API share one server; these checks need no database."""
from fastapi.testclient import TestClient

from app.main import app


def test_frontend_routes_and_assets():
    with TestClient(app) as client:
        for route in ('/', '/auth'):
            response = client.get(route)
            assert response.status_code == 200
            assert response.headers['content-type'].startswith('text/html')
            assert 'id="search-form"' in response.text
        for asset in ('app.js', 'style.css'):
            assert client.get(f'/assets/{asset}').status_code == 200
        assert client.get('/assets/missing.js').status_code == 404


def test_frontend_does_not_override_api_routes():
    with TestClient(app) as client:
        assert client.get('/health').json() == {'ok': True}
        schema = client.get('/openapi.json').json()
        assert '/search' in schema['paths']
        assert '/auth/login' in schema['paths']
        assert client.post('/auth/login', json={}).status_code == 422
        assert client.get('/auth/me').status_code == 401
        assert client.get('/unknown').status_code == 404
