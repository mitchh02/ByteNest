"""Search modes use the same path ranking and support managers without jobs."""
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.routes import search
from app.main import app


def test_manager_without_job_can_be_reached(monkeypatch):
    query = Mock(side_effect=[[{'id': 1}], [{'id': 2}], []])
    paths = Mock(return_value=[{'target_id': 2, 'path': [1, 2]}])
    monkeypatch.setattr(search.db, 'query', query)
    monkeypatch.setattr(search.graph, 'best_paths', paths)
    result = search.search(1, '  Alex   Chen ', search_type='manager')
    assert query.call_args_list[1].args[1] == ('%Alex Chen%',)
    paths.assert_called_once_with(1, [2], limit=3)
    assert result['results'][0]['job'] is None


def test_same_name_managers_remain_distinct(monkeypatch):
    job = {'id': 10, 'posted_by': 2, 'title': 'Engineer', 'company': 'Demo'}
    query = Mock(side_effect=[[{'id': 1}], [{'id': 2}, {'id': 3}], [job]])
    paths = Mock(return_value=[{'target_id': 2}, {'target_id': 3}])
    monkeypatch.setattr(search.db, 'query', query)
    monkeypatch.setattr(search.graph, 'best_paths', paths)
    result = search.search(1, 'Alex', search_type='manager')
    paths.assert_called_once_with(1, [2, 3], limit=3)
    assert [r['job'] for r in result['results']] == [job, None]


def test_role_search_keeps_existing_behavior(monkeypatch):
    job = {'id': 10, 'posted_by': 2, 'title': 'Engineer', 'company': 'Demo'}
    query = Mock(side_effect=[[{'id': 1}], [job, {**job, 'id': 11}]])
    paths = Mock(return_value=[{'target_id': 2}])
    monkeypatch.setattr(search.db, 'query', query)
    monkeypatch.setattr(search.graph, 'best_paths', paths)
    result = search.search(1, 'engineer')
    assert query.call_args_list[1].args[1] == ('%engineer%', '%engineer%')
    paths.assert_called_once_with(1, [2], limit=3)
    assert result['results'][0]['job'] == job


def test_manager_no_matches_skips_graph(monkeypatch):
    monkeypatch.setattr(search.db, 'query', Mock(side_effect=[[{'id': 1}], []]))
    paths = Mock()
    monkeypatch.setattr(search.graph, 'best_paths', paths)
    assert search.search(1, 'Nobody', search_type='manager')['results'] == []
    paths.assert_not_called()


def test_unknown_seeker(monkeypatch):
    monkeypatch.setattr(search.db, 'query', Mock(return_value=[]))
    with pytest.raises(HTTPException) as error:
        search.search(999, 'Alex', search_type='manager')
    assert error.value.status_code == 404


def test_user_lookup_returns_distinct_profiles_and_escapes_name(monkeypatch):
    users = [{'id': 2, 'first_name': 'Alex', 'last_name': 'Chen', 'company': 'Demo'},
             {'id': 3, 'first_name': 'Alex', 'last_name': 'Chen', 'company': 'Other'}]
    query = Mock(return_value=users)
    monkeypatch.setattr(search.db, 'query', query)
    with TestClient(app) as client:
        response = client.get('/users/lookup', params={'q': '  Alex   Chen%_! '})
    assert response.status_code == 200
    assert response.json()['users'] == users
    assert query.call_args.args[1] == ('%Alex Chen!%!_!!%',)


def test_user_lookup_empty_name_and_validation(monkeypatch):
    query = Mock()
    monkeypatch.setattr(search.db, 'query', query)
    with TestClient(app) as client:
        assert client.get('/users/lookup', params={'q': '  '}).json() == {'users': []}
        assert client.get('/users/lookup', params={'q': ''}).status_code == 422
        assert client.get('/users/lookup', params={'q': 'a' * 202}).status_code == 422
    query.assert_not_called()
