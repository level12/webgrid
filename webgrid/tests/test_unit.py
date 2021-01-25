from __future__ import absolute_import

import re
from decimal import Decimal
from os import path

import arrow
import flask
import pytest
from mock import mock
import sqlalchemy.sql as sasql
from werkzeug.datastructures import MultiDict

from webgrid import Column, BoolColumn, YesNoColumn
from webgrid.extensions import RequestArgsLoader, WebSessionArgsLoader
from webgrid.filters import FilterBase, TextFilter, IntFilter, AggregateIntFilter
from webgrid_ta.model.entities import Person, Status, Stopwatch, db
from webgrid_ta.grids import Grid, PeopleGrid, PeopleGridByConfig
from .helpers import assert_in_query, assert_not_in_query, query_to_str, inrequest
from webgrid.renderers import CSV


class TestGrid(object):
    class TG(Grid):
        Column('First Name', Person.firstname)

    class KeyGrid(Grid):
        # demonstrate grid operations when multiple column expressions have the same key
        Column('Person ID', Person.id, IntFilter)
        Column('Stopwatch ID', Stopwatch.id, IntFilter)

        query_joins = [(Stopwatch, Stopwatch.id > 0)]

    def setup_method(self, _):
        Status.delete_cascaded()
        Person.testing_create()
        Person.testing_create()
        Person.testing_create()
        Person.testing_create()
        Person.testing_create()

    def test_static_path(self):
        g = self.TG()
        assert g.manager.static_path().endswith('webgrid{}static'.format(path.sep))

    def test_column_key(self):
        g = self.TG()
        g.build_query()
        assert g.columns[0].key == 'firstname'

    def test_columns_are_new_instances(self):
        g = self.TG()
        g2 = self.TG()
        assert g.columns[0] is not self.TG.__cls_cols__[0]
        assert g.columns[0].__class__ is self.TG.__cls_cols__[0].__class__
        assert g.columns[0] is not g2.columns[0]
        assert g.columns[0] is g.key_column_map['firstname']

    def test_grid_ident(self):
        class Grid1(Grid):
            identifier = 'cars'

        class Grid2(Grid):
            pass

        mg = Grid2()
        assert mg.ident == 'grid2'

        mg = Grid1()
        assert mg.ident == 'cars'

        mg = Grid1('foo')
        assert mg.ident == 'foo'

    def test_base_query(self):
        class CTG(Grid):
            Column('First Name', Person.firstname)
        g = CTG()
        query = g.build_query()
        assert_not_in_query(query, 'WHERE')
        if db.engine.dialect.name != 'mssql':
            assert_not_in_query(query, 'ORDER BY')
        else:
            # MSSQL queries get an ORDER BY patched in if none is provided,
            # else paging doesn't work
            assert_in_query(query, 'ORDER BY')
        with mock.patch('logging.Logger.debug') as m_debug:
            rs = g.records
            assert len(rs) > 0, rs
            expected = [
                r'^<Grid "CTG">$',
                r'^No filters$',
                r'^No sorts$',
                r'^Page 1; 50 per page$',
                r'^Data query ran in \d+\.?\d* seconds$',
            ]
            assert len(expected) == len(m_debug.call_args_list)
            for idx, call in enumerate(m_debug.call_args_list):
                assert re.match(expected[idx], call[0][0])

    @mock.patch('logging.Logger.debug')
    def test_subtotal_sum_by_default(self, m_debug):
        class CTG(Grid):
            Column('Sum Total', Person.numericcol.label('something'), has_subtotal=True)
        Person.testing_create(numericcol=5)
        Person.testing_create(numericcol=10)
        g = CTG()
        totals = g.grand_totals
        assert totals.something == 15
        expected = [
            r'^<Grid "CTG">$',
            r'^No filters$',
            r'^Totals query ran in \d+\.?\d* seconds$',
        ]
        assert len(expected) == len(m_debug.call_args_list)
        for idx, call in enumerate(m_debug.call_args_list):
            assert re.match(expected[idx], call[0][0])

    def test_subtotal_sum(self):
        class CTG(Grid):
            Column('Sum Total', Person.numericcol.label('something'), has_subtotal='sum')
        Person.testing_create(numericcol=5)
        Person.testing_create(numericcol=10)
        g = CTG()
        totals = g.grand_totals
        assert totals.something == 15

    def test_subtotal_avg(self):
        class CTG(Grid):
            Column('Sum Total', Person.numericcol.label('something'), has_subtotal='avg')
        Person.testing_create(numericcol=5)
        Person.testing_create(numericcol=10)
        g = CTG()
        totals = g.grand_totals
        assert totals.something == Decimal('7.5')

    def test_subtotal_expr_string(self):
        class CTG(Grid):
            ratio_expr = Person.numericcol / Person.sortorder
            Column('Numeric', Person.numericcol.label('numeric_col'), has_subtotal=True)
            Column('Ints', Person.floatcol.label('float_col'), has_subtotal=True)
            Column('Ratio', Person.numericcol.label('something'),
                   has_subtotal='sum(numeric_col) / sum(float_col)')
        Person.testing_create(numericcol=5, floatcol=1)
        Person.testing_create(numericcol=10, floatcol=3)
        g = CTG()
        totals = g.grand_totals
        assert totals.something == Decimal('3.75'), totals

    def test_subtotal_expr(self):
        sum_ = sasql.functions.sum

        class CTG(Grid):
            ratio_expr = Person.numericcol / Person.sortorder
            Column('Numeric', Person.numericcol.label('numeric_col'), has_subtotal=True)
            Column('Ints', Person.floatcol.label('float_col'), has_subtotal=True)
            Column('Ratio', Person.numericcol.label('something'),
                   has_subtotal=sum_(Person.numericcol) / sum_(Person.floatcol))
        Person.testing_create(numericcol=5, floatcol=1)
        Person.testing_create(numericcol=10, floatcol=3)
        g = CTG()
        totals = g.grand_totals
        assert totals.something == Decimal('3.75'), totals

    def test_query_prep_sorting(self):
        class CTG(Grid):
            Column('First Name', Person.firstname)

            def query_prep(self, query, has_sort, has_filters):
                assert not has_sort
                assert not has_filters
                return query.order_by(Person.lastname)

        g = CTG()
        assert_in_query(g, 'ORDER BY persons.last_name')

    def test_filter_class(self):
        class CTG(Grid):
            Column('First Name', Person.firstname, TextFilter)
            Column('Last Name', Person.lastname, TextFilter)

        g = CTG()
        g.set_filter('firstname', 'eq', 'foo')
        if db.engine.dialect.name == 'mssql':
            assert_in_query(g, "WHERE persons.firstname = 'foo'")
        else:
            assert_in_query(g, "WHERE upper(persons.firstname) = upper('foo')")

        with mock.patch('logging.Logger.debug') as m_debug:
            g.records
            g.set_filter('lastname', 'eq', 'bar')
            g.records
            expected = [
                r'^<Grid "CTG">$',
                r'^firstname: class=TextFilter, op=eq, value1=foo, value2=None$',
                r'^No sorts$',
                r'^Page 1; 50 per page$',
                r'^Data query ran in \d+\.?\d* seconds$',
                r'^<Grid "CTG">$',
                r'^firstname: class=TextFilter, op=eq, value1=foo, value2=None;'
                r'lastname: class=TextFilter, op=eq, value1=bar, value2=None$',
                r'^No sorts$',
                r'^Page 1; 50 per page$',
                r'^Data query ran in \d+\.?\d* seconds$',
            ]
            assert len(expected) == len(m_debug.call_args_list)
            for idx, call in enumerate(m_debug.call_args_list):
                assert re.match(expected[idx], call[0][0])

    def test_filter_instance(self):
        class CTG(Grid):
            Column('First Name', Person.firstname, TextFilter(Person.lastname))

        g = CTG()
        g.set_filter('firstname', 'eq', 'foo')
        if db.engine.dialect.name == 'mssql':
            assert_in_query(g, "WHERE persons.last_name = 'foo'")
        else:
            assert_in_query(g, "WHERE upper(persons.last_name) = upper('foo')")

    def test_filter_two_values(self):
        class CTG(Grid):
            Column('Sort Order', Person.sortorder, IntFilter(Person.sortorder))

        g = CTG()
        g.set_filter('sortorder', 'between', 5, value2=10)
        assert_in_query(g, "WHERE persons.sortorder BETWEEN 5 AND 10")

    def test_order_by(self):
        class CTG(Grid):
            Column('First Name', Person.firstname)

        g = CTG()
        g.set_sort('-firstname')
        assert_in_query(g, 'ORDER BY persons.firstname')
        with mock.patch('logging.Logger.debug') as m_debug:
            g.records
            expected = [
                r'^<Grid "CTG">$',
                r'^No filters$',
                r'^firstname$',
                r'^Page 1; 50 per page$',
                r'^Data query ran in \d+\.?\d* seconds$',
            ]
            assert len(expected) == len(m_debug.call_args_list)
            for idx, call in enumerate(m_debug.call_args_list):
                re.match(expected[idx], call[0][0])

    def test_redundant_order_by(self):
        class CTG(Grid):
            Column('First Name', Person.firstname)
            Column('Last Name', Person.lastname)

        g = CTG()
        g.set_sort('firstname', 'lastname', '-firstname')
        assert_in_query(g, 'ORDER BY persons.firstname, persons.last_name')
        assert_not_in_query(g, 'ORDER BY persons.firstname, persons.last_name,')
        with mock.patch('logging.Logger.debug') as m_debug:
            g.records
            expected = [
                r'^<Grid "CTG">$',
                r'^No filters$',
                r'^firstname,lastname$',
                r'^Page 1; 50 per page$',
                r'^Data query ran in \d+\.?\d* seconds$',
            ]
            assert len(expected) == len(m_debug.call_args_list)
            for idx, call in enumerate(m_debug.call_args_list):
                assert re.match(expected[idx], call[0][0])

    def test_paging(self):
        g = self.TG()
        if db.engine.dialect.name == 'mssql':
            assert_in_query(g, 'SELECT TOP 50 ')
        else:
            assert_in_query(g, 'LIMIT 50 OFFSET 0')

        g.set_paging(2, 1)
        if db.engine.dialect.name == 'mssql':
            assert_in_query(g, 'SELECT TOP 2 ')
        else:
            assert_in_query(g, 'LIMIT 2 OFFSET 0')

        g.set_paging(10, 5)
        if db.engine.dialect.name == 'mssql':
            assert_in_query(g, 'WHERE mssql_rn > 40 AND mssql_rn <= 10 + 40')
            assert_in_query(g, 'SELECT persons.firstname AS firstname, ROW_NUMBER() '
                               'OVER (ORDER BY persons.firstname) AS mssql_rn')
        else:
            assert_in_query(g, 'LIMIT 10 OFFSET 40')

    def test_paging_disabled(self):
        class TG(Grid):
            pager_on = False
            Column('First Name', Person.firstname)
        g = TG()
        assert_not_in_query(g, 'LIMIT 50 OFFSET 0')
        assert g.page_count == 1

    def test_page_count(self):
        g = self.TG()
        assert g.page_count == 1

        g.set_paging(1, 2)
        assert g.page_count == 5

        g = self.TG(per_page=None)
        assert g.page_count == 1

    @mock.patch('logging.Logger.debug')
    def test_record_count(self, m_debug):
        g = self.TG()
        assert g.record_count == 5
        expected = [
            r'^<Grid "TG">$',
            r'^No filters$',
            r'^Count query ran in \d+\.?\d* seconds$',
        ]
        assert len(expected) == len(m_debug.call_args_list)
        for idx, call in enumerate(m_debug.call_args_list):
            assert re.match(expected[idx], call[0][0])

    def test_column_iterators_for_rendering(self):
        class TG(Grid):
            Column('C1', Person.firstname)
            Column('C1.5', Person.firstname.label('fn2'), render_in=None)
            Column('C2', Person.lastname, render_in='xls')
            BoolColumn('C3', Person.inactive, render_in=('xls', 'html'))
            YesNoColumn('C4', Person.inactive.label('yesno'), render_in='html')
            Column('C5', Person.firstname.label('fn3'), render_in='xlsx')
            Column('C6', Person.firstname.label('fn4'), render_in=('csv'))
            Column('C7', Person.firstname.label('fn5'),
                   render_in=('xls', 'xlsx', 'html', 'csv'), visible=False)

        tg = TG()

        html_cols = tuple(tg.iter_columns('html'))
        assert len(html_cols) == 3
        assert html_cols[0].key == 'firstname'
        assert html_cols[1].key == 'inactive'
        assert html_cols[2].key == 'yesno'

        xls_cols = tuple(tg.iter_columns('xls'))
        assert len(xls_cols) == 3
        assert xls_cols[0].key == 'firstname'
        assert xls_cols[1].key == 'lastname'
        assert xls_cols[2].key == 'inactive'

        xlsx_cols = tuple(tg.iter_columns('xlsx'))
        assert len(xlsx_cols) == 2
        assert xlsx_cols[0].key == 'firstname'
        assert xlsx_cols[1].key == 'fn3'
        csv_cols = tuple(tg.iter_columns('csv'))
        assert len(csv_cols) == 2
        assert xls_cols[0].key == 'firstname'
        assert csv_cols[1].key == 'fn4'

    def test_grid_inheritance(self):
        class SomeGrid(Grid):
            Column('n1', Person.firstname)

        class SomeGrid2(SomeGrid):
            Column('n2', Person.lastname)

        pg = SomeGrid2()
        assert len(pg.columns) == 2
        assert pg.columns[1].key == 'lastname'

    def test_export_as_response(self):
        export_xls = mock.MagicMock()
        export_xlsx = mock.MagicMock()

        class TG(Grid):
            Column('First Name', Person.firstname)

            def set_renderers(self):
                super(TG, self).set_renderers()
                self.xls = export_xls
                self.xlsx = export_xlsx

        grid = TG()
        grid.set_export_to('xls')
        grid.export_as_response()
        export_xls.as_response.assert_called_once_with(None, None)
        export_xlsx.as_response.assert_not_called()

        export_xls.reset_mock()

        grid.set_export_to('xlsx')
        grid.export_as_response()
        export_xls.as_response.assert_not_called()
        export_xlsx.as_response.assert_called_once_with(None, None)

        grid = TG()
        with pytest.raises(ValueError, match='No export format set'):
            grid.export_as_response()

    def test_export_as_response_with_csv(self):
        export_csv = mock.MagicMock()

        class TG(Grid):
            Column('First Name', Person.firstname)
            allowed_export_targets = {'csv': CSV}

            def set_renderers(self):
                super(TG, self).set_renderers()
                self.csv = export_csv

        grid = TG()
        grid.set_export_to('csv')
        grid.export_as_response()
        export_csv.as_response.assert_called_once_with()

        grid = TG()
        with pytest.raises(ValueError, match='No export format set'):
            grid.export_as_response('xls')

    def test_search_expressions_filtering_nones(self):
        class NonSearchingFilter(FilterBase):
            def get_search_expr(self):
                return None

        class CTG(Grid):
            Column('First Name', Person.firstname, NonSearchingFilter)

        assert len(CTG().search_expression_generators) == 0

    def test_search_expressions_generate_nones(self):
        class NonSearchingFilter(FilterBase):
            def get_search_expr(self):
                return lambda value: None

        class CTG(Grid):
            Column('First Name', Person.firstname, NonSearchingFilter)

        assert len(CTG().search_expression_generators) == 1
        g = CTG()
        g.search_value = 'foo'
        assert_not_in_query(g, 'WHERE')

    def test_search_expressions_uncallable(self):
        class BadFilter(FilterBase):
            def get_search_expr(self):
                return 'foo'

        class CTG(Grid):
            Column('First Name', Person.firstname, BadFilter)

        with pytest.raises(Exception, match='bad filter search expression: foo is not callable'):
            CTG().search_expression_generators

    def test_search_query(self):
        class CTG(Grid):
            Column('First Name', Person.firstname, TextFilter)
            Column('Last Name', Person.lastname, TextFilter)

        g = CTG()
        g.search_value = 'foo'
        if db.engine.dialect.name == 'sqlite':
            search_where = ("WHERE lower(persons.firstname) LIKE lower('%foo%')"
                            " OR lower(persons.last_name) LIKE lower('%foo%')")
        elif db.engine.dialect.name == 'postgresql':
            search_where = ("WHERE persons.firstname ILIKE '%foo%'"
                            " OR persons.last_name ILIKE '%foo%'")
        elif db.engine.dialect.name == 'mssql':
            search_where = ("WHERE persons.firstname LIKE '%foo%'"
                            " OR persons.last_name LIKE '%foo%'")
        assert_in_query(g, search_where)

    def test_search_query_with_aggregate_column(self):
        class TG(Grid):
            Column('First Name', Person.firstname, TextFilter)
            Column('Count', sasql.func.count(Person.id).label('num_people'), AggregateIntFilter)

            # Column in set for filtering only. Not in select, so not needed in grouping.
            Column('Last Name', 'no_expr', TextFilter(Person.lastname), visible=False)

            def query_prep(self, query, has_sort, has_filters):
                return query.group_by(Person.firstname)

        g = TG()
        g.search_value = 'foo'

        search_expr = {
            'sqlite': (
                "WHERE lower(persons.firstname) LIKE lower('%foo%')"
                " OR lower(persons.last_name) LIKE lower('%foo%')"
            ),
            'postgresql': (
                "WHERE persons.firstname ILIKE '%foo%'"
                " OR persons.last_name ILIKE '%foo%'"
            ),
            'mssql': (
                "WHERE persons.firstname LIKE '%foo%'"
                " OR persons.last_name LIKE '%foo%'"
            )
        }[db.engine.dialect.name]
        assert_in_query(g, search_expr)
        g.records

        g.clear_record_cache()
        g.filtered_cols.pop('firstname')
        g.filtered_cols.pop('no_expr')
        search_expr = {
            'sqlite': (
                "HAVING CAST(count(persons.id) AS VARCHAR) LIKE '%foo%'"
            ),
            'postgresql': (
                "HAVING CAST(count(persons.id) AS VARCHAR) LIKE '%foo%'"
            ),
            'mssql': (
                "HAVING CAST(count(persons.id) AS NVARCHAR(max)) LIKE N'%foo%'"
            )
        }[db.engine.dialect.name]
        assert_in_query(g, search_expr)
        g.records

    def test_column_keys_unique(self):
        grid = self.KeyGrid()
        assert grid.column('id').expr == Person.id
        assert grid.column('id_1').expr == Stopwatch.id

    def test_column_keys_unique_query_default_sort(self):
        grid = self.KeyGrid()
        grid.query_default_sort = 'id'
        assert_in_query(grid, 'ORDER BY stopwatches.id')
        grid.query_default_sort = Stopwatch.id
        assert_in_query(grid, 'ORDER BY stopwatches.id')
        grid.query_default_sort = Person.id
        assert_in_query(grid, 'ORDER BY persons.id')

    @inrequest('/foo?op(id)=gte&v1(id)=0')
    def test_column_keys_unique_filter_persons(self):
        grid = self.KeyGrid()
        grid.apply_qs_args()
        assert_in_query(grid, 'WHERE persons.id >= 0')

    @inrequest('/foo?op(id_1)=gte&v1(id_1)=0')
    def test_column_keys_unique_filter_stopwatches(self):
        grid = self.KeyGrid()
        grid.apply_qs_args()
        assert_in_query(grid, 'WHERE stopwatches.id >= 0')

    @inrequest('/foo?sort1=id_1&sort2=id')
    def test_column_keys_unique_sort(self):
        grid = self.KeyGrid()
        grid.apply_qs_args()
        assert_in_query(grid, 'ORDER BY stopwatches.id, persons.id')


class TestQueryStringArgs(object):

    @classmethod
    def setup_class(cls):
        Status.delete_cascaded()
        Status.testing_create('pending')
        Status.testing_create('in process')
        Status.testing_create('complete')
        Person.testing_create('bob')
        Person.testing_create('bob')
        Person.testing_create()

    @inrequest('/foo?dg_perpage=1&dg_onpage=2')
    @pytest.mark.parametrize('grid_cls', [PeopleGrid, PeopleGridByConfig])
    def test_qs_prefix(self, grid_cls):
        pg = grid_cls(qs_prefix='dg_')
        pg.apply_qs_args()
        assert pg.on_page == 2
        assert pg.per_page == 1

    @inrequest('/foo?perpage=1&onpage=2')
    def test_qs_paging(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.on_page == 2
        assert pg.per_page == 1

        # make sure the corret values get applied to the query
        if db.engine.dialect.name == 'mssql':
            assert 'WHERE mssql_rn > 1 AND mssql_rn <= 1 + 1' in query_to_str(pg.build_query())
        else:
            assert 'LIMIT 1 OFFSET 1' in query_to_str(pg.build_query())

    @inrequest('/foo?perpage=5&onpage=foo')
    def test_qs_onpage_invalid(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.on_page == 1
        assert pg.per_page == 5
        assert pg.user_warnings[0] == '"onpage" grid argument invalid, ignoring'

    @inrequest('/foo?perpage=5&onpage=-1')
    def test_qs_onpage_negative(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.on_page == 1
        assert pg.per_page == 5
        assert len(pg.user_warnings) == 0

    @inrequest('/foo?perpage=1&onpage=100')
    def test_qs_onpage_too_high(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.on_page == 3
        assert pg.per_page == 1
        assert len(pg.user_warnings) == 0

        # the records should be the same as if we were on the last page
        assert len(pg.records) == 1

    @inrequest('/foo?perpage=foo&onpage=2')
    def test_qs_perpage_invalid(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.on_page == 2
        assert pg.per_page == 1
        assert pg.user_warnings[0] == '"perpage" grid argument invalid, ignoring'

    @inrequest('/foo?perpage=-1&onpage=2')
    def test_qs_perpage_negative(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.on_page == 2
        assert pg.per_page == 1
        assert len(pg.user_warnings) == 0

    @inrequest('/foo?sort1=foo&sort2=firstname&sort3=-status')
    def test_qs_sorting(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.order_by == [('firstname', False), ('status', True)]
        assert pg.user_warnings[0] == 'can\'t sort on invalid key "foo"'

    @inrequest('/foo?sort1=fullname&sort2=firstname&sort3=-status')
    def test_qs_sorting_not_allowed(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.order_by == [('firstname', False), ('status', True)]
        assert pg.user_warnings[0] == 'can\'t sort on invalid key "fullname"'

    @inrequest('/foo?sort1=')
    def test_qs_sorting_ignores_emptystring(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.order_by == []
        assert len(pg.user_warnings) == 0

    def test_qs_filtering(self):
        first_id = Status.query.filter_by(label='pending').one().id
        second_id = Status.query.filter_by(label='in process').one().id
        with flask.current_app.test_request_context(
            '/foo?op(firstname)=eq&v1(firstname)=fn001&op(status)=is'
            f'&v1(status)={first_id}&v1(status)={second_id}'
        ):
            pg = PeopleGrid()
            pg.apply_qs_args()
        assert pg.columns[0].filter.op == 'eq'
        assert pg.columns[0].filter.value1 == 'fn001'
        assert pg.columns[0].filter.value2 is None

        assert pg.columns[4].filter.op == 'is'
        assert pg.columns[4].filter.value1 == [first_id, second_id]
        assert pg.columns[4].filter.value2 is None

    @inrequest('/foo')
    def test_qs_filtering_default_op(self):
        from webgrid_ta.grids import DefaultOpGrid
        pg = DefaultOpGrid()
        pg.apply_qs_args()
        assert pg.columns[0].filter.op == 'eq'
        assert pg.columns[0].filter.value1 is None

    @inrequest('/foo?op(firstname)=!eq&v1(firstname)=bob')
    def test_qs_filtering_default_op_override(self):
        from webgrid_ta.grids import DefaultOpGrid
        pg = DefaultOpGrid()
        pg.apply_qs_args()
        assert pg.columns[0].filter.op == '!eq'
        assert pg.columns[0].filter.value1 == 'bob'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_qs_paging_doesnt_get_page_count_before_filters_are_handled(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        # this ensures that the filtering in apply_qs_args() takes place before
        # the paging.  Since the paging section uses .page_count, we have to
        # make sure the filters get processed first.  Otherwise an incorrect
        # page count gets cached.
        assert pg.record_count == 2

    @inrequest('/foo')
    def test_qs_no_session(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.column('firstname').filter.op is None

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_qs_keyed_session(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        flask.request.args['op(firstname)'] = '!eq'
        pg2 = PeopleGrid()
        pg2.apply_qs_args()
        assert pg2.column('firstname').filter.op == '!eq'
        flask.request.args = MultiDict([('session_key', pg.session_key)])
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.column('firstname').filter.op == 'eq'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_grid_args_ignores_url(self):
        pg = PeopleGrid()
        pg.apply_qs_args(grid_args=MultiDict({
            'op(firstname)': 'contains',
            'v1(firstname)': 'bill',
        }))
        assert pg.column('firstname').filter.op == 'contains'
        assert pg.column('firstname').filter.value1 == 'bill'

    @inrequest('/foo?op(firstname)=&v1(firstname)=foo&op(status)=&v1(status)=1')
    def test_qs_blank_operator(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.columns[0].filter.op is None
        assert pg.columns[0].filter.value1 is None
        assert pg.columns[0].filter.value2 is None

        assert pg.columns[4].filter.op is None
        assert pg.columns[4].filter.value1 is None
        assert pg.columns[4].filter.value2 is None

    @inrequest('/foo?sort1=legacycol1&sort2=legacycol2')
    def test_sa_expr_sort(self):
        class AGrid(Grid):
            Column('First Name', 'firstname')
            Column('LC1', Person.legacycol1)
            Column('LC2', Person.legacycol2)

            def query_base(self, has_sort, has_filters):
                query = db.session.query(
                    Person.id, Person.firstname,
                    Person.legacycol1, Person.legacycol2
                )
                return query

        g = AGrid()
        g.apply_qs_args()

        # this will fail if we are not using SA expressions correctly to sort
        g.records

    @inrequest('/thepage?export_to=xls')
    def test_export_to_xls(self):
        g = PeopleGrid()
        g.apply_qs_args()
        assert g.export_to == 'xls'

    @inrequest('/thepage?export_to=xlsx')
    def test_export_to_xlsx(self):
        g = PeopleGrid()
        g.apply_qs_args()
        assert g.export_to == 'xlsx'

    @inrequest('/thepage?export_to=foo')
    def test_export_to_unrecognized(self):
        g = PeopleGrid()
        g.apply_qs_args()
        assert g.export_to is None

    @inrequest('/foo?op(id)=eq&v1(id)=d')
    def test_exc_msg_in_warnings(self):
        class TGrid(Grid):
            Column('T', Person.id, IntFilter)
        g = TGrid()
        g.apply_qs_args()
        assert g.user_warnings[0] == 'T: Please enter an integer value'

    @inrequest('/foo?search=bar')
    def test_qs_search(self):
        g = PeopleGrid()
        g.enable_search = True
        g.apply_qs_args()
        assert g.search_value == 'bar'

    @inrequest('/foo?search=bar')
    def test_qs_search_disabled(self):
        g = PeopleGrid()
        g.enable_search = False
        g.apply_qs_args()
        assert g.search_value is None

    @inrequest('/foo?search=bar')
    def test_qs_no_searchable_columns(self):
        class TG(Grid):
            Column('First Name', Person.firstname)

        g = TG()
        g.enable_search = True
        g.apply_qs_args()
        assert g.search_value is None


class TestRequestArgsLoader:
    def test_passthru(self):
        source_args = MultiDict([('foo', 'bar'), ('baz', 'bin')])
        source_args_copy = source_args.copy()
        grid = PeopleGrid()
        loader = RequestArgsLoader(grid.manager)
        result = loader.get_args(grid, source_args)
        assert result == source_args == source_args_copy

    def test_qs_prefix_filter(self):
        source_args = MultiDict([('foo', 'bar'), ('baz', 'bin'), ('boo', 'hoo'),
                                 ('baz', 'bid')])
        source_args_copy = source_args.copy()
        grid = PeopleGrid(qs_prefix='b')
        loader = RequestArgsLoader(grid.manager)
        result = loader.get_args(grid, source_args)
        assert source_args == source_args_copy
        assert result == MultiDict([('az', 'bin'), ('az', 'bid'), ('oo', 'hoo')])

    def test_reset(self):
        source_args = MultiDict([('foo', 'bar'), ('baz', 'bin'), ('dgreset', '1')])
        grid = PeopleGrid()
        loader = RequestArgsLoader(grid.manager)
        result = loader.get_args(grid, source_args)
        assert result == MultiDict([('dgreset', 1)])

    def test_reset_with_session_key(self):
        source_args = MultiDict([('foo', 'bar'), ('baz', 'bin'), ('dgreset', '1'),
                                 ('session_key', '123')])
        grid = PeopleGrid()
        loader = RequestArgsLoader(grid.manager)
        result = loader.get_args(grid, source_args)
        assert result == MultiDict([('dgreset', 1), ('session_key', '123')])


class TestWebSessionArgsLoader:
    @inrequest('/foo')
    def test_no_session_present(self):
        source_args = MultiDict([('foo', 'bar'), ('baz', 'bin')])
        source_args_copy = source_args.copy()
        grid = PeopleGrid()
        loader = WebSessionArgsLoader(grid.manager)
        result = loader.get_args(grid, source_args)
        assert source_args == source_args_copy
        assert result == MultiDict([
            ('foo', 'bar'),
            ('baz', 'bin'),
            ('__foreign_session_loaded__', False),
        ])

    @inrequest('/foo')
    def test_empty_session_not_stored(self):
        source_args = MultiDict([])
        grid = PeopleGrid()
        loader = WebSessionArgsLoader(grid.manager)
        loader.get_args(grid, source_args)
        assert '_PeopleGrid' not in flask.session['dgsessions']
        assert grid.session_key not in flask.session['dgsessions']

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob')
    def test_matching_session_not_stored(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        pg2 = PeopleGrid()
        loader.get_args(pg2, flask.request.args)
        assert '_PeopleGrid' in flask.session['dgsessions']
        assert pg.session_key in flask.session['dgsessions']
        assert pg2.session_key not in flask.session['dgsessions']

    @inrequest('/foo?dgreset=1&op(firstname)=eq&v1(firstname)=bob')
    def test_reset_result(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        args = loader.get_args(pg, flask.request.args)
        assert args == MultiDict([('dgreset', 1), ('session_key', None)])

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_reset_removes_session(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('dgreset', '1'),
        ])
        pg = PeopleGrid()
        loader.get_args(pg, flask.request.args)
        assert '_PeopleGrid' not in flask.session['dgsessions']
        assert pg.session_key not in flask.session['dgsessions']

    @inrequest('/foo')
    def test_session_load_from_none(self):
        # test backwards compatibility for multidict load
        flask.session['dgsessions'] = {}
        grid = PeopleGrid()
        loader = WebSessionArgsLoader(grid.manager)
        args = loader.get_session_store(grid, MultiDict())
        assert args == MultiDict([])

    @inrequest('/foo')
    def test_session_load_from_multidict(self):
        # test backwards compatibility for multidict load
        flask.session['dgsessions'] = {
            '_PeopleGrid': MultiDict([('a', 'b'), ('a', 'c')])
        }
        grid = PeopleGrid()
        loader = WebSessionArgsLoader(grid.manager)
        args = loader.get_session_store(grid, MultiDict())
        assert args == MultiDict([('a', 'b'), ('a', 'c')])

    @inrequest('/foo')
    def test_session_load_from_dict(self):
        # test backwards compatibility for dict load
        flask.session['dgsessions'] = {
            '_PeopleGrid': {'a': 'b', 'c': 'd'}
        }
        grid = PeopleGrid()
        loader = WebSessionArgsLoader(grid.manager)
        args = loader.get_session_store(grid, MultiDict())
        assert args == MultiDict([('a', 'b'), ('c', 'd')])

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_default_session(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        pg2 = PeopleGrid()
        loader = WebSessionArgsLoader(pg2.manager)
        args = loader.get_args(pg2, MultiDict())
        assert args['op(firstname)'] == 'eq'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_keyed_session(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args['op(firstname)'] = '!eq'
        pg2 = PeopleGrid()
        args = loader.get_args(pg2, flask.request.args)
        assert args['op(firstname)'] == '!eq'
        flask.request.args = MultiDict([('session_key', pg.session_key)])
        pg = PeopleGrid()
        args = loader.get_args(pg, flask.request.args)
        assert args['op(firstname)'] == 'eq'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100&sort1=foo')
    def test_page_args_always_applied(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('perpage', '15'),
            ('onpage', '100'),
        ])
        pg = PeopleGrid()
        args = loader.get_args(pg, flask.request.args)
        assert args['op(firstname)'] == 'eq'
        assert args['perpage'] == '15'
        assert args['onpage'] == '100'
        assert args['sort1'] == 'foo'
        assert '["perpage", "15"]' in flask.session['dgsessions'][pg.session_key]

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100&sort1=foo')
    def test_sort_args_always_applied(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('sort1', 'bar'),
        ])
        pg = PeopleGrid()
        args = loader.get_args(pg, flask.request.args)
        assert args['op(firstname)'] == 'eq'
        assert args['perpage'] == '1'
        assert args['sort1'] == 'bar'
        assert '["sort1", "bar"]' in flask.session['dgsessions'][pg.session_key]

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_keyed_session_with_export(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args['op(firstname)'] = '!eq'
        pg2 = PeopleGrid()
        args = loader.get_args(pg2, flask.request.args)
        assert args['op(firstname)'] == '!eq'
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('export_to', 'xls'),
        ])
        pg = PeopleGrid()
        args = loader.get_args(pg, flask.request.args)
        assert args['op(firstname)'] == 'eq'
        assert args['export_to'] == 'xls'
        assert 'export_to' not in flask.session['dgsessions'][pg.session_key]

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_keyed_session_with_override(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('session_override', 1),
            ('op(createdts)', '!eq'),
            ('v1(createdts)', '2017-05-06'),
        ])
        pg2 = PeopleGrid()
        args = loader.get_args(pg2, flask.request.args)
        assert args['op(firstname)'] == 'eq'
        assert args['v1(firstname)'] == 'bob'
        assert args['op(createdts)'] == '!eq'
        assert args['v1(createdts)'] == '2017-05-06'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_keyed_session_without_override(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('op(createdts)', '!eq'),
            ('v1(createdts)', '2017-05-06'),
        ])
        pg2 = PeopleGrid()
        args = loader.get_args(pg2, flask.request.args)
        assert 'op(firstname)' not in args
        assert 'v1(firstname)' not in args
        assert args['op(createdts)'] == '!eq'
        assert args['v1(createdts)'] == '2017-05-06'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_apply_prevents_session_load(self):
        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, flask.request.args)
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('apply', None),
        ])
        pg2 = PeopleGrid()
        args = loader.get_args(pg2, flask.request.args)
        assert 'op(firstname)' not in args
        assert 'v1(firstname)' not in args
        assert 'apply' not in flask.session['dgsessions'][pg.session_key]

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_expired_session_cleaned_up(self):
        with mock.patch(
            'webgrid.extensions.arrow.utcnow',
            lambda *args: arrow.get('2021-01-05 15:14:13')
        ):
            pg = PeopleGrid()
            loader = WebSessionArgsLoader(pg.manager)
            loader.get_args(pg, flask.request.args)

        assert '_PeopleGrid' in flask.session['dgsessions']
        assert pg.session_key in flask.session['dgsessions']

        with mock.patch(
            'webgrid.extensions.arrow.utcnow',
            lambda *args: arrow.get('2021-01-06 03:14:15')
        ):
            pg = PeopleGrid()
            loader = WebSessionArgsLoader(pg.manager)
            loader.get_args(pg, MultiDict([]))

        assert '_PeopleGrid' not in flask.session['dgsessions']
        assert pg.session_key not in flask.session['dgsessions']

    @inrequest('/foo')
    def test_expired_session_no_stamp(self):
        flask.session['dgsessions'] = {
            '_PeopleGrid': MultiDict([('a', 'b'), ('a', 'c')])
        }

        pg = PeopleGrid()
        loader = WebSessionArgsLoader(pg.manager)
        loader.cleanup_expired_sessions()
        assert flask.session['dgsessions']['_PeopleGrid'] == MultiDict([('a', 'b'), ('a', 'c')])

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_expired_session_no_max_hours(self):
        with mock.patch(
            'webgrid.extensions.arrow.utcnow',
            lambda *args: arrow.get('2021-01-05 15:14:13')
        ):
            pg = PeopleGrid()
            loader = WebSessionArgsLoader(pg.manager)
            loader.get_args(pg, flask.request.args)

        assert '_PeopleGrid' in flask.session['dgsessions']
        assert pg.session_key in flask.session['dgsessions']

        pg = PeopleGrid()
        pg.manager.session_max_hours = None
        loader = WebSessionArgsLoader(pg.manager)
        loader.get_args(pg, MultiDict([]))

        assert '_PeopleGrid' in flask.session['dgsessions']
