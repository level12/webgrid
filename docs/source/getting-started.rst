Getting Started
===============

.. contents::
    :local: 1

.. _gs-install:

Installation
------------

Install using `pip`::

    pip install webgrid

Some basic internationalization features are available via extra requirements::

    pip install webgrid[i18n]


.. _gs-manager:

Manager
-------

Because WebGrid is generally framework-agnostic, a number of features are segmented into
a grid framework manager. These include items like request object, session, serving files,
etc.::

    class Grid(webgrid.BaseGrid):
        manager = webgrid.flask.WebGrid()

The above may be specified once in the application and used as a base class for all grids.

Depending on the framework, setting up the manager also requires some additional steps to
integrate with the application.

Flask Integration
^^^^^^^^^^^^^^^^^

In Flask, two integrations are necessary:

- Set up the connection to SQLAlchemy
- Integrate WebGrid with the Flask application

For a Flask app using Flask-SQLAlchemy for database connection/session management, the grids
may use the same object that the rest of the app uses for query/data access. As an
extension, the grid manager will register a blueprint on the Flask app to serve static
files.

The following is an example of a minimal Flask app that is then integrated with WebGrid::

    from flask import Flask
    from flask_sqlalchemy import SQLAlchemy
    import webgrid

    class Grid(webgrid.BaseGrid):
        """Common base grid class for the application."""
        manager = webgrid.flask.WebGrid()

    # Minimal Flask app setup
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'
    db = SQLAlchemy(app)

    # Integrate WebGrid as an extension
    Grid.manager.init_db(db)
    Grid.manager.init_app(app)


.. _gs-basic-grid:

Basic Grid
----------

Once the application's main `Grid` class has been defined with the appropriate manager, app
grids may be created::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name)
        Column('Age', entities.Person.age)
        Column('Location', entities.Person.city)

The options available for setting up grids is truly massive. For starters, some good places
to begin would be:

- :ref:`column-usage` for ways to configure the column layout
- :ref:`base-grid` for grid options and query setup


.. _gs-templates:

Templates
---------

If WebGrid is being used in an HTML context, some template inclusions must be made to support the
header features, default styling, etc. The following will assume a Flask app with a Jinja template
environment; customize to the needed framework and application.

Note, with the Flask grid manager, static assets are available through the blueprint the manager
adds to the application.

CSS
^^^

Two CSS sheets are required and may be included as follows::

    <link href="{{url_for('webgrid.static', filename='webgrid.css')}}" rel="stylesheet" media="screen">
    <link href="{{url_for('webgrid.static', filename='multiple-select.css')}}" rel="stylesheet" media="screen">

JS
^^

WebGrid requires jQuery to be available. In addition, two JS assets are needed::

    <script src="{{url_for('webgrid.static', filename='jquery.multiple.select.js')}}"></script>
    <script src="{{url_for('webgrid.static', filename='webgrid.js')}}"></script>

Rendering
^^^^^^^^^

Once the templates have all of the required assets included, rendering the grids themselves is
fairly basic::

    {{ grid.html() | safe}}

The `safe` filter is important for Jinja environments where auto-escape is enabled, which is the
recommended configuration. The grid renderer output contains HTML markup and so must be directly
inserted.


.. _gs-i18n:

Internationalization
--------------------

WebGrid supports `Babel`-style internationalization of text strings through the `morphi` library.
To use this feature, specify the extra requirements on install::

    pip install webgrid[i18n]

Currently, English (default) and Spanish are the supported languages in the UI.
