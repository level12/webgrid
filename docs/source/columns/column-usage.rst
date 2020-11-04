.. _column-usage:

General Column Usage
====================

Columns make up the grid's definition, as columns specify the data, layout, and formatting
of the grid table. In WebGrid, a column knows how to render itself to any output target and how
to apply sorting. In addition, the column is responsible for configuration of subtotals,
filtering, etc.

The most basic usage of the column is to specify a heading label and the SQLAlchemy expression
to be used. With this usage, sorting will be available in the grid/column headers, and the column
will be rendered on all targets::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name)


The grid will have a keyed lookup for the column as it is defined. In the above case, the grid
will pull the key from the SQLAlchemy expression, so the column may be referred to in surrounding
code as::

    grid.column('name')


Filtering
---------

When defining a column for a grid, a filter may be specified as part of the spec::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, TextFilter)


In the above, filtering options will be available for the `name` column. Because `TextFilter`
supports the single-search UI, the column will also be automatically searched with that feature.

While the most common usage of filters simply provides the filter class for the column definition,
a filter instance may be provided instead. Filter instances are useful when the column being
filtered differs from the column being displayed::

    class PeopleGrid(Grid):
        query_joins = ([entities.Person.location], )

        class LocationFilter(OptionsIntFilterBase):
            options_from = db.session.query(
                entities.Location.id, entities.Location.label
            ).all()

        Column('Name', entities.Person.name, TextFilter)
        Column('Location', entities.Location.name, LocationFilter(entities.Location.id))

A number of things are happening there:

- The grid is joining two entities
- A custom filter is provided for selecting locations from a list (see :ref:`custom-filters`)
- The location column renders the name, but filters based on the location ID


Sorting
-------

Some columns are display-only or filter-only and do not make sense as sorting options. For these,
use the `can_sort` option (default is True)::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, can_sort=False)

More advanced sort customization is available for column subclasses. See :ref:`custom-columns`
for more information.


Visibility
----------

WebGrid allows columns to be "turned off" for the table area (i.e. sort/filter only)::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, visible=False)

Also, a column may be designated as being present for specific renderers. This can be helpful
when a width-restricted format (like HTML) needs to leave out columns that are useful in more
extensive exports::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, render_in=('xlsx', 'csv'))


Subtotals
---------

Useful for numeric columns in particlar, subtotals options may be specified to provide a way
for the grid query to aggregate a column's data. Grids then have the option to turn on
subtotals for display at the page or grand level (or both).

The most basic subtotal specification is simply turning it on for a column, which will use the
SUM function::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, has_subtotal=True)

The same result may be achieved with one of the string options recognized::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, has_subtotal='sum')

The other string option recognized applies an average on the data::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, has_subtotal='avg')

For greater customization, a callable may be provided that takes the aggregated expression
and returns the function expression to use in the SQL query::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name,
               has_subtotal=lambda col: sa.sql.func.count(col))

Finally, a string may be provided for output on the totals row(s) instead of aggregated data::

    class PeopleGrid(Grid):
        Column('Name', entities.Person.name, has_subtotal="What's in a name?")
