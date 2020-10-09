from __future__ import absolute_import
from os import path as opath
from unittest import mock

from blazeutils.testing import assert_equal_txt
import flask
from flask_webtest import SessionScope
import sqlalchemy as sa
import sqlalchemy.orm
from werkzeug.datastructures import MultiDict
import wrapt

from webgrid_ta.model import db
from webgrid import Column

cdir = opath.dirname(__file__)

db_sess_scope = SessionScope(db)


class ModelBase(object):

    @classmethod
    def setup_class(cls):
        db_sess_scope.push()

    @classmethod
    def teardown_class(cls):
        db_sess_scope.pop()


def compiler_instance_factory(compiler, dialect, statement):  # noqa: C901
    class LiteralCompiler(compiler.__class__):
        def render_literal_value(self, value, type_):
            import datetime
            """
            For date and datetime values, convert to a string
            format acceptable to the dialect. That seems to be the
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
                return "'{:%H:%M:%S.%f}'".format(value)
            elif value is None:
                return 'NULL'
            else:
                # Turn off double percent escaping, since we don't run these strings and
                # it creates a large number of differences for test cases
                with mock.patch.object(
                    dialect.identifier_preparer,
                    '_double_percents',
                    False
                ):
                    return super(LiteralCompiler, self).render_literal_value(value, type_)

        def visit_bindparam(
                self, bindparam, within_columns_clause=False,
                literal_binds=False, **kwargs
        ):
            return super(LiteralCompiler, self).render_literal_bindparam(
                bindparam, within_columns_clause=within_columns_clause,
                literal_binds=literal_binds, **kwargs
            )

        def visit_table(self, table, asfrom=False, iscrud=False, ashint=False,
                        fromhints=None, use_schema=True, **kwargs):
            """Strip the default schema from table names when it is not needed"""
            ret_val = super().visit_table(table, asfrom, iscrud, ashint, fromhints, use_schema,
                                          **kwargs)
            if db.engine.dialect.name == 'mssql' and ret_val.startswith('dbo.'):
                return ret_val[4:]
            return ret_val

        def visit_column(self, column, add_to_result_map=None, include_table=True, **kwargs):
            """Strip the default schema from table names when it is not needed"""
            ret_val = super().visit_column(column, add_to_result_map, include_table, **kwargs)
            if db.engine.dialect.name == 'mssql' and ret_val.startswith('dbo.'):
                return ret_val[4:]
            return ret_val

    return LiteralCompiler(dialect, statement)


def query_to_str(statement, bind=None):
    """
        returns a string of a sqlalchemy.orm.Query with parameters bound

        WARNING: this is dangerous and ONLY for testing, executing the results
        of this function can result in an SQL Injection attack.
    """
    if isinstance(statement, sqlalchemy.orm.Query):
        if bind is None:
            bind = statement.session.get_bind(
                statement._mapper_zero()
            )
        statement = statement.statement
    elif bind is None:
        bind = statement.bind

    if bind is None:
        raise Exception('bind param (engine or connection object) required when using with an'
                        ' unbound statement')

    dialect = bind.dialect
    compiler = statement._compiler(dialect)
    literal_compiler = compiler_instance_factory(compiler, dialect, statement)
    return 'TESTING ONLY BIND: ' + literal_compiler.process(statement)


def eq_html(html, filename):
    with open(opath.join(cdir, 'data', filename), 'rb') as fh:
        file_html = fh.read().decode('ascii')
    assert_equal_txt(html, file_html)


def assert_in_query(obj, test_for):
    if hasattr(obj, 'build_query'):
        query = obj.build_query()
    else:
        query = obj
    query_str = query_to_str(query)
    assert test_for in query_str, query_str


def assert_not_in_query(obj, test_for):
    if hasattr(obj, 'build_query'):
        query = obj.build_query()
    else:
        query = obj
    query_str = query_to_str(query)
    assert test_for not in query_str, query_str


def inrequest(*req_args, **req_kwargs):
    @wrapt.decorator
    def wrapper(wrapped, instance, args, kwargs):
        with flask.current_app.test_request_context(*req_args, **req_kwargs):
            # replaces request.args wth MultiDict so it is mutable
            flask.request.args = MultiDict(flask.request.args)
            return wrapped(*args, **kwargs)
    return wrapper


def render_in_grid(grid_cls, render_in):
    """ Class factory which extends an existing grid class
        to add a column that is rendered everywhere except "render_in"
    """
    other_render_types = set(Column._render_in)
    other_render_types.remove(render_in)

    class RenderInGrid(grid_cls):
        Column('Exclude', sa.literal('Exclude'), render_in=tuple(other_render_types))

    return RenderInGrid
