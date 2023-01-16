from __future__ import absolute_import
import datetime as dt
import inspect
import logging
import sys
import six
import time

from blazeutils.containers import HTMLAttributes
from blazeutils.datastructures import BlankObject, OrderedDict
from blazeutils.helpers import tolist
from blazeutils.numbers import decimalfmt
from blazeutils.strings import case_cw2us, randchars
from blazeutils.spreadsheets import xlsxwriter, openpyxl
from formencode import Invalid
import formencode.validators as fev
import sqlalchemy as sa
import sqlalchemy.sql as sasql
from werkzeug.datastructures import MultiDict
from werkzeug.urls import url_encode

from .extensions import gettext as _
from .renderers import HTML, XLSX
from .version import VERSION as __version__  # noqa: F401

# conditional imports to support libs without requiring them
try:
    import arrow
except ImportError:
    arrow = None

log = logging.getLogger(__name__)


# subtotals functions
sum_ = sasql.functions.sum
avg_ = sasql.func.avg


def subtotal_function_map(v):
    """Maps string value to a function, or passes the value through.

    Recognizes True, "sum" or "avg". If True, "sum" is used as the default
    subtotal function.

    Args:
        v (Union(str, callable)): Value defining the subtotal method.

    Returns:
        Union(str, callable): `sum` or `avg` SQLAlchemy functions, or the value.
    """
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
    """Column represents the data and render specification for a table column.

    Args:
        label (str): Label to use for filter/sort selection and table header.

        key (Union[Expression, str], optional): Field key or SQLAlchemy expression.
        If an expression is provided, column attempts to derive a string key name from
        the expression. Defaults to None.

        filter (FilterBase, optional): Filter class or instance. Defaults to None.

        can_sort (bool, optional): Enables column for selection in sort keys. Defaults to True.

        xls_num_format (str, optional): XLSX number/date format. Defaults to None.

        render_in (Union(list(str), callable), optional): Targets to render as a column.
        Defaults to _None.

        has_subtotal (Union(bool,str,callable), optional): Subtotal method to use, if any.
        True or "sum" will yield a sum total. "avg" maps to average. Can also be a
        callable that will be called with the aggregate expression and is expected
        to return a SQLAlchemy expression. Defaults to False.

        visible (Union(bool, callable), optional): Enables any target in `render_in`.
        Defaults to True.

        group (ColumnGroup, optional): Render grouping under a single heading. Defaults to None.

    Class Attributes:
        xls_width (float, optional): Override to autocalculated width in Excel exports.

        xls_num_format (str, optional): Default numeric/date format type.
    """
    xls_width = None
    xls_num_format = None
    json_type_helper = None
    _render_in = 'html', 'xlsx', 'csv', 'json'
    _visible = True

    @property
    def render_in(self):
        """Target(s) in which the field should be rendered as a column.

        Can be set to a callable, which will be called with the column instance.

        Returns:
            tuple(str): Renderer identifiers.
        """
        resolved = self._render_in
        if callable(resolved):
            resolved = resolved(self)
        return tuple(tolist(resolved))

    @render_in.setter
    def render_in(self, val):
        self._render_in = val

    @property
    def visible(self):
        """Enables column to be rendered to any target in `render_in`.

        Can be set to a callable, which will be called with the column instance.

        Returns:
            bool: Enable render.
        """
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
        """Columns being set up in declarative fashion need to be attached to the class
        somewhere. In WebGrid, we have a class attribute `__cls_cols__` that columns
        append themselves to. Subclasses, use of mixins, etc. will combine these column
        lists elsewhere.
        """
        grid_locals = sys._getframe(2).f_locals
        grid_cls_cols = grid_locals.setdefault('__cls_cols__', [])
        grid_cls_cols.append(self)

    def __init__(self, label, key=None, filter=None, can_sort=True,  # noqa: C901
                 xls_width=None, xls_num_format=None, render_in=_None, has_subtotal=False,
                 visible=True, group=None, **kwargs):
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
        """Create a "copy" instance that is linked to a grid instance.

        Used during the grid instantiation process. Grid classes have column instances defining
        the grid structure. When the grid instantiates, we have to copy those column instances
        along with it, to attach them to the grid instance.
        """
        cls = self.__class__
        key = grid.get_unique_column_key(
            self.key
            or case_cw2us(str(self.label).replace(' ', ''))
            or 'unnamed_expression'
        )

        column = cls(self.label, key, None, self.can_sort, group=self.group, _dont_assign=True)
        column.key = key
        column.grid = grid
        column.expr = self.expr
        column._query_key = self._query_key

        if self.filter:
            column.filter = self.filter.new_instance(
                dialect=grid.manager.db.engine.dialect, col=column.expr
            )

        column.head = BlankObject()
        column.head.hah = HTMLAttributes(self.kwargs)
        column.body = BlankObject()
        column.body.hah = HTMLAttributes(self.kwargs)

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
        """Entrypoint from renderer.

        Uses any renderer-specific overrides from the column, or else falls back to
        the output of `extract_and_format_data`.

        Renderer-specific methods are expected to be named `render_<type>`,
        e.g. `render_html` or `render_xlsx`.
        """
        render_attr = 'render_{0}'.format(render_type)
        if hasattr(self, render_attr):
            return getattr(self, render_attr)(record, *args, **kwargs)
        return self.extract_and_format_data(record)

    def apply_sort(self, query, flag_desc):
        """Query modifier to enable sort for this column's expression."""
        if self.expr is None:
            direction = 'DESC' if flag_desc else 'ASC'
            return query.order_by(sasql.text('{0} {1}'.format(self.key, direction)))
        if flag_desc:
            return query.order_by(self.expr.desc())
        return query.order_by(self.expr)

    def __repr__(self):
        return '<Column "{0.key}" from "{0.grid}">'.format(self)

    def xls_width_calc(self, value):
        """Calculate a width to use for an Excel renderer.

        Defaults to the `xls_width` attribute, if it is set to a non-zero value. Otherwise,
        use the length of the stringified value.
        """
        if self.xls_width:
            return self.xls_width
        if isinstance(value, six.string_types):
            return len(value)
        return len(str(value))


class LinkColumnBase(Column):
    """Base class for columns rendering as links in HTML.

    Expects a subclass to supply a `create_url` method for defining the link target.

    Notable args:
        link_label (str, optional): Caption to use instead of extracted data from the record.

    Class attributes:
        link_attrs (dict): Additional attributes to render on the A tag.

    """
    link_attrs = {}

    def __init__(self, label, key=None, filter=None, can_sort=True,
                 link_label=None, xls_width=None, xls_num_format=None,
                 render_in=_None, has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key, filter, can_sort, xls_width,
                         xls_num_format, render_in, has_subtotal, visible,
                         group=group, **kwargs)
        self.link_label = link_label

    def link_to(self, label, url, **kwargs):
        """Basic render of an anchor tag."""
        return self.grid.html._render_jinja(
            '<a href="{{url}}" {{- attrs|wg_attributes }}>{{label}}</a>',
            url=url,
            attrs=kwargs,
            label=label
        )

    def render_html(self, record, hah):
        """Renderer override for HTML to set up a link rather than using the raw data value."""
        url = self.create_url(record)
        if self.link_label is not None:
            label = self.link_label
        else:
            label = self.extract_and_format_data(record)
        return self.link_to(label, url, **self.link_attrs)

    def create_url(self, record):
        """Generate a URL from the given record.

        Expected to be overridden in subclass.
        """
        raise NotImplementedError('create_url() must be defined on a subclass')


class BoolColumn(Column):
    """Column rendering values as True/False (or the given labels).

    Notable args:
        reverse (bool, optional): Switch true/false cases.

        true_label (str, optional): String to use for the true case.

        false_label (str, optional): String to use for the false case.
    """
    json_type_helper = 'boolean'

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 reverse=False, true_label=_('True'), false_label=_('False'),
                 xls_width=None, xls_num_format=None, render_in=_None, has_subtotal=False,
                 visible=True, group=None, **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, xls_width,
                         xls_num_format, render_in,
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
    """BoolColumn rendering values as Yes/No.

    Notable args:
        reverse (bool, optional): Switch true/false cases.

    """

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 reverse=False, xls_width=None, xls_num_format=None, render_in=_None,
                 has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, reverse,
                         _('Yes'), _('No'), xls_width, xls_num_format,
                         render_in, has_subtotal, visible, group=group, **kwargs)


class DateColumnBase(Column):
    """Base column for rendering date values in specified formats.

    Designed to work with Python date/datetime/time and Arrow.

    Notable args/attributes:
        html_format (str, optional): Date format string for HTML.

        csv_format (str, optional): Date format string for CSV.

        xls_num_format (str, optional): Date format string for Excel.

    """

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 html_format=None, csv_format=None, xls_width=None,
                 xls_num_format=None, render_in=_None, has_subtotal=False, visible=True, group=None,
                 **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, xls_width,
                         xls_num_format, render_in, has_subtotal,
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

    def render_xlsx(self, record):
        data = self.extract_and_format_data(record)
        if not data:
            return data
        # if we have an arrow date, pull the underlying datetime, else the renderer won't know
        #   how to handle it
        if arrow and isinstance(data, arrow.Arrow):
            data = data.datetime
        # Excel can't use timezone data, so strip it out
        if isinstance(data, dt.datetime) and data.tzinfo is not None:
            data = data.replace(tzinfo=None)
        return data

    def render_csv(self, record):
        data = self.extract_and_format_data(record)
        if not data:
            return data
        return self._format_datetime(data, self.csv_format)

    def xls_width_calc(self, value):
        """Determine approximate width from value.

        Value will be a date or datetime object, format as if it was going
        to be in HTML as an approximation of its format in Excel.
        """
        if self.xls_width:
            return self.xls_width
        try:
            html_version = value.strftime(self.html_format)
            return len(html_version)
        except AttributeError as e:
            if "has no attribute 'strftime'" not in str(e):
                raise
            # must be the column heading
            return Column.xls_width_calc(self, value)


class DateColumn(DateColumnBase):
    """Column for rendering date values in specified formats.

    Designed to work with Python date and Arrow.

    Notable args/attributes:
        html_format (str, optional): Date format string for HTML.

        csv_format (str, optional): Date format string for CSV.

        xls_num_format (str, optional): Date format string for Excel.

    """
    # !!!: localize
    html_format = '%m/%d/%Y'
    csv_format = '%Y-%m-%d'
    xls_num_format = 'm/dd/yyyy'
    json_type_helper = 'date'


class DateTimeColumn(DateColumnBase):
    """Column for rendering datetime values in specified formats.

    Designed to work with Python datetime and Arrow.

    Notable args/attributes:
        html_format (str, optional): Date format string for HTML.

        csv_format (str, optional): Date format string for CSV.

        xls_num_format (str, optional): Date format string for Excel.

    """
    # !!!: localize
    html_format = '%m/%d/%Y %I:%M %p'
    csv_format = '%Y-%m-%d %H:%M:%S%z'
    xls_num_format = 'mm/dd/yyyy hh:mm am/pm'
    json_type_helper = 'datetime'


class TimeColumn(DateColumnBase):
    """Column for rendering time values in specified formats.

    Designed to work with Python time and Arrow.

    Notable args/attributes:
        html_format (str, optional): Date format string for HTML.

        csv_format (str, optional): Date format string for CSV.

        xls_num_format (str, optional): Date format string for Excel.

    """
    # !!!: localize
    html_format = '%I:%M %p'
    csv_format = '%H:%M'
    xls_num_format = 'hh:mm am/pm'
    json_type_helper = 'time'


class NumericColumn(Column):
    """Column for rendering formatted number values.

    Notable args:
        format_as (str, optional): Generic formats. Default "general".
        - general: thousands separator and decimal point
        - accounting: currency symbol, etc.
        - percent: percentage symbol, etc.

        places (int, optional): Decimal places to round to for general. Default 2.

        curr (str, optional): Currency symbol for general. Default empty string.

        sep (str, optional): Thousands separator. Default empty string.

        dp (str, optional): Decimal separator. Default empty string.

        pos (str, optional): Positive number indicator. Default empty string.

        neg (str, optional): Negative number indicator for general. Default empty string.

        trailneg (str, optional): Negative number suffix. Default empty string.

        xls_neg_red (bool, optional): Renders negatives in red for Excel. Default True.

    Class attributes:
        `xls_fmt_general`, `xls_fmt_accounting`, `xls_fmt_percent` are Excel number
        formats used for the corresponding `format_as` setting.
    """
    # !!!: localize
    xls_fmt_general = '#,##0{dec_places};{neg_prefix}-#,##0{dec_places}'
    xls_fmt_accounting = '_($* #,##0{dec_places}_);{neg_prefix}_($* (#,##0{dec_places})' + \
                         ';_($* "-"??_);_(@_)'
    xls_fmt_percent = '0{dec_places}%;{neg_prefix}-0{dec_places}%'

    def __init__(self, label, key_or_filter=None, key=None, can_sort=True,
                 reverse=False, xls_width=None, xls_num_format=None,
                 render_in=_None, format_as='general', places=2, curr='',
                 sep=',', dp='.', pos='', neg='-', trailneg='',
                 xls_neg_red=True, has_subtotal=False, visible=True, group=None, **kwargs):
        super().__init__(label, key_or_filter, key, can_sort, xls_width,
                         xls_num_format, render_in,
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
        self.json_type_helper = f'number_{format_as}'

    def html_decimal_format_opts(self, data):
        """Return tuple of options to expand for decimalfmt arguments.

        `places`, `curr`, `neg`, and `trailneg` attributes are passed through unless `format_as`
        is "accounting".
        """
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
        """HTML render override for numbers.

        If format is percent, the value is multiplied by 100 to get the render value.

        Negative values are given a "negative" CSS class in the render.
        """
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
        """Apply places and xls_neg_red settings to the given number format string."""
        neg_prefix = '[RED]' if self.xls_neg_red else ''
        dec_places = '.'.ljust(self.places + 1, '0') if self.places else ''
        return fmt_str.format(dec_places=dec_places, neg_prefix=neg_prefix)

    def get_num_format(self):
        """Match format_as setting to one of the format strings in class attributes."""
        if self.format_as == 'general':
            return self.xls_construct_format(self.xls_fmt_general)
        if self.format_as == 'percent':
            return self.xls_construct_format(self.xls_fmt_percent)
        if self.format_as == 'accounting':
            return self.xls_construct_format(self.xls_fmt_accounting)
        return None

    @property
    def xlsx_style(self):
        """Number format for XLSX target."""
        return {
            'num_format': self.get_num_format()
        }


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
    r"""Represents a grouping of grid columns which may be rendered within a group label.

    Args:
        label (str): Grouping label to be rendered for the column set.
        class\_ (str): CSS class name to apply in HTML rendering.
    """  # noqa: W605
    label = None
    class_ = None

    def __init__(self, label, class_=None):
        self.label = label
        self.class_ = class_


class QueryStringBuilder:
    arg_factories = (
        'session',
        'search',
        'paging',
        'sort',
        'filter',
    )

    def __init__(self, grid, include_session=False):
        self.grid = grid
        self.include_session = include_session

    def __call__(self):
        return self.build()

    def args_session(self):
        if not self.include_session:
            return []
        return [('session_key', self.grid.session_key)]

    def args_search(self):
        if not self.grid.search_value:
            return []
        return [('search', self.grid.search_value)]

    def args_paging(self):
        grid_args = []
        if self.grid.on_page != self.grid.__class__.on_page:
            grid_args.append(('onpage', self.grid.on_page))
        if self.grid.per_page != self.grid.__class__.per_page:
            grid_args.append(('perpage', self.grid.per_page))
        return grid_args

    def args_sort(self):
        # sort args are stored as tuple of (key, flag_desc)
        return map(
            lambda item: (f'sort{item[0]}', ('-' if item[1][1] else '') + item[1][0]),
            enumerate(self.grid.order_by, 1),
        )

    def args_filter(self):
        # for any filters, we only want to include args if the filter is set
        grid_args = []
        for col in self.grid.filtered_cols.values():
            _filter = col.filter
            if not _filter.is_active:
                continue
            grid_args.append((f'op({col.key})', _filter.op))
            if _filter.value1:
                grid_args.extend(map(
                    lambda item: (f'v1({col.key})', item),
                    tolist(_filter.value1),
                ))
            if _filter.value2:
                grid_args.append((f'v2({col.key})', _filter.value2))
        return grid_args

    def build(self):
        grid_args = []
        for _factory_key in self.arg_factories:
            grid_args.extend(getattr(self, f'args_{_factory_key}')())

        # note: sorting is not strictly necessary but ensures order of keys for testing
        return url_encode(MultiDict(grid_args), sort=True)


class BaseGrid(six.with_metaclass(_DeclarativeMeta, object)):
    r"""WebGrid grid base class.

    Handles class declarative-style grid description of columns, filterers, and rendering.

    The constructor is responsible for:

    - setting initial attributes
    - initializing renderers
    - setting up columns for the grid instance
    - running the grid's `post_init` method

    Args:
        ident (str, optional): Identifier value for ident instance property. Defaults to None.

        per_page (int, optional): Default number of records per page. Defaults to _None.

        on_page (int, optional): Default starting page. Defaults to _None.

        qs_prefix (str, optional): Arg name prefix to apply in query string. Useful for having
        multiple unconnected grids on a single page. Defaults to ''.

        class\_ (str, optional): CSS class name for main grid div. Defaults to 'datagrid'.

    Class Attributes:
        identifier (str): Optional string identifier used for the ident property.

        sorter_on (bool): Enable HTML sorting UX. Default True.

        pager_on (bool): Enable record limits in queries and HTML pager UX. Default True.

        per_page (int): Default number of records per page, can be overridden in constructor
        or through query string args. Default 50.

        on_page (int): Default page number, can be overridden in constructor or through
        query string args. Default 1.

        hide_controls_box (bool): Hides HTML filter/page/sort/count UX. Default False.

        session_on (bool): Enable web context session storage of grid filter/page/sort args.
        Default True.

        subtotals (string): Enable subtotals. Can be none|page|grand|all. Default "none".

        manager (Manager): Framework plugin for the web context, such as webgrid.flask.WebGrid.

        allowed_export_targets (dict[str, Renderer]): Map non-HTML export targets to the
        Renderer classes.

        enable_search (bool): Enable single-search UX. Default True.

        unconfirmed_export_limit (int): Ask for confirmation before exporting more than this many
        records. Set to None to disable. Default 10000.

        query_select_from (selectable): Entity, table, or other selectable(s) to use as the query
        from. If attributes like query_filter are used along with select_from, SQLAlchemy may
        require the select_from to precede the filtering.

        query_joins (tuple): Tuple of joins to bring the query together for all columns. May
        have just the join object, or also conditions.
        e.g. [Blog], ([Blog.category], ), or [(Blog, Blog.active == sa.true())]
        Note, relationship attributes must be referenced within tuples, due to SQLAlchemy magic.

        query_outer_joins (tuple): Tuple of outer joins. See query_joins.

        query_filter (tuple): Filter parameter(s) tuple to be used on the query.
        Note, relationship attributes must be referenced within tuples, due to SQLAlchemy magic.

        query_default_sort (tuple): Parameter(s) tuple to be passed to order_by if sort options
        are not set on the grid.
        Note, relationship attributes must be referenced within tuples, due to SQLAlchemy magic.

    """  # noqa: W605
    __cls_cols__ = ()
    identifier = None
    sorter_on = True
    pager_on = True
    per_page = 50
    on_page = 1
    hide_controls_box = False
    # enables keyed session store of grid arguments
    session_on = True
    # enables page/grand subtotals: none|page|grand|all
    subtotals = 'none'
    manager = None
    allowed_export_targets = None
    # Enables single-search feature, where one search value is applied to every supporting
    # filter at once
    enable_search = True

    # Base selectable(s) to be used in the FROM clause of the query
    query_select_from = None
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

        if self.allowed_export_targets is None:
            self.allowed_export_targets = {}
            # If the grid doesn't define any export targets
            # lets setup the export target for xlsx if we have the requirement
            if openpyxl or xlsxwriter:
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
        """Create column instances to attach to a grid instance.

        Columns set up in the declarative grid description are instances bound to the grid
        class. When the grid is instantiated, those column instances need to be copied over
        to the grid instance.

        Columns are responsible for their own "copy" process with the `new_instance` method.
        """
        for col in self.__cls_cols__:
            self.add_column(col)

    def add_column(self, column):
        new_col = column.new_instance(self)
        self.columns.append(new_col)
        self.key_column_map[new_col.key] = new_col
        if new_col.filter is not None:
            self.filtered_cols[new_col.key] = new_col
        if new_col.has_subtotal is not False and new_col.has_subtotal is not None:
            self.subtotal_cols[new_col.key] = (
                subtotal_function_map(new_col.has_subtotal),
                new_col
            )

    def drop_columns(self, column_keys):
        self.columns = list(filter(
            lambda col: col.key not in tolist(column_keys),
            self.columns
        ))
        for key in tolist(column_keys):
            self.key_column_map.pop(key, None)
            self.filtered_cols.pop(key, None)
            self.subtotal_cols.pop(key, None)

    def post_init(self):
        """Provided for subclasses to run post-initialization customizations.
        """
        pass

    def set_column_order(self, column_keys):
        """Most renderers output columns in the order they appear in the grid's ``columns``
        list. When bringing mixins together or subclassing a grid, however, the order is
        often not what is intended.

        This method allows a manual override of column order, based on keys."""
        key_check = set(column_keys) - set(self.key_column_map.keys())
        if key_check:
            raise Exception(f'Keys not recognized on grid: {key_check}')

        self.columns = [
            self.key_column_map[key] for key in column_keys
        ]

    def before_query_hook(self):
        """Hook to give subclasses a chance to change things before executing the query.
        """
        pass

    def build(self, grid_args=None):
        """Apply query args, run `before_query_hook`, and execute a record count query.

        Calling `build` is preferred to simply calling `apply_qs_args` in a view. Otherwise,
        AttributeErrors can be hidden when the grid is used in Jinja templates.
        """
        self.apply_qs_args(grid_args=grid_args)
        self.before_query_hook()
        # this will force the query to execute.  We used to wait to evaluate this but it ended
        # up causing AttributeErrors to be hidden when the grid was used in Jinja.
        # Calling build is now preferred over calling .apply_qs_args() and then .html()
        self.record_count

    def check_auth(self):
        """For API usage, provides a hook for grids to specify authorization that should be
        applied for the API responder method.

        If a 40* response is warranted, take that action here.

        Note, this method is not part of normal grid/render operation. It will only be
        executed if run by a calling layer, such as the Flask WebGridAPI manager/extension.
        """
        pass

    def column(self, ident):
        """Retrieve a grid column instance via either the key string or index int.

        Args:
            ident (Union[str, int]): Key/index for lookup.

        Returns:
            Column: Instance column matching the ident.

        Raises:
            KeyError when ident is a string not matching any column.

            IndexError when ident is an int but out of bounds for the grid.
        """
        if isinstance(ident, six.string_types):
            return self.key_column_map[ident]
        return self.columns[ident]

    def has_column(self, ident):
        """Verify string key or int index is defined for the grid instance.

        Args:
            ident (Union[str, int]): Key/index for lookup.

        Returns:
            bool: Indicates whether key/index is in the grid columns.

        """
        if ident is None:
            return False
        if isinstance(ident, six.string_types):
            return ident in self.key_column_map
        return 0 <= ident < len(self.columns)

    def get_unique_column_key(self, key):
        """Apply numeric suffix to a field key to make the key unique to the grid.

        Helpful for when multiple entities are represented in grid columns but have
        the same field names.

        For instance, Blog.label and Author.label both have the field name `label`.
        The first column will have the `label` key, and the second will get `label_1`.

        Args:
            key (str): field key to make unique.

        Returns:
            str: unique key that may be assigned in the grid's `key_column_map`.
        """
        suffix_counter = 0
        new_key = key
        while self.has_column(new_key):
            suffix_counter += 1
            new_key = '{}_{}'.format(key, suffix_counter)
        return new_key

    def iter_columns(self, render_type):
        """Generator yielding columns that are visible and enabled for target `render_type`.

        Args:
            render_type (str): [description]

        Yields:
            Column: Grid instance's column instance that is renderable for `render_type`.
        """
        for col in self.columns:
            if col.visible and render_type in col.render_in:
                yield col

    def can_search(self):
        """Grid `enable_search` attr turns on search, but check if there are supporting filters.

        Returns:
            bool: search enabled and supporting filters exist
        """
        return self.enable_search and len(self.search_expression_generators) > 0

    @property
    def search_expression_generators(self):
        """Get single-search query modifier factories from the grid filters.

        Raises:
            Exception: filter's `get_search_expr` did not return None or callable

        Returns:
            tuple(callable): search expression callables from grid filters
        """
        is_aggregate = self.search_uses_aggregate

        # We filter out None here so as to disregard filters that don't support the search feature.
        def check_expression_generator(expr_gen):
            if expr_gen is not None and not callable(expr_gen):
                raise Exception(
                    'bad filter search expression: {} is not callable'.format(str(expr_gen))
                )
            return expr_gen is not None

        # Also conditionally filter aggregate/non-aggregate so we're not mixing expression types.
        return tuple(filter(
            check_expression_generator,
            [col.filter.get_search_expr() for col in self.filtered_cols.values()
             if col.filter.is_aggregate is is_aggregate]
        ))

    @property
    def search_uses_aggregate(self):
        """Determine whether search should use aggregate filtering.

        By default, only use the HAVING clause if all search-enabled filters are marked
        as aggregate. Otherwise, we'd be requiring all grid columns to be in query
        grouping. If there are filters for search that are not aggregate, the grid will
        only search on the non-aggregate columns.

        Returns:
            bool: search aggregate usage determined from filter info
        """
        has_search = False
        for col in self.filtered_cols.values():
            if col.filter.get_search_expr() is not None:
                has_search = True
                if not col.filter.is_aggregate:
                    return False
        return has_search

    def set_renderers(self):
        """Renderers assigned as attributes on the grid instance, named by render target.
        """
        self.html = HTML(self)
        for key, value in self.allowed_export_targets.items():
            setattr(self, key, value(self))

    def set_filter(self, key, op, value, value2=None):
        """Set filter parameters on a column's filter. Resets record cache.

        Args:
            key (str): Column identifier
            op (str): Operator
            value (Any): First filter value
            value2 (Any, optional): Second filter value if applicable. Defaults to None.
        """
        self.clear_record_cache()
        self.filtered_cols[key].filter.set(op, value, value2=value2)

    def set_sort(self, *args):
        """Set sort parameters for main query. Resets record cache.

        If keys are passed in that do not belong to this grid, raise user warnings
        (not exceptions). These warnings are suppressed if the grid has a "foreign"
        session assigned (i.e. two grids share some of the same columns, and should
        load as much information as possible from the shared session key).

        Args:
            Each arg is expected to be a column key. If the sort is to be descending for
            that key, prepend with a "-".
            E.g. `grid.set_sort('author', '-post_date')`
        """
        self.clear_record_cache(preserve_count=True)
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
        """Set paging parameters for the main query. Resets record cache.

        Args:
            per_page (int): Record limit for each page.
            on_page (int): With `per_page`, computes the offset.
        """
        self.clear_record_cache(preserve_count=True)
        self.per_page = per_page
        self.on_page = on_page

    def clear_record_cache(self, preserve_count=False):
        """Reset records and record count cached from previous queries.

        Args:
            preserve_count (bool): Direct grid to retain count of records, effectively removing
            only the table of records itself.
        """
        if not preserve_count:
            self._record_count = None
        self._records = None

    @property
    def ident(self):
        return self._ident \
            or self.identifier \
            or case_cw2us(self.__class__.__name__)

    @property
    def default_session_key(self):
        return f'_{self.__class__.__name__}'

    @property
    def has_filters(self):
        """Indicates whether filters will be applied in `build_query`.

        Returns:
            bool: True if filter(s) have op/value set or single search value is given.
        """
        for col in six.itervalues(self.filtered_cols):
            if col.filter.is_active:
                return True
        return self.search_value is not None

    @property
    def has_sort(self):
        """Indicates whether ordering will be applied in `build_query`.

        Returns:
            bool: True if grid's `order_by` list is populated.
        """
        return bool(self.order_by)

    @property
    def record_count(self):
        """Count of records for current filtered query.

        Value is cached to prevent duplicate query execution. Methods changing
        the query (e.g. `set_filter`) will reset the cached value.

        Returns:
            int: Count of records.
        """
        if self._record_count is None:
            query = self.build_query(for_count=True)
            t0 = time.perf_counter()
            self._record_count = query.count()
            t1 = time.perf_counter()
            log.debug('Count query ran in {} seconds'.format(t1 - t0))
        return self._record_count

    @property
    def records(self):
        """Records returned for current filtered/sorted/paged query.

        Result is cached to prevent duplicate query execution. Methods changing
        the query (e.g. `set_filter`) will reset the cached result.

        Returns:
            list(Any): Result records from SQLAlchemy query.
        """
        if self._records is None:
            query = self.build_query()
            t0 = time.perf_counter()
            self._records = query.all()
            t1 = time.perf_counter()
            log.debug('Data query ran in {} seconds'.format(t1 - t0))
        return self._records

    def _totals_col_results(self, page_totals_only):
        """Executes query to retrieve subtotals for the filtered query.

        A single result record is returned, which will have fields corresponding to all of the
        grid columns (same as a record returned in the general records query).

        Args:
            page_totals_only (bool): Tells query builder to use only current page records.

        Returns:
            Any: Single result record.
        """
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
        """Executes query to retrieve subtotals for the filtered query on the current page.

        For page totals to be queried/returned, the grid's `subtotals` must be page/all
        and one or more columns must have subtotals configured.

        A single result record is returned, which will have fields corresponding to all of the
        grid columns (same as a record returned in the general records query).

        Returns:
            Any: Single result record, or None if page totals are not configured.
        """
        if (
            self._page_totals is None
            and self.subtotals in ('page', 'all')
            and self.subtotal_cols
        ):
            self._page_totals = self._totals_col_results(page_totals_only=True)
        return self._page_totals

    @property
    def grand_totals(self):
        """Executes query to retrieve subtotals for the filtered query.

        For grand totals to be queried/returned, the grid's `subtotals` must be grand/all
        and one or more columns must have subtotals configured.

        A single result record is returned, which will have fields corresponding to all of the
        grid columns (same as a record returned in the general records query).

        Returns:
            Any: Single result record, or None if grand totals are not configured.
        """
        if (
            self._grand_totals is None
            and self.subtotals in ('grand', 'all')
            and self.subtotal_cols
        ):
            self._grand_totals = self._totals_col_results(page_totals_only=False)
        return self._grand_totals

    @property
    def page_count(self):
        """Page count, or 1 if no `per_page` is set.
        """
        if self.per_page is None:
            return 1
        return max(0, self.record_count - 1) // self.per_page + 1

    def build_query(self, for_count=False):
        """Constructs, but does not execute, a grid query from columns and configuration.

        This is the query the grid functions trust for results for records, count, page
        count, etc. Customization of the query should happen here or in the methods called
        within.

        Build sequence:
        - `query_base`
        - `query_prep`
        - `query_filters`
        - `query_sort`
        - `query_paging`

        Args:
            for_count (bool, optional): Excludes sort/page from query. Defaults to False.

        Returns:
            Query: SQLAlchemy query object
        """
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
        """Assign a set of records to the grid's cache.

        Useful for simple grids that simply need to be rendered as a table. Note that any
        ops performed on the grid, such as setting filter/sort/page options, will clear this
        cached information.

        Args:
            records (list(Any)): List of record objects that can be referenced for column data.
        """
        self._record_count = len(records)
        self._records = records

    def query_base(self, has_sort, has_filters):
        """Construct a query from grid columns, using grid's join/filter/sort attributes.

        Used by `build_query` to establish the basic query from column spec. If query is to be
        modified, it is recommended to do so in `query_prep` if possible, rather than overriding
        `query_base`.

        Args:
            has_sort (bool): Tells method not to order query, since the grid has sort params.
            has_filters (bool): Tells method if grid has filter params. Not used.

        Returns:
            Query: SQLAlchemy query
        """
        for idx, column in enumerate(filter(lambda col: col.expr is not None, self.columns)):
            column._query_idx = idx
        cols = [col.expr for col in self.columns if col.expr is not None]
        query = self.manager.sa_query(*cols)

        if self.query_select_from is not None:
            query = query.select_from(*tolist(self.query_select_from))

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
        """Modify the query that was constructed in `query_base`.

        Joins, query filtering, and default sorting can be applied via grid attributes. However,
        sometimes grid queries need columns added, instance-time modifications applied, etc.

        Called by `build_query`.

        Args:
            query (Query): SQLAlchemy query object.
            has_sort (bool): Tells method grid has sort params defined.
            has_filters (bool): Tells method if grid has filter params.

        Returns:
            Query: SQLAlchemy query
        """
        return query

    def query_filters(self, query):
        """Modify the query by applying filter terms.

        Called by `build_query` to apply any column filters as needed. Also enacts
        the single-search value if specified.

        Args:
            query (Query): SQLAlchemy query object.

        Returns:
            Query: SQLAlchemy query
        """
        filter_display = []
        if self.search_value:
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
        """Modify the query by applying a filter term constructed from search clauses.

        Calls each filter search expression factory with the search value to get a search
        clause, then ORs them all together for the main query.

        Args:
            query (Query): SQLAlchemy query.
            value (str): Search value.

        Returns:
            Query: SQLAlchemy query
        """
        filter_method = query.having if self.search_uses_aggregate else query.filter
        filter_clauses = list(filter(
            lambda item: item is not None,
            (expr(value) for expr in self.search_expression_generators)
        ))

        if not filter_clauses:
            return query
        return filter_method(sa.or_(*filter_clauses))

    def query_paging(self, query):
        """Modify the query by applying limit/offset to match grid parameters.

        Args:
            query (Query): SQLAlchemy query.

        Returns:
            Query: SQLAlchemy query
        """
        if self.on_page and self.per_page:
            offset = (self.on_page - 1) * self.per_page
            query = query.offset(offset).limit(self.per_page)
            log.debug('Page {}; {} per page'.format(self.on_page, self.per_page))
        return query

    def query_sort(self, query):
        """Modify the query by applying sort to match grid parameters.

        Args:
            query (Query): SQLAlchemy query.

        Returns:
            Query: SQLAlchemy query
        """
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
            and not query._order_by_clauses
        ):
            query = self._fix_mssql_order_by(query)

        return query

    def _fix_mssql_order_by(self, query):
        """MSSQL must have an ORDER BY for paging to work. If no sort clause has been
        defined, sort by the first column. If that doesn't work, error out.
        """
        if len(self.columns):
            query = self.columns[0].apply_sort(query, False)
            if query._order_by_clauses:
                return query
        raise Exception(
            'Paging is enabled, but query does not have ORDER BY clause required for MSSQL'
        )

    def build_qs_args(self, include_session=False):
        """Build a URL query string based on current grid attributes.

        This is designed to be framework-agnostic and not require a request context. Usually
        the result would be used in a background task or similar (i.e. outside the flow of the
        rendered grid), so typically the session key is unnecessary.

        Args:
            include_session (bool, optional): Include session_key in the string. Defaults to False.
        """
        return QueryStringBuilder(self, include_session)()

    def apply_qs_args(self, add_user_warnings=True, grid_args=None):
        """Process args from manager for filter/page/sort/export.

        Args:
            add_user_warnings (bool, optional): Add flash messages for warnings. Defaults to True.
            grid_args (MultiDict, optional): Supply args directly to the grid.
        """
        args = grid_args if grid_args is not None else self.manager.get_args(self)

        if self.session_on:
            self.session_key = args.get('session_key') or self.session_key
            self.foreign_session_loaded = args.get('__foreign_session_loaded__', False)

        # search
        self._apply_search(args)

        # filtering (make sure this is above paging otherwise self.page_count
        # used in the paging section below won't work)
        self._apply_filtering(args)

        # paging
        self._apply_paging(args)

        # sorting
        self._apply_sorting(args)

        # export
        self._apply_export(args)

        # Having this here is not ideal. Due to separation of concerns, it would be nice to
        #   have flash warnings in the HTML renderer. However, by the time the renderer is
        #   called, an app template has probably already loaded and rendered any messages to
        #   be shown, and it's too late to add new ones.
        if add_user_warnings:
            for msg in self.user_warnings:
                self.manager.flash_message('warning', msg)

    def _apply_search(self, args):
        if (
            'search' in args
            and self.can_search()
        ):
            self.search_value = args['search'].strip() if args['search'] else None

    def _apply_filtering(self, args):
        """Turn request/session args into filter settings.

        Args:
            args (MultiDict): Full arguments to search for filters.
        """
        for col in six.itervalues(self.filtered_cols):
            filter = col.filter
            filter_op_qsk = 'op({0})'.format(col.key)
            filter_v1_qsk = 'v1({0})'.format(col.key)
            filter_v2_qsk = 'v2({0})'.format(col.key)

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
        """Turn request/session args into page settings.

        Args:
            args (MultiDict): Full arguments to search for paging.
        """
        pp_qsk = 'perpage'
        if pp_qsk in args:
            per_page = self.apply_validator(fev.Int, args[pp_qsk], pp_qsk)
            if per_page is None:
                per_page = self.__class__.per_page
            elif per_page < 1:
                per_page = 1
            self.per_page = per_page

        op_qsk = 'onpage'
        if op_qsk in args:
            on_page = self.apply_validator(fev.Int, args[op_qsk], op_qsk)
            if on_page is None or on_page < 1:
                on_page = 1
            if on_page > self.page_count:
                on_page = self.page_count
            self.on_page = on_page

    def _apply_sorting(self, args):
        """Turn request/session args into sort settings.

        No limit is present here for how many sort args may be passed. However, the
        args are expected to be contiguous. I.e. sort1, sort2, sort3 will be processed,
        but sort1, sort3, sort5 will only process sort1.

        Args:
            args (MultiDict): Full arguments to search for sort keys.
        """
        counter = 0
        sort_qs_values = []

        while True:
            counter += 1
            sort_arg = 'sort{}'.format(counter)
            if sort_arg not in args:
                break
            sort_qs_values.append(args[sort_arg])

        if sort_qs_values:
            self.set_sort(*sort_qs_values)

    def _apply_export(self, args):
        # handle other file formats
        self.set_export_to(args.get('export_to', None))

    def prefix_qs_arg_key(self, key):
        """Given a bare arg key, return the prefixed version that will actually be in the request.

        This is necessary for render targets that will construct ensuing requests. Prefixing is
        not needed for incoming args on internal grid ops, as long as the grid manager's
        args loaders sanitize the args properly.

        Args:
            key (str): Bare arg key.

        Returns:
            str: Prefixed arg key.
        """
        return '{0}{1}'.format(self.qs_prefix, key)

    def apply_validator(self, validator, value, qs_arg_key):
        """Apply a FormEncode validator to value, and produce a warning if invalid.

        Args:
            validator (Validator): FormEncode-style validator.
            value (str): Value to validate.
            qs_arg_key (str): Arg name to include in warning if value is invalid.

        Returns:
            Any: Output of `validator.to_python(value)`, or `None` if invalid.
        """
        try:
            return validator.to_python(value)
        except Invalid:
            invalid_msg = _('"{arg}" grid argument invalid, ignoring', arg=qs_arg_key)
            self.user_warnings.append(invalid_msg)
            return None

    def set_export_to(self, to):
        """Set export parameter after validating it exists in known targets.

        Args:
            to (str): Renderer attribute if it is known. Invalid value ignored.
        """
        if to in self.allowed_export_targets:
            self.export_to = to

    def export_as_response(self, wb=None, sheet_name=None):
        """Return renderer response for view layer to provide as a file.

        Args:
            wb (Workbook, optional): XlsxWriter Workbook. Defaults to None.
            sheet_name (Worksheet, optional): XlsxWriter Worksheet. Defaults to None.

        Raises:
            ValueError: No export parameter given.

        Returns:
            Response: Return response processed through renderer and manager.
        """
        if not self.export_to:
            raise ValueError('No export format set')
        exporter = getattr(self, self.export_to)
        if self.export_to == 'xlsx':
            return exporter.as_response(wb, sheet_name)
        return exporter.as_response()

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
