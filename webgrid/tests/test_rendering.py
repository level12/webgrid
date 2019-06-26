from __future__ import absolute_import

import datetime as dt
import json
import warnings
from io import BytesIO
import six

import arrow
from nose.tools import eq_, raises
from six.moves import range
import xlrd
import csv
import xlsxwriter

from webgrid import (
    Column,
    LinkColumnBase,
    YesNoColumn,
    BoolColumn,
    row_styler,
    col_filter,
    col_styler,
    NumericColumn,
)
from webgrid.filters import TextFilter
from webgrid.renderers import RenderLimitExceeded, HTML, XLS, XLSX, CSV
from webgrid_ta.model.entities import ArrowRecord, Person, Status, Email, db, AccountType

from webgrid_ta.grids import ArrowGrid, Grid, PeopleGrid as PG, ArrowCSVGrid
from .helpers import inrequest, eq_html


class PeopleGrid(PG):
    def query_prep(self, query, has_sort, has_filters):
        query = PG.query_prep(self, query, True, True)

        # default sort
        if not has_sort:
            query = query.order_by(Person.id.desc())

        # default filter
        if not has_filters:
            query = query.filter(Person.id != 3)

        return query


class PeopleCSVGrid(PG):
    allowed_export_targets = {'csv': CSV}

    def query_prep(self, query, has_sort, has_filters):
        query = PG.query_prep(self, query, True, True)

        # default sort
        if not has_sort:
            query = query.order_by(Person.id.desc())

        # default filter
        if not has_filters:
            query = query.filter(Person.id != 3)

        return query


def setup_module():
    Status.delete_cascaded()
    sp = Status(label='pending')
    sip = Status(label='in process')
    sc = Status(label='complete', flag_closed=1)
    db.session.add_all([sp, sip, sc])

    for x in range(1, 5):
        p = Person()
        p.firstname = 'fn%03d' % x
        p.lastname = 'ln%03d' % x
        p.sortorder = x
        p.numericcol = '2.13'
        p.state = 'st%03d' % x
        if x != 2:
            p.createdts = dt.datetime(2012, 0o2, 22, 10, x, 16)
            p.due_date = dt.date(2012, 0o2, x)
        db.session.add(p)
        p.emails.append(Email(email='email%03d@example.com' % x))
        p.emails.append(Email(email='email%03d@gmail.com' % x))
        if x % 4 == 1:
            p.status = sip
            p.account_type = AccountType.admin
        elif x % 4 == 2:
            p.status = sp
            p.account_type = AccountType.employee
        elif x % 4 == 0:
            p.status = None

    db.session.commit()


class SimpleGrid(Grid):
    on_page = 1
    per_page = 1

    Column('ID', 'id')
    Column('Name', 'name', filter=TextFilter(Person.firstname))
    Column('Status', 'status')
    Column('Emails', 'emails', can_sort=False)


class ColorColumn(Column):
    def format_data(self, data):
        if data == 'blue':
            return 'blue :)'
        return data


class EditColumn(LinkColumnBase):
    link_attrs = {'target': '_blank'}

    def create_url(self, record):
        return '/vehicle-edit/{0}'.format(record['id'])


class DealerColumn(LinkColumnBase):
    def create_url(self, record):
        return '/dealer-edit/{0}'.format(record['dealer_id'])

    def extract_data(self, record):
        return record['dealer'] + record['dealer_id']


class CarGrid(Grid):
    EditColumn('ID', 'id')
    EditColumn('Edit', 'edit', link_label='edit')
    DealerColumn('Dealer', 'dealer')
    Column('Make', 'make')
    Column('Model', 'model', class_='model')
    ColorColumn('Color', 'color')
    BoolColumn('Active', 'active')
    BoolColumn('Active Reverse', 'active', reverse=True)
    YesNoColumn('Active Yes/No', 'active')

    @row_styler
    def style_row(self, rownum, attrs, record):
        attrs.id = 'tr_{0}'.format(record['id'])

    @col_styler('model')
    def highlight_1500(self, attrs, record):
        if record['model'] == '1500':
            attrs.class_ += 'red'

    @col_filter('color')
    def pink_is_ugly(self, value):
        if value == 'pink':
            return 'pink :('
        return value


class TestHtmlRenderer(object):
    key_data = (
        {'id': 1, 'name': 'one'},
        {'id': 2, 'name': 'two'},
        {'id': 3, 'name': 'three'},
        {'id': 4, 'name': 'three'},
        {'id': 5, 'name': 'three'},
    )

    @inrequest('/')
    def test_car_html(self):
        key_data = (
            {'id': 1, 'make': 'ford', 'model': 'F150&', 'color': 'pink',
             'dealer': 'bob', 'dealer_id': '7', 'active': True},
            {'id': 2, 'make': 'chevy', 'model': '1500', 'color': 'blue',
             'dealer': 'fred', 'dealer_id': '9', 'active': False},
        )

        mg = CarGrid()
        mg.set_records(key_data)
        eq_html(mg.html.table(), 'basic_table.html')

    @inrequest('/')
    def test_people_html(self):
        pg = PeopleGrid()
        eq_html(pg.html.table(), 'people_table.html')

    @inrequest('/')
    def test_default_jinja_env(self):
        class TGrid(Grid):
            manager = None
            hide_controls_box = True
            session_on = False
            allowed_export_targets = None

            Column('ID', 'id', can_sort=False)
            Column('Value', 'value', can_sort=False)

        tg = TGrid()
        tg.set_records([
            {'id': 1, 'value': 'foo'},
        ])
        tg.html()

    @inrequest('/')
    def test_no_filters(self):
        class TGrid(Grid):
            Column('Test', Person.id)

        tg = TGrid()
        assert 'Add Filter' not in tg.html()

    @inrequest('/')
    def test_hide_excel_deprecated(self):
        class TGrid(Grid):
            hide_excel_link = True
            Column('Test', Person.id)
        with warnings.catch_warnings(record=True) as warn:
            warnings.simplefilter("always")
            TGrid()
        eq_(warn[0].category, DeprecationWarning)
        eq_(
            str(warn[0].message),
            "Hide excel link is deprecated, you should just override allowed_export_targets instead" # noqa
        )

    def get_grid(self, **kwargs):
        g = SimpleGrid(**kwargs)
        g.set_records(self.key_data)
        g.apply_qs_args()
        return g

    @inrequest('/thepage?perpage=5&onpage=1')
    def test_current_url(self):
        g = self.get_grid()
        eq_('/thepage?onpage=1&perpage=5', g.html.current_url())
        eq_('/thepage?onpage=1&perpage=10', g.html.current_url(perpage=10))

    @inrequest('/thepage')
    def test_current_url_qs_prefix(self):
        g = self.get_grid(qs_prefix='dg_')
        eq_('/thepage?dg_perpage=10', g.html.current_url(perpage=10))

    @inrequest('/thepage?perpage=5&onpage=1')
    def test_xls_url(self):
        g = self.get_grid()
        with warnings.catch_warnings(record=True) as warn:
            warnings.simplefilter("always")
            url = g.html.xls_url()
        eq_(url, '/thepage?export_to=xls&onpage=1&perpage=5')
        eq_(len(warn), 1)
        eq_(warn[0].category, DeprecationWarning)
        eq_(str(warn[0].message), 'xls_url is deprecated. Use export_url instead.')

    @inrequest('/thepage?perpage=5&onpage=1')
    def test_export_url(self):
        g = self.get_grid()
        eq_(g.html.export_url('xlsx'), '/thepage?export_to=xlsx&onpage=1&perpage=5')
        eq_(g.html.export_url('xls'), '/thepage?export_to=xls&onpage=1&perpage=5')
        eq_(g.html.export_url('csv'), '/thepage?export_to=csv&onpage=1&perpage=5')

    @inrequest('/thepage?onpage=3')
    def test_paging_url_first(self):
        g = self.get_grid()
        eq_('/thepage?onpage=1&perpage=1', g.html.paging_url_first())

    @inrequest('/thepage?onpage=3')
    def test_paging_url_next(self):
        g = self.get_grid()
        eq_('/thepage?onpage=4&perpage=1', g.html.paging_url_next())

    @inrequest('/thepage?onpage=3')
    def test_paging_url_prev(self):
        g = self.get_grid()
        eq_('/thepage?onpage=2&perpage=1', g.html.paging_url_prev())

    @inrequest('/thepage?onpage=3')
    def test_paging_url_last(self):
        g = self.get_grid()
        eq_('/thepage?onpage=5&perpage=1', g.html.paging_url_last())

    @inrequest('/thepage?foo=bar&onpage=5&perpage=10&sort1=1&sort2=2&sort3=3&op(name)=eq&v1(name)'
               '=bob&v2(name)=fred')
    def test_reset_url(self):
        g = self.get_grid()
        eq_(
            '/thepage?dgreset=1&foo=bar&session_key={0}'.format(g.session_key),
            g.html.reset_url()
        )

    @inrequest('/thepage?foo=bar&onpage=5')
    def test_form_action_url(self):
        g = self.get_grid()
        eq_(
            '/thepage?foo=bar&session_key={0}'.format(g.session_key),
            g.html.form_action_url()
        )

    @inrequest('/thepage?onpage=2')
    def test_paging_html(self):
        g = self.get_grid()

        select_html = g.html.paging_select()
        assert '<select' in select_html
        assert 'name="onpage"' in select_html
        assert '<option value="1">1 of 5</option>' in select_html
        assert '<option selected="selected" value="2">2 of 5</option>' in select_html, select_html
        assert '<option value="5">5 of 5</option>' in select_html

        input_html = g.html.paging_input()
        eq_(input_html, '<input name="perpage" type="text" value="1" />')

        img_html = g.html.paging_img_first()
        eq_(img_html,
            '<img alt="&lt;&lt;" height="13" src="/static/webgrid/b_firstpage.png" width="16" />')

        img_html = g.html.paging_img_first_dead()
        eq_(img_html,
            '<img alt="&lt;&lt;" height="13" src="/static/webgrid/bd_firstpage.png" width="16" />')

        img_html = g.html.paging_img_prev()
        eq_(img_html,
            '<img alt="&lt;" height="13" src="/static/webgrid/b_prevpage.png" width="8" />')

        img_html = g.html.paging_img_prev_dead()
        eq_(img_html,
            '<img alt="&lt;" height="13" src="/static/webgrid/bd_prevpage.png" width="8" />')

        img_html = g.html.paging_img_next()
        eq_(img_html,
            '<img alt="&gt;" height="13" src="/static/webgrid/b_nextpage.png" width="8" />')

        img_html = g.html.paging_img_next_dead()
        eq_(img_html,
            '<img alt="&gt;" height="13" src="/static/webgrid/bd_nextpage.png" width="8" />')

        img_html = g.html.paging_img_last()
        eq_(img_html,
            '<img alt="&gt;&gt;" height="13" src="/static/webgrid/b_lastpage.png" width="16" />')

        img_html = g.html.paging_img_last_dead()
        eq_(img_html,
            '<img alt="&gt;&gt;" height="13" src="/static/webgrid/bd_lastpage.png" width="16" />')

        # since we are on page 2, all links should be live
        footer_html = g.html.footer()
        assert g.html.paging_img_first() in footer_html
        assert g.html.paging_img_next() in footer_html
        assert g.html.paging_img_prev() in footer_html
        assert g.html.paging_img_last() in footer_html

        g.set_paging(1, 1)
        g.set_records(self.key_data)
        footer_html = g.html.footer()
        assert g.html.paging_img_first() not in footer_html, footer_html
        assert g.html.paging_img_first_dead() in footer_html
        assert g.html.paging_img_prev_dead() in footer_html

        g.set_paging(2, 3)
        g.set_records(self.key_data)
        footer_html = g.html.footer()
        assert g.html.paging_img_last() not in footer_html, footer_html
        assert g.html.paging_img_next_dead() in footer_html
        assert g.html.paging_img_last_dead() in footer_html

    @inrequest('/thepage?sort1=name&sort2=-id')
    def test_sorting_html(self):
        g = self.get_grid()

        select_html = g.html.sorting_select1()
        assert '<select id="sort1" name="sort1">' in select_html
        assert '<option value="">&nbsp;</option>' in select_html, select_html
        assert '<option selected="selected" value="name">Name</option>' in select_html
        assert '<option value="-name">Name DESC</option>' in select_html
        assert '<option value="id">ID</option>' in select_html
        assert '<option value="emails">Emails</option>' not in select_html

        select_html = g.html.sorting_select2()
        assert '<option selected="selected" value="name">Name</option>' not in select_html
        assert '<option selected="selected" value="-id">ID DESC</option>' in select_html

        select_html = g.html.sorting_select3()
        assert '<option selected="selected" value="">&nbsp;</option>' in select_html

        heading_row = g.html.table_column_headings()
        assert 'sort-asc' not in heading_row
        assert 'sort-desc' not in heading_row

    @inrequest('/thepage?sort1=name')
    def test_sorting_headers_asc(self):
        g = self.get_grid()
        heading_row = g.html.table_column_headings()
        assert '<th><a class="sort-asc" href="/thepage?sort1=-name">Name</a></th>' in heading_row

    @inrequest('/thepage?sort1=-name')
    def test_sorting_headers_desc(self):
        g = self.get_grid()
        heading_row = g.html.table_column_headings()
        assert '<th><a class="sort-desc" href="/thepage?sort1=name">Name</a></th>' in heading_row

    @inrequest('/thepage?op(firstname)=eq&v1(firstname)=foo&op(createdts)=between&v1(createdts)='
               '2%2F15%2F12&&v2(createdts)=2012-02-16')
    def test_filtering_input_html(self):
        g = PeopleGrid()

        filter_html = g.html.filtering_col_inputs1(g.key_column_map['firstname'])
        assert '<input id="firstname_input1" name="v1(firstname)" type="text" />' in filter_html, \
            filter_html

        filter_html = g.html.filtering_col_inputs1(g.key_column_map['createdts'])
        assert '<input id="createdts_input1" name="v1(createdts)" type="text" />' in filter_html, \
            filter_html

        filter_html = g.html.filtering_col_inputs2(g.key_column_map['createdts'])
        assert '<input id="createdts_input2" name="v2(createdts)" type="text" />' in filter_html, \
            filter_html

        g.apply_qs_args()

        filter_html = g.html.filtering_col_inputs1(g.key_column_map['firstname'])
        assert '<input id="firstname_input1" name="v1(firstname)" type="text" value="foo" />' in \
            filter_html, filter_html

        filter_html = g.html.filtering_col_inputs1(g.key_column_map['createdts'])
        assert '<input id="createdts_input1" name="v1(createdts)" type="text" value=' + \
            '"02/15/2012 12:00 AM" />' in filter_html, filter_html

        filter_html = g.html.filtering_col_inputs2(g.key_column_map['createdts'])
        assert '<input id="createdts_input2" name="v2(createdts)" type="text" value=' + \
            '"02/16/2012 11:59 PM" />' in filter_html, filter_html

    @inrequest('/thepage?op(firstname)=foobar&v1(firstname)=baz')
    def test_filtering_invalid_operator(self):
        g = PeopleGrid()

        filter_html = g.html.filtering_col_inputs1(g.key_column_map['firstname'])
        assert '<input id="firstname_input1" name="v1(firstname)" type="text" />' in filter_html, \
            filter_html

    @inrequest('/thepage')
    def test_extra_filter_attrs(self):
        g = PeopleGrid()
        g.key_column_map['firstname'].filter.html_extra = {'data-special-attr': 'foo'}
        filter_html = g.html.filtering_table_row(g.key_column_map['firstname'])
        assert '<tr class="firstname_filter" data-special-attr="foo">' in filter_html, filter_html

    @inrequest('/thepage')
    def test_confirm_export(self):
        g = PeopleGrid()
        eq_(json.loads(g.html.confirm_export()), {'confirm_export': False, 'record_count': 3})

        g.unconfirmed_export_limit = 2
        eq_(json.loads(g.html.confirm_export()), {'confirm_export': True, 'record_count': 3})

        g.unconfirmed_export_limit = None
        eq_(json.loads(g.html.confirm_export()), {'confirm_export': False, 'record_count': 3})

    @inrequest('/thepage')
    def test_grid_rendering(self):
        g = PeopleGrid()
        # really just making sure no exceptions come through at this point
        assert g.html()

    @inrequest('/thepage')
    def test_no_records(self):
        g = PeopleGrid()
        g.set_records([])
        g.html
        assert '<p class="no-records">No records to display</p>' in g.html()

    @inrequest('/thepage')
    def test_no_pager(self):
        class PgNP(PeopleGrid):
            pager_on = False

        g = PgNP()
        assert '<td class="page">' not in g.html()
        assert '<td class="perpage">' not in g.html()
        assert '<th class="page">' not in g.html()
        assert '<th class="perpage">' not in g.html()

    def test_can_render(self):
        assert PeopleGrid().html.can_render() is True

    @raises(RenderLimitExceeded)
    def test_render_error(self):
        class Renderer(HTML):
            def can_render(self):
                return False

        class TestGrid(PeopleGrid):
            def set_renderers(self):
                super(TestGrid, self).set_renderers()
                self.html = Renderer(self)

        TestGrid().html()


class PGPageTotals(PeopleGrid):
    subtotals = 'page'


class TestPageTotals(object):
    @inrequest('/')
    def test_people_html(self):
        g = PGPageTotals()
        g.html
        assert '<td class="totals-label" colspan="7">Page Totals (3 records):</td>' in g.html()
        assert '<td class="totals-label" colspan="7">Grand Totals (3 records):</td>' not in g.html()


class PGGrandTotals(PeopleGrid):
    subtotals = 'grand'


class TestGrandTotals(object):
    @inrequest('/')
    def test_people_html(self):
        g = PGGrandTotals()
        g.html
        assert '<td class="totals-label" colspan="7">Grand Totals (3 records):</td>' in g.html()
        assert '<td class="totals-label" colspan="7">Page Totals (3 records):</td>' not in g.html()


class TestFooterRendersCorrectly(object):
    @inrequest('/')
    def test_people_html_footer(self):
        g = PeopleGrid()
        g.html
        assert '<a class="export-link" href="/?export_to=xlsx">XLSX</a>' in g.html()
        assert '<a class="export-link" href="/?export_to=xls">XLS</a>' in g.html()
        # make sure we are rendering the seperator
        assert '&nbsp;|' in g.html()

    @inrequest('/')
    def test_people_html_footer_only_csv(self):
        g = PeopleCSVGrid()
        g.html
        assert '<a class="export-link" href="/?export_to=xls">XLS</a>' not in g.html()
        assert '<a class="export-link" href="/?export_to=csv">CSV</a>' in g.html()


class PGAllTotals(PeopleGrid):
    subtotals = 'all'


class TestAllTotals(object):
    @inrequest('/')
    def test_people_html(self):
        g = PGAllTotals()
        html = g.html()
        assert '<td class="totals-label" colspan="7">Grand Totals (3 records):</td>' in html
        assert '<td class="totals-label" colspan="7">Page Totals (3 records):</td>' in html


class PGTotalsStringExpr(PeopleGrid):
    subtotals = 'all'
    Column('FloatCol', 'float_col', has_subtotal=True)

    def query_prep(self, query, has_sort, has_filters):
        query = super(PGTotalsStringExpr, self).query_prep(query, has_sort, has_filters)
        return query.add_columns(Person.floatcol.label('float_col'))


class TestStringExprTotals(PeopleGrid):
    @inrequest('/')
    def test_people_html(self):
        g = PGTotalsStringExpr()
        html = g.html()

        assert '<td class="totals-label" colspan="7">Grand Totals (3 records):</td>' in html
        assert '<td class="totals-label" colspan="7">Page Totals (3 records):</td>' in html


class TestXLSRenderer(object):

    def test_some_basics(self):
        g = PeopleGrid(per_page=1)
        buffer = BytesIO()
        wb = g.xls()
        wb.save(buffer)
        buffer.seek(0)

        book = xlrd.open_workbook(file_contents=buffer.getvalue())
        sh = book.sheet_by_name('people_grid')
        # headers
        eq_(sh.cell_value(0, 0), 'First Name')
        eq_(sh.cell_value(0, 7), 'Sort Order')

        # last data row
        eq_(sh.cell_value(3, 0), 'fn001')
        eq_(sh.cell_value(3, 7), 1)
        eq_(sh.nrows, 4)

    def test_subtotals_with_no_records(self):
        g = PGGrandTotals()
        g.column('firstname').filter.op = 'eq'
        g.column('firstname').filter.value1 = 'foobar'
        buffer = six.BytesIO()
        wb = g.xls()
        wb.save(buffer)
        buffer.seek(0)

    def test_long_grid_name(self):
        class PeopleGridWithAReallyReallyLongName(PeopleGrid):
            pass
        g = PeopleGridWithAReallyReallyLongName()
        buffer = BytesIO()
        wb = g.xls()
        wb.save(buffer)
        buffer.seek(0)

        book = xlrd.open_workbook(file_contents=buffer.getvalue())
        book.sheet_by_name('people_grid_with_a_really_r...')

    def test_can_render(self):
        class FakeCountsGrid(PeopleGrid):
            def __init__(self, record_count, col_count, has_subtotals):
                self._num_records = record_count
                self._col_count = col_count
                self.subtotals = 'all' if has_subtotals else 'none'
                super(FakeCountsGrid, self).__init__()

            @property
            def record_count(self):
                return self._num_records

            def iter_columns(self, render_type):
                for _ in range(self._col_count):
                    yield None

        assert FakeCountsGrid(65535, 256, False).xls.can_render() is True
        assert FakeCountsGrid(65536, 256, False).xls.can_render() is False
        assert FakeCountsGrid(65535, 256, True).xls.can_render() is False
        assert FakeCountsGrid(65534, 256, True).xls.can_render() is True
        assert FakeCountsGrid(65535, 257, False).xls.can_render() is False

    @raises(RenderLimitExceeded)
    def test_render_error(self):
        class Renderer(XLS):
            def can_render(self):
                return False

        class TestGrid(PeopleGrid):
            def set_renderers(self):
                super(TestGrid, self).set_renderers()
                self.xls = Renderer(self)

        TestGrid().xls()


class TestXLSXRenderer(object):

    def test_some_basics(self):
        g = PeopleGrid(per_page=1)
        wb = g.xlsx()
        wb.filename.seek(0)

        book = xlrd.open_workbook(file_contents=wb.filename.getvalue())
        sh = book.sheet_by_name('people_grid')
        # headers
        eq_(sh.cell_value(0, 0), 'First Name')
        eq_(sh.cell_value(0, 7), 'State')

        # last data row
        eq_(sh.cell_value(3, 0), 'fn001')
        eq_(sh.cell_value(3, 7), 'st001')
        eq_(sh.nrows, 4)

    def test_subtotals_with_no_records(self):
        g = PGGrandTotals()
        g.column('firstname').filter.op = 'eq'
        g.column('firstname').filter.value1 = 'foobar'
        wb = g.xlsx()
        wb.filename.seek(0)

    def test_long_grid_name(self):
        class PeopleGridWithAReallyReallyLongName(PeopleGrid):
            pass
        g = PeopleGridWithAReallyReallyLongName()
        wb = g.xlsx()
        wb.filename.seek(0)

        book = xlrd.open_workbook(file_contents=wb.filename.getvalue())
        book.sheet_by_name('people_grid_with_a_really_r...')

    def test_totals(self):
        g = PeopleGrid()
        g.subtotals = 'grand'

        wb = g.xlsx()
        wb.filename.seek(0)

        book = xlrd.open_workbook(file_contents=wb.filename.getvalue())
        sheet = book.sheet_by_index(0)
        eq_(sheet.nrows, 5)
        eq_(sheet.cell_value(4, 0), 'Totals (3 records):')
        eq_(sheet.cell_value(4, 8), 6.39)
        assert sheet.merged_cells == [(4, 5, 0, 8)]

    def test_totals_no_merge(self):
        class TestGrid(Grid):
            subtotals = 'all'
            Column('First Name', Person.firstname)
            NumericColumn('Number', Person.numericcol, has_subtotal=True)

        g = TestGrid()
        wb = g.xlsx()
        wb.filename.seek(0)

        book = xlrd.open_workbook(file_contents=wb.filename.getvalue())
        sheet = book.sheet_by_index(0)

        eq_(sheet.nrows, 6)
        eq_(sheet.cell_value(5, 0), 'Totals (4 records):')
        assert sheet.merged_cells == []

    def test_can_render(self):
        class FakeCountsGrid(PeopleGrid):
            def __init__(self, record_count, col_count, has_subtotals):
                self._num_records = record_count
                self._col_count = col_count
                self.subtotals = 'all' if has_subtotals else 'none'
                super(FakeCountsGrid, self).__init__()

            @property
            def record_count(self):
                return self._num_records

            def iter_columns(self, render_type):
                for _ in range(self._col_count):
                    yield None

        assert FakeCountsGrid(1048575, 16384, False).xlsx.can_render() is True
        assert FakeCountsGrid(1048576, 16384, False).xlsx.can_render() is False
        assert FakeCountsGrid(1048575, 16384, True).xlsx.can_render() is False
        assert FakeCountsGrid(1048574, 16384, True).xlsx.can_render() is True
        assert FakeCountsGrid(1048575, 16385, False).xlsx.can_render() is False

    @raises(RenderLimitExceeded)
    def test_render_error(self):
        class Renderer(XLSX):
            def can_render(self):
                return False

        class TestGrid(PeopleGrid):
            def set_renderers(self):
                super(TestGrid, self).set_renderers()
                self.xlsx = Renderer(self)

        TestGrid().xlsx()

    def test_xlsx_format_caching(self):
        grid = PeopleGrid()
        wb = xlsxwriter.Workbook()
        format1 = grid.xlsx.style_for_column(wb, grid.column('status'))
        format2 = grid.xlsx.style_for_column(wb, grid.column('state'))
        format3 = grid.xlsx.style_for_column(wb, grid.column('numericcol'))

        assert format1 is not None
        assert format2 is not None
        assert format3 is not None

        assert format1 is format2
        assert format3 is not format1

        grid = PeopleGrid()
        grid.column('status').xlsx_style = {'bold': True, 'border': 1}
        grid.column('state').xlsx_style = {'bold': True, 'border': 2}

        format1 = grid.xlsx.style_for_column(wb, grid.column('status'))
        format2 = grid.xlsx.style_for_column(wb, grid.column('state'))
        assert format1 is not format2

        grid = PeopleGrid()
        grid.column('status').xlsx_style = {'bold': True, 'border': 1}
        grid.column('state').xlsx_style = {'bold': True, 'border': 1}

        format1 = grid.xlsx.style_for_column(wb, grid.column('status'))
        format2 = grid.xlsx.style_for_column(wb, grid.column('state'))
        assert format1 is format2


class TestCSVRenderer(object):

    def test_some_basics(self):
        g = PeopleCSVGrid(per_page=1)
        csv_data = g.csv.build_csv()
        csv_data.seek(0)
        byte_str = six.StringIO(csv_data.read().decode('utf-8'))
        reader = csv.reader(byte_str, delimiter=',', quotechar='"')
        data = []
        for row in reader:
            data.append(row)
        assert data[0][0] == 'First Name'
        assert data[0][2] == 'Active'
        assert data[1][0] == 'fn004'

    def test_it_renders_date_time_with_tz(self):
        ArrowRecord.query.delete()
        ArrowRecord.testing_create(
            created_utc=arrow.Arrow(2016, 8, 10, 1, 2, 3)
        )
        g = ArrowCSVGrid()
        g.allowed_export_targets = {'csv': CSV}
        csv_data = g.csv.build_csv()
        csv_data.seek(0)
        byte_str = six.StringIO(csv_data.read().decode('utf-8'))
        reader = csv.reader(byte_str, delimiter=',', quotechar='"')
        data = []
        for row in reader:
            data.append(row)
        assert data[0][0] == 'Created'
        assert data[1][0] == '2016-08-10 01:02:03+00:00'


class TestHideSection(object):
    @inrequest('/')
    def test_controlls_hidden(self):
        class NoControlBoxGrid(PG):
            hide_controls_box = True
        g = NoControlBoxGrid()
        assert '<tr class="status"' not in g.html()
        assert '<div class="footer">' not in g.html()


class TestArrowDate(object):
    @inrequest('/')
    def test_arrow_render_html(self):
        ArrowRecord.query.delete()
        ArrowRecord.testing_create(created_utc=arrow.Arrow(2016, 8, 10, 1, 2, 3))
        g = ArrowGrid()
        assert '<td>08/10/2016 01:02 AM</td>' in g.html(), g.html()

        g.column('created_utc').html_format = 'YYYY-MM-DD HH:mm:ss ZZ'
        assert '<td>2016-08-10 01:02:03 +00:00</td>' in g.html(), g.html()

    @inrequest('/')
    def test_arrow_timezone(self):
        # regardless of timezone given, ArrowType stored as UTC and will display that way
        ArrowRecord.query.delete()
        ArrowRecord.testing_create(created_utc=arrow.Arrow(2016, 8, 10, 1, 2, 3).to('US/Pacific'))
        g = ArrowGrid()
        assert '<td>08/10/2016 01:02 AM</td>' in g.html(), g.html()

        g.column('created_utc').html_format = 'YYYY-MM-DD HH:mm:ss ZZ'
        assert '<td>2016-08-10 01:02:03 +00:00</td>' in g.html(), g.html()

    def test_xls(self):
        ArrowRecord.query.delete()
        ArrowRecord.testing_create(created_utc=arrow.Arrow(2016, 8, 10, 1, 2, 3))
        g = ArrowGrid()
        buffer = BytesIO()
        wb = g.xls()
        wb.save(buffer)
        buffer.seek(0)

        book = xlrd.open_workbook(file_contents=buffer.getvalue())
        sh = book.sheet_by_name('arrow_grid')
        # headers
        eq_(sh.cell_value(0, 0), 'Created')
        # data row
        eq_(
            dt.datetime(*xlrd.xldate_as_tuple(sh.cell_value(1, 0), sh.book.datemode)[:6]),
            dt.datetime(2016, 8, 10, 1, 2, 3)
        )
