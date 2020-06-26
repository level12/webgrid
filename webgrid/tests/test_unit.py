from __future__ import absolute_import

import re
from datetime import datetime
from decimal import Decimal
from os import path

import flask
import pytest
from mock import mock
import sqlalchemy.sql as sasql
from werkzeug.datastructures import MultiDict

from webgrid import Column, BoolColumn, YesNoColumn
from webgrid.filters import FilterBase, TextFilter, IntFilter
from webgrid_ta.model.entities import Person, Status, db
from webgrid_ta.grids import Grid, PeopleGrid, PeopleGridByConfig
from .helpers import assert_in_query, assert_not_in_query, query_to_str, inrequest
from webgrid.renderers import CSV


class TestGrid(object):
    class TG(Grid):
        Column('First Name', Person.firstname)

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
        assert_not_in_query(query, 'ORDER BY')
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
        assert_in_query(g, "WHERE upper(persons.last_name) = upper('foo')")

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
        assert_in_query(g, 'ORDER BY persons.firstname, persons.last_name\n')
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
        assert_in_query(g, 'LIMIT 50 OFFSET 0')

        g.set_paging(2, 1)
        assert_in_query(g, 'LIMIT 2 OFFSET 0')

        g.set_paging(10, 5)
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
        search_where = ("WHERE lower(persons.firstname) LIKE lower('%foo%')"
                        " OR lower(persons.last_name) LIKE lower('%foo%')")
        assert_in_query(g, search_where)


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

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=fn001&op(status)=is&v1(status)=1&v1(status)=2')
    def test_qs_filtering(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.columns[0].filter.op == 'eq'
        assert pg.columns[0].filter.value1 == 'fn001'
        assert pg.columns[0].filter.value2 is None

        assert pg.columns[4].filter.op == 'is'
        assert pg.columns[4].filter.value1 == [1, 2]
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
    def test_qs_default_session(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        flask.request.args = MultiDict()
        pg2 = PeopleGrid()
        pg2.apply_qs_args()
        assert pg2.column('firstname').filter.op == 'eq'
        assert '_PeopleGrid' in flask.session['dgsessions']
        assert pg.session_key in flask.session['dgsessions']
        assert pg2.session_key in flask.session['dgsessions']

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

    @inrequest('/foo')
    def test_session_load_from_none(self):
        # test backwards compatibility for multidict load
        flask.session['dgsessions'] = {}
        pg = PeopleGrid()
        args = pg.get_session_store(MultiDict())
        assert args == MultiDict([])

    @inrequest('/foo')
    def test_session_load_from_multidict(self):
        # test backwards compatibility for multidict load
        flask.session['dgsessions'] = {
            '_PeopleGrid': MultiDict([('a', 'b'), ('a', 'c')])
        }
        pg = PeopleGrid()
        args = pg.get_session_store(MultiDict())
        assert args == MultiDict([('a', 'b'), ('a', 'c')])

    @inrequest('/foo')
    def test_session_load_from_dict(self):
        # test backwards compatibility for dict load
        flask.session['dgsessions'] = {
            '_PeopleGrid': {'a': 'b', 'c': 'd'}
        }
        pg = PeopleGrid()
        args = pg.get_session_store(MultiDict())
        assert args == MultiDict([('a', 'b'), ('c', 'd')])

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_qs_keyed_session_with_export(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        flask.request.args['op(firstname)'] = '!eq'
        pg2 = PeopleGrid()
        pg2.apply_qs_args()
        assert pg2.column('firstname').filter.op == '!eq'
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('export_to', 'xls'),
        ])
        pg = PeopleGrid()
        pg.apply_qs_args()
        assert pg.column('firstname').filter.op == 'eq'

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_qs_keyed_session_with_override(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('session_override', 1),
            ('op(createdts)', '!eq'),
            ('v1(createdts)', '2017-05-06'),
        ])
        pg2 = PeopleGrid()
        pg2.apply_qs_args()
        assert pg2.column('firstname').filter.op == 'eq'
        assert pg2.column('firstname').filter.value1 == 'bob'
        assert pg2.column('createdts').filter.op == '!eq'
        assert pg2.column('createdts').filter.value1 == datetime(2017, 5, 6)

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_qs_keyed_session_without_override(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('op(createdts)', '!eq'),
            ('v1(createdts)', '2017-05-06'),
        ])
        pg2 = PeopleGrid()
        pg2.apply_qs_args()
        assert not pg2.column('firstname').filter.op
        assert not pg2.column('firstname').filter.value1
        assert pg2.column('createdts').filter.op == '!eq'
        assert pg2.column('createdts').filter.value1 == datetime(2017, 5, 6)

    @inrequest('/foo?op(firstname)=eq&v1(firstname)=bob&perpage=1&onpage=100')
    def test_qs_apply_prevents_session_load(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        flask.request.args = MultiDict([
            ('session_key', pg.session_key),
            ('apply', None),
        ])
        pg2 = PeopleGrid()
        pg2.apply_qs_args()
        assert not pg2.column('firstname').filter.op
        assert not pg2.column('firstname').filter.value1

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
            firstname = Column('First Name')
            legacycol1 = Column('LC1')
            legacycol2 = Column('LC2')

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
