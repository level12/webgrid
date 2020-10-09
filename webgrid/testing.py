"""
A collection of utilities for testing webgrid functionality in client applications
"""
import re
import urllib

import flask
from pyquery import PyQuery
import xlrd

from webgrid.tests import helpers


def assert_list_equal(list1, list2):
    """
    A list-specific equality assertion.

    This method is based on the Python `unittest.TestCase.assertListEqual` method.

    :param list1:
    :param list2:
    :return:
    """

    # resolve generators
    list1, list2 = map(list, (list1, list2))

    assert len(list1) == len(list2), \
        'Lists are different lengths: {} != {}'.format(
            len(list1),
            len(list2)
    )

    if list1 == list2:
        # the lists are the same, we're done
        return

    # the lists are different in at least one element; find it
    # and report it
    for index, (val1, val2) in enumerate(zip(list1, list2)):
        assert val1 == val2, (
            'First differing element at index {}: {} != {}'.format(
                index,
                repr(val1),
                repr(val2)
            )
        )


def assert_rendered_xls_matches(rendered_xls, xls_headers, xls_rows):
    """
    Verifies that `rendered_xls` has a set of headers and values that match
    the given parameters.

    NOTE: This method does not perform in-depth analysis of complex workbooks!
          Assumes up to one row of headers, and data starts immediately after.
          Multiple worksheets or complex (multi-row) headers *are not verified!*

    :param rendered_xls: binary data passed to xlrd as file_contents
    :param xls_headers: iterable with length, represents single row of column headers
    :param xls_rows: list of rows in order as they will appear in the worksheet
    :return:
    """
    assert rendered_xls
    workbook = xlrd.open_workbook(file_contents=rendered_xls)

    assert workbook.nsheets >= 1
    sheet = workbook.sheet_by_index(0)

    # # verify the shape of the sheet

    # ## shape of rows (1 row for the headers, 1 for each row of data)
    nrows = len(xls_rows)
    if xls_headers:
        nrows += 1
    assert nrows == sheet.nrows

    # ## shape of columns
    ncols = max(
        len(xls_headers) if xls_headers else 0,
        max(len(values) for values in xls_rows) if xls_rows else 0
    )
    assert ncols == sheet.ncols

    if xls_headers:
        assert_list_equal(
            (cell.value for cell in sheet.row(0)),
            xls_headers
        )

    if xls_rows:
        row_iter = sheet.get_rows()

        # skip header row
        if xls_headers:
            next(row_iter)

        for row, expected_row in zip(row_iter, xls_rows):
            assert_list_equal(
                (cell.value for cell in row),
                expected_row
            )


class GridBase:
    """ Test base for Flask or Keg apps """
    grid_cls = None
    filters = ()
    sort_tests = ()

    @classmethod
    def setup_class(cls):
        if hasattr(cls, 'init'):
            cls.init()

    def query_to_str(self, statement, bind=None):
        return helpers.query_to_str(statement, bind=bind)

    def assert_in_query(self, look_for, grid=None, **kwargs):
        grid = grid or self.get_session_grid(**kwargs)
        helpers.assert_in_query(grid, look_for)

    def assert_not_in_query(self, look_for, grid=None, **kwargs):
        grid = grid or self.get_session_grid(**kwargs)
        helpers.assert_not_in_query(grid, look_for)

    def assert_regex_in_query(self, look_for, grid=None, **kwargs):
        grid = grid or self.get_session_grid(**kwargs)
        query_str = self.query_to_str(grid.build_query())

        if hasattr(look_for, 'search'):
            assert look_for.search(query_str), \
                '"{0}" not found in: {1}'.format(look_for.pattern, query_str)
        else:
            assert re.search(look_for, query_str), \
                '"{0}" not found in: {1}'.format(look_for, query_str)

    def get_session_grid(self, *args, **kwargs):
        grid = self.grid_cls(*args, **kwargs)
        grid.apply_qs_args()
        return grid

    def get_pyq(self, grid=None, **kwargs):
        session_grid = grid or self.get_session_grid(**kwargs)
        html = session_grid.html()
        return PyQuery('<html>{0}</html>'.format(html))

    def check_filter(self, name, op, value, expected):
        qs_args = [('op({0})'.format(name), op)]
        if isinstance(value, (list, tuple)):
            for v in value:
                qs_args.append(('v1({0})'.format(name), v))
        else:
            qs_args.append(('v1({0})'.format(name), value))

        def sub_func(ex):
            url = '/?' + urllib.parse.urlencode(qs_args)
            with flask.current_app.test_request_context(url):
                if isinstance(ex, re.compile('').__class__):
                    self.assert_regex_in_query(ex)
                else:
                    self.assert_in_query(ex)
                self.get_pyq()  # ensures the query executes and the grid renders without error

        def page_func():
            url = '/?' + urllib.parse.urlencode([('onpage', 2), ('perpage', 1), *qs_args])
            with flask.current_app.test_request_context(url):
                pg = self.get_session_grid()
                if pg.page_count > 1:
                    self.get_pyq()

        if self.grid_cls.pager_on:
            page_func()

        return sub_func(expected)

    def test_filters(self):
        if callable(self.filters):
            cases = self.filters()
        else:
            cases = self.filters
        for name, op, value, expected in cases:
            self.check_filter(name, op, value, expected)

    def check_sort(self, k, ex, asc):
        if not asc:
            k = '-' + k
        d = {'sort1': k}

        def sub_func():
            with flask.current_app.test_request_context('/?' + urllib.parse.urlencode(d)):
                self.assert_in_query('ORDER BY %s%s' % (ex, '' if asc else ' DESC'))
                self.get_pyq()  # ensures the query executes and the grid renders without error

        return sub_func()

    def test_sort(self):
        for col, expect in self.sort_tests:
            self.check_sort(col, expect, True)
            self.check_sort(col, expect, False)

    def _compare_table_block(self, block_selector, tag, expect):
        print(block_selector)
        assert len(block_selector) == len(expect)

        for row_idx, row in enumerate(expect):
            cells = block_selector.eq(row_idx).find(tag)
            assert len(cells) == len(row)
            for col_idx, val in enumerate(row):
                read = cells.eq(col_idx).text()
                assert read == val, 'row {} col {} {} != {}'.format(row_idx, col_idx, read, val)

    def expect_table_header(self, expect, grid=None, **kwargs):
        d = self.get_pyq(grid, **kwargs)
        self._compare_table_block(
            d.find('table.records thead tr'),
            'th',
            expect,
        )

    def expect_table_contents(self, expect, grid=None, **kwargs):
        d = self.get_pyq(grid, **kwargs)
        self._compare_table_block(
            d.find('table.records tbody tr'),
            'td',
            expect,
        )

    def test_search_expr_passes(self, grid=None):
        # not concerned with the query contents here, just that the query executes without error
        grid = grid or self.get_session_grid()
        if grid.enable_search:
            grid.records


class MSSQLGridBase(GridBase):
    """ MSSQL dialect produces some string oddities compared to other dialects, such as
        having the N'foo' syntax for unicode strings instead of 'foo'. This can clutter
        tests a bit. Using MSSQLGridBase will patch that into the asserts, so that
        look_for will match whether it has the N-prefix or not.
    """
    def query_to_str_replace_type(self, compiled_query):
        query_str = self.query_to_str(compiled_query)
        # pyodbc rendering includes an additional character for some strings,
        # like N'foo' instead of 'foo'. This is not relevant to what we're testing.
        return re.sub(
            r"(\(|WHEN|LIKE|ELSE|THEN|[,=\+])( ?)N'(.*?)'", r"\1\2'\3'", query_str
        )

    def assert_in_query(self, look_for, grid=None, context=None, **kwargs):
        session_grid = grid or self.get_session_grid(**kwargs)
        query_str = self.query_to_str(session_grid.build_query())
        query_str_repl = self.query_to_str_replace_type(session_grid.build_query())
        assert look_for in query_str or look_for in query_str_repl, \
            '"{0}" not found in: {1}'.format(look_for, query_str)

    def assert_not_in_query(self, look_for, grid=None, context=None, **kwargs):
        session_grid = grid or self.get_session_grid(**kwargs)
        query_str = self.query_to_str(session_grid.build_query())
        query_str_repl = self.query_to_str_replace_type(session_grid.build_query())
        assert look_for not in query_str or look_for not in query_str_repl, \
            '"{0}" found in: {1}'.format(look_for, query_str)

    def assert_regex_in_query(self, look_for, grid=None, context=None, **kwargs):
        session_grid = grid or self.get_session_grid(**kwargs)
        query_str = self.query_to_str(session_grid.build_query())
        query_str_repl = self.query_to_str_replace_type(session_grid.build_query())

        if hasattr(look_for, 'search'):
            assert look_for.search(query_str) or look_for.search(query_str_repl), \
                '"{0}" not found in: {1}'.format(look_for.pattern, query_str)
        else:
            assert re.search(look_for, query_str) or re.search(look_for, query_str_repl), \
                '"{0}" not found in: {1}'.format(look_for, query_str)
