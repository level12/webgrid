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
SQLAlchemy ORM entities and queries.

With a grid configured from one or more entities, WebGrid provides these features for reporting:

- Automated SQL query construction based on specified columns and query join/filter/sort options
- Renderers to various targets/formats

  - HTML output paired with JS (jQuery) for dynamic features
  - Excel (XLSX)
  - CSV
- User-controlled data filters

  - Per-column selection of filter operator and value(s)
  - Generic single-entry search
- Session storage/retrieval of selected filter options, sorting, and paging

Installation
------------

Install using `pip`::

    pip install webgrid

Some basic internationalization features are available via extra requirements::

    pip install webgrid[i18n]

A Simple Example
----------------

For a simple example, see the `Getting Started guide <https://webgrid.readthedocs.io/en/stable/getting-started.html>`_ in the docs.

Running the Tests
-----------------

Webgrid uses `Tox <https://tox.readthedocs.io/en/latest/>`_ to manage testing environments & initiate tests. Once you
have installed it via `pip install tox` you can run `tox` to kick off the test suite.

Webgrid is continuously tested against Python 3.6, 3.7, and 3.8. You can test against only a certain version by running
`tox -e py38-base` for whichever Python version you are testing.


Links
---------------------

* Documentation: https://webgrid.readthedocs.io/en/stable/index.html
* Releases: https://pypi.org/project/WebGrid/
* Code: https://github.com/level12/webgrid
* Issue tracker: https://github.com/level12/webgrid/issues
* Questions & comments: http://groups.google.com/group/blazelibs
