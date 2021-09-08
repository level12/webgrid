Arguments Loaders
=================

Grid arguments are run-time configuration for a grid instance. This includes filter
operator/values, sort terms, search, paging, session key, etc.

Arguments may be provided to the grid directly, or else it pulls them from the assigned
framework manager. The most common use case will use the manager.


Managed arguments
-----------------

The common use case supported by the defaults has the framework manager providing arguments. In
this scenario, simply call `apply_qs_args` or `build` to have the grid load these for use in
queries and rendering::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name)
        Column('Age', entities.Person.age)
        Column('Location', entities.Person.city)

    grid = PeopleGrid()
    grid.apply_qs_args()


To load the arguments, the grid manager uses "args loaders" - subclasses of ArgsLoader. These
loaders are run in order of priority, and they are chained: each loader's input is the output of
the previous loader. The first loader gets a blank MultiDict as input.

The default setup provides request URL arguments to the first loader, and then
applies session information as needed.

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
