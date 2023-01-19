from __future__ import absolute_import
import datetime as dt
from decimal import Decimal as D

from blazeutils.containers import HTMLAttributes
import pytest

from webgrid import (
    Column,
    LinkColumnBase,
    BoolColumn,
    YesNoColumn,
    DateTimeColumn,
    DateColumn,
    NumericColumn,
)
from webgrid.filters import DateFilter, IntFilter, TextFilter

from webgrid_ta.grids import Grid
from webgrid_ta.model.entities import Person


class FirstNameColumn(LinkColumnBase):
    def create_url(self, record):
        return '/person-edit/{0}'.format(record.id)


class FullNameColumn(LinkColumnBase):
    def extract_data(self, record):
        return '{0.firstname} {0.lastname}'.format(record)

    def create_url(self, record):
        return '/person-edit/{0}'.format(record.id)


class TestColumn(object):
    def test_attr_copy(self):
        class TG(Grid):
            Column('ID', Person.id, TextFilter, can_sort=False, visible=False)
            FirstNameColumn(
                'First Name',
                Person.firstname,
                TextFilter,
                can_sort=False,
                link_label='hi',
                visible=False,
            )

            # Test filter with no SA column specified, assumes same as Column
            Column(
                'Last Name',
                Person.lastname,
                TextFilter(default_op='contains'),
                can_sort=False,
                visible=False,
            )

            YesNoColumn(
                'Active',
                Person.inactive,
                TextFilter,
                can_sort=False,
                reverse=True,
                visible=False,
            )
            # DateColumn & DateTime Column are just subclasses of DateColumnBase
            # so we don't need to explicitly test both
            DateTimeColumn(
                'Created',
                Person.createdts,
                DateFilter,
                can_sort=False,
                html_format='foo',
                visible=False,
            )
            NumericColumn('Address', Person.address, IntFilter, can_sort=False, visible=False)

        g = TG()

        col = g.columns[0]
        assert col.key == 'id'
        assert col.expr is Person.id
        assert isinstance(col.filter, TextFilter)
        assert col.can_sort is False
        assert col.visible is False

        col = g.columns[1]
        assert col.key == 'firstname'
        assert col.expr is Person.firstname
        assert isinstance(col.filter, TextFilter)
        assert col.can_sort is False
        assert col.link_label == 'hi'
        assert col.visible is False

        col = g.columns[2]
        assert col.key == 'lastname'
        assert col.expr is Person.lastname
        assert isinstance(col.filter, TextFilter)
        assert col.can_sort is False
        assert col.visible is False

        col = g.columns[3]
        assert col.key == 'inactive'
        assert col.expr is Person.inactive
        assert isinstance(col.filter, TextFilter)
        assert col.can_sort is False
        assert col.reverse is True
        assert col.true_label == 'Yes'
        assert col.false_label == 'No'
        assert col.visible is False

        col = g.columns[4]
        assert col.key == 'createdts'
        assert col.expr is Person.createdts
        assert isinstance(col.filter, DateFilter)
        assert col.can_sort is False
        assert col.html_format == 'foo'
        assert col.visible is False

        col = g.columns[5]
        assert col.key == 'address'
        assert col.expr is Person.address
        assert isinstance(col.filter, IntFilter)
        assert col.can_sort is False
        assert col.visible is False

    def test_nonkeyed_not_sort(self):
        class TG(Grid):
            FullNameColumn('Full Name')

        g = TG()
        col = g.columns[0]
        assert col.can_sort is False

    def test_filter_without_column_key(self):
        with pytest.raises(ValueError, match='no column-like object is available'):

            class TG(Grid):
                Column('ID', 'id', TextFilter)

            TG()

    def test_filter_of_wrong_type(self):
        with pytest.raises(ValueError, match=r'expected.+column-like object'):

            class TG(Grid):
                Column('ID', Person, TextFilter)

            TG()

    def test_filters_are_new_instances(self):
        tf = TextFilter

        class TG(Grid):
            Column('Name', Person.firstname, tf)

        g = TG()
        g2 = TG()
        col = g.columns[0]
        col2 = g2.columns[0]
        assert isinstance(col.filter, TextFilter)
        assert col is not col2
        assert col.filter is not tf
        assert col.filter is not col2.filter
        assert g.filtered_cols['firstname'] is col

    def test_xls_width_calc(self):
        class C3(Column):
            xls_width = 15

        class TG(Grid):
            Column('C1', Person.firstname)
            Column('C2', Person.lastname, xls_width=10)
            C3('C3', Person.state)
            DateColumn('Date', Person.due_date)

        g = TG()

        value = '12345'
        assert g.columns[0].xls_width_calc(value) == 5
        assert g.columns[1].xls_width_calc(value) == 10
        assert g.columns[2].xls_width_calc(value) == 15

        value = '123456'
        assert g.columns[0].xls_width_calc(value) == 6

        value = 123
        assert g.columns[0].xls_width_calc(value) == 3

        value = 123.333
        assert g.columns[0].xls_width_calc(value) == 7

        value = dt.date(2012, 1, 1)
        assert g.columns[3].xls_width_calc(value) == 10

    def test_xls_width_setting(self):
        class LinkColumn(LinkColumnBase):
            pass

        class TG(Grid):
            Column('C1', Person.firstname, xls_width=1)
            LinkColumn('C2', Person.lastname, xls_width=1)
            BoolColumn('C3', Person.inactive, xls_width=1)
            YesNoColumn('C4', Person.inactive.label('yesno'), xls_width=1)
            DateColumn('Date', Person.due_date, xls_width=1)
            DateColumn('DateTime', Person.createdts, xls_width=1)

        g = TG()

        assert g.columns[0].xls_width_calc('123') == 1
        assert g.columns[1].xls_width_calc('123') == 1
        assert g.columns[2].xls_width_calc('123') == 1
        assert g.columns[3].xls_width_calc('123') == 1
        assert g.columns[4].xls_width_calc(dt.date(2012, 1, 1)) == 1
        assert g.columns[5].xls_width_calc(dt.date(2012, 1, 1)) == 1

    def test_xls_number_format_setting(self):
        class LinkColumn(LinkColumnBase):
            pass

        class TG(Grid):
            Column('C1', Person.firstname, xls_num_format='General')
            LinkColumn('C2', Person.lastname, xls_num_format='General')
            BoolColumn('C3', Person.inactive, xls_num_format='General')
            YesNoColumn('C4', Person.inactive.label('yesno'), xls_num_format='General')
            DateColumn('Date', Person.due_date, xls_num_format='General')
            DateColumn('DateTime', Person.createdts)

        g = TG()

        assert g.columns[0].xls_num_format == 'General'
        assert g.columns[1].xls_num_format == 'General'
        assert g.columns[2].xls_num_format == 'General'
        assert g.columns[3].xls_num_format == 'General'
        assert g.columns[4].xls_num_format == 'General'
        # should pull from the class if not given when instantiating
        assert g.columns[5].xls_num_format == 'm/dd/yyyy'

    def test_render_in_setting(self):
        class LinkColumn(LinkColumnBase):
            pass

        class TG(Grid):
            c6_render_in = 'csv'

            Column('C1', Person.firstname)
            Column('C1.5', Person.firstname.label('fn2'), render_in=None)
            LinkColumn('C2', Person.lastname, render_in='xlsx')
            BoolColumn('C3', Person.inactive, render_in=('xlsx', 'html'))
            YesNoColumn('C4', Person.inactive.label('yesno'), render_in='xlsx')
            DateColumn('Date', Person.due_date, render_in='xlsx')
            DateColumn('DateTime', Person.createdts, render_in='xlsx')
            BoolColumn('C5', Person.inactive, render_in=['xlsx', 'html'])
            Column(
                'C6',
                Person.firstname.label('fn3'),
                render_in=lambda self: self.grid.c6_render_in,
            )
            Column(
                'C7',
                Person.firstname.label('fn4'),
                render_in=lambda self: self.grid.c7_render_in(),
            )

            def c7_render_in(self):
                return [self.c6_render_in, 'xlsx']

        g = TG()

        assert g.columns[0].render_in == ('html', 'xlsx', 'csv', 'json')
        assert g.columns[1].render_in == tuple()
        assert g.columns[2].render_in == ('xlsx',)
        assert g.columns[3].render_in == ('xlsx', 'html')
        assert g.columns[4].render_in == ('xlsx',)
        assert g.columns[5].render_in == ('xlsx',)
        assert g.columns[6].render_in == ('xlsx',)
        assert g.columns[7].render_in == ('xlsx', 'html')
        assert g.columns[8].render_in == ('csv',)
        assert g.columns[9].render_in == ('csv', 'xlsx')

    def test_visible_setting(self):
        class TestGrid(Grid):
            c3_visible = False
            Column('C1', Person.firstname)
            Column('C2', Person.firstname.label('fn2'), visible=False)
            Column(
                'C3',
                Person.firstname.label('fn3'),
                visible=lambda self: self.grid.c3_visible,
            )
            Column(
                'C4',
                Person.firstname.label('fn4'),
                visible=lambda self: self.grid.c4_visible(),
            )

            def c4_visible(self):
                return self.c3_visible

        grid = TestGrid()
        assert grid.columns[0].visible is True
        assert grid.columns[1].visible is False
        assert grid.columns[2].visible is False
        assert grid.columns[3].visible is False

        grid.c3_visible = True
        assert grid.columns[2].visible is True
        assert grid.columns[3].visible is True

    def test_number_formatting(self):
        class TG(Grid):
            NumericColumn('C1', Person.numericcol, places=1)

        g = TG()

        c = g.columns[0]
        record = {'numericcol': D('1234.16')}
        assert c.render_html(record, None) == '1,234.2'

        c.format_as = 'accounting'
        assert c.render_html(record, None) == '$1,234.16'

        # accounting with negative value
        record = {'numericcol': D('-1234.16')}
        hah = HTMLAttributes()
        assert c.render_html(record, hah) == '($1,234.16)'
        assert hah['class'] == 'negative'

        record = {'numericcol': D('.1673')}
        c.format_as = 'percent'
        assert c.render_html(record, None) == '16.7%'

    def test_number_formatting_for_excel(self):
        class TG(Grid):
            NumericColumn('C1', Person.numericcol, places=2)

        g = TG()

        c = g.columns[0]
        assert c.xls_construct_format(c.xls_fmt_general) == '#,##0.00;[RED]-#,##0.00'
        assert (
            c.xls_construct_format(c.xls_fmt_accounting)
            == '_($* #,##0.00_);[RED]_($* (#,##0.00);_($* "-"??_);_(@_)'
        )
        assert c.xls_construct_format(c.xls_fmt_percent) == '0.00%;[RED]-0.00%'

        # no red
        c.xls_neg_red = False
        assert c.xls_construct_format(c.xls_fmt_general) == '#,##0.00;-#,##0.00'
        assert (
            c.xls_construct_format(c.xls_fmt_accounting)
            == '_($* #,##0.00_);_($* (#,##0.00);_($* "-"??_);_(@_)'
        )
        assert c.xls_construct_format(c.xls_fmt_percent) == '0.00%;-0.00%'

        # adjust places
        c.places = 0
        assert c.xls_construct_format(c.xls_fmt_general) == '#,##0;-#,##0'
        assert (
            c.xls_construct_format(c.xls_fmt_accounting)
            == '_($* #,##0_);_($* (#,##0);_($* "-"??_);_(@_)'
        )
        assert c.xls_construct_format(c.xls_fmt_percent) == '0%;-0%'

    def test_post_init(self):
        class TG(Grid):
            NumericColumn('C1', Person.numericcol, places=2)

            def post_init(self):
                self.column('numericcol').render_in = 'foo'

        g = TG()
        assert g.column('numericcol').render_in == ('foo',)

    def test_group_attr_error(self):
        with pytest.raises(ValueError, match='expected group to be a subclass of ColumnGroup'):
            Column('label', Person.id, group='not a ColumnGroup')
