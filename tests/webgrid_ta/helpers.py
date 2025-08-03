from pathlib import Path

from blazeutils.testing import assert_equal_txt
import sqlalchemy.orm


cdir = Path(__file__).parent


def query_to_str(statement, bind=None):
    """
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
        raise Exception(
            'bind param (engine or connection object) required when using with an unbound statement',  # noqa: E501
        )

    dialect = bind.dialect
    compiler = statement._compiler(dialect)

    class LiteralCompiler(compiler.__class__):
        def visit_bindparam(
            self,
            bindparam,
            within_columns_clause=False,
            literal_binds=False,
            **kwargs,
        ):
            return super().render_literal_bindparam(
                bindparam,
                within_columns_clause=within_columns_clause,
                literal_binds=literal_binds,
                **kwargs,
            )

    compiler = LiteralCompiler(dialect, statement)
    return 'TESTING ONLY BIND: ' + compiler.process(statement)


def eq_html(html, filename):
    with cdir.joinpath('data', filename).open('rb') as fh:
        file_html = fh.read()
    assert_equal_txt(html, file_html)


def assert_in_query(obj, test_for):
    query = obj.build_query() if hasattr(obj, 'build_query') else obj
    query_str = query_to_str(query)
    assert test_for in query_str, query_str


def assert_not_in_query(obj, test_for):
    query = obj.build_query() if hasattr(obj, 'build_query') else obj
    query_str = query_to_str(query)
    assert test_for not in query_str, query_str
