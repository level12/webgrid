from unittest import mock

import flask
import flask_webtest
import flask_wtf
import pytest
from webgrid import BaseGrid, Column
from webgrid.flask import WebGridAPI
from webgrid.renderers import JSON


@pytest.fixture
def app():
    app = flask.Flask(__name__)
    app.secret_key = 'only-testing-api'
    app.config['TESTING'] = True
    yield app


@pytest.fixture
def csrf(app):
    csrf = flask_wtf.CSRFProtect()
    csrf.init_app(app)
    yield csrf


@pytest.fixture
def test_app(app):
    yield flask_webtest.TestApp(app)


@pytest.fixture
def api_manager(app):
    manager = WebGridAPI()
    manager.init_app(app)
    yield manager


def create_grid_cls(grid_manager):
    class Grid(BaseGrid):
        manager = grid_manager
        allowed_export_targets = {'json': JSON}

        Column('Foo', 'foo')

        @property
        def records(self):
            return [{'foo': 'bar'}]

    return Grid


def register_grid(manager, identifier, grid_cls):
    manager.register_grid(identifier, grid_cls)


class TestFlaskAPI:
    def test_default_route(self, api_manager, test_app):
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        resp = test_app.post('/webgrid-api/foo', {})
        assert resp.json['records'] == [{"foo": "bar"}]

    def test_custom_route(self, app, test_app):
        class GridManager(WebGridAPI):
            api_route = '/custom-routing/<grid_ident>'

        api_manager = GridManager()
        api_manager.init_app(app)
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        resp = test_app.post('/custom-routing/foo', {})
        assert resp.json['records'] == [{"foo": "bar"}]

    def test_grid_not_registered(self, api_manager, test_app):
        test_app.post('/webgrid-api/foo', {}, status=404)

    def test_grid_registered_twice(self, api_manager, test_app):
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        with pytest.raises(Exception, match='API grid_ident must be unique'):
            register_grid(api_manager, 'foo', create_grid_cls(api_manager))

    def test_csrf_missing_token(self, api_manager, csrf, test_app):
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        resp = test_app.post('/webgrid-api/foo', {}, status=400)
        assert 'The CSRF token is missing.' in resp

    def test_csrf_missing_session(self, api_manager, csrf, test_app):
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        resp = test_app.post(
            '/webgrid-api/foo', {}, headers={'X-CSRFToken': flask_wtf.csrf.generate_csrf()},
            status=400)
        assert 'The CSRF session token is missing.' in resp

    def test_csrf_invalid(self, api_manager, csrf, test_app):
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        test_app.get('/webgrid-api-testing/__csrf__').body
        resp = test_app.post(
            '/webgrid-api/foo', {}, headers={'X-CSRFToken': 'my-bad-token'},
            status=400)
        assert 'The CSRF token is invalid.' in resp

    def test_csrf_protected(self, api_manager, csrf, test_app):
        register_grid(api_manager, 'foo', create_grid_cls(api_manager))
        csrf_token = test_app.get('/webgrid-api-testing/__csrf__').body
        resp = test_app.post(
            '/webgrid-api/foo', {}, headers={'X-CSRFToken': csrf_token})
        assert resp.json['records'] == [{"foo": "bar"}]

    def test_csrf_token_route_only_testing(self, app, csrf, test_app):
        manager = WebGridAPI()
        with mock.patch.dict(app.config, {'TESTING': False}):
            manager.init_app(app)

        test_app.get('/webgrid-api-testing/__csrf__', status=404)
