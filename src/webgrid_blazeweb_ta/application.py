from blazeweb.application import WSGIApp
from blazeweb.middleware import full_wsgi_stack
from blazeweb.scripting import application_entry
from sqlalchemybwc.lib.middleware import SQLAlchemyApp

import webgrid_blazeweb_ta.config.settings as settingsmod


def make_wsgi(profile='Dev'):
    app = WSGIApp(settingsmod, profile)

    app = SQLAlchemyApp(app)

    return full_wsgi_stack(app)


def script_entry():
    application_entry(make_wsgi)


if __name__ == '__main__':
    script_entry()
