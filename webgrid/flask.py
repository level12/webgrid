from __future__ import absolute_import

from flask import request, session, flash, Blueprint, url_for, send_file

from webgrid import extensions

try:
    from morphi.helpers.jinja import configure_jinja_environment
except ImportError:
    configure_jinja_environment = lambda *args, **kwargs: None  # noqa: E731


class WebGrid(extensions.FrameworkManager):
    """Grid manager for connecting grids to Flask webapps.

    Instance should be assigned to the manager attribute of a grid class::

        class MyGrid(BaseGrid):
            manager = WebGrid()

    Args:
        db (flask_sqlalchemy.SQLAlchemy, optional): Database instance. Defaults to None.
        If db is not supplied here, it can be set via `init_db` later.

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

    def init_app(self, app):
        """Register a blueprint for webgrid assets, and configure jinja templates."""
        self.blueprint = Blueprint(
            self.blueprint_name,
            __name__,
            static_folder='static',
            static_url_path=app.static_url_path + '/webgrid'
        )
        app.register_blueprint(self.blueprint)
        configure_jinja_environment(app.jinja_env, extensions.translation_manager)

    def file_as_response(self, data_stream, file_name, mime_type):
        """Return response from framework for sending a file."""
        as_attachment = (file_name is not None)
        return send_file(data_stream, mimetype=mime_type, as_attachment=as_attachment,
                         attachment_filename=file_name)


class WebGridAPI(WebGrid):
    blueprint_name = 'webgrid-api'
    api_route = '/webgrid-api/<grid_ident>'
    args_loaders = (extensions.RequestJsonLoader, )

    def init(self):
        self._registered_grids = {}

    def init_app(self, app):
        super().init_app(app)
        self.setup_route()

    def register_grid(self, grid_ident, grid_cls_or_creator):
        if grid_ident in self._registered_grids:
            raise Exception('API grid_ident must be unique')

        self._registered_grids[grid_ident] = grid_cls_or_creator

    def api_init_grid(self, grid_cls_or_creator):
        return grid_cls_or_creator()

    def api_on_render_limit_exceeded(self, grid):
        return flask.jsonify({'error': 'too many records for render target'})

    def api_export_response(self, grid):
        import webgrid

        try:
            return grid.export_as_response()
        except webgrid.renderers.RenderLimitExceeded:
            return self.on_render_limit_exceeded(grid)

    def api_view_method(self, grid_ident):
        if grid_ident not in self._registered_grids:
            flask.abort(404)

        grid = self.api_init_grid(self._registered_grids.get(grid_ident))
        grid.manager = self
        grid.check_auth()
        grid.apply_qs_args()

        if grid.export_to:
            return self.api_export_response()

        return grid.json()

    def setup_route(self):
        # add view to blueprint
        self.blueprint.route(self.api_route, methods=('GET', 'POST', 'HEAD'))(
            self.api_view_method
        )
