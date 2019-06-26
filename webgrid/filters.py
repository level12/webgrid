from __future__ import absolute_import
import calendar
import datetime as dt
from decimal import Decimal as D
import inspect

from blazeutils import tolist
from blazeutils.dates import ensure_date, ensure_datetime
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta, SU
import formencode
import formencode.validators as feval
from sqlalchemy.sql import or_, and_
import sqlalchemy as sa
import six

from .extensions import (
    gettext,
    lazy_gettext as _
)


class UnrecognizedOperator(ValueError):
    pass


class Operator(object):
    def __init__(self, key, display, field_type, hint=None):
        self.key = key
        self.display = display
        self.field_type = field_type
        self.hint = hint

    def __eq__(self, other):
        return self.key == getattr(other, 'key', other)

    def __hash__(self):
        return hash(self.key)


class ops(object):
    eq = Operator('eq', _('is'), 'input')
    not_eq = Operator('!eq', _('is not'), 'input')
    is_ = Operator('is', _('is'), 'select')
    not_is = Operator('!is', _('is not'), 'select')
    empty = Operator('empty', _('empty'), None)
    not_empty = Operator('!empty', _('not empty'), None)
    contains = Operator('contains', _('contains'), 'input')
    not_contains = Operator('!contains', _('doesn\'t contain'), 'input')
    less_than_equal = Operator('lte', _('less than or equal'), 'input')
    greater_than_equal = Operator('gte', _('greater than or equal'), 'input')
    between = Operator('between', _('between'), '2inputs')
    not_between = Operator('!between', _('not between'), '2inputs')
    days_ago = Operator('da', _('days ago'), 'input', 'days')
    less_than_days_ago = Operator('ltda', _('less than days ago'), 'input', 'days')
    more_than_days_ago = Operator('mtda', _('more than days ago'), 'input', 'days')
    today = Operator('today', _('today'), None)
    this_week = Operator('thisweek', _('this week'), None)
    in_less_than_days = Operator('iltd', _('in less than days'), 'input', 'days')
    in_more_than_days = Operator('imtd', _('in more than days'), 'input', 'days')
    in_days = Operator('ind', _('in days'), 'input', 'days')
    this_month = Operator('thismonth', _('this month'), None)
    last_month = Operator('lastmonth', _('last month'), None)
    select_month = Operator('selmonth', _('select month'), 'select+input')
    this_year = Operator('thisyear', _('this year'), None)


class FilterBase(object):
    operators = ops.eq, ops.not_eq, ops.empty, ops.not_empty
    # if needed, specifiy the name of attributes set on the static instance of
    # this class that should get copied over to a new instance by
    # new_instance()
    init_attrs_for_instance = ()
    # current HTML renderer allows for "input", "input2", and/or "select"
    input_types = 'input',
    # does this filter take a list of values in it's set() method
    receives_list = False

    def __init__(self, sa_col, default_op=None, default_value1=None, default_value2=None,
                 dialect=None):
        # attributes from static instance
        self.sa_col = sa_col
        self._default_op = default_op
        self.default_op = None
        self.default_value1 = default_value1
        self.default_value2 = default_value2
        self.dialect = dialect

        # attributes that will start fresh for each instance
        self.op = None
        self.value1 = None
        self.value2 = None
        self.value1_set_with = None
        self.value2_set_with = None
        self._op_keys = None
        self.error = False

        # find the outermost call to a subclass's init method so we can store the exact arguments
        # used to construct it
        outermost = None
        frame = inspect.currentframe()
        # Can't use inspect.stack() here because when called from within a Jinja template,
        # inspect.getframeinfo raises an exception
        while frame:
            if frame.f_code.co_name != '__init__' or \
                    not isinstance(frame.f_locals.get('self'), FilterBase):
                break
            outermost = inspect.getargvalues(frame)
            frame = frame.f_back

        self._vargs = [outermost.locals[a] for a in outermost.args[1:]] + \
            list(outermost.locals[outermost.varargs] if outermost.varargs else [])

        self._kwargs = outermost.locals[outermost.keywords] if outermost.keywords else {}

    @property
    def is_active(self):
        operator_by_key = {op.key: op for op in self.operators}
        return self.op is not None and not self.error and (
            operator_by_key[self.op].field_type is None or self.value1 is not None
        )

    @property
    def is_display_active(self):
        return self.op is not None

    @property
    def op_keys(self):
        if self._op_keys is None:
            self._op_keys = [op.key for op in self.operators]
        return self._op_keys

    def _default_value(self, value):
        if callable(value):
            return value()
        return value

    def set(self, op, value1, value2=None):
        if not op:
            self.default_op = self._default_op() if callable(self._default_op) else self._default_op
            self.op = self.default_op
            self.using_default_op = (self.default_op is not None)
            if self.op is None:
                return

        if not op and self.using_default_op:
            value1 = self._default_value(self.default_value1)
            value2 = self._default_value(self.default_value2)

        # set values used in display first, since processing validation may
        #   raise exceptions
        self.op = feval.OneOf(self.op_keys, not_empty=True).to_python(
            op or self.default_op
        )
        self.value1_set_with = value1
        self.value2_set_with = value2
        try:
            self.value1 = self.process(value1, False)
            self.value2 = self.process(value2, True)
        except formencode.Invalid:
            self.error = True
            raise

    def raise_unrecognized_op(self):
        raise UnrecognizedOperator(_('unrecognized operator: {op}', op=self.op))

    def apply(self, query):
        if self.op == self.default_op and self.value1 is None:
            return query
        if self.op == ops.eq:
            return query.filter(self.sa_col == self.value1)
        if self.op == ops.not_eq:
            return query.filter(self.sa_col != self.value1)
        if self.op == ops.empty:
            return query.filter(self.sa_col.is_(None))
        if self.op == ops.not_empty:
            return query.filter(self.sa_col.isnot(None))
        if self.op == ops.less_than_equal:
            return query.filter(self.sa_col <= self.value1)
        if self.op == ops.greater_than_equal:
            return query.filter(self.sa_col >= self.value1)

        self.raise_unrecognized_op()

    def process(self, value, is_value2):
        """
            Process the values as given to .set(), validating and manipulating
            as needed.
        """
        return value

    def format_invalid(self, exc, col):
        return '{0}: {1}'.format(
            col.label,
            str(exc)
        )

    def new_instance(self, **kwargs):
        """
        Note: Ensure any overrides of this method accept and pass through kwargs to preserve
        compatibility in future
        """
        cls = self.__class__
        new_filter = cls(*self._vargs, **self._kwargs)
        new_filter.dialect = kwargs.get('dialect')
        return new_filter


class _NoValue(object):
    pass


class OptionsFilterBase(FilterBase):
    operators = ops.is_, ops.not_is, ops.empty, ops.not_empty
    input_types = 'select'
    receives_list = True
    options_from = ()

    def __init__(self, sa_col, value_modifier='auto', default_op=None, default_value1=None,
                 default_value2=None):
        FilterBase.__init__(self, sa_col, default_op=default_op, default_value1=default_value1,
                            default_value2=default_value2)
        # attributes from static instance
        self.value_modifier = value_modifier

        # attributes that will start fresh for each instance
        self._options_seq = None
        self._options_keys = None

    def new_instance(self, **kwargs):
        filter = FilterBase.new_instance(self, **kwargs)
        filter.setup_validator()
        return filter

    @property
    def options_seq(self):
        if self._options_seq is None:
            try:
                self._options_seq = self.options_from()
            except TypeError as e:
                if 'is not callable' not in str(e):
                    raise
                self._options_seq = self.options_from
            if self.default_op:
                self._options_seq = [(-1, _('-- All --'))] + list(self._options_seq)
        return self._options_seq

    @property
    def option_keys(self):
        if self._options_keys is None:
            self._options_keys = [k for k, v in self.options_seq]
        return self._options_keys

    def setup_validator(self):
        # make an educated guess about what type the unicode values sent in on
        # a set() operation should be converted to
        if self.value_modifier == 'auto' or self.value_modifier is None:
            if self.value_modifier and len(self.option_keys) == 0:
                raise ValueError(_('value_modifier argument set to "auto", but '
                                   'the options set is empty and the type can therefore not '
                                   'be determined for {name}', name=self.__class__.__name__))
            first_key = self.option_keys[0]
            if isinstance(first_key, six.string_types) or self.value_modifier is None:
                self.value_modifier = feval.UnicodeString
            elif isinstance(first_key, int):
                self.value_modifier = feval.Int
            elif isinstance(first_key, float):
                self.value_modifier = feval.Number
            elif isinstance(first_key, D):
                self.value_modifier = feval.Wrapper(to_python=D)
            else:
                raise TypeError(
                    _("can't use value_modifier='auto' when option keys are {key_type}",
                      key_type=type(first_key))
                )
        else:
            # if its not the string 'auto' and its not a formencode validator, assume
            # its a callable and wrap with a formencode validator
            if not hasattr(self.value_modifier, 'to_python'):
                if not hasattr(self.value_modifier, '__call__'):
                    raise TypeError(
                        _('value_modifier must be the string "auto", have a "to_python" attribute, '
                          'or be a callable')
                    )
                self.value_modifier = feval.Wrapper(to_python=self.value_modifier)

    def set(self, op, values, value2=None):
        self.default_op = self._default_op() if callable(self._default_op) else self._default_op
        if not op and not self.default_op:
            return
        self.op = op or self.default_op
        self.using_default_op = (self.default_op is not None)

        if self.using_default_op and op is None and self.default_value1 is not None:
            values = tolist(self._default_value(self.default_value1))

        self.value1 = []
        if values is not None:
            for v in values:
                try:
                    v = self.process(v)
                    if v is not _NoValue:
                        self.value1.append(v)
                except formencode.Invalid:
                    # A normal user should be selecting from the options given,
                    # so if we encounter an Invalid exception, we are going to
                    # assume the value is erronious and just ignore it
                    pass

        # if there are no values after processing, the operator is irrelevent
        # and should be set to None so that it is as if the filter
        # is not set.
        #
        # however, we have to test the operator first, because if it is empty
        # or !empty, then it would make sense for self.value1 to be empty.
        if self.op in (ops.is_, ops.not_is) and not (self.value1 or self.default_op):
            self.op = None

    def process(self, value):
        if self.value_modifier is not None:
            value = self.value_modifier.to_python(value)
            if value not in self.option_keys:
                return _NoValue
            if self.default_op and value == -1:
                return _NoValue
        return value

    def apply(self, query):
        if self.op == ops.is_:
            if len(self.value1) == 1:
                return query.filter(self.sa_col == self.value1[0])
            elif len(self.value1) > 1:
                return query.filter(self.sa_col.in_(self.value1))
            else:
                return query
        if self.op == ops.not_is:
            if len(self.value1) == 1:
                return query.filter(self.sa_col != self.value1[0])
            elif len(self.value1) > 1:
                return query.filter(~self.sa_col.in_(self.value1))
            else:
                return query
        return FilterBase.apply(self, query)


class OptionsIntFilterBase(OptionsFilterBase):
    def __init__(self, sa_col, value_modifier=feval.Int, default_op=None, default_value1=None,
                 default_value2=None):
        OptionsFilterBase.__init__(self, sa_col, value_modifier, default_op, default_value1,
                                   default_value2)


class OptionsEnumFilter(OptionsFilterBase):
    def __init__(
            self,
            sa_col,
            value_modifier=None,
            default_op=None,
            default_value1=None,
            default_value2=None,
            enum_type=None,
    ):
        self.enum_type = enum_type
        if self.enum_type is None:
            raise ValueError('enum_type argument not given')
        if value_modifier is None:
            value_modifier = self.default_modifier
        super(OptionsEnumFilter, self).__init__(
            sa_col,
            value_modifier=value_modifier,
            default_op=default_op,
            default_value1=default_value1,
            default_value2=default_value2,
        )

    def default_modifier(self, value):
        if isinstance(value, self.enum_type):
            return value

        try:
            return self.enum_type[value]
        except KeyError:
            raise ValueError('Not a valid selection')

    def options_from(self):
        return [(x.name, x.value) for x in self.enum_type]

    def new_instance(self, **kwargs):
        new_inst = super(OptionsEnumFilter, self).new_instance(**kwargs)
        new_inst.enum_type = self.enum_type
        return new_inst

    def process(self, value):
        if self.value_modifier is None:
            return value

        return self.value_modifier.to_python(value)


class TextFilter(FilterBase):
    operators = (ops.eq, ops.not_eq, ops.contains, ops.not_contains, ops.empty, ops.not_empty)

    @property
    def comparisons(self):
        if self.dialect and self.dialect.name in ('postgresql', 'sqlite'):
            return {
                ops.eq: lambda col, value: sa.func.upper(col) == sa.func.upper(value),
                ops.not_eq: lambda col, value: sa.func.upper(col) != sa.func.upper(value),
                ops.contains: lambda col, value: col.ilike(u'%{}%'.format(value)),
                ops.not_contains: lambda col, value: ~col.ilike(u'%{}%'.format(value))
            }
        return {
            ops.eq: lambda col, value: col == value,
            ops.not_eq: lambda col, value: col != value,
            ops.contains: lambda col, value: col.like(u'%{}%'.format(value)),
            ops.not_contains: lambda col, value: ~col.like(u'%{}%'.format(value))
        }

    def apply(self, query):
        if self.op == self.default_op and not self.value1:
            return query
        if self.op == ops.empty:
            return query.filter(or_(
                self.sa_col.is_(None),
                self.sa_col == u'',
            ))
        if self.op == ops.not_empty:
            return query.filter(and_(
                self.sa_col.isnot(None),
                self.sa_col != u'',
            ))

        if self.op in self.comparisons:
            return query.filter(self.comparisons[self.op](self.sa_col, self.value1))
        return FilterBase.apply(self, query)


class NumberFilterBase(FilterBase):
    operators = (ops.eq, ops.not_eq, ops.less_than_equal, ops.greater_than_equal, ops.empty,
                 ops.not_empty)

    def process(self, value, is_value2):
        if self.op == self.default_op and not value:
            return None
        if self.op in (ops.eq, ops.not_eq, ops.less_than_equal,
                       ops.greater_than_equal) and not is_value2:
            return self.validator(not_empty=True).to_python(value)
        return self.validator.to_python(value)


class IntFilter(NumberFilterBase):
    validator = feval.Int


class NumberFilter(NumberFilterBase):
    """
        Same as int filter, but will handle real numbers and type
        everything as a decimal.Decimal object
    """
    # our process() doesn't use a validator to return, but parent class does
    validator = feval.Number

    def process(self, value, is_value2):
        # call the validator to ensure the value is in the right format, but
        # don't use its value b/c it converts to float
        NumberFilterBase.process(self, value, is_value2)
        if value is None or (isinstance(value, six.string_types) and not len(value)):
            return None
        return D(value)


class _DateMixin(object):
    options_from = [
        (1, _('01-Jan')), (2, _('02-Feb')), (3, _('03-Mar')), (4, _('04-Apr')),
        (5, _('05-May')), (6, _('06-Jun')), (7, _('07-Jul')), (8, _('08-Aug')),
        (9, _('09-Sep')), (10, _('10-Oct')), (11, _('11-Nov')), (12, _('12-Dec')),
    ]

    @property
    def options_seq(self):
        _options_seq = self.options_from
        if self.default_op:
            _options_seq = [(-1, _('-- All --'))] + _options_seq
        return _options_seq

    def format_display_vals(self):
        if isinstance(self.value1, dt.date) and self.op in (
            ops.eq.key,
            ops.not_eq.key,
            ops.less_than_equal.key,
            ops.greater_than_equal.key,
            ops.between.key,
            ops.not_between.key
        ):
            # !!!: localize
            self.value1_set_with = self.value1.strftime('%m/%d/%Y')
        if isinstance(self.value2, dt.date) and self.op in (
            ops.between.key,
            ops.not_between.key
        ):
            # !!!: localize
            self.value2_set_with = self.value2.strftime('%m/%d/%Y')

    @property
    def description(self):
        """
            String description of the filter operation and values
            - Useful for Excel reports
        """
        today = self._get_today()
        last_day = first_day = None
        prefix = ''

        if self.error:
            return _('invalid')

        # these filters can be set as default ops without input values, so don't ignore them
        if self.op == ops.this_month:
            last_day = today + relativedelta(day=1, months=+1, days=-1)
            first_day = today + relativedelta(day=1)
        elif self.op == ops.last_month:
            last_day = today + relativedelta(day=1, days=-1)
            first_day = today + relativedelta(day=1, months=-1)
        elif self.op == ops.this_year:
            last_day = dt.date(today.year, 12, 31)
            first_day = dt.date(today.year, 1, 1)
        elif self.op == ops.this_week:
            first_day = today - relativedelta(weekday=SU(-1))
            last_day = today + relativedelta(weekday=calendar.SATURDAY)
        elif self.op == ops.today:
            first_day = today

        if not first_day and (
            not self.op or (
                self.default_op == self.op and (
                    self.value2 is None and self.value1 is None
                )
            )
        ):
            return _('all')

        # ops with both dates populated
        if self.op == ops.select_month:
            if not (
                isinstance(self.value1, int) and isinstance(self.value2, int)
            ):
                return _('All')
            if self.value1 < 1 or self.value1 > 12:
                return self.value2
            # !!!: localize
            return dt.date(self.value2, self.value1, 1).strftime('%b %Y')
        elif self.op in (ops.between, ops.not_between):
            if self.value1 <= self.value2:
                first_day = self.value1
                last_day = self.value2
            else:
                first_day = self.value2
                last_day = self.value1
            if self.op == ops.not_between:
                prefix = _('excluding ')
        elif self.op == ops.less_than_days_ago:
            first_day = today - dt.timedelta(days=self.value1)
            last_day = today
        elif self.op == ops.in_less_than_days:
            last_day = today + dt.timedelta(days=self.value1)
            first_day = today

        if last_day and first_day:
            # !!!: localize dates
            return _('{descriptor}{first_date} - {second_date}',
                     descriptor=prefix,
                     first_date=first_day.strftime('%m/%d/%Y'),
                     second_date=last_day.strftime('%m/%d/%Y'))

        # ops with single date populated
        if self.op in (ops.days_ago, ops.more_than_days_ago):
            first_day = today - dt.timedelta(days=self.value1)
            if self.op == ops.more_than_days_ago:
                prefix = _('before ')
        elif self.op in (ops.in_days, ops.in_more_than_days):
            first_day = today + dt.timedelta(days=self.value1)
            if self.op == ops.in_more_than_days:
                prefix = _('after ')
        elif self.op == ops.empty:
            return _('date not specified')
        elif self.op == ops.not_empty:
            return _('any date')
        elif self.op in (ops.eq, ops.not_eq, ops.less_than_equal, ops.greater_than_equal):
            first_day = self.value1
            if self.op == ops.not_eq:
                prefix = _('excluding ')
            elif self.op == ops.less_than_equal:
                prefix = _('up to ')
            elif self.op == ops.greater_than_equal:
                prefix = _('beginning ')
        # !!!: localize
        return _('{descriptor}{date}',
                 descriptor=prefix,
                 date=first_day.strftime('%m/%d/%Y'))


class DateFilter(FilterBase, _DateMixin):
    operators = (
        ops.eq, ops.not_eq, ops.less_than_equal,
        ops.greater_than_equal, ops.between, ops.not_between,
        ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago,
        ops.today, ops.this_week, ops.in_days, ops.in_less_than_days,
        ops.in_more_than_days, ops.empty, ops.not_empty, ops.this_month,
        ops.last_month, ops.select_month, ops.this_year
    )
    days_operators = (
        ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago,
        ops.in_less_than_days, ops.in_more_than_days, ops.in_days
    )
    no_value_operators = (
        ops.empty, ops.not_empty, ops.today, ops.this_week, ops.this_month,
        ops.last_month, ops.this_year
    )
    input_types = 'input', 'select', 'input2'

    def __init__(self, sa_col, _now=None, default_op=None, default_value1=None,
                 default_value2=None):
        self.first_day = None
        self.last_day = None
        FilterBase.__init__(self, sa_col, default_op=default_op, default_value1=default_value1,
                            default_value2=default_value2)
        # attributes from static instance
        self._now = _now

        # attributes that will start fresh for each instance
        self._was_time_given1 = False
        self._was_time_given2 = False

    def _get_now(self):
        return self._now or dt.datetime.now()

    def _get_today(self):
        # this filter is date-only, so our "now" is a date without time
        return ensure_date(self._get_now())

    def set(self, op, value1, value2=None):
        super(DateFilter, self).set(op, value1, value2)
        self.format_display_vals()

        # store first/last day for customized usage
        today = self._get_today()
        first_day = last_day = None
        if self.op == ops.this_month:
            last_day = today + relativedelta(day=1, months=+1, days=-1)
            first_day = today + relativedelta(day=1)
        elif self.op == ops.last_month:
            last_day = today + relativedelta(day=1, days=-1)
            first_day = today + relativedelta(day=1, months=-1)
        elif self.op == ops.select_month:
            if not self.value2:
                return
            month = self.value1 if self.value1 > 0 else 1
            first_day = dt.date(self.value2, month, 1)
            last_day = first_day + relativedelta(day=1, months=+1, days=-1)
            if self.value1 == -1:
                last_day = dt.date(self.value2, 12, 31)
        elif self.op == ops.this_year:
            last_day = dt.date(today.year, 12, 31)
            first_day = dt.date(today.year, 1, 1)
        elif self.op in (ops.between, ops.not_between):
            if self.value1 <= self.value2:
                first_day = self.value1
                last_day = self.value2
            else:
                first_day = self.value2
                last_day = self.value1
        elif self.op in (ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago):
            target_date = today - dt.timedelta(days=self.value1)
            if self.op == ops.less_than_days_ago:
                first_day = target_date
                last_day = today
            elif self.op == ops.more_than_days_ago:
                first_day = None
                last_day = target_date
            elif self.op == ops.days_ago:
                first_day = last_day = target_date
        elif self.op == ops.today:
            first_day = last_day = today
        elif self.op == ops.this_week:
            sunday = today - relativedelta(weekday=SU(-1))
            saturday = today + relativedelta(weekday=calendar.SATURDAY)
            first_day = sunday
            last_day = saturday
        elif self.op == ops.eq:
            first_day = last_day = self.value1

        self.first_day = first_day
        self.last_day = last_day

    def apply(self, query):
        today = self._get_today()

        if self.op == ops.today:
            return query.filter(self.sa_col == today)

        if self.op == ops.this_week:
            sunday = today - relativedelta(weekday=SU(-1))
            saturday = today + relativedelta(weekday=calendar.SATURDAY)
            return query.filter(self.sa_col.between(sunday, saturday))

        if self.op == ops.select_month and not (self.value1 and self.value2):
            return query

        if self.op in (ops.this_month, ops.last_month, ops.select_month, ops.this_year,):
            return query.filter(self.sa_col.between(
                self.first_day,
                self.last_day
            ))

        # filters above are handled specifically before this check because they do not require any
        #   input values (or selmonth, which is grouped and handled specially). Filters below this
        #   need at least one value to proceed, and if a default value is displayed but not
        #   populated, we need to ignore it
        if self.op == self.default_op and self.value1 is None:
            return query

        if self.op in (ops.between, ops.not_between):
            if self.value1 <= self.value2:
                left_side = self.value1
                right_side = self.value2
            else:
                left_side = self.value2
                right_side = self.value1
            if self.op == ops.between:
                return query.filter(self.sa_col.between(left_side, right_side))
            else:
                return query.filter(~self.sa_col.between(left_side, right_side))

        if self.op in (ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago):
            target_date = today - dt.timedelta(days=self.value1)
            if self.op == ops.less_than_days_ago:
                return query.filter(and_(
                    self.sa_col > target_date,
                    self.sa_col < today,
                ))
            if self.op == ops.more_than_days_ago:
                return query.filter(self.sa_col < target_date)
            # op == 'da'
            return query.filter(self.sa_col == target_date)

        if self.op in (ops.in_days, ops.in_less_than_days, ops.in_more_than_days):
            target_date = today + dt.timedelta(days=self.value1)
            if self.op == ops.in_less_than_days:
                return query.filter(and_(
                    self.sa_col >= today,
                    self.sa_col < target_date
                ))
            if self.op == ops.in_more_than_days:
                return query.filter(self.sa_col > target_date)
            # op == 'ind'
            return query.filter(self.sa_col == target_date)

        return FilterBase.apply(self, query)

    def process(self, value, is_value2):
        if value is None and self.op in (ops.between, ops.not_between):
            if is_value2:
                value = ''
            else:
                raise formencode.Invalid(gettext('invalid date'), value, self)

        if value is None or self.op in self.no_value_operators:
            return None

        if self.op == self.default_op and not value:
            return None

        if self.op == ops.select_month:
            if is_value2:
                return feval.Int(not_empty=False, min=1900, max=9999).to_python(value)
            return feval.Int(not_empty=False).to_python(value)

        if self.op in self.days_operators:
            if is_value2:
                return None
            filter_value = feval.Int(not_empty=True).to_python(value)

            if self.op in (ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago):
                try:
                    self._get_today() - dt.timedelta(days=filter_value)
                except OverflowError:
                    raise formencode.Invalid(gettext('date filter given is out of range'),
                                             value, self)

            if self.op in (ops.in_days, ops.in_less_than_days, ops.in_more_than_days):
                try:
                    self._get_today() + dt.timedelta(days=filter_value)
                except OverflowError:
                    raise formencode.Invalid(gettext('date filter given is out of range'),
                                             value, self)

            return filter_value

        try:
            d = ensure_date(parse(value))

            if isinstance(d, (dt.date, dt.datetime)) and d.year < 1900:
                return feval.Int(min=1900).to_python(d.year)

            return d
        except ValueError:
            # allow open ranges when blanks are submitted as a second value
            if is_value2 and not value:
                return dt.date.today()

            raise formencode.Invalid(gettext('invalid date'), value, self)


class DateTimeFilter(DateFilter):
    def __init__(self, sa_col, _now=None, default_op=None, default_value1=None,
                 default_value2=None):
        self._has_date_only1 = self._has_date_only2 = False
        super(DateTimeFilter, self).__init__(sa_col, _now=_now, default_op=default_op,
                                             default_value1=default_value1,
                                             default_value2=default_value2)

    def format_display_vals(self):
        ops_single_val = (
            ops.eq.key,
            ops.not_eq.key,
            ops.less_than_equal.key,
            ops.greater_than_equal.key,
        )
        ops_double_val = (
            ops.between.key,
            ops.not_between.key
        )
        if isinstance(self.value1, dt.datetime) and self.op in ops_single_val + ops_double_val:
            # !!!: localize
            self.value1_set_with = self.value1.strftime('%m/%d/%Y %I:%M %p')
            if self.op in ops_single_val and self._has_date_only1:
                # !!!: localize
                self.value1_set_with = self.value1.strftime('%m/%d/%Y')
        if isinstance(self.value2, dt.datetime) and self.op in ops_double_val:
            # !!!: localize
            self.value2_set_with = self.value2.strftime('%m/%d/%Y %I:%M %p')
            if self._has_date_only2:
                # !!!: localize
                self.value2_set_with = self.value2.strftime('%m/%d/%Y 11:59 PM')

    def process(self, value, is_value2):
        if value is None or (value == '' and is_value2):
            return None

        if self.op == self.default_op and not value:
            return None

        if self.op == ops.select_month:
            if is_value2:
                return feval.Int(not_empty=False, min=1900, max=9999).to_python(value)
            return feval.Int(not_empty=False).to_python(value)

        if self.op in self.days_operators:
            if is_value2:
                return None

            filter_value = feval.Int(not_empty=True).to_python(value)

            if self.op in (ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago):
                try:
                    self._get_today() - dt.timedelta(days=filter_value)
                except OverflowError:
                    raise formencode.Invalid(gettext('date filter given is out of range'),
                                             value, self)

            if self.op in (ops.in_days, ops.in_less_than_days, ops.in_more_than_days):
                try:
                    self._get_today() + dt.timedelta(days=filter_value)
                except OverflowError:
                    raise formencode.Invalid(gettext('date filter given is out of range'),
                                             value, self)

            return filter_value
        elif value == '' and self.op in self.no_value_operators:
            return None

        try:
            dt_value = parse(value)
        except ValueError:
            raise formencode.Invalid(gettext('invalid date'), value, self)

        if is_value2:
            self._has_date_only2 = self._has_date_only(dt_value, value)
        else:
            self._has_date_only1 = self._has_date_only(dt_value, value)

        return dt_value

    def _has_date_only(self, dt_value, value):
        return bool(
            dt_value.hour == 0
            and dt_value.minute == 0
            and dt_value.second == 0
            and '00:00' not in value
        )

    def apply(self, query):
        today = self._get_today()

        if self.op == ops.today:
            left_side = ensure_datetime(today)
            right_side = ensure_datetime(today, time_part=dt.time(23, 59, 59, 999999))
            return query.filter(self.sa_col.between(left_side, right_side))

        if self.op == ops.this_week:
            sunday = today - relativedelta(weekday=SU(-1))
            saturday = today + relativedelta(weekday=calendar.SATURDAY)

            left_side = ensure_datetime(sunday)
            right_side = ensure_datetime(saturday, time_part=dt.time(23, 59, 59, 999999))
            return query.filter(self.sa_col.between(left_side, right_side))

        if self.op == ops.this_month:
            last_day = today + relativedelta(day=1, months=+1, microseconds=-1)
            first_day = ensure_datetime(today + relativedelta(day=1))
            return query.filter(self.sa_col.between(first_day, last_day))

        if self.op == ops.last_month:
            last_day = today + relativedelta(day=1, microseconds=-1)
            first_day = ensure_datetime(today + relativedelta(day=1, months=-1))
            return query.filter(self.sa_col.between(first_day, last_day))

        if self.op == ops.this_year:
            last_day = today + relativedelta(day=31, month=12, days=+1, microseconds=-1)
            first_day = ensure_datetime(today + relativedelta(day=1, month=1))
            return query.filter(self.sa_col.between(first_day, last_day))

        if self.op == ops.select_month and not self.value2:
            return query

        if self.op == ops.select_month:
            first_day = ensure_datetime(self.first_day)
            last_day = self.last_day + relativedelta(days=1, microseconds=-1)
            return query.filter(self.sa_col.between(first_day, last_day))

        # filters above are handled specifically before this check because they do not require any
        #   input values (or selmonth, which is grouped and handled specially). Filters below this
        #   need at least one value to proceed, and if a default value is displayed but not
        #   populated, we need to ignore it
        if self.op == self.default_op and self.value1 is None:
            return query

        if self.op in (ops.days_ago, ops.less_than_days_ago, ops.more_than_days_ago):
            target_date = today - dt.timedelta(days=self.value1)
            if self.op == ops.days_ago:
                left_side = ensure_datetime(target_date)
                right_side = ensure_datetime(target_date, time_part=dt.time(23, 59, 59, 999999))
                return query.filter(self.sa_col.between(left_side, right_side))
            if self.op == ops.less_than_days_ago:
                return query.filter(and_(
                    self.sa_col > ensure_datetime(target_date,
                                                  time_part=dt.time(23, 59, 59, 999999)),
                    self.sa_col < ensure_datetime(today),
                ))
            # else self.op == 'mtda'
            return query.filter(self.sa_col < ensure_datetime(target_date))

        if self.op in (ops.in_days, ops.in_less_than_days, ops.in_more_than_days):
            target_date = today + dt.timedelta(days=self.value1)
            now = self._get_now()
            if self.op == ops.in_less_than_days:
                return query.filter(and_(
                    self.sa_col >= now,
                    self.sa_col < ensure_datetime(target_date),
                ))
            if self.op == ops.in_more_than_days:
                return query.filter(
                    self.sa_col > ensure_datetime(target_date,
                                                  time_part=dt.time(23, 59, 59, 999999))
                )
            # else self.op == 'ind'
            left_side = ensure_datetime(target_date)
            right_side = ensure_datetime(target_date, time_part=dt.time(23, 59, 59, 999999))
            return query.filter(self.sa_col.between(left_side, right_side))

        # if this is an equal operation, but the date given did not have a time
        # portion, make the filter cover the whole day
        if self.op in (ops.eq, ops.not_eq) and self._has_date_only1:
            left_side = ensure_datetime(self.value1.date())
            right_side = ensure_datetime(self.value1.date(), time_part=dt.time(23, 59, 59, 999999))
            between_clause = self.sa_col.between(left_side, right_side)
            if self.op == ops.eq:
                return query.filter(between_clause)
            else:
                return query.filter(~between_clause)

        if self.op == ops.less_than_equal and self._has_date_only1:
            value1 = ensure_datetime(self.value1.date(), time_part=dt.time(23, 59, 59, 999999))
            return query.filter(self.sa_col <= value1)

        # sometimes we need to tweak the user given value if they have not
        # specified a time
        if self.op in (ops.between, ops.not_between):
            if self._has_date_only2:
                right_side = ensure_datetime(self.value2.date(),
                                             time_part=dt.time(23, 59, 59, 999999))
            else:
                right_side = self.value2
            between_clause = self.sa_col.between(ensure_datetime(self.value1), right_side)
            if self.op == ops.between:
                return query.filter(between_clause)
            else:
                return query.filter(~between_clause)

        return DateFilter.apply(self, query)


class TimeFilter(FilterBase):
    operators = (ops.eq, ops.not_eq, ops.less_than_equal, ops.greater_than_equal, ops.between,
                 ops.not_between, ops.empty, ops.not_empty)
    input_types = 'input', 'input2'

    # !!!: localize
    time_format = '%I:%M %p'

    def apply(self, query):
        if self.op == self.default_op and self.value1 is None:
            return query

        if self.op in (ops.between, ops.not_between):
            left = min(self.value1, self.value2)
            right = max(self.value1, self.value2)
            cond = self.sa_col.between(sa.cast(left, sa.Time), sa.cast(right, sa.Time))
            if self.op == ops.not_between:
                cond = ~cond
            return query.filter(cond)

        # Casting this because some SQLAlchemy dialects (MSSQL) convert the value to datetime
        # before binding.
        val = sa.cast(self.value1, sa.Time)

        if self.op == ops.eq:
            query = query.filter(self.sa_col == val)
        elif self.op == ops.not_eq:
            query = query.filter(self.sa_col != val)
        elif self.op == ops.less_than_equal:
            query = query.filter(self.sa_col <= val)
        elif self.op == ops.greater_than_equal:
            query = query.filter(self.sa_col >= val)
        else:
            query = super(TimeFilter, self).apply(query)
        return query

    def process(self, value, is_value2):
        if value in (None, ''):
            return None

        if self.op == self.default_op and not value:
            return None

        try:
            return dt.datetime.strptime(value, self.time_format).time()
        except ValueError:
            raise formencode.Invalid(_('invalid time'), value, self)


class YesNoFilter(FilterBase):
    class ops(object):
        all = Operator('a', _('all'), None)
        yes = Operator('y', _('yes'), None)
        no = Operator('n', _('no'), None)

    operators = (
        ops.all,
        ops.yes,
        ops.no
    )

    def apply(self, query):
        if self.op == self.ops.all:
            return query
        if self.op == self.ops.yes:
            return query.filter(self.sa_col == sa.true())
        if self.op == self.ops.no:
            return query.filter(self.sa_col == sa.false())
        return FilterBase.apply(self, query)
