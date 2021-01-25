from __future__ import absolute_import
import datetime as dt
from collections import namedtuple
from decimal import Decimal as D

import pytest
import formencode
from .helpers import query_to_str

from webgrid.filters import Operator
from webgrid.filters import OptionsFilterBase, TextFilter, IntFilter, NumberFilter, DateFilter, \
    DateTimeFilter, FilterBase, TimeFilter, YesNoFilter, OptionsEnumFilter, AggregateIntFilter
from webgrid_ta.model.entities import ArrowRecord, Person, db, AccountType

from .helpers import ModelBase


class CheckFilterBase(ModelBase):

    def assert_in_query(self, query, test_for):
        query_str = query_to_str(query)
        assert test_for in query_str, '{} not found in {}'.format(test_for, query_str)

    def assert_not_in_query(self, query, test_for):
        query_str = query_to_str(query)
        assert test_for not in query_str, '{} found in {}'.format(test_for, query_str)

    def assert_filter_query(self, filter, test_for):
        query = filter.apply(db.session.query(Person.id))
        self.assert_in_query(query, test_for)


class TestOperator:
    def test_string_equality(self):
        eq = Operator('eq', 'is', 'input')
        assert eq == 'eq'
        assert 'eq' == eq

        assert eq != '!eq'
        assert '!eq' != eq

    def test_string_in(self):
        a = Operator('a', 'a', 'a')
        b = Operator('b', 'b', 'b')
        c = Operator('c', 'c', 'c')
        d = Operator('d', 'd', 'd')

        assert a in (a, b, c)
        assert 'a' in (a, b, c)

        assert d not in (a, b, c)
        assert 'd' not in (a, b, c)

    def test_self_equality(self):
        eq = Operator('eq', 'is', 'input')
        assert eq == eq

    def test_operator_equality(self):
        a = Operator('eq', 'is', 'input')
        b = Operator('eq', 'is', 'input')
        c = Operator('fb', 'is', 'input')

        assert a == b
        assert a != c

    def test_hashable(self):
        a = Operator('ab', 'is', 'input')
        b = Operator('bc', 'is', 'input')
        c = Operator('cd', 'is', 'input')

        lookup = {a: 1, b: 2, c: 3}
        assert lookup[a] == 1


class TestTextFilter(CheckFilterBase):
    def test_eq(self):
        tf = TextFilter(Person.firstname)
        tf.set('eq', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname = 'foo'")

    def test_not_eq(self):
        tf = TextFilter(Person.firstname)
        tf.set('!eq', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname != 'foo'")

    def test_empty(self):
        tf = TextFilter(Person.firstname)
        tf.set('empty', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname IS NULL OR persons.firstname = ''")

    def test_not_empty(self):
        tf = TextFilter(Person.firstname)
        tf.set('!empty', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query,
                             "WHERE persons.firstname IS NOT NULL AND persons.firstname != ''")

    def test_contains(self):
        tf = TextFilter(Person.firstname)
        tf.set('contains', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname LIKE '%foo%'")

    def test_doesnt_contain(self):
        tf = TextFilter(Person.firstname)
        tf.set('!contains', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname NOT LIKE '%foo%'")

    def test_default(self):
        tf = TextFilter(Person.firstname, default_op='contains', default_value1='foo')
        tf.set(None, None)
        assert tf.is_active
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname LIKE '%foo%'")

    def test_default_op_callable(self):
        def def_op():
            return 'contains'
        tf = TextFilter(Person.firstname, default_op=def_op, default_value1='bar')
        tf.set(None, None)
        assert tf.is_active
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname LIKE '%bar%'")

    def test_default_callable(self):
        def def_val():
            return 'bar'
        tf = TextFilter(Person.firstname, default_op='contains', default_value1=def_val)
        tf.set(None, None)
        assert tf.is_active
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, "WHERE persons.firstname LIKE '%bar%'")

    def test_default_no_value(self):
        tf = TextFilter(Person.firstname, default_op='contains')
        tf.set(None, None)
        assert not tf.is_active

    def test_search_expr(self):
        expr_factory = TextFilter(Person.firstname).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('foo')
        assert str(expr) == 'persons.firstname LIKE :firstname_1'
        assert expr.right.value == '%foo%'


class TestTextFilterWithCaseSensitiveDialect(CheckFilterBase):
    def get_filter(self):
        class MockDialect:
            name = 'postgresql'
        return TextFilter(Person.firstname).new_instance(dialect=MockDialect())

    def test_eq(self):
        tf = self.get_filter()
        tf.set('eq', 'foo')
        query_term = "'foo'"
        if db.engine.dialect.name == 'mssql':
            query_term = f'N{query_term}'
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, f'WHERE upper(persons.firstname) = upper({query_term})')

    def test_not_eq(self):
        tf = self.get_filter()
        tf.set('!eq', 'foo')
        query_term = "'foo'"
        if db.engine.dialect.name == 'mssql':
            query_term = f'N{query_term}'
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, f'WHERE upper(persons.firstname) != upper({query_term})')

    def test_contains(self):
        sql_check = {
            'sqlite': "WHERE lower(persons.firstname) LIKE lower('%foo%')",
            'postgresql': "WHERE persons.firstname ILIKE '%foo%'",
            'mssql': "WHERE lower(persons.firstname) LIKE lower('%foo%')",
        }
        tf = self.get_filter()
        tf.set('contains', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, sql_check.get(db.engine.dialect.name))

    def test_doesnt_contain(self):
        sql_check = {
            'sqlite': "WHERE lower(persons.firstname) NOT LIKE lower('%foo%')",
            'postgresql': "WHERE persons.firstname NOT ILIKE '%foo%'",
            'mssql': "WHERE lower(persons.firstname) NOT LIKE lower('%foo%')",
        }
        tf = self.get_filter()
        tf.set('!contains', 'foo')
        query = tf.apply(db.session.query(Person.id))
        self.assert_in_query(query, sql_check.get(db.engine.dialect.name))

    def test_search_expr(self):
        expr_factory = self.get_filter().get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('foo')
        assert str(expr) == 'lower(persons.firstname) LIKE lower(:firstname_1)', str(expr)


class TestNumberFilters(CheckFilterBase):
    """
        Testing IntFilter mostly because the other classes inherit from the same base,
        but make sure we test value typing for each.

        Also, most of the operators are inherited, so only testing the ones
        that are specific to number filters.
    """

    def test_int_eq(self):
        filter = IntFilter(Person.numericcol)
        filter.set('eq', '1')
        self.assert_filter_query(filter, "WHERE persons.numericcol = 1")

    def test_aggregate_int_eq(self):
        filter = AggregateIntFilter(Person.numericcol)
        filter.set('eq', '1')
        self.assert_filter_query(filter, "HAVING persons.numericcol = 1")

    def test_int_lte(self):
        filter = IntFilter(Person.numericcol)
        filter.set('lte', '1')
        self.assert_filter_query(filter, "WHERE persons.numericcol <= 1")

    def test_int_gte(self):
        filter = IntFilter(Person.numericcol)
        filter.set('gte', '1')
        self.assert_filter_query(filter, "WHERE persons.numericcol >= 1")

    def test_int_between(self):
        filter = IntFilter(Person.numericcol)
        filter.set('between', '5', '10')
        self.assert_filter_query(filter, "WHERE persons.numericcol BETWEEN 5 AND 10")

    def test_int_not_between(self):
        filter = IntFilter(Person.numericcol)
        filter.set('!between', '5', '10')
        self.assert_filter_query(filter, "WHERE persons.numericcol NOT BETWEEN 5 AND 10")

    def test_number_filter_type_conversion1(self):
        filter = NumberFilter(Person.numericcol)
        filter.set('eq', '1')
        self.assert_filter_query(filter, "WHERE persons.numericcol = 1")

    def test_number_filter_type_conversion2(self):
        filter = NumberFilter(Person.numericcol)
        filter.set('eq', '1.5')
        self.assert_filter_query(filter, "WHERE persons.numericcol = 1.5")

    def test_int_invalid(self):
        filter = IntFilter(Person.numericcol)
        with pytest.raises(formencode.Invalid, match='Please enter an integer value'):
            filter.set('eq', 'a')

    def test_number_invalid(self):
        filter = NumberFilter(Person.numericcol)
        with pytest.raises(formencode.Invalid, match='Please enter a number'):
            filter.set('eq', 'a')

    def test_number_lte_null(self):
        filter = NumberFilter(Person.numericcol)
        with pytest.raises(formencode.Invalid, match='Please enter a value'):
            filter.set('lte', None)

    def test_number_gte_null(self):
        filter = NumberFilter(Person.numericcol)
        with pytest.raises(formencode.Invalid, match='Please enter a value'):
            filter.set('gte', None)

    def test_number_eq_null(self):
        filter = NumberFilter(Person.numericcol)
        with pytest.raises(formencode.Invalid, match='Please enter a value'):
            filter.set('eq', None)

    def test_number_neq_null(self):
        filter = NumberFilter(Person.numericcol)
        with pytest.raises(formencode.Invalid, match='Please enter a value'):
            filter.set('!eq', None)

    def test_number_empty(self):
        filter = NumberFilter(Person.numericcol)
        filter.set('empty', '')

    def test_number_not_empty(self):
        filter = NumberFilter(Person.numericcol)
        filter.set('!empty', '')

    def test_default(self):
        tf = NumberFilter(Person.numericcol, default_op='eq', default_value1='1.5')
        tf.set(None, None)
        self.assert_filter_query(tf, "WHERE persons.numericcol = 1.5")

    def test_search_expr(self):
        expr_factory = NumberFilter(Person.numericcol).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('12345')
        assert str(expr) == 'CAST(persons.numericcol AS VARCHAR) LIKE :param_1', str(expr)
        assert expr.right.value == '%12345%'


class TestDateFilter(CheckFilterBase):
    between_sql = "WHERE persons.due_date BETWEEN '2012-01-01' AND '2012-01-31'"
    between_week_sql = "WHERE persons.due_date BETWEEN '2012-01-01' AND '2012-01-07'"

    def test_eq(self):
        filter = DateFilter(Person.due_date)
        filter.set('eq', '12/31/2010')
        self.assert_filter_query(filter, "WHERE persons.due_date = '2010-12-31'")
        assert filter.description == '12/31/2010'

    def test_eq_none(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid):
            filter.set('eq', None)

    def test_eq_default(self):
        filter = DateFilter(Person.due_date, default_op='eq')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_not_eq(self):
        filter = DateFilter(Person.due_date)
        filter.set('!eq', '12/31/2010')
        self.assert_filter_query(filter, "WHERE persons.due_date != '2010-12-31'")
        assert filter.description == 'excluding 12/31/2010'

    def test_noteq_default(self):
        filter = DateFilter(Person.due_date, default_op='!eq')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_not_eq_none(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid):
            filter.set('!eq', None)

    def test_lte(self):
        filter = DateFilter(Person.due_date)
        filter.set('lte', '12/31/2010')
        self.assert_filter_query(filter, "WHERE persons.due_date <= '2010-12-31'")
        assert filter.description == 'up to 12/31/2010'
        with pytest.raises(formencode.Invalid):
            filter.set('lte', '')

    def test_lte_default(self):
        filter = DateFilter(Person.due_date, default_op='lte')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_lte_none(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid):
            filter.set('lte', None)

    def test_gte(self):
        filter = DateFilter(Person.due_date)
        filter.set('gte', '12/31/2010')
        self.assert_filter_query(filter, "WHERE persons.due_date >= '2010-12-31'")
        assert filter.description == 'beginning 12/31/2010'

    def test_gte_default(self):
        filter = DateFilter(Person.due_date, default_op='gte')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_gte_none(self):
        figter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid):
            figter.set('gte', None)

    def test_empty(self):
        filter = DateFilter(Person.due_date)
        filter.set('empty', None)
        self.assert_filter_query(filter, "WHERE persons.due_date IS NULL")
        assert filter.description == 'date not specified'
        filter.set('empty', '')
        self.assert_filter_query(filter, "WHERE persons.due_date IS NULL")
        assert filter.description == 'date not specified'

    def test_empty_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='empty')
        filter.set(None, None)
        assert filter.description == 'date not specified'

    def test_not_empty(self):
        filter = DateFilter(Person.due_date)
        filter.set('!empty', None)
        self.assert_filter_query(filter, "WHERE persons.due_date IS NOT NULL")
        assert filter.description == 'any date'
        filter.set('!empty', '')
        self.assert_filter_query(filter, "WHERE persons.due_date IS NOT NULL")
        assert filter.description == 'any date'

    def test_not_empty_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='!empty')
        filter.set(None, None)
        assert filter.description == 'any date'

    def test_between(self):
        filter = DateFilter(Person.due_date)
        filter.set('between', '1/31/2010', '12/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date BETWEEN '2010-01-31' AND '2010-12-31'"
        )
        assert filter.description == '01/31/2010 - 12/31/2010'

    def test_between_swap(self):
        filter = DateFilter(Person.due_date)
        filter.set('between', '12/31/2010', '1/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date BETWEEN '2010-01-31' AND '2010-12-31'"
        )
        assert filter.description == '01/31/2010 - 12/31/2010'

    def test_between_missing_date(self):
        filter = DateFilter(Person.due_date)
        filter.set('between', '12/31/2010', '')
        today = dt.date.today().strftime('%Y-%m-%d')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date BETWEEN '2010-12-31' AND '{}'".format(today)
        )

    def test_between_none_date(self):
        filter = DateFilter(Person.due_date)
        filter.set('between', '12/31/2010')
        today = dt.date.today().strftime('%Y-%m-%d')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date BETWEEN '2010-12-31' AND '{}'".format(today)
        )

        with pytest.raises(formencode.Invalid):
            filter.set('between', None)
        assert filter.error is True
        assert filter.description == 'invalid'

    def test_between_blank(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid):
            filter.set('between', '', '')
        assert filter.error is True
        assert filter.description == 'invalid'

    def test_between_default(self):
        filter = DateFilter(Person.due_date, default_op='between')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_not_between_missing_date(self):
        filter = DateFilter(Person.due_date)
        filter.set('!between', '12/31/2010', '')
        today = dt.date.today().strftime('%Y-%m-%d')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date NOT BETWEEN '2010-12-31' AND '{}'".format(today)
        )

    def test_not_between_none_date(self):
        filter = DateFilter(Person.due_date)
        filter.set('!between', '12/31/2010')
        today = dt.date.today().strftime('%Y-%m-%d')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date NOT BETWEEN '2010-12-31' AND '{}'".format(today)
        )

        with pytest.raises(formencode.Invalid):
            filter.set('!between', None)
        assert filter.error is True
        assert filter.description == 'invalid'

    def test_not_between(self):
        filter = DateFilter(Person.due_date)
        filter.set('!between', '1/31/2010', '12/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date NOT BETWEEN '2010-01-31' AND '2010-12-31'"
        )
        assert filter.description == 'excluding 01/31/2010 - 12/31/2010'

    def test_not_between_default(self):
        filter = DateFilter(Person.due_date, default_op='!between')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_days_ago(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('da', '10')
        self.assert_filter_query(filter, "WHERE persons.due_date = '2011-12-22'")
        assert filter.description == '12/22/2011'

    def test_days_ago_default(self):
        filter = DateFilter(Person.due_date, default_op='da')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_days_ago_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('da', None)

    def test_less_than_days_ago(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('ltda', '10')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date > '2011-12-22' AND persons.due_date <= '2012-01-01'"
        )
        assert filter.description == '12/22/2011 - 01/01/2012'

    def test_less_than_days_ago_default(self):
        filter = DateFilter(Person.due_date, default_op='ltda')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_less_than_days_ago_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('ltda', None)

    def test_more_than_days_ago(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('mtda', '10')
        self.assert_filter_query(filter, "WHERE persons.due_date < '2011-12-22'")
        assert filter.description == 'before 12/22/2011'

    def test_more_than_days_ago_default(self):
        filter = DateFilter(Person.due_date, default_op='mtda')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_more_than_days_ago_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('mtda', None)

    def test_in_less_than_days(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('iltd', '10')
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date >= '2012-01-01' AND persons.due_date < '2012-01-11'"
        )
        assert filter.description == '01/01/2012 - 01/11/2012'

    def test_in_less_than_days_default(self):
        filter = DateFilter(Person.due_date, default_op='iltd')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_in_less_than_days_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('iltd', None)

    def test_in_more_than_days(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('imtd', '10')
        self.assert_filter_query(filter, "WHERE persons.due_date > '2012-01-11'")
        assert filter.description == 'after 01/11/2012'

    def test_in_more_than_days_default(self):
        filter = DateFilter(Person.due_date, default_op='imtd')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_in_more_than_days_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('imtd', None)

    def test_in_days(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('ind', '10')
        self.assert_filter_query(filter, "WHERE persons.due_date = '2012-01-11'")
        assert filter.description == '01/11/2012'

    def test_in_days_default(self):
        filter = DateFilter(Person.due_date, default_op='ind')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_in_days_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('ind', None)

    def test_today(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('today', None)
        self.assert_filter_query(filter, "WHERE persons.due_date = '2012-01-01'")
        assert filter.description == '01/01/2012'

    def test_today_default(self):
        filter = DateFilter(Person.due_date, default_op='today', _now=dt.date(2012, 1, 1))
        filter.set(None, None)
        assert filter.description == '01/01/2012'

    def test_this_week(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 4))
        filter.set('thisweek', None)
        self.assert_filter_query(filter, self.between_week_sql)
        assert filter.description == '01/01/2012 - 01/07/2012'

    def test_this_week_default(self):
        filter = DateFilter(Person.due_date, default_op='thisweek', _now=dt.date(2012, 1, 4))
        filter.set(None, None)
        assert filter.description == '01/01/2012 - 01/07/2012'

    def test_this_week_left_edge(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('thisweek', None)
        self.assert_filter_query(filter, self.between_week_sql)
        assert filter.description == '01/01/2012 - 01/07/2012'

    def test_this_week_right_edge(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 7))
        filter.set('thisweek', None)
        self.assert_filter_query(filter, self.between_week_sql)
        assert filter.description == '01/01/2012 - 01/07/2012'

    def test_days_operator_with_blank_value(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid, match='Please enter a value'):
            filter.set('ind', '')

    def test_this_month(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 4))
        filter.set('thismonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_month_default(self):
        filter = DateFilter(Person.due_date, default_op='thismonth', _now=dt.date(2012, 1, 4))
        filter.set(None, None)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_month_left_edge(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('thismonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_month_right_edge(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 31))
        filter.set('thismonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 4))
        filter.set('lastmonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month_default(self):
        filter = DateFilter(Person.due_date, default_op='lastmonth', _now=dt.date(2012, 2, 4))
        filter.set(None, None)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month_left_edge(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 1))
        filter.set('lastmonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month_right_edge(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 29))
        filter.set('lastmonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_year(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 4))
        filter.set('thisyear', None)
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date BETWEEN '2012-01-01' AND '2012-12-31'"
        )
        assert filter.description == '01/01/2012 - 12/31/2012'

    def test_this_year_default(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 4), default_op='thisyear')
        filter.set(None, None)
        self.assert_filter_query(
            filter,
            "WHERE persons.due_date BETWEEN '2012-01-01' AND '2012-12-31'"
        )
        assert filter.description == '01/01/2012 - 12/31/2012'

    def test_selmonth(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 4))
        filter.set('selmonth', 1, 2012)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == 'Jan 2012'

    def test_selmonth_default(self):
        filter = DateFilter(Person.due_date, default_op='selmonth', _now=dt.date(2012, 2, 4))
        filter.set(None, None)
        assert filter.description == 'All'

    def test_selmonth_none(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 4))
        with pytest.raises(formencode.Invalid):
            filter.set('selmonth', None, 2012)

    def test_int_filter_process(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 2, 29))
        filter.set('ltda', '1', '')
        assert filter.error is False

    def test_bad_date(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid):
            filter.set('eq', '1/1/2015 - 8/31/2015')
        assert filter.error is True
        assert filter.description == 'invalid'

    def test_days_ago_overflow(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid, match='date filter given is out of range'):
            filter.set('da', '10142015')

    def test_in_days_overflow(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid, match='date filter given is out of range'):
            filter.set('ind', '10000000')

    def test_in_days_empty_value2(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        filter.set('ind', '10', '')
        self.assert_filter_query(filter, "WHERE persons.due_date = '2012-01-11'")

    def test_invalid_date(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid, match='invalid date'):
            filter.set('eq', '7/45/2007')

    def test_overflow_date(self):
        filter = DateFilter(Person.due_date)
        with pytest.raises(formencode.Invalid, match='invalid date'):
            filter.set('eq', '12345678901234567890')

    def test_days_operator_with_invalid_value(self):
        filter = DateFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid, match='Please enter an integer value'):
            filter.set('ind', 'a')

    def test_default(self):
        filter = DateFilter(Person.due_date, default_op='between', default_value1='1/31/2010',
                            default_value2='12/31/2010')
        filter.set(None, None)
        self.assert_filter_query(filter,
                                 "WHERE persons.due_date BETWEEN '2010-01-31' AND '2010-12-31'")

    def test_search_expr(self):
        expr_factory = DateFilter(Person.due_date).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('foo')
        assert str(expr) == 'CAST(persons.due_date AS VARCHAR) LIKE :param_1', str(expr)
        assert expr.right.value == '%foo%'

    def test_search_expr_with_numeric(self):
        fake_dialect = namedtuple('dialect', 'name')

        # mssql within range
        filter = DateFilter(Person.due_date).new_instance(dialect=fake_dialect('mssql'))
        expr_factory = filter.get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('1753')
        assert str(expr) == (
            'CAST(persons.due_date AS VARCHAR) LIKE :param_1 OR persons.due_date = :due_date_1'
        )
        assert expr.clauses[0].right.value == '%1753%', expr.clauses[0].right.value
        assert expr.clauses[1].right.value.year == 1753

        # mssql out of range
        filter = DateFilter(Person.due_date).new_instance(dialect=fake_dialect('mssql'))
        expr_factory = filter.get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('1752')
        assert str(expr) == 'CAST(persons.due_date AS VARCHAR) LIKE :param_1'
        assert expr.right.value == '%1752%'

    def test_search_expr_with_date(self):
        expr_factory = DateFilter(Person.due_date).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('6/19/2019')
        assert str(expr) == (
            'CAST(persons.due_date AS VARCHAR) LIKE :param_1 OR persons.due_date = :due_date_1'
        )
        assert expr.clauses[0].right.value == '%6/19/2019%'
        assert expr.clauses[1].right.value == dt.datetime(2019, 6, 19)

    def test_overflow_search_expr(self):
        expr_factory = DateFilter(Person.due_date).get_search_expr()
        # This generates an overflow error that should be handled
        expr_factory('12345678901234567890')

    def test_valid_date_for_backend(self):
        fake_dialect = namedtuple('dialect', 'name')

        filter = DateFilter(Person.due_date)
        assert filter.valid_date_for_backend(dt.date(1, 1, 1)) is True

        filter = DateFilter(Person.due_date).new_instance()
        assert filter.valid_date_for_backend('foo') is True

        filter = DateFilter(Person.due_date).new_instance(dialect=fake_dialect('postgresql'))
        assert filter.valid_date_for_backend(dt.date(1, 1, 1)) is True
        assert filter.valid_date_for_backend(dt.date(9999, 12, 31)) is True
        assert filter.valid_date_for_backend(dt.datetime(1, 1, 1)) is True
        assert filter.valid_date_for_backend(dt.datetime(9999, 12, 31, 23, 59, 59)) is True

        filter = DateFilter(Person.due_date).new_instance(dialect=fake_dialect('sqlite'))
        assert filter.valid_date_for_backend(dt.date(1, 1, 1)) is True
        assert filter.valid_date_for_backend(dt.date(9999, 12, 31)) is True
        assert filter.valid_date_for_backend(dt.datetime(1, 1, 1)) is True
        assert filter.valid_date_for_backend(dt.datetime(9999, 12, 31, 23, 59, 59)) is True

        filter = DateFilter(Person.due_date).new_instance(dialect=fake_dialect('mssql'))
        assert filter.valid_date_for_backend(dt.date(1, 1, 1)) is False
        assert filter.valid_date_for_backend(dt.date(1752, 12, 31)) is False
        assert filter.valid_date_for_backend(dt.date(1753, 1, 1)) is True
        assert filter.valid_date_for_backend(dt.date(9999, 12, 31)) is True

        assert filter.valid_date_for_backend(dt.datetime(1, 1, 1)) is False
        assert filter.valid_date_for_backend(dt.datetime(1752, 12, 31, 23, 59, 59)) is False
        assert filter.valid_date_for_backend(dt.datetime(1753, 1, 1)) is True
        assert filter.valid_date_for_backend(dt.datetime(9999, 12, 31, 23, 59, 59)) is True
        assert filter.valid_date_for_backend(dt.datetime(9999, 12, 31, 23, 59, 59, 9999)) is False

        filter = DateFilter(Person.due_date).new_instance(dialect=fake_dialect('foo'))
        assert filter.valid_date_for_backend(dt.date(1, 1, 1)) is True


class TestDateTimeFilter(CheckFilterBase):
    between_sql = "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND " \
        "'2012-01-31 23:59:59.999999'"

    def test_arrow_support_eq(self):
        filter = DateTimeFilter(ArrowRecord.created_utc)
        filter.set('eq', '12/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE arrow_records.created_utc BETWEEN '2010-12-31 00:00:00.000000' "
            "AND '2010-12-31 23:59:59.999999'")

    def test_arrow_support_lastmonth(self):
        filter = DateTimeFilter(ArrowRecord.created_utc, _now=dt.datetime(2016, 7, 18))
        filter.set('lastmonth', None)
        self.assert_filter_query(
            filter,
            "WHERE arrow_records.created_utc BETWEEN '2016-06-01 00:00:00.000000' "
            "AND '2016-06-30 23:59:59.999999'")

    def test_eq(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('eq', '12/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2010-12-31 00:00:00.000000' "
            "AND '2010-12-31 23:59:59.999999'")
        assert filter.value1_set_with == '12/31/2010'

    def test_eq_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='eq')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_eq_none(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid):
            filter.set('eq', None)

    def test_overflow_date(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid, match='invalid date'):
            filter.set('eq', '12345678901234567890')

    def test_eq_with_time(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('eq', '12/31/2010 10:26:27')
        self.assert_filter_query(filter, "WHERE persons.createdts = '2010-12-31 10:26:27.000000'")
        assert filter.value1_set_with == '12/31/2010 10:26 AM'

    def test_not_eq(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('!eq', '12/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts NOT BETWEEN '2010-12-31 00:00:00.000000' AND "
            "'2010-12-31 23:59:59.999999'")
        assert filter.value1_set_with == '12/31/2010'

    def test_not_eq_default(self):
        filter = DateFilter(Person.createdts, default_op='!eq')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_not_eq_none(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('!eq', '12/31/2010')

    def test_not_eq_with_time(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('!eq', '12/31/2010 10:26:27')
        self.assert_filter_query(filter, "WHERE persons.createdts != '2010-12-31 10:26:27.000000'")

    def test_lte(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('lte', '12/31/2010')
        self.assert_filter_query(filter, "WHERE persons.createdts <= '2010-12-31 23:59:59.999999'")
        filter.set('lte', '12/31/2010', '')
        self.assert_filter_query(filter, "WHERE persons.createdts <= '2010-12-31 23:59:59.999999'")
        assert filter.value1_set_with == '12/31/2010'
        with pytest.raises(formencode.Invalid):
            filter.set('lte', '')
        with pytest.raises(formencode.Invalid):
            filter.set('lte', None)

    def test_lte_default(self):
        filter = DateFilter(Person.createdts, default_op='lte')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_lte_with_time(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('lte', '12/31/2010 12:00')
        self.assert_filter_query(filter, "WHERE persons.createdts <= '2010-12-31 12:00:00.000000'")

    def test_lte_none(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid):
            filter.set('lte', None)

    def test_gte(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('gte', '12/31/2010')
        self.assert_filter_query(filter, "WHERE persons.createdts >= '2010-12-31 00:00:00.000000'")
        assert filter.value1_set_with == '12/31/2010'
        with pytest.raises(formencode.Invalid):
            filter.set('gte', '')
        with pytest.raises(formencode.Invalid):
            filter.set('gte', None)

    def test_gte_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='gte')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_gte_none(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid):
            filter.set('gte', None)

    def test_gte_with_time(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('gte', '12/31/2010 12:35')
        self.assert_filter_query(filter, "WHERE persons.createdts >= '2010-12-31 12:35:00.000000'")

    def test_empty(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('empty', None)
        self.assert_filter_query(filter, "WHERE persons.createdts IS NULL")
        filter.set('empty', '')
        self.assert_filter_query(filter, "WHERE persons.createdts IS NULL")

    def test_empty_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='empty')
        filter.set(None, None)
        assert filter.description == 'date not specified'

    def test_not_empty(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('!empty', None)
        self.assert_filter_query(filter, "WHERE persons.createdts IS NOT NULL")
        filter.set('!empty', '')
        self.assert_filter_query(filter, "WHERE persons.createdts IS NOT NULL")

    def test_not_empty_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='!empty')
        filter.set(None, None)
        assert filter.description == 'any date'

    def test_between(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('between', '1/31/2010', '12/31/2010')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2010-01-31 00:00:00.000000' AND "
            "'2010-12-31 23:59:59.999999'")
        assert filter.value1_set_with == '01/31/2010 12:00 AM'
        assert filter.value2_set_with == '12/31/2010 11:59 PM'

    def test_between_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='between')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_between_none(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid):
            filter.set('between', None, None)

    def test_between_missing_date(self):
        filter = DateTimeFilter(Person.createdts,
                                _now=dt.datetime(2018, 12, 15, 1, 2, 3, 5))
        filter.set('between', '12/31/2010', '')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2010-12-31 00:00:00.000000' "
            "AND '2018-12-15 01:02:03.000005'"
        )

    def test_between_blank(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid):
            filter.set('between', '', '')
        assert filter.error is True
        assert filter.description == 'invalid'

    def test_between_with_time(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('between', '1/31/2010 10:00', '12/31/2010 10:59:59')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2010-01-31 10:00:00.000000' AND "
            "'2010-12-31 10:59:59.000000'")
        assert filter.value1_set_with == '01/31/2010 10:00 AM'
        assert filter.value2_set_with == '12/31/2010 10:59 AM'

    def test_between_with_explicit_midnight(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('between', '1/31/2010 10:00', '12/31/2010 00:00')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2010-01-31 10:00:00.000000' AND "
            "'2010-12-31 00:00:00.000000'")

    def test_not_between(self):
        filter = DateTimeFilter(Person.createdts)
        filter.set('!between', '1/31/2010', '12/31/2010')
        assert filter.error is False
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts NOT BETWEEN '2010-01-31 00:00:00.000000' AND "
            "'2010-12-31 23:59:59.999999'")

    def test_not_between_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='!between')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_not_between_none(self):
        filter = DateTimeFilter(Person.createdts)
        with pytest.raises(formencode.Invalid):
            filter.set('!between', None, None)

    def test_days_ago(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 1))
        filter.set('da', '10')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2011-12-22 00:00:00.000000' AND "
            "'2011-12-22 23:59:59.999999'")

    def test_days_ago_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='da')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_days_ago_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('da', None)

    def test_days_ago_overflow(self):
        filter = DateTimeFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid, match='date filter given is out of range'):
            filter.set('da', '10000000')

    def test_less_than_days_ago(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 1, 1, 1, 1))
        filter.set('ltda', '10')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts > '2011-12-22 23:59:59.999999' AND "
            "persons.createdts <= '2012-01-01 01:01:01.000001'")

    def test_less_than_days_ago_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='ltda')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_less_than_days_ago_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('ltda', None)

    def test_more_than_days_ago(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 1))
        filter.set('mtda', '10')
        self.assert_filter_query(filter, "WHERE persons.createdts < '2011-12-22 00:00:00.000000'")

    def test_more_than_days_ago_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='mtda')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_more_than_days_ago_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid):
            filter.set('mtda', None)

    def test_in_less_than_days(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.set('iltd', '10')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts >= '2012-01-01 12:35:00.000000' AND "
            "persons.createdts < '2012-01-11 00:00:00.000000'")

    def test_in_less_than_days_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='iltd')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_in_less_than_days_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        with pytest.raises(formencode.Invalid):
            filter.set('iltd', None)

    def test_in_more_than_days(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.set('imtd', '10')
        self.assert_filter_query(filter, "WHERE persons.createdts > '2012-01-11 23:59:59.999999'")

    def test_in_more_than_days_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='imtd')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_in_more_than_days_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        with pytest.raises(formencode.Invalid):
            filter.set('imtd', None)

    def test_in_days(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.set('ind', '10')
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-11 00:00:00.000000' AND "
            "'2012-01-11 23:59:59.999999'")

    def test_in_days_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='ind')
        filter.set(None, None)
        assert filter.description == 'all'

    def test_in_days_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        with pytest.raises(formencode.Invalid):
            filter.set('ind', None)

    def test_in_days_overflow(self):
        filter = DateTimeFilter(Person.due_date, _now=dt.date(2012, 1, 1))
        with pytest.raises(formencode.Invalid, match='date filter given is out of range'):
            filter.set('ind', '10000000')

    def test_today(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.set('today', None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND "
            "'2012-01-01 23:59:59.999999'")

    def test_today_default(self):
        filter = DateTimeFilter(
            Person.createdts, default_op='today', _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.set(None, None)
        assert filter.description == '01/01/2012'

    def test_this_week(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 4, 12, 35))
        filter.set('thisweek', None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND "
            "'2012-01-07 23:59:59.999999'")

    def test_this_week_default(self):
        filter = DateTimeFilter(
            Person.createdts, default_op='thisweek', _now=dt.datetime(2012, 1, 4, 12, 35))
        filter.set(None, None)
        assert filter.description == '01/01/2012 - 01/07/2012'

    def test_this_week_left_edge(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1))
        filter.set('thisweek', None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND "
            "'2012-01-07 23:59:59.999999'")

    def test_this_week_right_edge(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 23, 59, 59, 999999))
        filter.set('thisweek', None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND "
            "'2012-01-07 23:59:59.999999'")

    def test_days_operator_with_empty_value(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        with pytest.raises(formencode.Invalid, match='Please enter a value'):
            filter.set('ind', '')

    def test_non_days_operator_with_empty_value(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.set('lastmonth', '')

    def test_set_makes_op_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.datetime(2012, 1, 1, 12, 35))
        filter.op = 'foo'
        filter.set('', '')
        assert filter.op is None

    def test_default(self):
        filter = DateTimeFilter(Person.createdts, default_op='between', default_value1='1/31/2010',
                                default_value2='12/31/2010')
        filter.set(None, None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2010-01-31 00:00:00.000000' AND "
            "'2010-12-31 23:59:59.999999'")

    def test_this_month(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 4))
        filter.set('thismonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_month_default(self):
        filter = DateTimeFilter(
            Person.createdts, default_op='thismonth', _now=dt.date(2012, 1, 4))
        filter.set(None, None)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_month_left_edge(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 1))
        filter.set('thismonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_month_right_edge(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 1, 31))
        filter.set('thismonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 4))
        filter.set('lastmonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month_default(self):
        filter = DateTimeFilter(
            Person.createdts, default_op='lastmonth', _now=dt.date(2012, 2, 4))
        filter.set(None, None)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month_left_edge(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 1))
        filter.set('lastmonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_last_month_right_edge(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 29))
        filter.set('lastmonth', None)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == '01/01/2012 - 01/31/2012'

    def test_this_year(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 4))
        filter.set('thisyear', None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND "
            "'2012-12-31 23:59:59.999999'"
        )
        assert filter.description == '01/01/2012 - 12/31/2012'

    def test_this_year_default(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 4), default_op='thisyear')
        filter.set(None, None)
        self.assert_filter_query(
            filter,
            "WHERE persons.createdts BETWEEN '2012-01-01 00:00:00.000000' AND "
            "'2012-12-31 23:59:59.999999'"
        )
        assert filter.description == '01/01/2012 - 12/31/2012'

    def test_selmonth(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 4))
        filter.set('selmonth', 1, 2012)
        self.assert_filter_query(filter, self.between_sql)
        assert filter.description == 'Jan 2012'

    def test_selmonth_default(self):
        filter = DateTimeFilter(
            Person.createdts, default_op='selmonth', _now=dt.date(2012, 2, 4))
        filter.set(None, None)
        assert filter.description == 'All'

    def test_selmonth_none(self):
        filter = DateTimeFilter(Person.createdts, _now=dt.date(2012, 2, 4))
        with pytest.raises(formencode.Invalid):
            filter.set('selmonth', None, None)

    def test_search_expr(self):
        expr_factory = DateTimeFilter(Person.due_date).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('foo')
        assert str(expr) == 'CAST(persons.due_date AS VARCHAR) LIKE :param_1', str(expr)
        assert expr.right.value == '%foo%'

    def test_search_expr_with_date(self):
        expr_factory = DateTimeFilter(Person.due_date).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('6/19/2019')
        assert str(expr) == (
            'CAST(persons.due_date AS VARCHAR) LIKE :param_1 '
            'OR persons.due_date BETWEEN :due_date_1 AND :due_date_2'
        ), str(expr)
        assert expr.clauses[0].right.value == '%6/19/2019%'
        assert expr.clauses[1].right.clauses[0].value == dt.datetime(2019, 6, 19)
        assert expr.clauses[1].right.clauses[1].value == dt.datetime(2019, 6, 19, 23, 59, 59, 999999)  # noqa: E501

    def test_search_expr_invalid_date(self):
        fake_dialect = namedtuple('dialect', 'name')
        filter = DateTimeFilter(Person.due_date).new_instance(dialect=fake_dialect('mssql'))

        expr_factory = filter.get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('6/19/1752')
        assert str(expr) == 'CAST(persons.due_date AS VARCHAR) LIKE :param_1', str(expr)
        assert expr.right.value == '%6/19/1752%'

    def test_search_expr_overflow_date(self):
        expr_factory = DateTimeFilter(Person.due_date).get_search_expr()
        # This generates an overflow error that should be handled
        expr_factory('12345678901234567890')


class TestTimeFilter(CheckFilterBase):
    def dialect_time(self, time_str):
        sql = {
            'sqlite': f'CAST(\'{time_str}:00.000000\' AS TIME)',
            'postgresql': f'CAST(\'{time_str}:00.000000\' AS TIME WITHOUT TIME ZONE)',
            'mssql': f'CAST(\'{time_str}:00.000000\' AS TIME)',
        }
        return sql.get(db.engine.dialect.name)

    def test_eq(self):
        time_string = self.dialect_time('11:30')
        filter = TimeFilter(Person.start_time)
        filter.set('eq', '11:30 am')
        self.assert_filter_query(filter,
                                 "WHERE persons.start_time = " + time_string)

    def test_not_eq(self):
        time_string = self.dialect_time('23:30')
        filter = TimeFilter(Person.start_time)
        filter.set('!eq', '11:30 pm')
        self.assert_filter_query(filter,
                                 "WHERE persons.start_time != " + time_string)

    def test_lte(self):
        time_string = self.dialect_time('09:00')
        filter = TimeFilter(Person.start_time)
        filter.set('lte', '9:00 am')
        self.assert_filter_query(filter,
                                 "WHERE persons.start_time <= " + time_string)

    def test_gte(self):
        time_string = self.dialect_time('10:15')
        filter = TimeFilter(Person.start_time)
        filter.set('gte', '10:15 am')
        self.assert_filter_query(filter,
                                 "WHERE persons.start_time >= " + time_string)

    def test_between(self):
        time_start = self.dialect_time('09:00')
        time_end = self.dialect_time('17:00')
        filter = TimeFilter(Person.start_time)
        filter.set('between', '9:00 am', '5:00 pm')
        self.assert_filter_query(
            filter,
            f"WHERE persons.start_time BETWEEN {time_start} AND {time_end}")

    def test_not_between(self):
        time_start = self.dialect_time('09:00')
        time_end = self.dialect_time('17:00')
        filter = TimeFilter(Person.start_time)
        filter.set('!between', '9:00 am', '5:00 pm')
        self.assert_filter_query(
            filter,
            f"WHERE persons.start_time NOT BETWEEN {time_start} AND {time_end}")

    def test_empty(self):
        filter = TimeFilter(Person.start_time)
        filter.set('empty', None)
        self.assert_filter_query(filter, "WHERE persons.start_time IS NULL")

    def test_not_empty(self):
        filter = TimeFilter(Person.start_time)
        filter.set('!empty', None)
        self.assert_filter_query(filter, "WHERE persons.start_time IS NOT NULL")

    def test_search_expr(self):
        expr_factory = TimeFilter(Person.start_time).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('foo')
        assert str(expr) == 'CAST(persons.start_time AS VARCHAR) LIKE :param_1', str(expr)
        assert expr.right.value == '%foo%'


class StateFilter(OptionsFilterBase):
    options_from = (('in', 'IN'), ('ky', 'KY'))


class SortOrderFilter(OptionsFilterBase):
    options_from = ((1, 'One'), (2, 'Two'))


class FloatFilter(OptionsFilterBase):
    options_from = ((1.1, '1.1'), (2.2, '2.2'))


class DecimalFilter(OptionsFilterBase):
    options_from = ((D('1.1'), '1.1'), (D('2.2'), '2.2'))


class BoolFilter(OptionsFilterBase):
    options_from = ((1, 'True'), (0, 'False'))


class BadTypeFilter(OptionsFilterBase):
    options_from = (([], 'Empty List'),)


class TestOptionsFilter(CheckFilterBase):
    def test_search_expr(self):
        class FooFilter(OptionsFilterBase):
            options_from = (('foo', 'Foo'), ('bar', 'Bar'), (5, 'Baz'))
        expr_factory = FooFilter(Person.state).new_instance().get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('foo')
        assert str(expr) == 'persons.state IN (:state_1)'
        assert expr.right.clauses[0].value == 'foo'

        expr = expr_factory('ba')
        assert str(expr) == 'persons.state IN (:state_1, :state_2)'
        assert expr.right.clauses[0].value == 'bar'
        assert expr.right.clauses[1].value == 5

    def test_is(self):
        filter = StateFilter(Person.state).new_instance()
        # the "foo" should get filtered out
        filter.set('is', ['in', 'foo'])
        self.assert_filter_query(filter, "WHERE persons.state = 'in'")

    def test_is_multiple(self):
        filter = StateFilter(Person.state).new_instance()
        filter.set('is', ['in', 'ky'])
        self.assert_filter_query(filter, "WHERE persons.state IN ('in', 'ky')")

    def test_is_not(self):
        filter = StateFilter(Person.state).new_instance()
        filter.set('!is', ['in'])
        self.assert_filter_query(filter, "WHERE persons.state != 'in'")

    def test_is_not_multiple(self):
        filter = StateFilter(Person.state).new_instance()
        filter.set('!is', ['in', 'ky'])
        self.assert_filter_query(filter, "WHERE persons.state NOT IN ('in', 'ky')")

    def test_empty(self):
        filter = StateFilter(Person.state).new_instance()
        filter.set('empty', None)
        self.assert_filter_query(filter, "WHERE persons.state IS NULL")

    def test_not_empty(self):
        filter = StateFilter(Person.state).new_instance()
        filter.set('!empty', None)
        self.assert_filter_query(filter, "WHERE persons.state IS NOT NULL")

    def test_integer_conversion(self):
        filter = SortOrderFilter(Person.sortorder).new_instance()
        # the '3' should get filtered out because its not a valid option
        # the 'foo' should get filtered out because its the wrong type (and isn't an option)
        filter.set('is', ['1', '2', '3', 'foo'])
        self.assert_filter_query(filter, "WHERE persons.sortorder IN (1, 2)")

    def test_float_conversion(self):
        filter = FloatFilter(Person.floatcol).new_instance()
        filter.set('is', ['1.1'])
        self.assert_filter_query(filter, "WHERE persons.floatcol = 1.1")

    def test_decimal_conversion(self):
        filter = DecimalFilter(Person.numericcol).new_instance()
        filter.set('is', ['1.1'])
        self.assert_filter_query(filter, "WHERE persons.numericcol = 1.1")

    def test_custom_validator(self):
        filter = BoolFilter(Person.boolcol, lambda x: 1 if x == '1' else 0).new_instance()
        filter.set('is', ['1'])
        self.assert_filter_query(filter, "WHERE persons.boolcol = 1")

    def test_unknown_type(self):
        with pytest.raises(
            TypeError,
            match="can't use value_modifier='auto' when option keys are <(class|type) 'list'>"
        ):
            BadTypeFilter(Person.boolcol).new_instance()

    def test_value_not_in_options_makes_inactive(self):
        filter = StateFilter(Person.state).new_instance()

        filter.set('is', ['foo'])
        assert not filter.is_active

        filter.set('!is', ['foo'])
        assert not filter.is_active

    def test_auto_validation_with_no_options(self):
        with pytest.raises(
            ValueError,
            match='value_modifier argument set to "auto", but the options set is empty and '
            'the type can therefore not be determined for NoOptionsFilter'
        ):
            class NoOptionsFilter(OptionsFilterBase):
                pass
            NoOptionsFilter(Person.numericcol).new_instance()

    def test_modifier_wrong_type(self):
        with pytest.raises(
            TypeError,
            match='value_modifier must be the string "auto", have a "to_python" attribute, '
            'or be a callable'
        ):
            StateFilter(Person.state, value_modifier=1).new_instance()

    def test_default(self):
        filter = SortOrderFilter(Person.sortorder, default_op='is',
                                 default_value1=['1', '2', '3', 'foo']).new_instance()
        filter.set(None, None)
        self.assert_filter_query(filter, "WHERE persons.sortorder IN (1, 2)")

    def test_default_op_callable(self):
        def def_op():
            return 'is'
        filter = SortOrderFilter(Person.sortorder, default_op=def_op,
                                 default_value1=['1', '2', '3', 'foo']).new_instance()
        filter.set(None, None)
        self.assert_filter_query(filter, "WHERE persons.sortorder IN (1, 2)")

    def test_default_callable(self):
        def def_val():
            return list(map(str, list(range(1, 4))))
        filter = SortOrderFilter(Person.sortorder, default_op='is',
                                 default_value1=def_val).new_instance()
        filter.set(None, None)
        self.assert_filter_query(filter, "WHERE persons.sortorder IN (1, 2)")


class TestEnumFilter(CheckFilterBase):
    def test_create_without_enum_type(self):
        with pytest.raises(ValueError, match='enum_type argument not given'):
            OptionsEnumFilter(Person.account_type)

    def test_default_modifier_throws_error_when_not_exists(self):
        f = OptionsEnumFilter(Person.account_type, enum_type=AccountType)
        with pytest.raises(ValueError, match='Not a valid selection'):
            f.default_modifier('doesntexist')

    def test_returns_value_when_value_modifier_is_none(self):
        f = OptionsEnumFilter(Person.account_type, enum_type=AccountType)
        f.value_modifier = None
        f.process('value')

    def test_is(self):
        filter = OptionsEnumFilter(Person.account_type, enum_type=AccountType).new_instance()
        filter.set('is', ['admin'])
        self.assert_filter_query(filter, "WHERE persons.account_type = 'admin'")

    def test_is_multiple(self):
        filter = OptionsEnumFilter(Person.account_type, enum_type=AccountType).new_instance()
        filter.set('is', ['admin', 'manager'])
        self.assert_filter_query(filter, "WHERE persons.account_type IN ('admin', 'manager')")

    def test_literal_value(self):
        filter = OptionsEnumFilter(Person.account_type, enum_type=AccountType).new_instance()
        filter.set('is', [AccountType.admin])
        self.assert_filter_query(filter, "WHERE persons.account_type = 'admin'")


class TestIntrospect(CheckFilterBase):
    def test_new_instance(self):
        class TestFilter(FilterBase):
            def __init__(self, a, b, *vargs, **kwargs):
                super(TestFilter, self).__init__(a)
                self.a = a
                self.b = b
                self.vargs = vargs
                self.kwargs = kwargs

        tf1 = TestFilter(Person.firstname, 'foo', 'bar', 'baz', x=1, y=2)
        assert tf1.a == Person.firstname
        assert tf1.b == 'foo'
        assert tf1.vargs == ('bar', 'baz')
        assert tf1.kwargs == {'x': 1, 'y': 2}

        tf2 = tf1.new_instance()
        assert tf2.a == Person.firstname
        assert tf2.b == 'foo'
        assert tf2.vargs == ('bar', 'baz')
        assert tf2.kwargs == {'x': 1, 'y': 2}

        assert tf1 is not tf2


class TestYesNoFilter(CheckFilterBase):
    def test_y(self):
        sql_check = {
            'sqlite': "WHERE persons.boolcol = 1",
            'postgresql': "WHERE persons.boolcol = true",
            'mssql': "WHERE persons.boolcol = 1",
        }
        filterobj = YesNoFilter(Person.boolcol)
        filterobj.set('y', None)
        query = filterobj.apply(db.session.query(Person.boolcol))
        self.assert_in_query(query, sql_check.get(db.engine.dialect.name))

    def test_n(self):
        sql_check = {
            'sqlite': "WHERE persons.boolcol = 0",
            'postgresql': "WHERE persons.boolcol = false",
            'mssql': "WHERE persons.boolcol = 0",
        }
        filterobj = YesNoFilter(Person.boolcol)
        filterobj.set('n', None)
        query = filterobj.apply(db.session.query(Person.boolcol))
        self.assert_in_query(query, sql_check.get(db.engine.dialect.name))

    def test_a(self):
        filterobj = YesNoFilter(Person.boolcol)
        filterobj.set('a', None)
        query = filterobj.apply(db.session.query(Person.boolcol))
        self.assert_not_in_query(query, "WHERE persons.boolcol")

    def test_search_expr(self):
        expr_factory = YesNoFilter(Person.boolcol).get_search_expr()
        assert callable(expr_factory)
        expr = expr_factory('Yes')
        assert str(expr) == 'persons.boolcol = true'

        expr = expr_factory('No')
        assert str(expr) == 'persons.boolcol = false'

        expr = expr_factory('Foo')
        assert expr is None
