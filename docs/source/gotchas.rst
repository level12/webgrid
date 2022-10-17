Common Gotchas
==============

Following are some common scenarios encountered in application development with WebGrid. Generally,
there is a reason why the given behavior occurs. If you run into a problem that is not listed here
but seems to be wrong or counterintuitive behavior, feel free to create an issue for it.

Grid
----

**Grid identifier**

Every grid instance has an identifier: the `ident` property. This value is used for session lookups
to grab/store the most recent set of request args applied to that grid.

The identifier is set in one of three ways, in order of priority:

- Value passed in grid constructor::

    class PeopleGrid(BaseGrid):
        Column('Name', Person.name)

    grid = PeopleGrid(ident='my-awesome-grid')

- Class attribute assigned::

    class PeopleGrid(BaseGrid):
        identifier = 'my-awesome-grid'
        Column('Name', Person.name)

- Default derived from class name, e.g. `people_grid`

**Query usage**

Grid classes are generally loaded at import time. Because Column instances attached to a grid class
can refer to SQLAlchemy expressions, some frameworks have limitations in what can be declared.

Most entity attributes used directly will be fine. However, if a grid refers to attributes in a
SQLAlchemy query, under Flask-SQLAlchemy you will see some import-time issues. Creating queries
within that framework requires the app context to be present, but at import time, that is usually
not the case.

To resolve this, currently, the grid class would need to be defined in a factory method::

    def people_grid_factory():
        query = db.session.query(Person.name).subquery()

        class PeopleGrid(BaseGrid):
            Column('Name', query.c.name)

        return PeopleGrid

Request Management
------------------

**Multiple grids on a page**

Because grids use URL arguments to configure page/filter/sort, having more than one grid on
a page requires some additional setup. Use the qs_prefix on one of the grids to differentiate
it in session/request loads::

    class PeopleGrid(BaseGrid):
        Column('Name', Person.name)

    class EquipmentGrid(BaseGrid):
        Column('Model', Equipment.model)

    people_grid = PeopleGrid()
    equipment_grid = EquipmentGrid(qs_prefix='equip')

**Query string too long**

Submitting the header form typically directs to a GET request with args for all page/filter/sort information.
While we trim out any filter inputs we can to keep the string size manageable, with enough filters
selected, the query can overflow the limits of the target server.

This scenario comes up most commonly with multiselect filters having lots of options. Each option
selected results in the full filter value arg being added to the query string, and so it will
easily cause the overflow.

The solution is to use the form POSTed args loader (``RequestFormLoader``), which will direct the
UI form to use a POST instead of a GET. This is not the default due to backwards-compatibility, since
many views using WebGrid are GET-only routes. However, the default may change in the future.

Please refer to :ref:`args-loaders` for details about customizing the loading of grid configuration.

An alternative solution would be to configure your nginx/apache/etc. parameters accordingly for
maximum request size.

**Overriding the session**

Session storage in WebGrid is generally all-or-nothing for filter information. That is, we have
two basic scenarios:

- `session_key` URL argument is present without any filter arguments

  - Filter information will be pulled from session and applied

- Filter arguments are present along with the `session_key`

  - Session information is discarded, and the new filter information stored in its place

Page/sort arguments do not trigger the session discard.

In some situations, it can be helpful to provide a single filter in a request without discarding
session information. To do this, include a `session_override` arg (properly prefixed). The
following example will retain any other filters in the session, and override only the name
filter::

    https://mysite.com/mypage?session_key=12345&session_override=1&op(name)=eq&v1(name)=steve

**Sharing session between grids**

Sometimes, grids are similar enough that a common set of filters will apply to multiple grids. For
instance, a tabbed report of similar data may show varying levels of detail, but have the same
top-level filters.

To share filter values across such a set of grids, you can pass the `session_key`. The target grid
will recognize that a foreign session has loaded and ignore any filters that don't match up on the
target.

Note, when doing this sort of operation, the session will update to reflect the new grid.

Column
------

**Multiple columns with the same name**

WebGrid does not enforce unique column key names in the grid definition. However, these keys are
made to be unique at run time, to preserve the ability to refer to any column by its key. For
example::

    class PeopleGrid(BaseGrid):
        query_joins = ([entities.Person.location], )

        Column('Name', entities.Person.name, TextFilter)
        Column('Location', entities.Location.name, TextFilter)

In this example, both columns would be keyed as 'name'. To make this unique, WebGrid will
find unique keys at run time. `Person.name` will have the `name` key, but `Location.name`
will be assigned `name_1`. Further `name` columns would get `name_2`, `name_3`, etc.

Keep in mind, filter/sort arguments must follow the key. If we try to set a filter on
location name in the view, that would become::

    people_grid.set_filter('name_1', 'eq', 'Paris')

To apply a specific key in this scenario rather than accepting the one generated, simply label
one of the columns::

    class PeopleGrid(BaseGrid):
        query_joins = ([entities.Person.location], )

        Column('Name', entities.Person.name, TextFilter)
        Column('Location', entities.Location.name.label('location'), TextFilter)

**Subclassing Column with a new constructor**

In many cases, creating a subclass of `Column` for app-specific behavior is not a problem
(see :ref:`custom-columns`). If you need to put in a custom constructor, though, beware,
for here be monsters.

In WebGrid, with the declarative grid setup, `Column` instances are created and attached to
a grid class definition. When the grid class is instantiated, these column instances must
be copied to new instances for the grid instance to use.

That instance copy assumes a certain arrangement of constructor arguments. The first four
arguments must be in the same order: `label`, `key`, `filter`, and `can_sort`. The remaining
arguments should also be present in the new constructor, or else they will likely not be
carried over to the new instance (unless the custom constructor sets them).

This is a known limitation to the way that columns are instantiated for grids. Because the
need for custom constructors is minimal in practice, this arrangement will likely stay in
place for the foreseeable future.

**Column only for filter, no display**

For summary-level tables, it can be desirable to filter the recordset on values that are not
in the rendered result. One must be careful when dealing with aggregations and grouping,
however, because having the column in the SELECT list may require grouping and affect data
granularity for the result.

To avoid inclusion in SELECT, pass the column expression directly to the filter rather than
the column itself::

    Column('Last Name', 'no_expr', TextFilter(Person.lastname), visible=False, can_sort=False)

In the above case, `Person.lastname` will not be in SELECT. But, it will be included in the
WHERE clause if the filter is set or search is used. The other keyword arguments remove the
column from rendering and sorting, so the column is useful only for filtering.

Filter
------

**Setting a filter**

Filters may be set directly::

    grid.column('name').filter.set('eq', 'steve')

Or, through the grid::

    grid.set_filter('name', 'eq', 'steve')

Some filters have two values::

    grid.column('date').filter.set('selmonth', '3', value2='2020')

The first value of a filter is required when setting, even if the filter does not take any values::

    grid.column('name').filter.set('empty', None)

**OptionsEnumFilter**

Most filters can be assigned to a column as a class or an instance. One, `OptionsEnumFilter` currently
requires an instance, so the `enum_type` can be passed in the constructor. This means the column also
must be passed to the filter::

    EnumColumn(
        'Type', Project.type, OptionsEnumFilter(Project.type, enum_type=ProjectType),
    )

**Aggregate columns**

When constructing a grid column from an aggregate, remember that filters for that column will not be
allowed in the SQL WHERE clause. Instead, they need to be in the HAVING clause.

Because of this, use the `Aggregate` filters instead of `IntFilter` and `NumberFilter`.

Using aggregate filters will require having a GROUP BY clause set on the grid query.

**Aggregate filters and search**

Search will only include aggregate filters if all searchable filters are aggregate.

The search box assumes that all search expressions can be combined with OR to generate a complete
search expression. Because of this, search can use the WHERE clause or the HAVING clause, but not
both. Using columns in HAVING requires they be in the GROUP BY, which will affect data granularity
for some reports.

If search should include columns computed with aggregate functions, build a wrapping select
query that includes the necessary aggregation and grouping in a nested select or CTE. Then, build
the grid with the results of the wrapping query, which will not involve the need for aggregate
filters.


File Exports
------------

**Excel sheet name limitations**

Excel has a limit of 30 characters on worksheet names. If a name is provided that will exceed
that limit, it will be truncated with a trailing ellipse.

**Excel records limitations**

Excel file formats have limits of how many rows can be included. This was a bigger issue when
XLS was the common format, but XLSX does have limits as well.

The XLSX renderer will raise a `RenderLimitExceeded` exception if the query result is too
large.

**Excel file naming**

Excel will not load multiple files with the same filename, even though they are in different
directories. For this reason, we append a random numeric suffix on the filenames, so Excel
will see them as different workbooks.
