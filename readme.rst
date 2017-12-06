WebGrid
#######

.. image:: https://ci.appveyor.com/api/projects/status/6s1886gojqi9c8h6?svg=true
    :target: https://ci.appveyor.com/project/level12/webgrid

.. image:: https://circleci.com/gh/level12/webgrid.svg?style=shield
    :target: https://circleci.com/gh/level12/webgrid

.. image:: https://codecov.io/gh/level12/webgrid/branch/master/graph/badge.svg
    :target: https://codecov.io/gh/level12/webgrid

Introduction
---------------

WebGrid is a datagrid library for Flask and other Python web frameworks designed to work with
SQLAlchemy ORM entities.

Based on the configured grid, it will output an HTML table with sorting, filtering, and paging.

It also will export the grid to Excel.

For now, if you are interested in using it, you will need to see the source code and tests therein
for example usage.

Questions & Comments
---------------------

Please visit: http://groups.google.com/group/blazelibs

Running the Tests
----------------

Make sure to include the `--nologcapture` flag to nosetests or else you will get
failures when testing the logging features.

Current Status
---------------

Currently beta quality.

Changes in 0.2.0
----------------

This update includes backwards-incompatible changes that affect the way column classes
are defined.

From this point forward, column classes should declare their pertinent configuration options
via class attributes, rather than as initialization parameters.

Pre-0.2.0:

    class SomeColumn(Column):
        def __init__(self, label, key=None, filter=None, can_sort=False,
                 link_label=None, xls_width=None, xls_style=None, xls_num_format=None,
                 render_in=_None, **kwargs):
            Column.__init__(self, label, key, filter, can_sort, xls_width,
                        xls_style, xls_num_format, render_in, **kwargs)
            self.link_label = link_label


The equivalent code, beginning in 0.2.0:

    class SomeColumn(Column):
        can_sort = False
        link_label = None

