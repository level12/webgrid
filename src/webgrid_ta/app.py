from __future__ import absolute_import
import warnings

import flask
from flask import Flask
from flask_bootstrap import Bootstrap

from webgrid.flask import WebGrid

from webgrid_ta.extensions import translation_manager

try:
    from morphi.helpers.jinja import configure_jinja_environment
except ImportError:
    configure_jinja_environment = lambda *args, **kwargs: None  # noqa: E731

try:
    from morphi.registry import default_registry
except ImportError:
    from blazeutils.datastructures import BlankObject
    default_registry = BlankObject()


# ignore warning about Decimal lossy conversion with SQLite from SA
warnings.filterwarnings('ignore', '.*support Decimal objects natively.*')

webgrid = WebGrid()


def create_app(config='Dev', database_url=None):
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # app.config['SQLALCHEMY_ECHO'] = True
    # app.config['DEBUG'] = True
    if config == 'Test':
        app.config['TEST'] = True
    app.secret_key = 'only-testing'

    from webgrid_ta.model import db
    db.init_app(app)
    webgrid.init_db(db)
    default_registry.locales = app.config.get('DEFAULT_LOCALE', 'en')
    configure_jinja_environment(app.jinja_env, translation_manager)
    Bootstrap(app)
    webgrid.init_app(app)

    from webgrid_ta.views import main
    app.register_blueprint(main)

    @app.before_request
    def set_language():
        default_registry.locales = str(flask.request.accept_languages)
        configure_jinja_environment(app.jinja_env, translation_manager)

    return app
