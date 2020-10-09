from __future__ import absolute_import
import datetime as dt
import inspect
import json
import logging
import re
import sys
import six
import time
import warnings

from blazeutils.containers import HTMLAttributes
from blazeutils.datastructures import BlankObject, OrderedDict
from blazeutils.helpers import tolist
from blazeutils.numbers import decimalfmt
from blazeutils.strings import case_cw2us, randchars
from blazeutils.spreadsheets import xlsxwriter
from formencode import Invalid
import formencode.validators as fev
import sqlalchemy as sa
import sqlalchemy.sql as sasql
from werkzeug.datastructures import MultiDict

from .extensions import gettext as _
from .renderers import HTML, XLS, XLSX

# conditional imports to support libs without requiring them
try:
    import arrow
except ImportError:
    arrow = None

try:
    import xlwt
except ImportError:
    xlwt = None

log = logging.getLogger(__name__)


# subtotals functions
sum_ = sasql.functions.sum
avg_ = sasql.func.avg


def subtotal_function_map(v):
    # subtotals default to the simplest expression (sum). avg is also an option, or you
    #   can assign a string or expression (string using column labels would probably
    #   work best at this stage)
    if v is True or v == 'sum':
        return sum_
    elif v == 'avg':
        return avg_
    return v


class _None(object):
    """
        A sentinal object to indicate no value
    """
    pass


class ExtractionError(TypeError):
    """ raised when we are unable to extract a value from the record """
    pass


class DuplicateQueryNameError(TypeError):
    """
        Raised when an SQ query is used that has more than one column with
        the same name
    """
    pass


class _DeclarativeMeta(type):

    def __new__(cls, name, bases, class_dict):
        class_dict['_rowstylers'] = []
        class_dict['_colstylers'] = []
        class_dict['_colfilters'] = []
        class_columns = []

        # add columns from base classes
        for base in bases:
            base_columns = getattr(base, '__cls_cols__', ())
            class_columns.extend(base_columns)
        class_columns.extend(class_dict.get('__cls_cols__', ()))
        class_dict['__cls_cols__'] = class_columns

        # we have to assign the attribute name
        for k, v in six.iteritems(class_dict):
            # catalog the row stylers
            if getattr(v, '__grid_rowstyler__', None):
                class_dict['_rowstylers'].append(v)

            # catalog the column stylers
            for_column = getattr(v, '__grid_colstyler__', None)
            if for_column:
                class_dict['_colstylers'].append((v, for_column))

            # catalog the column filters
            for_column = getattr(v, '__grid_colfilter__', None)
            if for_column:
                class_dict['_colfilters'].append((v, for_column))

        return super(_DeclarativeMeta, cls).__new__(cls, name, bases, class_dict)


class Column(object):
    """
        Column represents the fixed settings for a datagrid column
    """
    _creation_counter = 0
    xls_width = None
    xls_num_format = None
    xls_style = None
    _render_in = 'html', 'xls', 'xlsx', 'csv'
    _visible = True

    @property
    def render_in(self):
        resolved = self._render_in
        if callable(resolved):
            resolved = resolved(self)
        return tuple(tolist(resolved))

    @render_in.setter
    def render_in(self, val):
        self._render_in = val

    @property
    def visible(self):
        resolved = self._visible
        if callable(resolved):
            resolved = resolved(self)
        return resolved

    @visible.setter
    def visible(self, val):
        self._visible = val

    def __new__(cls, *args, **kwargs):
        col_inst = super(Column, cls).__new__(cls)
        if '_dont_assign' not in kwargs:
            col_inst._assign_to_grid()
        return col_inst

    def _assign_to_grid(self):
        grid_locals = sys._getframe(2).f_locals
        grid_cls_cols = grid_locals.setdefault('__cls_cols__', [])
        grid_cls_cols.append(self)

    def __init__(self, label, key=None, filter=None, can_sort=True,  # noqa: C901
                 xls_width=None, xls_style=None, xls_num_format=None,
                 render_in=_None, has_subtotal=False, visible=True, group=None, **kwargs):
        self.label = label
        self.key = key
        self.filter = filter
        self.filter_for = None
        self.filter_op = None
        self._create_order = False
        self.can_sort = can_sort
        self.has_subtotal = has_subtotal
        self.kwargs = kwargs
        self.grid = None
        self.expr = None
        self._query_idx = None
        self._query_key = None
        if render_in is not _None:
            self.render_in = render_in
        self.visible = visible
        if xls_width:
            self.xls_width = xls_width
        if xls_num_format:
            self.xls_num_format = xls_num_format
        if xls_style:
            self.xls_style = xls_style

        try:
            is_group_cls = issubclass(type(group), ColumnGroup) or issubclass(group, ColumnGroup)
        except TypeError:
            is_group_cls = False

        if group is not None and not is_group_cls:
            raise ValueError(_('expected group to be a subclass of ColumnGroup'))

        self.group = group

        # if the key isn't a base string, assume its a column-like object that
        # works with a SA Query instance
        if key is None:
            self.can_sort = False
        elif not isinstance(key, six.string_types):
            self.expr = col = key
            # use column.key, column.name, or None in that order
            key = getattr(col, 'key', getattr(col, 'name', None))

            if key is None:
                raise ValueError(_('expected filter to be a SQLAlchemy column-like'
                                   ' object, but it did not have a "key" or "name"'
                                   ' attribute'))
            self.key = self._query_key = key

        # filters can be sent in as a class (not class instance) if needed
        if inspect.isclass(filter):
            if self.expr is None:
                raise ValueError(_('the filter was a class type, but no'
                                   ' column-like object is available from "key" to pass in as'
                                   ' as the first argument'))
            self.filter = filter(self.expr)

    def new_instance(self, grid):
        cls = self.__class__
        key = grid.get_unique_column_key(self.key)

        column = cls(self.label, key, None, self.can_sort, group=self.group, _dont_assign=True)
        column.grid = grid
        column.expr = self.expr
        column._query_key = self._query_key

        if self.filter:
            column.filter = self.filter.new_instance(dialect=grid.manager.db.engine.dialect)

        column.head = BlankObject()
        column.head.hah = HTMLAttributes(self.kwargs)
        column.body = BlankObject()
        column.body.hah = HTMLAttributes(self.kwargs)
        if xlwt is not None:
            column.xlwt_stymat = self.xlwt_stymat_init()
        else:
            column.xlwt_stymat = None

        # try to be smart about which attributes should get copied to the
        # new instance by looking for attributes on the class that have the
        # same name as arguments to the classes __init__ method
        args = (inspect.getargspec(self.__init__).args
                if six.PY2 else inspect.getfullargspec(self.__init__).args)

        for argname in args:
            if argname != 'self' and argname not in (
                'label', 'key', 'filter', 'can_sort', 'render_in', 'visible'
            ) and hasattr(self, argname):
                setattr(column, argname, getattr(self, argname))

        # Copy underlying value of render_in and visible, in case they are
        # lambdas that should be called per grid instance.
        column.render_in = self._render_in
        column.visible = self._visible

        return column

    def extract_and_format_data(self, record):
        """
            Extract a value from the record for this column and run it through
            the data formaters.
        """
        data = self.extract_data(record)
        data = self.format_data(data)
        for _filter, cname in self.grid._colfilters:
            for_column = self.grid.column(cname)
            if self.key == for_column.key:
                data = _filter(self.grid, data)
        return data

    def extract_data(self, record):  # noqa: C901
        """
            Locate the data for this column in the record and return it.
        """
        # key style based on key
        try:
            return record[self.key]
        except (TypeError, KeyError):
            pass

        # index style based on position in query and key
        if (
            self._query_idx is not None
            and hasattr(record, '_fields')
        ):
            try:
                if record._fields[self._query_idx] == self._query_key:
                    return record[self._query_idx]
            except IndexError:
                pass

        # attribute style
        try:
            return getattr(record, self._query_key)
        except AttributeError as e:
            if ("object has no attribute '%s'" % self._query_key) not in str(e):
                raise
        except TypeError as e:
            if 'attribute name must be string' not in str(e):
                raise

        # attribute style with grid key
        try:
            return getattr(record, self.key)
        except AttributeError as e:
            if ("object has no attribute '%s'" % self.key) not in str(e):
                raise

        raise ExtractionError(_('key "{key}" not found in record', key=self.key))

    def format_data(self, value):
        """
            Use to adjust the value extracted from the record for this column.
            By default, no change is made. Useful in sub-classes.
        """
        return value

    def render(self, render_type, record, *args, **kwargs):
        render_attr = 'render_{0}'.format(render_type)
        if hasattr(self, render_attr):
            return getattr(self, render_attr)(record, *args, **kwargs)
        return self.extract_and_format_data(record)

    def apply_sort(self, query, flag_desc):
        if self.expr is None:
            direction = 'DESC' if flag_desc else 'ASC'
            return query.order_by(sasql.text('{0} {1}'.format(self.key, direction)))
        if flag_desc:
            return query.order_by(self.expr.desc())
        return query.order_by(self.expr)

    def __repr__(self):
        return '<Column "{0.key}" from "{0.grid}">'.format(self)

    def xls_width_calc(self, value):
        if self.xls_width:
            return self.xls_width
        if isinstance(value, six.string_types):
            return len(value)
        return len(str(value))

    def xlwt_stymat_init(self):
        """
            Because Excel gets picky about a lot of styles, its likely that
            a column will use one style object instance.  This method will
            be called once.

            If a column needs to support more than one style, override
            xlwt_stymat_calc()
        """
        return xlwt.easyxf(self.xls_style, self.xls_num_format)

    def xlwt_stymat_calc(self, value):
        """
            By default, the xlwt style & number format is per-column and not
            based ont he value.
        """
        return self.xlwt_stymat


class LinkColumnBase(Column):
    link_attrs = {}

    def __init__(self, label, key=None, filter=None, can_sort=True,
                 link_label=None, xls_width=None, xls_style=None, xls_num_format=None,
                 render_in=_None, has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key, filter, can_sort, xls_width,
                         xls_style, xls_num_format, render_in,
                         has_subtotal, visible, group=group, **kwargs)
        self.link_label = link_label

    def link_to(self, label, url, **kwargs):
        return self.grid.html._render_jinja(
            '<a href="{{url}}" {{- attrs|wg_attributes }}>{{label}}</a>',
            url=url,
            attrs=kwargs,
            label=label
        )

    def render_html(self, record, hah):
        url = self.create_url(record)
        if self.link_label is not None:
            label = self.link_label
        else:
            label = self.extract_and_format_data(record)
        return self.link_to(label, url, **self.link_attrs)

    def create_url(self, record):
        raise NotImplementedError('create_url() must be defined on a subclass')


class BoolColumn(Column):

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 reverse=False, true_label=_('True'), false_label=_('False'),
                 xls_width=None, xls_style=None, xls_num_format=None,
                 render_in=_None, has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, xls_width,
                         xls_style, xls_num_format, render_in,
                         has_subtotal, visible, group=group, **kwargs)
        self.reverse = reverse
        self.true_label = true_label
        self.false_label = false_label

    def format_data(self, data):
        if self.reverse:
            data = not data
        if data:
            return self.true_label
        return self.false_label


class YesNoColumn(BoolColumn):

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 reverse=False, xls_width=None, xls_style=None, xls_num_format=None,
                 render_in=_None, has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, reverse,
                         _('Yes'), _('No'), xls_width, xls_style, xls_num_format,
                         render_in, has_subtotal, visible, group=group, **kwargs)


class DateColumnBase(Column):

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 html_format=None, csv_format=None, xls_width=None, xls_style=None,
                 xls_num_format=None, render_in=_None, has_subtotal=False, visible=True, group=None,
                 **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, xls_width,
                         xls_style, xls_num_format, render_in, has_subtotal,
                         visible, group=group, **kwargs)
        if html_format:
            self.html_format = html_format

        if csv_format:
            self.csv_format = csv_format

    def _format_datetime(self, data, format):
        # if we have an arrow date, allow html_format to use that functionality
        if arrow and isinstance(data, arrow.Arrow):
            if data.strftime(format) == format:
                return data.format(format)
        return data.strftime(format)

    def render_html(self, record, hah):
        data = self.extract_and_format_data(record)
        if not data:
            return data
        return self._format_datetime(data, self.html_format)

    def render_xls(self, record):
        data = self.extract_and_format_data(record)
        if not data:
            return data
        # if we have an arrow date, pull the underlying datetime, else the renderer won't know
        #   how to handle it
        if arrow and isinstance(data, arrow.Arrow):
            data = data.datetime
        # xlwt has no idea what to do with zone information
        if isinstance(data, dt.datetime) and data.tzinfo is not None:
            data = data.replace(tzinfo=None)
        return data

    def render_xlsx(self, record):
        return self.render_xls(record)

    def render_csv(self, record):
        data = self.extract_and_format_data(record)
        if not data:
            return data
        return self._format_datetime(data, self.csv_format)

    def xls_width_calc(self, value):
        if self.xls_width:
            return self.xls_width
        try:
            # value will be a date or datetime object, format as if it was going
            # to be in HTML as an approximation of its format in excel
            html_version = value.strftime(self.html_format)
            return len(html_version)
        except AttributeError as e:
            if "has no attribute 'strftime'" not in str(e):
                raise
            # must be the column heading
            return Column.xls_width_calc(self, value)


class DateColumn(DateColumnBase):
    # !!!: localize
    html_format = '%m/%d/%Y'
    csv_format = '%Y-%m-%d'
    xls_num_format = 'm/dd/yyyy'


class DateTimeColumn(DateColumnBase):
    # !!!: localize
    html_format = '%m/%d/%Y %I:%M %p'
    csv_format = '%Y-%m-%d %H:%M:%S%z'
    xls_num_format = 'mm/dd/yyyy hh:mm am/pm'


class TimeColumn(DateColumnBase):
    # !!!: localize
    html_format = '%I:%M %p'
    csv_format = '%H:%M'
    xls_num_format = 'hh:mm am/pm'


class NumericColumn(Column):
    # !!!: localize
    xls_fmt_general = '#,##0{dec_places};{neg_prefix}-#,##0{dec_places}'
    xls_fmt_accounting = '_($* #,##0{dec_places}_);{neg_prefix}_($* (#,##0{dec_places})' + \
                         ';_($* "-"??_);_(@_)'
    xls_fmt_percent = '0{dec_places}%;{neg_prefix}-0{dec_places}%'

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 reverse=False, xls_width=None, xls_style=None, xls_num_format=None,
                 render_in=_None, format_as='general', places=2, curr='',
                 sep=',', dp='.', pos='', neg='-', trailneg='',
                 xls_neg_red=True, has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, xls_width,
                         xls_style, xls_num_format, render_in,
                         has_subtotal, visible, group=group, **kwargs)
        self.places = places
        self.curr = curr
        self.sep = sep
        self.dp = dp
        self.pos = pos
        self.neg = neg
        self.trailneg = trailneg
        self.xls_neg_red = xls_neg_red
        self.format_as = format_as

    def html_decimal_format_opts(self, data):
        return (
            2 if self.format_as == 'accounting' else self.places,
            '$' if self.format_as == 'accounting' else self.curr,
            self.sep,
            self.dp,
            self.pos,
            '(' if self.format_as == 'accounting' else self.neg,
            ')' if self.format_as == 'accounting' else self.trailneg,
        )

    def render_html(self, record, hah):
        data = self.extract_and_format_data(record)
        if not data and data != 0:
            return data

        if self.format_as == 'percent':
            data = data * 100

        formatted = decimalfmt(data, *self.html_decimal_format_opts(data))

        if self.format_as == 'percent':
            formatted += '%'

        if data < 0:
            hah.class_ += 'negative'

        return formatted

    def xls_construct_format(self, fmt_str):
        neg_prefix = '[RED]' if self.xls_neg_red else ''
        dec_places = '.'.ljust(self.places + 1, '0') if self.places else ''
        return fmt_str.format(dec_places=dec_places, neg_prefix=neg_prefix)

    def get_num_format(self):
        if self.format_as == 'general':
            return self.xls_construct_format(self.xls_fmt_general)
        if self.format_as == 'percent':
            return self.xls_construct_format(self.xls_fmt_percent)
        if self.format_as == 'accounting':
            return self.xls_construct_format(self.xls_fmt_accounting)
        return None

    @property
    def xlsx_style(self):
        return {
            'num_format': self.get_num_format()
        }

    def xlwt_stymat_init(self):
        num_format = self.get_num_format()
        if num_format:
            return xlwt.easyxf(self.xls_style, num_format)
        return Column.xlwt_stymat_init(self)


class EnumColumn(Column):
    """
    This column type is meant to be used with python `enum.Enum` type columns. It expects that
    the display value is the `value` attribute of the enum instance.
    """
    def format_data(self, value):
        if value is None:
            return None
        return value.value


class ColumnGroup(object):
    label = None
    class_ = None

    def __init__(self, label, class_=None):
        self.label = label
        self.class_ = class_


class BaseGrid(six.with_metaclass(_DeclarativeMeta, object)):
    __cls_cols__ = ()
    identifier = None
    sorter_on = True
    pager_on = True
    per_page = 50
    on_page = 1
    hide_controls_box = False
    hide_excel_link = False
    # enables keyed session store of grid arguments
    session_on = False
    # enables page/grand subtotals: none|page|grand|all
    subtotals = 'none'
    manager = None
    allowed_export_targets = None
    # Enables single-search feature, where one search value is applied to every supporting
    # filter at once
    enable_search = False

    # List of joins to bring the query together for all columns. May have just the join object,
    # or also conditions
    # e.g. [Blog], ([Blog.category], ), or [(Blog, Blog.active == sa.true())]
    # note: relationship attributes must be referenced within tuples, due to SQLAlchemy magic
    query_joins = None
    query_outer_joins = None
    # Filter parameter(s) tuple to be used on the query
    # note: relationship attributes must be referenced within tuples, due to SQLAlchemy magic
    query_filter = None
    # Parameter(s) tuple to be passed to order_by if sort options are not set on the grid
    # note: relationship attributes must be referenced within tuples, due to SQLAlchemy magic
    query_default_sort = None

    # Will ask for confirmation before exporting more than this many records.
    # Set to None to disable this check
    unconfirmed_export_limit = 10000

    def __init__(self, ident=None, per_page=_None, on_page=_None, qs_prefix='', class_='datagrid',
                 **kwargs):
        self._ident = ident
        self.hah = HTMLAttributes(kwargs)
        self.hah.id = self.ident
        self.hah.class_ += class_
        self.filtered_cols = OrderedDict()
        self.subtotal_cols = OrderedDict()
        self.order_by = []
        self.qs_prefix = qs_prefix
        self.user_warnings = []
        self.search_value = None
        self._record_count = None
        self._records = None
        self._page_totals = None
        self._grand_totals = None
        if self.hide_excel_link is True:
            warnings.warn(
                "Hide excel link is deprecated, you should just override allowed_export_targets instead", # noqa
                DeprecationWarning
            )
        if self.allowed_export_targets is None:
            self.allowed_export_targets = {}
            # If the grid doesn't define any export targets
            # lets setup the export targets for xls and xlsx if we have the requirement
            if xlwt is not None:
                self.allowed_export_targets['xls'] = XLS
            if xlsxwriter is not None:
                self.allowed_export_targets['xlsx'] = XLSX
        self.set_renderers()
        self.export_to = None
        # when session feature is enabled, key is the unique string
        #   used to distinguish grids. Initially set to a random
        #   string, but will be set to the session key in args
        self.session_key = randchars(12)
        # at times, different grids may be made to share a session
        self.foreign_session_loaded = False

        self.per_page = per_page if per_page is not _None else self.__class__.per_page
        self.on_page = on_page if on_page is not _None else self.__class__.on_page

        self.columns = []
        self.key_column_map = {}

        self._init_columns()
        self.post_init()

    def _init_columns(self):
        for col in self.__cls_cols__:
            new_col = col.new_instance(self)
            self.columns.append(new_col)
            self.key_column_map[new_col.key] = new_col
            if new_col.filter is not None:
                self.filtered_cols[new_col.key] = new_col
            if new_col.has_subtotal is not False and new_col.has_subtotal is not None:
                self.subtotal_cols[new_col.key] = (
                    subtotal_function_map(new_col.has_subtotal),
                    new_col
                )

    def post_init(self):
        """Provided for subclasses to run post-initialization customizations"""
        pass

    def before_query_hook(self):
        """ Just a hook to give subclasses a chance to change things before executing the query """
        pass

    def build(self):
        self.apply_qs_args()
        self.before_query_hook()
        # this will force the query to execute.  We used to wait to evaluate this but it ended
        # up causing AttributeErrors to be hidden when the grid was used in Jinja.
        # Calling build is now preferred over calling .apply_qs_args() and then .html()
        self.record_count

    def column(self, ident):
        if isinstance(ident, six.string_types):
            return self.key_column_map[ident]
        return self.columns[ident]

    def has_column(self, ident):
        if isinstance(ident, six.string_types):
            return ident in self.key_column_map
        return ident in self.columns

    def get_unique_column_key(self, key):
        suffix_counter = 0
        new_key = key
        while self.has_column(new_key):
            suffix_counter += 1
            new_key = '{}_{}'.format(key, suffix_counter)
        return new_key

    def iter_columns(self, render_type):
        for col in self.columns:
            if col.visible and render_type in col.render_in:
                yield col

    def can_search(self):
        # enable_search will turn the feature on/off, but don't enable it if none of the filters
        # support it
        return self.enable_search and len(self.search_expression_generators) > 0

    @property
    def search_expression_generators(self):
        # See FilterBase.get_search_expr
        # Should return a tuple of callables, each taking a single argument (the search value).
        # We filter out None here so as to disregard filters that don't support the search feature.
        def check_expression_generator(expr_gen):
            if expr_gen is not None and not callable(expr_gen):
                raise Exception(
                    'bad filter search expression: {} is not callable'.format(str(expr_gen))
                )
            return expr_gen is not None
        return tuple(filter(
            check_expression_generator,
            [col.filter.get_search_expr() for col in self.filtered_cols.values()]
        ))

    def set_renderers(self):
        self.html = HTML(self)
        for key, value in self.allowed_export_targets.items():
            setattr(self, key, value(self))

    def set_filter(self, key, op, value, value2=None):
        self.clear_record_cache()
        self.filtered_cols[key].filter.set(op, value, value2=value2)

    def set_sort(self, *args):
        self.clear_record_cache()
        self.order_by = []

        for key in args:
            if not key:
                continue
            flag_desc = False
            if key.startswith('-'):
                flag_desc = True
                key = key[1:]
            if key in self.key_column_map and self.key_column_map[key].can_sort:
                self.order_by.append((key, flag_desc))
            elif not self.foreign_session_loaded:
                self.user_warnings.append(_('''can't sort on invalid key "{key}"''', key=key))

    def set_paging(self, per_page, on_page):
        self.clear_record_cache()
        self.per_page = per_page
        self.on_page = on_page

    def clear_record_cache(self):
        self._record_count = None
        self._records = None

    @property
    def ident(self):
        return self._ident \
            or self.identifier \
            or case_cw2us(self.__class__.__name__)

    @property
    def has_filters(self):
        for col in six.itervalues(self.filtered_cols):
            if col.filter.is_active:
                return True
        return self.search_value is not None

    @property
    def has_sort(self):
        return bool(self.order_by)

    @property
    def record_count(self):
        if self._record_count is None:
            query = self.build_query(for_count=True)
            t0 = time.perf_counter()
            self._record_count = query.count()
            t1 = time.perf_counter()
            log.debug('Count query ran in {} seconds'.format(t1 - t0))
        return self._record_count

    @property
    def records(self):
        if self._records is None:
            query = self.build_query()
            t0 = time.perf_counter()
            self._records = query.all()
            t1 = time.perf_counter()
            log.debug('Data query ran in {} seconds'.format(t1 - t0))
        return self._records

    def _totals_col_results(self, page_totals_only):
        SUB = self.build_query(for_count=(not page_totals_only)).subquery()

        cols = []
        # Not all columns can be totaled. But, we should put in null placeholders
        # for any untotaled columns, so that the same query indices from query_base
        # can be applied.
        # This will apply to any columns with an expr. Other subtotaled columns can be
        # tacked onto the end - these will not be indexed and must be referred to by name
        for colobj in [
            col for col in self.columns if col.expr is not None
        ] + [
            coltuple[1] for _, coltuple in self.subtotal_cols.items() if coltuple[1].expr is None
        ]:
            colname = colobj._query_key or colobj.key

            if colobj.key not in self.subtotal_cols:
                cols.append(
                    sa.literal(None).label(colname)
                )
                continue

            sa_aggregate_func, _ = self.subtotal_cols[colobj.key]

            # column may have a label. If it does, use it
            if isinstance(colobj.expr, sasql.expression._Label):
                aggregate_this = sasql.text(colobj.key)
            elif colobj.expr is None:
                aggregate_this = sasql.literal_column(colobj.key)
            else:
                aggregate_this = colobj.expr

            # sa_aggregate_func could be an expression, or a callable. If it is callable, give it
            #   the column
            labeled_aggregate_col = None
            if callable(sa_aggregate_func):
                labeled_aggregate_col = sa_aggregate_func(aggregate_this).label(colname)
            elif isinstance(sa_aggregate_func, six.string_types):
                labeled_aggregate_col = sasql.literal_column(sa_aggregate_func).label(colname)
            else:
                labeled_aggregate_col = sa_aggregate_func.label(colname)
            cols.append(labeled_aggregate_col)
        cols.append(sa.literal(1).label('__is_total__'))

        t0 = time.perf_counter()
        result = self.manager.sa_query(*cols).select_entity_from(SUB).first()
        t1 = time.perf_counter()
        log.debug('Totals query ran in {} seconds'.format(t1 - t0))

        return result

    @property
    def page_totals(self):
        if self._page_totals is None:
            self._page_totals = self._totals_col_results(page_totals_only=True)
        return self._page_totals

    @property
    def grand_totals(self):
        if self._grand_totals is None:
            self._grand_totals = self._totals_col_results(page_totals_only=False)
        return self._grand_totals

    @property
    def page_count(self):
        if self.per_page is None:
            return 1
        return max(0, self.record_count - 1) // self.per_page + 1

    def build_query(self, for_count=False):
        log.debug(str(self))

        has_filters = self.has_filters
        query = self.query_base(self.has_sort, has_filters)
        query = self.query_prep(query, self.has_sort or for_count, has_filters)

        if has_filters:
            query = self.query_filters(query)
        else:
            log.debug('No filters')

        if for_count:
            return query

        query = self.query_sort(query)
        if self.pager_on:
            query = self.query_paging(query)

        return query

    def set_records(self, records):
        self._record_count = len(records)
        self._records = records

    def query_base(self, has_sort, has_filters):
        for idx, column in enumerate(filter(lambda col: col.expr is not None, self.columns)):
            column._query_idx = idx
        cols = [col.expr for col in self.columns if col.expr is not None]
        query = self.manager.sa_query(*cols)

        for join_terms in (tolist(self.query_joins) or tuple()):
            query = query.join(*tolist(join_terms))

        for join_terms in (tolist(self.query_outer_joins) or tuple()):
            query = query.outerjoin(*tolist(join_terms))

        if self.query_filter:
            query = query.filter(*tolist(self.query_filter))

        if not has_sort and self.query_default_sort is not None:
            query = query.order_by(*tolist(self.query_default_sort))

        return query

    def query_prep(self, query, has_sort, has_filters):
        return query

    def query_filters(self, query):
        filter_display = []
        if self.search_value is not None:
            query = self.apply_search(query, self.search_value)

        for col in six.itervalues(self.filtered_cols):
            if col.filter.is_active:
                filter_display.append('{}: {}'.format(col.key, str(col.filter)))
                query = col.filter.apply(query)
        if filter_display:
            log.debug(';'.join(filter_display))
        else:
            log.debug('No filters')
        return query

    def apply_search(self, query, value):
        # We depend on the filters to know what to do with the search value, and then OR the
        # expressions together for our query
        return query.filter(sa.or_(*filter(
            lambda item: item is not None,
            (expr(value) for expr in self.search_expression_generators)
        )))

    def query_paging(self, query):
        if self.on_page and self.per_page:
            offset = (self.on_page - 1) * self.per_page
            query = query.offset(offset).limit(self.per_page)
            log.debug('Page {}; {} per page'.format(self.on_page, self.per_page))
        return query

    def query_sort(self, query):
        redundant = []
        sort_display = []
        for key, flag_desc in self.order_by:
            if key in self.key_column_map:
                col = self.key_column_map[key]
                # remove any redundant names, whichever comes first is what we will keep
                if col.key in redundant:
                    continue
                else:
                    sort_display.append(col.key)
                    redundant.append(col.key)
                query = col.apply_sort(query, flag_desc)
        if sort_display:
            log.debug(','.join(sort_display))
        else:
            log.debug('No sorts')

        # Special consideration for MSSQL, because if paging is to work, the query
        # must have an ORDER BY clause. This is problematic, because if an app
        # does not test for the query case where paging is enabled for page > 1,
        # the query will not hit the error state. Fix the case if possible.
        if (
            self.pager_on
            and self.manager
            and self.manager.db.engine.dialect.name == 'mssql'
            and not query._order_by
        ):
            query = self._fix_mssql_order_by(query)

        return query

    def _fix_mssql_order_by(self, query):
        # MSSQL must have an ORDER BY for paging to work. If no sort clause has been
        # defined, sort by the first column. If that doesn't work, error out.
        if len(self.columns):
            query = self.columns[0].apply_sort(query, False)
            if query._order_by:
                return query
        raise Exception(
            'Paging is enabled, but query does not have ORDER BY clause required for MSSQL'
        )

    def args_have_op(self, args):
        # any of the grid's query string args can be used to
        #   override the session behavior (except export_to)
        r = re.compile(
            self.qs_prefix + r'(op\(.*\))'
        )
        return any(r.match(a) for a in args.keys())

    def args_have_session_override(self, args):
        r = re.compile(
            self.qs_prefix + 'session_override'
        )
        return any(r.match(a) for a in args.keys())

    def args_have_page(self, args):
        r = re.compile(
            self.qs_prefix + '(onpage|perpage)'
        )
        return any(r.match(a) for a in args.keys())

    def args_have_sort(self, args):
        r = re.compile(
            self.qs_prefix + '(sort[1-3])'
        )
        return any(r.match(a) for a in args.keys())

    def apply_qs_args(self, add_user_warnings=True):
        args = MultiDict(self.manager.request_args())
        if (
            'search' in args
            and self.can_search()
            and self.prefix_qs_arg_key('dgreset') not in args
        ):
            self.search_value = args['search'].strip()

        # args are pulled first from the request. If the session feature
        #   is enabled and the request doesn't include grid-related args,
        #   check for either the session key or a default set in the
        #   session args store
        if self.session_on:
            # if session key is in request, set the unique key
            self.session_key = args.get(
                self.prefix_qs_arg_key('session_key'),
                self.session_key
            )
            session_override = self.args_have_session_override(args)
            # apply arg indicates that filtering/paging/sorting form was submitted
            apply = self.prefix_qs_arg_key('apply') in args
            args.pop(self.prefix_qs_arg_key('apply'), None)
            if (not self.args_have_op(args) and not apply) or session_override:
                session_args = self.get_session_store(args, session_override)
                # override paging if it exists in the query
                if self.args_have_page(args):
                    session_args['onpage'] = args.get('onpage')
                    session_args['perpage'] = args.get('perpage')
                # override sorting if it exists in the query
                if self.args_have_sort(args):
                    session_args['sort1'] = args.get('sort1')
                    session_args['sort2'] = args.get('sort2')
                    session_args['sort3'] = args.get('sort3')
                # flag a foreign session if loading from another grid's session
                grid_key = self.__class__.__name__
                if session_args.get('datagrid', grid_key) != grid_key:
                    self.foreign_session_loaded = True
                args = session_args

            req_args = self.manager.request_args()
            if self.prefix_qs_arg_key('export_to') in req_args:
                args[self.prefix_qs_arg_key('export_to')] = \
                    req_args[self.prefix_qs_arg_key('export_to')]
            self.save_session_store(args)

        # filtering (make sure this is above paging otherwise self.page_count
        # used in the paging section below won't work)
        self._apply_filtering(args)

        # paging
        self._apply_paging(args)

        # sorting
        self._apply_sorting(args)

        if add_user_warnings:
            for msg in self.user_warnings:
                self.manager.flash_message('warning', msg)

    def _apply_filtering(self, args):
        for col in six.itervalues(self.filtered_cols):
            filter = col.filter
            filter_op_qsk = self.prefix_qs_arg_key('op({0})'.format(col.key))
            filter_v1_qsk = self.prefix_qs_arg_key('v1({0})'.format(col.key))
            filter_v2_qsk = self.prefix_qs_arg_key('v2({0})'.format(col.key))

            filter_op_value = args.get(filter_op_qsk, None)

            if filter._default_op:
                filter.set(None, None, None)

            if filter_op_value is not None:
                if filter.receives_list:
                    v1 = args.getlist(filter_v1_qsk)
                    v2 = args.getlist(filter_v2_qsk)
                else:
                    v1 = args.get(filter_v1_qsk, None)
                    v2 = args.get(filter_v2_qsk, None)

                try:
                    filter.set(
                        filter_op_value,
                        v1,
                        v2,
                    )
                except Invalid as e:
                    invalid_msg = filter.format_invalid(e, col)
                    self.user_warnings.append(invalid_msg)

    def _apply_paging(self, args):
        pp_qsk = self.prefix_qs_arg_key('perpage')
        if pp_qsk in args:
            per_page = self.apply_validator(fev.Int, args[pp_qsk], pp_qsk)
            if per_page is None or per_page < 1:
                per_page = 1
            self.per_page = per_page

        op_qsk = self.prefix_qs_arg_key('onpage')
        if op_qsk in args:
            on_page = self.apply_validator(fev.Int, args[op_qsk], op_qsk)
            if on_page is None or on_page < 1:
                on_page = 1
            if on_page > self.page_count:
                on_page = self.page_count
            self.on_page = on_page

    def _apply_sorting(self, args):
        sort_qs_keys = [
            self.prefix_qs_arg_key('sort1'),
            self.prefix_qs_arg_key('sort2'),
            self.prefix_qs_arg_key('sort3'),
        ]
        sort_qs_values = [args[sort_qsk] for sort_qsk in sort_qs_keys if sort_qsk in args]
        if sort_qs_values:
            self.set_sort(*sort_qs_values)

        # handle other file formats
        export_qsk = self.prefix_qs_arg_key('export_to')
        self.set_export_to(args.get(export_qsk, None))

    def prefix_qs_arg_key(self, key):
        return '{0}{1}'.format(self.qs_prefix, key)

    def apply_validator(self, validator, value, qs_arg_key):
        try:
            return validator.to_python(value)
        except Invalid:
            invalid_msg = _('"{arg}" grid argument invalid, ignoring', arg=qs_arg_key)
            self.user_warnings.append(invalid_msg)
            return None

    def set_export_to(self, to):
        if to in self.allowed_export_targets:
            self.export_to = to

    def export_as_response(self, wb=None, sheet_name=None):
        if not self.export_to:
            raise ValueError('No export format set')
        exporter = getattr(self, self.export_to)
        if self.export_to in ['xls', 'xlsx']:
            return exporter.as_response(wb, sheet_name)
        return exporter.as_response()

    def get_session_store(self, args, session_override=False):
        # check args for a session key. If the key is present,
        #   look it up in the session and use the saved args
        #   (if they have been saved under that key). If not,
        #   look up the class name for a default arg store.
        web_session = self.manager.web_session()
        if 'dgsessions' not in web_session:
            return args
        dgsessions = web_session['dgsessions']
        stored_args = None
        # if dgreset is in args, store the session key if present
        #   and then pass back the incoming args
        reset = self.prefix_qs_arg_key('dgreset') in args

        # session is stored as a JSON-serialized list of tuples, which we can turn into MultiDict
        session_key = '_{0}'.format(self.__class__.__name__)
        if args.get(self.prefix_qs_arg_key('session_key'), None):
            if dgsessions.get(self.session_key, None):
                session_key = self.session_key
        stored_args_json = dgsessions.get(session_key, '[]')
        if isinstance(stored_args_json, MultiDict):
            stored_args_json = json.dumps(list(stored_args_json.items(multi=True)))
        elif isinstance(stored_args_json, dict):
            stored_args_json = json.dumps(list(stored_args_json.items()))
        stored_args = MultiDict(json.loads(stored_args_json))

        if stored_args and session_override:
            for arg, value in args.items():
                stored_args[arg] = value
            stored_args.pop('session_override')
        return stored_args if (stored_args and not reset) else args

    def save_session_store(self, args):
        # save the args in the session under the session key
        #   and also as the default args for this grid
        web_session = self.manager.web_session()
        if 'dgsessions' not in web_session:
            web_session['dgsessions'] = dict()
        dgsessions = web_session['dgsessions']
        # work with a copy here
        args = MultiDict(args)
        # remove keys that should not be stored
        args.pop(self.prefix_qs_arg_key('export_to'), None)
        args.pop(self.prefix_qs_arg_key('dgreset'), None)
        args['datagrid'] = self.__class__.__name__
        # serialize the args so we can enforce the correct MultiDict type on the other side
        args_json = json.dumps(list(args.items(multi=True)))
        # save in store under grid default and session key
        dgsessions[self.session_key] = args_json
        dgsessions['_{0}'.format(self.__class__.__name__)] = args_json

        # some frameworks/sessions need these changes manually persisted
        self.manager.persist_web_session()

    def __repr__(self):
        return '<Grid "{0}">'.format(self.__class__.__name__)


def row_styler(f):
    f.__grid_rowstyler__ = True
    return f


def col_styler(for_column):
    def decorator(f):
        f.__grid_colstyler__ = for_column
        return f
    return decorator


def col_filter(for_column):
    def decorator(f):
        f.__grid_colfilter__ = for_column
        return f
    return decorator
