from __future__ import absolute_import

from flask import request, session, flash, Blueprint, url_for, send_file

from webgrid.extensions import FrameworkManager, translation_manager

try:
    from morphi.helpers.jinja import configure_jinja_environment
except ImportError:
    configure_jinja_environment = lambda *args, **kwargs: None  # noqa: E731


class WebGrid(FrameworkManager):
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

    """
    def init_db(self, db):
        """Set the db connector."""
        self.db = db

    def sa_query(self, *args, **kwargs):
        """Wrap SQLAlchemy query instantiation."""
        return self.db.session.query(*args, **kwargs)

    def request_args(self):
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
        return url_for('webgrid.static', filename=url_tail)

    def init_app(self, app):
        """Register a blueprint for webgrid assets, and configure jinja templates."""
        bp = Blueprint(
            'webgrid',
            __name__,
            static_folder='static',
            static_url_path=app.static_url_path + '/webgrid'
        )
        app.register_blueprint(bp)
        configure_jinja_environment(app.jinja_env, translation_manager)

    def file_as_response(self, data_stream, file_name, mime_type):
        """Return response from framework for sending a file."""
        return send_file(data_stream, mimetype=mime_type, as_attachment=True,
                         attachment_filename=file_name)
