Changelog
=========

0.3.4 released 2021-01-25
-------------------------

- Move request/session args loading to manager, prevent cookie overflow (9b4b39e_)
- Shift deprecated raises decorator usage to pytest.raises (42cf416_)
- Remove unused code objects/attributes (f6e2160_)

.. _9b4b39e: https://github.com/level12/webgrid/commit/9b4b39e
.. _42cf416: https://github.com/level12/webgrid/commit/42cf416
.. _f6e2160: https://github.com/level12/webgrid/commit/f6e2160


0.3.3 released 2020-12-10
-------------------------

- Exclude aggregate filters from search unless all are aggregate (8381960_)
- Set 2-part filter values next to each other (0ef2a99_)

.. _8381960: https://github.com/level12/webgrid/commit/8381960
.. _0ef2a99: https://github.com/level12/webgrid/commit/0ef2a99


0.3.2 released 2020-11-18
-------------------------

- remove werkzeug version pin (8082a46_)

.. _8082a46: https://github.com/level12/webgrid/commit/8082a46


0.3.1 released 2020-11-13
-------------------------

- Fix single-search from aggregate filters (33d772e_)

.. _33d772e: https://github.com/level12/webgrid/commit/33d772e


0.3.0 released 2020-11-04
-------------------------

- Set up documentation for use on readthedocs.io (d0a486b_)
- Move Add Filter select to top, combine with search row when applicable (4e0a502_)
- Create documentation with sphinx (6dbe96a_)
- Use openpyxl for testing XLSX output (xlrd is deprecated) (51bc80f_)
- Add helper classes for testing grids (3d5867f_)
- Run test suite against multiple databases (SQLite, PostgreSQL, MSSQL) (69ce644_)
- Assign unique keys when multiple columns have the same name (d34fc89_)
- Reduce clicks required to add a filter (c76320f_)
- Reduce vertical spacing used in the hader (54f8eb9_)
- Deprecate the XLS renderer (6e450f1_)
- Clarify removal of python 3.5 support (2f58762_)
- Pass all filter values through grid set_filter method (af06abe_)
- Add between ops to numeric filters (7736069_)
- Ensure grid reset clears search value (b8012d2_)

.. _d0a486b: https://github.com/level12/webgrid/commit/d0a486b
.. _4e0a502: https://github.com/level12/webgrid/commit/4e0a502
.. _6dbe96a: https://github.com/level12/webgrid/commit/6dbe96a
.. _51bc80f: https://github.com/level12/webgrid/commit/51bc80f
.. _3d5867f: https://github.com/level12/webgrid/commit/3d5867f
.. _69ce644: https://github.com/level12/webgrid/commit/69ce644
.. _d34fc89: https://github.com/level12/webgrid/commit/d34fc89
.. _c76320f: https://github.com/level12/webgrid/commit/c76320f
.. _54f8eb9: https://github.com/level12/webgrid/commit/54f8eb9
.. _6e450f1: https://github.com/level12/webgrid/commit/6e450f1
.. _2f58762: https://github.com/level12/webgrid/commit/2f58762
.. _af06abe: https://github.com/level12/webgrid/commit/af06abe
.. _7736069: https://github.com/level12/webgrid/commit/7736069
.. _b8012d2: https://github.com/level12/webgrid/commit/b8012d2


0.2.13 released 2020-07-21
--------------------------

- Fix multiselect filter rendering bug for selected enum options (5e9aa00_)

.. _5e9aa00: https://github.com/level12/webgrid/commit/5e9aa00


0.2.12 released 2020-07-08
--------------------------

- Fix multiselect filter rendering bug for list options (abfd32f_)

.. _abfd32f: https://github.com/level12/webgrid/commit/abfd32f


0.2.11 released 2020-07-07
--------------------------

- Fix date filter overflow error (116447b_)
- Switch test runner to pytest from nose (dfdb3b0_)

.. _116447b: https://github.com/level12/webgrid/commit/116447b
.. _dfdb3b0: https://github.com/level12/webgrid/commit/dfdb3b0


0.2.10 released 2020-05-15
--------------------------

- simplify page selection to use input instead of select (900abdd_)
- remove webhelpers2 usage in favor of inline jinja template strings (0d27fec_)
- change date filter "less than days ago" to include today (2e67da0_)
- allow custom CSV date formatting (1fb7d03_)
- provide query prep by grid configuration (77f68df_)
- verify i18n translations in CI and add helper for development (75c0ec0_)

.. _900abdd: https://github.com/level12/webgrid/commit/900abdd
.. _0d27fec: https://github.com/level12/webgrid/commit/0d27fec
.. _2e67da0: https://github.com/level12/webgrid/commit/2e67da0
.. _1fb7d03: https://github.com/level12/webgrid/commit/1fb7d03
.. _77f68df: https://github.com/level12/webgrid/commit/77f68df
.. _75c0ec0: https://github.com/level12/webgrid/commit/75c0ec0


0.2.9 released 2020-04-09
-------------------------

- Allow columns to be grouped in the UI with an additional header (HTML, XLSX targets) (3a9e64a_)
- Fix bug clearing single filter when sessions are enabled (c14c708_)

.. _3a9e64a: https://github.com/level12/webgrid/commit/3a9e64a
.. _c14c708: https://github.com/level12/webgrid/commit/c14c708


0.2.8 released 2020-03-20
-------------------------

- fix session persistence for flask (5ed62b8_)

.. _5ed62b8: https://github.com/level12/webgrid/commit/5ed62b8


0.2.7 released 2020-02-10
-------------------------

- fix issue searching date(time) fields for values that are out of bounds (3d33663_)

.. _3d33663: https://github.com/level12/webgrid/commit/3d33663


0.2.6 released 2020-01-14
-------------------------

- fix DateFilter/DateTimeFilter default op bugs introduced in 0.2.5 (edeb74e_)

.. _edeb74e: https://github.com/level12/webgrid/commit/edeb74e


0.2.5 released 2020-01-10
-------------------------

- reduce code complexity (e588630_)
- handle missing filter values for DateFilter an DateTimeFilter (b0e614b_)
- note: this release has some bugs in DateFilter/DateTimeFilter for handling default op

.. _e588630: https://github.com/level12/webgrid/commit/e588630
.. _b0e614b: https://github.com/level12/webgrid/commit/b0e614b


0.2.4 released 2019-12-06
-------------------------

- split filter key matching for search to a separate method for easier override (95032d2_)
- fix DateTimeFilter between operation when missing second operand (acfc86b_)

.. _95032d2: https://github.com/level12/webgrid/commit/95032d2
.. _acfc86b: https://github.com/level12/webgrid/commit/acfc86b


0.2.3 released 2019-11-27
-------------------------

- resolve bad option in multiselect filters (36fc18c_)

.. _36fc18c: https://github.com/level12/webgrid/commit/36fc18c


0.2.2 released 2019-11-26
-------------------------

- improve multiselect filter UI performance for large data sets (8b4fde7_)

.. _8b4fde7: https://github.com/level12/webgrid/commit/8b4fde7


0.2.1 released 2019-11-07
-------------------------

- layout fix for the search box in the filter block (71c5d56_)

.. _71c5d56: https://github.com/level12/webgrid/commit/71c5d56


0.2.0 released 2019-11-06
-------------------------

- Add generic search box (turned on via `enable_search`) to search on filtered columns (3624b78_)
- Add `visible` boolean parameter on Column, allow that and `render_in` to support lambdas for evaluation at run time (0e3e125_)
- Fixed pagination styling (b16ddbf_)
- Turn multiselect UI on for applicable filters (b7744e7_)
- Resolved some deprecation warnings (104a865_)
- Added debug logging of queries to aid in profiling (d6eae60_)
- Updated pypi license declaraton to use SPDX identifier in the license field (cf59e68_)
- Added BSD 3-Clause license (fb4184d_)

.. _3624b78: https://github.com/level12/webgrid/commit/3624b78
.. _0e3e125: https://github.com/level12/webgrid/commit/0e3e125
.. _b16ddbf: https://github.com/level12/webgrid/commit/b16ddbf
.. _b7744e7: https://github.com/level12/webgrid/commit/b7744e7
.. _104a865: https://github.com/level12/webgrid/commit/104a865
.. _d6eae60: https://github.com/level12/webgrid/commit/d6eae60
.. _cf59e68: https://github.com/level12/webgrid/commit/cf59e68
.. _fb4184d: https://github.com/level12/webgrid/commit/fb4184d


0.1.45 released 2019-09-04
--------------------------

- Merge pull request #59 from level12/20-allow-list-render-in (e2a5e46_)
- Merge pull request #64 from level12/40-cleanup-url-filters (a269e1c_)

.. _e2a5e46: https://github.com/level12/webgrid/commit/e2a5e46
.. _a269e1c: https://github.com/level12/webgrid/commit/a269e1c


0.1.44 released 2019-06-27
--------------------------

- Add column and filter classes to support enum types (#60) (9838669_)

.. _9838669: https://github.com/level12/webgrid/commit/9838669


0.1.43 released 2019-05-20
--------------------------

- fix BC case for session load when the key loads no data (7e11993_)

.. _7e11993: https://github.com/level12/webgrid/commit/7e11993


0.1.42 released 2019-05-13
--------------------------

- Ensure session store maintains proper data type through load/save (#35) (e7c5bdf_)
- Known issues: backwards-compatibility error when session store has no data

.. _e7c5bdf: https://github.com/level12/webgrid/commit/e7c5bdf


0.1.41 released 2019-03-25
--------------------------

- Fix warning from xlsxwriter when second column has a subtotal (05e0663_)

.. _05e0663: https://github.com/level12/webgrid/commit/05e0663


0.1.40 released 2019-02-18
--------------------------

- py3: Fix Deprecation Warning for Inspect Call (#53) (9c87cc4_)

.. _9c87cc4: https://github.com/level12/webgrid/commit/9c87cc4


0.1.39 released 2019-01-03
--------------------------

- Properly handle None in date filter "between" ops (4da6069_)

.. _4da6069: https://github.com/level12/webgrid/commit/4da6069


0.1.38 released 2018-11-14
--------------------------

- Add optional i18n support using morphi (3627e8f_)
  NOTE: there is a slight change that could result in a behavioral change during
  upgrade! Please see the 'Upgrading' section in the readme for more
  information!

.. _3627e8f: https://github.com/level12/webgrid/commit/3627e8f


0.1.37 released 2018-09-10
--------------------------

- XLSX formats are cached for performance

0.1.36 released 2018-08-09
--------------------------

- Add test helper `assert_rendered_xls_matches` in `webgrid.testing`
- Add support for XLSX, and CSV renderers
  - If you have xlsxwriter installed, xlsx export link will appear
- DEPRECATED old export mechanism
  - If you are calling `g.xls.as_response()` please replace that with 
  `g.export_as_response()` which will select the correct renderer and return
  the response correctly
  - If xlsx is enabled you will need to make this above change to enable xlsx exporting

0.1.35 released 2018-01-05
--------------------------

 - fix CSS collision in tr classes with Bootstrap
 - change multiselect to use body as the container for the multiselect list

0.1.34 released 2017-08-25
--------------------------

 - session_override GET arg added to allow patching additional operators into the session (rather than overriding session filters)

0.1.33 released 2017-06-13
--------------------------

 - limit XLS sheet names to 30 characters, per the Excel format limit

0.1.32 released 2017-06-09
--------------------------

 - corrected the results of Filter.is_active to account for default operation with no value
 - fixed formencode requirement for python 3
 - update options filter error to include class name

0.1.31 released 2016-11-03
--------------------------

 - corrected DateTimeFilter processing to avoid "invalid date" messages

0.1.30 released 2016-10-28
--------------------------

 - fixed problem with lambda default args being processed by the grid

0.1.29 released 2016-10-28
--------------------------

 - allow default operation passed to filter to be a callable

0.1.28 released 2016-10-13
--------------------------

 - fixed an additional regression in DateFilter and DateTimeFilter validation

0.1.27 released 2016-10-13
--------------------------

 - corrected DateFilter and DateTimeFilter operations for empty, not empty, and between

0.1.26 released 2016-10-03
--------------------------

 - update TextFilter to support case-insensitive operations for dialects like postgresql and sqlite

0.1.25 released 2016-09-12
--------------------------

 - various bug fixes in DateTimeFilter
 - introduce support for Arrow date objects in grid and date filters

0.1.24 released 2016-05-10
--------------------------

 - enhanced options for subtotals to include sum, avg, strings, and SQLAlchemy expressions

0.1.23 released 2016-04-18
--------------------------

 - change dependency to webhelpers2 from webhelpers
 - update to support new python-dateutil, including fix of old parsing exception
 - fix testing compatibility with Flask-SQLALchemy 2.1
 - fix testing dependencies problem in setup
 - support Python 3.4 and newer

0.1.22 released 2016-02-18
--------------------------

 - fix potential warnings for SQLAlchemy when sorting by a label instead of an SA expression

0.1.21 released 2016-02-18
--------------------------

 - bad release

0.1.20 released 2016-02-18
--------------------------

 - errant release, identical to 0.1.19

0.1.19 released 2016-02-16
--------------------------

 - fix edit/delete link display on large screens

0.1.18 released 2015-12-11
--------------------------

 - fix bugs related to default operations using no-input date filters

0.1.17 released 2015-12-04
--------------------------

 - add YesNoFilter and OptionsIntFilterBase helper
 - fix compatibility with SQLAlchemy 1.0.9 for tests to pass
 - add additional DateFilter operators

0.1.16 released 2015-10-15
--------------------------

 - fixed problem with possible date/datetime filter overflows

0.1.15 released 2015-07-02
--------------------------

 - add time column and filter

0.1.14 released 2015-05-11
--------------------------

 - fix problem where empty strings passed to set as a non-required value 2 causes validation error

0.1.13 released 2015-02-12
--------------------------

 - attempt to use column label for subtotaling if no SA expression is provided
 - allow callers to specify default arguments to filters

0.1.12 released 2014-11-18
--------------------------

 - allow filters to set additional html attributes on their table rows

0.1.11 released 2014-10-09
--------------------------

 - fixed setup to include only webgrid in install, without the test apps

0.1.10 released 2014-10-02
--------------------------

 - bug fix: hide_controls_box grid attribute used in rendering

0.1.9 released 2014-09-22
-------------------------

 - bug fix: corrected default_op processing on TextFilter

0.1.8 released 2014-09-22
-------------------------

 - enable default_op processing for all filter types

0.1.7 released 2014-09-18
-------------------------

 - BC break: replaced MultiSelect widget with multipleSelect plugin.
   Related JS and CSS must be included (available in webgrid static)
 - included missing images referenced by webgrid CSS

0.1.6 released 2014-08-22
-------------------------

 - updated filter tests to work with SA0.9
 - refactoring related to subtotaling feature
 - adjustments for SQLAlchemy 0.9+ (we now support 0.8+)
 - workaround for dateutils parsing bug
 - testing fixes
 - completed dev requirements list
 - fixed nose plugin bug, must not assume pathname case consistency (Windows)
 - added BlazeWeb adapter
 - xls_as_response now an adapter method, called by XLS renderer
 - render_template now an optional adapter method, falls back to Jinja2 call

0.1.5 released 2014-05-20
-------------------------

 - fix nose plugin setup to avoid warning message
 - fix javascript bug related to sorting & newer jQuery libraries
 - fix SA expression test to avoid boolean ambiguity
 - avoid accidental unicode to text conversion in filters

0.1.4 released 2014-05-18
-------------------------

  - fix string/unicode handling to avoid coercion of unicode to ascii

0.1.3 released 2014-05-18
-------------------------

  - adjust the way the Flask blueprint is created and registered
  - adjust route on blueprint so it has /static/... prefix for URL

0.1.0 - 0.1.2 released 2014-05-17
---------------------------------

  - initial release
  - fix packaging issues (0.1.1)
  - adjust init so xlwt not required if not used
