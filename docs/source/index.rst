Welcome to WebGrid
======================

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

**Table of Contents**

.. toctree::
   :maxdepth: 2

   getting-started
   grid/grid
   grid/managers
   grid/args-loaders
   grid/types
   columns/index
   filters/index
   renderers/index
   testing/index
   gotchas
