.. _args-loaders:

Arguments Loaders
=================

Grid arguments are run-time configuration for a grid instance. This includes filter
operator/values, sort terms, search, paging, session key, etc.

Arguments may be provided to the grid directly, or else it pulls them from the assigned
framework manager. The most common use case will use the manager.


Managed arguments
-----------------

The grid manager uses "args loaders" (subclasses of ``ArgsLoader``) to supply grid
configuration. These loaders each represent a source of configuration. For instance, a
loader can pull args from the GET query string, a POSTed form, etc.

Args loaders are run in order of priority, with the highest-priority loader first. The first
loader gets a blank MultiDict as input, and then the results are chain-loaded through the
list of loaders.

The default setup provides request URL arguments to the first loader, and then
applies session information as needed. Some cases where you might want to do something
different from the default:
- The grid has options filters with a large number of options to select
- The grid has a lot of complexity that would be cleaner as POSTs rather than GETs

To use managed arguments with the default priority loaders, simply call ``apply_qs_args``
or ``build`` to have the grid load these for use in queries and rendering::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name)
        Column('Age', entities.Person.age)
        Column('Location', entities.Person.city)

    grid = PeopleGrid()
    grid.apply_qs_args()

Customizing the loader list on a managed grid requires setting the ``args_loaders`` iterable
on the manager. This can be set as a class attribute or provided in the manager's constructor.

As a class attribute::

    from webgrid import BaseGrid
    from webgrid.extensions import RequestArgsLoader, RequestFormLoader, WebSessionArgsLoader
    from webgrid.flask import WebGrid

    class GridManager(WebGrid):
        args_loaders = (
            RequestArgsLoader,    # part of the default, takes args from URL query string
            RequestFormLoader,    # use args present in the POSTed form
            WebSessionArgsLoader, # part of the default, but lower priority from the form POST
        )

    class Grid(BaseGrid):
        manager = GridManager()

Using the manager's constructor to customize the loader list::

    from webgrid import BaseGrid
    from webgrid.extensions import RequestArgsLoader, RequestFormLoader, WebSessionArgsLoader
    from webgrid.flask import WebGrid

    class Grid(BaseGrid):
        manager = WebGrid(
            args_loaders = (
                RequestArgsLoader,    # part of the default, takes args from URL query string
                RequestFormLoader,    # use args present in the POSTed form
                WebSessionArgsLoader, # part of the default, but lower priority from the form POST
            )
        )


.. autoclass:: webgrid.extensions.ArgsLoader
    :members:

.. autoclass:: webgrid.extensions.RequestArgsLoader
    :members:

.. autoclass:: webgrid.extensions.RequestFormLoader
    :members:

.. autoclass:: webgrid.extensions.RequestJsonLoader
    :members:

.. autoclass:: webgrid.extensions.WebSessionArgsLoader
    :members:


Supplying arguments directly
----------------------------

Arguments may be provided directly to `apply_qs_args` or `build` as a MultiDict. If arguments
are supplied in this fashion, other sources are ignored::

    from werkzeug.datastructures import MultiDict

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name)
        Column('Age', entities.Person.age)
        Column('Location', entities.Person.city)

    grid = PeopleGrid()
    grid.apply_qs_args(grid_args=MultiDict([
        ('op(name)', 'contains'),
        ('v1(name)', 'bill'),
    ]))
