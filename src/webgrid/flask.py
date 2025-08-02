from __future__ import absolute_import
import json

import flask

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
    blueprint_class = flask.Blueprint

    def __init__(self, db=None, jinja_loader=None, args_loaders=None, session_max_hours=None,
                 blueprint_name=None, blueprint_class=None):
        self.blueprint_name = blueprint_name or self.blueprint_name
        self.blueprint_class = blueprint_class or self.blueprint_class
        self._registered_grids = {}
        super().__init__(db=db, jinja_loader=jinja_loader, args_loaders=args_loaders,
                         session_max_hours=session_max_hours)

    def init_db(self, db):
        """Set the db connector."""
        self.db = db

    def sa_query(self, *args, **kwargs):
        """Wrap SQLAlchemy query instantiation."""
        return self.db.session.query(*args, **kwargs)

    def request_form_args(self):
        """Return POST request args."""
        return flask.request.form

    def request_json(self):
        """Return json body of request."""
        return flask.request.json

    def request_url_args(self):
        """Return GET request args."""
        return flask.request.args

    def csrf_token(self):
        """Return a CSRF token for POST."""
        from flask_wtf.csrf import generate_csrf
        return generate_csrf()

    def web_session(self):
        """Return current session."""
        return flask.session

    def persist_web_session(self):
        """Some frameworks require an additional step to persist session data."""
        flask.session.modified = True

    def flash_message(self, category, message):
        """Add a flash message through the framework."""
        flask.flash(message, category)

    def request(self):
        """Return request."""
        return flask.request

    def test_request_context(self, url='/'):
        """Get request context for tests."""
        return flask.current_app.test_request_context(url)

    def static_url(self, url_tail):
        """Construct static URL from webgrid blueprint."""
        return flask.url_for('{}.static'.format(self.blueprint_name), filename=url_tail)

    def init_blueprint(self, app):
        """Create a blueprint for webgrid assets."""
        return self.blueprint_class(
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
        return flask.send_file(data_stream, mimetype=mime_type, as_attachment=as_attachment,
                               download_name=file_name)


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
    ``flask_wtf``, but that is not really applicable to API endpoints. We take posts
    on the API view, but they will not inject information for storage - the API simply sets
    up and returns a grid. If you do wish to have CSRF protection, use the ``csrf_protection``
    class attribute and apply ``CSRFProtect`` to your application. Note that in that scenario
    you will need to apply the CSRF token manually to any API requests. If CSRF protection
    is not desired for the grid API endpoint, make sure ``init_app`` is called on the
    CSRF extension prior to this grid manager.

    Special Class Attributes:
        api_route_prefix (string): Prefix for URL route to bind on the manager's blueprint.
        Default "/webgrid-api". By default, ``api_route`` uses this to construct
        "/webgrid-api/<grid_ident>".
    """
    blueprint_name = 'webgrid-api'
    api_route_prefix = '/webgrid-api'
    args_loaders = (extensions.RequestJsonLoader, )
    csrf_protection = False

    def __init__(self, db=None, jinja_loader=None, args_loaders=None, session_max_hours=None,
                 blueprint_name=None, blueprint_class=None, api_route_prefix=None):
        self.api_route_prefix = api_route_prefix or self.api_route_prefix
        self._registered_grids = {}
        super().__init__(db=db, jinja_loader=jinja_loader, args_loaders=args_loaders,
                         session_max_hours=session_max_hours, blueprint_name=blueprint_name,
                         blueprint_class=blueprint_class)

    def init_blueprint(self, app):
        """Create a blueprint for webgrid assets and set up a generic API endpoint."""
        blueprint = super().init_blueprint(app)

        # conditionally exempt the blueprint from CSRF protection
        if not self.csrf_protection and app.extensions.get('csrf'):
            app.extensions['csrf'].exempt(blueprint)

        blueprint.route(self.api_route, methods=('POST', ))(
            self.api_view_method
        )
        blueprint.route(self.api_route + '/count', methods=('POST', ))(
            self.api_count_view_method
        )

        if app.config.get('TESTING'):
            @blueprint.route(self.api_route_prefix + '/testing/__csrf__', methods=('GET', ))
            def csrf_get():
                from flask_wtf.csrf import generate_csrf
                return generate_csrf()

        return blueprint

    @property
    def api_route(self):
        """URL route to bind on the manager's blueprint for serving grids."""
        return self.api_route_prefix + '/<grid_ident>'

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

    def api_init_grid_post(self, grid):
        """Hook to run API-level init on every grid after instantiation"""
        pass

    def api_on_render_limit_exceeded(self, grid):
        """Export failed due to number of records. Returns a JSON response."""
        return flask.jsonify(error='too many records for render target')

    def api_export_response(self, grid):
        """Set up grid for export and return the response. Handles render limit exception."""
        import webgrid

        try:
            return grid.export_as_response()
        except webgrid.renderers.RenderLimitExceeded:
            return self.api_on_render_limit_exceeded(grid)

    def generate_requested_grid(self, grid_ident):
        if grid_ident not in self._registered_grids:
            flask.abort(404)

        grid = self.api_init_grid(self._registered_grids.get(grid_ident))
        self.api_init_grid_post(grid)

        # Make the API as flexible as possible to accept JSON post requests for grids
        # that may be used in other areas of the application, hence managed by a different
        # Flask extension/manager.
        grid.manager = self

        # Check auth before applying any args
        grid.check_auth()
        grid.apply_qs_args(add_user_warnings=False)

        return grid

    def api_view_method(self, grid_ident):
        """Main API view method. Returns JSON-rendered grid or desired export.

        No authentication/authorization is explicit here. Be sure to apply generic
        auth or set up ``check_auth`` on specific grids, if authorization is needed.

        If the ``grid_ident`` is not registered, response is 404.
        """
        grid = self.generate_requested_grid(grid_ident)

        if grid.export_to:
            return self.api_export_response(grid)

        # Be as flexible as possible here. If the grid has a JSON renderer, use it. But,
        # provide a default if it does not.
        renderer = getattr(grid, 'json', renderers.JSON(grid))

        # not using jsonify here because the JSON renderer returns a string
        return flask.Response(renderer(), mimetype='application/json')

    def api_count_view_method(self, grid_ident):
        """API view method to count records without returning the records and other grid info.
        Returns a dict with a count key.

        No authentication/authorization is explicit here. Be sure to apply generic
        auth or set up ``check_auth`` on specific grids, if authorization is needed.

        If the ``grid_ident`` is not registered, response is 404.
        """
        grid = self.generate_requested_grid(grid_ident)

        # not using jsonify here because the JSON renderer returns a string
        return flask.Response(json.dumps({'count': grid.record_count}), mimetype='application/json')
