from __future__ import absolute_import

import io
import warnings
from os import path

from flask import request, session, flash, Blueprint, url_for, send_file
import jinja2 as jinja

from webgrid.extensions import translation_manager

try:
    from morphi.helpers.jinja import configure_jinja_environment
except ImportError:
    configure_jinja_environment = lambda *args, **kwargs: None  # noqa: E731


class WebGrid(object):
    """Grid manager for connecting grids to Flask webapps.

    Instance should be assigned to the manager attribute of a grid class::

        class MyGrid(BaseGrid):
            manager = WebGrid()

    Args:
        db (flask_sqlalchemy.SQLAlchemy, optional): Database instance. Defaults to None.
        If db is not supplied here, it can be set via `init_db` later.

    Class Attributes:
        jinja_loader (jinja.Loader): Template loader to use for HTML rendering.

    """
    jinja_loader = jinja.PackageLoader('webgrid', 'templates')

    def __init__(self, db=None):
        self.init_db(db)
        self.jinja_environment = jinja.Environment(
            loader=self.jinja_loader,
            finalize=lambda x: x if x is not None else '',
            autoescape=True
        )

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

    def static_path(self):
        """Path containing static assets (images, CSS, JS)."""
        return path.join(path.dirname(__file__), 'static')

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

    def xls_as_response(self, workbook, file_name):
        warnings.warn('xls_as_response is deprecated. Use file_as_response instead',
                      DeprecationWarning)
        buf = io.BytesIO()
        workbook.save(buf)
        buf.seek(0)
        return self.file_as_response(buf, file_name, 'application/vnd.ms-excel')
