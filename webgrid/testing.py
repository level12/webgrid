"""
A collection of utilities for testing webgrid functionality in client applications
"""
import datetime
import re
import urllib

import flask
from pyquery import PyQuery
import sqlalchemy
from sqlalchemy.dialects.mssql.base import MSSQLCompiler
from sqlalchemy.dialects.postgresql.base import PGCompiler
import xlrd


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
        """This function is copied directly from sqlalchemybwc.lib.testing

            returns a string of a sqlalchemy.orm.Query with parameters bound
            WARNING: this is dangerous and ONLY for testing, executing the results
            of this function can result in an SQL Injection attack.
        """
        if isinstance(statement, sqlalchemy.orm.Query):
            if bind is None:
                bind = statement.session.get_bind()
            statement = statement.statement
        elif bind is None:
            bind = statement.bind

        if bind is None:
            raise Exception('bind param (engine or connection object) required when using with an '
                            'unbound statement')

        dialect = bind.dialect
        compiler = statement._compiler(dialect)

        class LiteralCompiler(compiler.__class__):
            def visit_bindparam(
                    self, bindparam, within_columns_clause=False,
                    literal_binds=False, **kwargs
            ):
                return super(LiteralCompiler, self).render_literal_bindparam(
                    bindparam, within_columns_clause=within_columns_clause,
                    literal_binds=literal_binds, **kwargs
                )

        compiler = LiteralCompiler(dialect, statement)
        return 'TESTING ONLY BIND: ' + compiler.process(statement)

    def assert_in_query(self, look_for, **kwargs):
        grid = self.get_session_grid(**kwargs)
        query_str = self.query_to_str(grid.build_query())
        assert look_for in query_str, '"{0}" not found in: {1}'.format(look_for, query_str)

    def assert_not_in_query(self, look_for, **kwargs):
        grid = self.get_session_grid(**kwargs)
        query_str = self.query_to_str(grid.build_query())
        assert look_for not in query_str, '"{0}" found in: {1}'.format(look_for, query_str)

    def assert_regex_in_query(self, look_for, **kwargs):
        grid = self.get_session_grid(**kwargs)
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

        def page_func():
            url = '/?' + urllib.parse.urlencode({'sort1': k, 'onpage': 2, 'perpage': 1})
            with flask.current_app.test_request_context(url):
                grid = self.get_session_grid()
                if grid.page_count > 1:
                    self.get_pyq()

        if self.grid_cls.pager_on:
            page_func()

        return sub_func()

    def test_sort(self):
        for col, expect in self.sort_tests:
            self.check_sort(col, expect, True)
            self.check_sort(col, expect, False)

    def assert_table(self, table, grid=None, **kwargs):
        d = self.get_pyq(grid, **kwargs)

        assert len(d.find('table.records thead th')) == len(table[0])
        for idx, val in enumerate(table[0]):
            assert d.find('table.records thead th').eq(idx).text() == val

        assert len(d.find('table.records tbody tr')) == len(table[1:])
        for row_idx, row in enumerate(table[1:]):
            assert len(d.find('table.records tbody tr').eq(row_idx)('td')) == len(row)
            for col_idx, val in enumerate(row):
                read = d.find('table.records tbody tr').eq(row_idx)('td').eq(col_idx).text()
                assert read == val, 'row {} col {} {} != {}'.format(row_idx, col_idx, read, val)

    def expect_table_contents(self, expect, grid=None, **kwargs):
        d = self.get_pyq(grid, **kwargs)
        assert len(d.find('table.records tbody tr')) == len(expect)

        for row_idx, row in enumerate(expect):
            td = d.find('table.records tbody tr').eq(row_idx).find('td')
            assert len(td) == len(row)
            for col_idx, val in enumerate(row):
                assert td.eq(col_idx).text() == val


class PGCompilerTesting(PGCompiler):
    def render_literal_value(self, value, type_):
        """
        For date and datetime values, convert to a string
        format acceptable to PGSQL. That seems to be this:

            yyyy-mm-dd hh:mi:ss.mmm(24h)

        For other data types, call the base class implementation.
        """
        if isinstance(value, datetime.datetime):
            return "'" + value.strftime('%Y-%m-%d %H:%M:%S.%f') + "'"
        elif isinstance(value, datetime.date):
            return "'" + value.strftime('%Y-%m-%d') + "'"
        elif isinstance(value, datetime.time):
            return "'{:%H:%M}'".format(value)
        elif value is None:
            return 'NULL'
        else:
            return super().render_literal_value(value, type_)


class PGCompilerMixin:
    @classmethod
    def setup_class(cls):
        if cls.grid_cls.manager.db.engine.dialect.name == 'postgresql':
            cls._real_statement_compiler = cls.grid_cls.manager.db.engine.dialect.statement_compiler
            cls.grid_cls.manager.db.engine.dialect.statement_compiler = PGCompilerTesting

    @classmethod
    def teardown_class(cls):
        if cls.grid_cls.manager.db.engine.dialect.name == 'postgresql':
            cls.grid_cls.manager.db.engine.dialect.statement_compiler = cls._real_statement_compiler


class MSSQLCompilerTesting(MSSQLCompiler):
    def render_literal_value(self, value, type_):
        """
        For date and datetime values, convert to a string
        format acceptable to MSSQL. That seems to be the
        so-called ODBC canonical date format which looks
        like this:
            yyyy-mm-dd hh:mi:ss.mmm(24h)
        For other data types, call the base class implementation.
        """
        if isinstance(value, datetime.datetime):
            return "'" + value.strftime('%Y-%m-%d %H:%M:%S.%f') + "'"
        elif isinstance(value, datetime.date):
            return "'" + value.strftime('%Y-%m-%d') + "'"
        elif isinstance(value, datetime.time):
            return "'{:%H:%M}'".format(value)
        elif value is None:
            return 'NULL'
        else:
            return super().render_literal_value(value, type_)

    def visit_table(self, table, asfrom=False, iscrud=False, ashint=False,
                    fromhints=None, use_schema=True, **kwargs):
        """Strip the default schema from table names when it is not needed"""
        ret_val = super().visit_table(table, asfrom, iscrud, ashint, fromhints, use_schema,
                                      **kwargs)
        if ret_val.startswith('dbo.'):
            return ret_val[4:]
        return ret_val

    def visit_column(self, column, add_to_result_map=None, include_table=True, **kwargs):
        """Strip the default schema from table names when it is not needed"""
        ret_val = super().visit_column(column, add_to_result_map, include_table, **kwargs)
        if ret_val.startswith('dbo.'):
            return ret_val[4:]
        return ret_val


class MSSQLCompilerMixin:
    @classmethod
    def setup_class(cls):
        if cls.grid_cls.manager.db.engine.dialect.name == 'mssql':
            from sqlalchemy_pyodbc_mssql.dialect import MssqlDialect_pyodbc_quoted
            MssqlDialect_pyodbc_quoted.statement_compiler = MSSQLCompilerTesting

    @classmethod
    def teardown_class(cls):
        if cls.grid_cls.manager.db.engine.dialect.name == 'mssql':
            from sqlalchemy_pyodbc_mssql.dialect import MssqlDialect_pyodbc_quoted
            MssqlDialect_pyodbc_quoted.statement_compiler = MSSQLCompiler

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
