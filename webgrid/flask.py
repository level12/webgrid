from __future__ import absolute_import

import flask
from flask import request, session, flash, Blueprint, url_for, send_file

from webgrid import extensions, renderers

try:
    from morphi.helpers.jinja import configure_jinja_environment
except ImportError:
    configure_jinja_environment = lambda *args, **kwargs: None  # noqa: E731


class WebGrid(extensions.FrameworkManager):
    """Grid manager for connecting grids to Flask webapps.

    Manager is a Flask extension, and may be bound to an app via ``init_app``.

    Instance should be assigned to the manager attribute of a grid class::

        class MyGrid(BaseGrid):
            manager = WebGrid()

    Args:
        db (flask_sqlalchemy.SQLAlchemy, optional): Database instance. Defaults to None.
        If db is not supplied here, it can be set via ``init_db`` later.

    Class Attributes:
        jinja_loader (jinja.Loader): Template loader to use for HTML rendering.

        args_loaders (ArgsLoader[]): Iterable of classes to use for loading grid args, in order
        of priority

        session_max_hours (int): Hours to hold a given grid session in storage. Set to None to
        disable. Default 12.

        blueprint_name (string): Identifier to use for the Flask blueprint on this extension.
        Default "webgrid". Needs to be unique if multiple managers are initialized as flask
        extensions.
    """
    blueprint_name = 'webgrid'

    def init_db(self, db):
        """Set the db connector."""
        self.db = db

    def sa_query(self, *args, **kwargs):
        """Wrap SQLAlchemy query instantiation."""
        return self.db.session.query(*args, **kwargs)

    def request_form_args(self):
        """Return POST request args."""
        return request.form

    def request_json(self):
        """Return json body of request."""
        return request.json

    def request_url_args(self):
        """Return GET request args."""
        return request.args

    def web_session(self):
        """Return current session."""
        return session

    def persist_web_session(self):
        """Some frameworks require an additional step to persist session data."""
        session.modified = True

    def flash_message(self, category, message):
        """Add a flash message through the framework."""
        flash(message, category)

    def request(self):
        """Return request."""
        return request

    def static_url(self, url_tail):
        """Construct static URL from webgrid blueprint."""
        return url_for('{}.static'.format(self.blueprint_name), filename=url_tail)

    def init_blueprint(self, app):
        """Create a blueprint for webgrid assets."""
        return Blueprint(
            self.blueprint_name,
            __name__,
            static_folder='static',
            static_url_path=app.static_url_path + '/webgrid'
        )

    def init_app(self, app):
        """Register a blueprint for webgrid assets, and configure jinja templates."""
        self.blueprint = self.init_blueprint(app)
        app.register_blueprint(self.blueprint)
        configure_jinja_environment(app.jinja_env, extensions.translation_manager)

    def file_as_response(self, data_stream, file_name, mime_type):
        """Return response from framework for sending a file."""
        as_attachment = (file_name is not None)
        return send_file(data_stream, mimetype=mime_type, as_attachment=as_attachment,
                         attachment_filename=file_name)


class WebGridAPI(WebGrid):
    """Subclass of WebGrid manager for creating an API connected to grid results.

    Manager is a Flask extension, and may be bound to an app via ``init_app``.

    Grids intended for API use should be registered on the manager via ``register_grid``.

    Security note: no attempt is made here to perform explicit authentication or
    authorization for the view. Those layers of functionality are the app developer's
    responsibility. For generic auth, ``api_view_method`` may be wrapped/overridden,
    or set up ``check_auth`` accordingly on your base grid class. Grid-specific auth can
    be handled in each grid's ``check_auth``.

    CSRF note: CSRF protection is standard security practice on Flask apps via
    ``flask_wtf``. If the API set up here will be used in scenarios with cookies
    (e.g. Ajax requests), protection should be applied here. If your app is set up
    with a simple ``CSRFProtect``, no further action should be required.

    Special Class Attributes:
        api_route (string): URL route to bind on the manager's blueprint.
        Default "/webgrid-api/<grid_ident>".
    """
    blueprint_name = 'webgrid-api'
    api_route = '/webgrid-api/<grid_ident>'
    args_loaders = (extensions.RequestJsonLoader, )

    def init(self):
        self._registered_grids = {}

    def init_blueprint(self, app):
        """Create a blueprint for webgrid assets and set up a generic API endpoint."""
        blueprint = super().init_blueprint(app)
        blueprint.route(self.api_route, methods=('POST', ))(
            self.api_view_method
        )

        if app.config.get('TESTING'):
            @blueprint.route('/webgrid-api-testing/__csrf__', methods=('GET', ))
            def csrf_get():
                from flask_wtf.csrf import generate_csrf
                return generate_csrf()

        return blueprint

    def register_grid(self, grid_ident, grid_cls_or_creator):
        """Identify a grid class for API use via an identifying string.

        The identifier provided here will be used in route matching to init the
        requested grid. Identifiers are enforced as unique.

        ``grid_cls_or_creator`` may be a grid class or some other callable returning
        a grid instance.
        """
        if grid_ident in self._registered_grids:
            raise Exception('API grid_ident must be unique')

        self._registered_grids[grid_ident] = grid_cls_or_creator

    def api_init_grid(self, grid_cls_or_creator):
        """Create the grid instance from the registered class/creator."""
        return grid_cls_or_creator()

    def api_on_render_limit_exceeded(self, grid):
        """Export failed due to number of records. Returns a JSON response."""
        return flask.jsonify(error='too many records for render target')

    def api_export_response(self, grid):
        """Set up grid for export and return the response. Handles render limit exception."""
        import webgrid

        try:
            return grid.export_as_response()
        except webgrid.renderers.RenderLimitExceeded:
            return self.on_render_limit_exceeded(grid)

    def api_view_method(self, grid_ident):
        """Main API view method. Returns JSON-rendered grid or desired export.

        No authentication/authorization is explicit here. Be sure to apply generic
        auth or set up ``check_auth`` on specific grids, if authorization is needed.

        If the ``grid_ident`` is not registered, response is 404.
        """
        if grid_ident not in self._registered_grids:
            flask.abort(404)

        grid = self.api_init_grid(self._registered_grids.get(grid_ident))
        grid.manager = self
        grid.check_auth()
        grid.apply_qs_args()

        if grid.export_to:
            return self.api_export_response()

        # not using jsonify here because the JSON renderer returns a string
        return flask.Response(grid.json(), mimetype='application/json')
