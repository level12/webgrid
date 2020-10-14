Framework Managers
==================

One design goal of the base grid class is that it be essentially framework-agnostic. That is,
the grid, by itself, should not care if it is being run in Flask, BlazeWeb, or another web
app framework. As long as it has a connection to the framework that provides required items
with a consistent interface, the grid should interact with the framework through that connection.

Wrapped features available through the manager:

- SQLAlchemy connection and queries
- Request
- Session storage
- Flash messages
- File export in response

.. autoclass:: webgrid.flask.WebGrid
    :members:
