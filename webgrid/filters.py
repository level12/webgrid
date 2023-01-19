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
from werkzeug.datastructures import ImmutableDict

from .extensions import (
    gettext,
    lazy_gettext as _
)
from . import types

try:
    import arrow
except ImportError:
    arrow = None
try:
    from sqlalchemy_utils.types import ArrowType
except ImportError:
    ArrowType = None


class UnrecognizedOperator(ValueError):
    pass


class Operator(object):
    """Filter operator representing name and potential inputs.

    See webgrid.filters.ops for a collection of predefined operators.

    Args:
        key (str): Internal identifier to be used in code and in request args.

        display (str): Label for rendering the operator.

        field_type (str): Input field spec. Can be:
        - None: no input fields
        - input: single freeform text input
        - 2inputs: two freeform text inputs
        - select: single select box
        - select+input: select box as first input, freeform text as second

        hint (str, optional): Input field hint to show in UI. Defaults to None.
    """
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
    """Base filter class interface for webgrid filters.

    Contains filter operators, inputs, render information, and the inner workings to apply
    the filter to the database query as needed.

    Args:
        sa_col (Expression): SQLAlchemy expression to which we apply operator/values.

        default_op (str, optional): UI shortcut to enable filter with the specified op if
        none is given by the user. Defaults to None.

        default_value1 (str, optional): Use with `default_op` to set input. Defaults to None.

        default_value2 (str, optional): Use with `default_op` to set input. Defaults to None.

        dialect (str, optional): DB dialect in use, for filters supporting multiple DBMS platforms.
        Defaults to None.

    Class attributes:
        operators (tuple(Operator)): Available filter operators in the order they should appear.

        primary_op (str, optional): Key of operator to be selected automatically when the filter
        is added in UI. Defaults to first available filter op.

        init_attrs_for_instance (tuple(str)): Attributes to set when copying filter instance.
        Should not normally need to be set.

        input_types (tuple(str)): Possible input types for renderer to make available. Can be
        "input", "input2", and/or "select". Defaults to `("input", )`.

        receives_list (bool): Filter takes a list of values in its `set` method. Defaults to False.

        is_aggregate (bool): Filter applies to HAVING clause instead of WHERE

    Instance attributes:
        op (str): Operator key set by the user or programmatically.

        value1 (Any): First input value following validation processing.

        value2 (Any): Second input value following validation processing.

        value1_set_with (str): First input value raw from `set` call.

        value2_set_with (str): Second input value raw from `set` call.

        error (bool): True if input processing encountered a validation error.
    """
    operators = ops.eq, ops.not_eq, ops.empty, ops.not_empty
    # one operator may be specified as the "primary", i.e. the one to select when filter is added
    # note, the renderer is responsible for using this operator
    primary_op = None
    # if needed, specifiy the name of attributes set on the static instance of
    # this class that should get copied over to a new instance by
    # new_instance()
    init_attrs_for_instance = ()
    # current HTML renderer allows for "input", "input2", and/or "select"
    input_types = 'input',
    # match operators to the HTML5 type(s)
    html_input_types = {}
    # does this filter take a list of values in it's set() method
    receives_list = False
    # does this filter apply to the HAVING clause
    is_aggregate = False

    def __init__(self, sa_col=None, default_op=None, default_value1=None, default_value2=None,
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
        """Filter is active if op is set and input requirements are met."""
        operator_by_key = {op.key: op for op in self.operators}
        return self.op is not None and not self.error and (
            operator_by_key[self.op].field_type is None or self.value1 is not None
        )

    @property
    def is_display_active(self):
        """Filter display is active (i.e. show as a selected filter in UI) if op is set."""
        return self.op is not None

    @property
    def op_keys(self):
        """List of Operator keys used by this filter."""
        if self._op_keys is None:
            self._op_keys = [op.key for op in self.operators]
        return self._op_keys

    def _default_value(self, value):
        if callable(value):
            return value()
        return value

    def set(self, op, value1, value2=None):
        """Set filter operator and input values.

        Stores the raw inputs, then processes the inputs for validation. Applies the default
        operator if needed.

        Args:
            op (str): Operator key.
            value1 (Any): First filter input value. Pass None if the operator takes no input.
            value2 (Any, optional): Second filter input value. Defaults to None.

        Raises:
            formencode.Invalid: One or more inputs did not validate.
        """
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
        """Specified operator was not in the filter's list."""
        raise UnrecognizedOperator(_('unrecognized operator: {op}', op=self.op))

    def apply(self, query):
        """Query modifier to apply the needed clauses for filter inputs."""
        filter_method = query.filter if not self.is_aggregate else query.having
        if self.op == self.default_op and self.value1 is None:
            return query
        if self.op == ops.eq:
            return filter_method(self.sa_col == self.value1)
        if self.op == ops.not_eq:
            return filter_method(self.sa_col != self.value1)
        if self.op == ops.empty:
            return filter_method(self.sa_col.is_(None))
        if self.op == ops.not_empty:
            return filter_method(self.sa_col.isnot(None))
        if self.op == ops.less_than_equal:
            return filter_method(self.sa_col <= self.value1)
        if self.op == ops.greater_than_equal:
            return filter_method(self.sa_col >= self.value1)

        self.raise_unrecognized_op()

    def process(self, value, is_value2):
        """
            Process the values as given to .set(), validating and manipulating
            as needed.
        """
        return value

    def format_invalid(self, exc, col):
        """Wrapper for generating a validation error string."""
        return '{0}: {1}'.format(
            col.label,
            str(exc)
        )

    def get_search_expr(self):
        """
            Filters can be used for the general "single search" function on the grid. For this to
            work in SQL, the grid needs to pull search expressions from all filters and OR them
            together.

            Return value is expected to be a callable taking one argument (the search value).
            E.g. `lambda value: self.sa_col.like('%{}%'.format(value))`

            Return value of `None` is filtered out, essentially disabling search for the filter.
        """
        return None

    def serialize_filter_operator(self, op):
        field_type = op.field_type
        if op in self.html_input_types:
            field_type += '.' + self.html_input_types[op]
        return types.FilterOperator(
            key=op.key,
            label=op.display,
            field_type=field_type,
            hint=op.hint,
        )

    def serialize_filter_option(self, key, value):
        return types.FilterOption(
            key=key,
            value=value,
        )

    def serialize_filter_spec(self):
        return types.FilterSpec(
            operators=[self.serialize_filter_operator(op) for op in self.operators],
            primary_op=self.serialize_filter_operator(
                self.primary_op) if self.primary_op else None,
        )

    def new_instance(self, **kwargs):
        """
        Note: Ensure any overrides of this method accept and pass through kwargs to preserve
        compatibility in future
        """
        cls = self.__class__
        new_filter = cls(*self._vargs, **self._kwargs)
        new_filter.dialect = kwargs.get('dialect')
        if 'col' in kwargs and new_filter.sa_col is None:
            new_filter.sa_col = kwargs['col']
        return new_filter

    def __repr__(self):
        return 'class={}, op={}, value1={}, value2={}'.format(
            self.__class__.__name__, self.op, self.value1, self.value2
        )


class _NoValue(object):
    pass


class OptionsFilterBase(FilterBase):
    """Base class for filters having a list of options.

    UI for these is a single select box. By default, these are all shown with a search
    box within the filter, and checkboxes to pick multiple items.

    Notable args:
        value_modifier (Union(str, callable, Validator), optional): modifier to apply to
        the input value(s) in the request. Generally, the options list in the filter will
        have the "true" type in the identifier, but the request will come in with strings.
        If `value_modifier` is "auto", we'll check one of the options IDs with some known
        types to pick a FormEncode validator. Or, a FormEncode validator can be passed in.
        Or, pass a callable, and it will be wrapped as a validator. Defaults to "auto".

    Class attributes:
        options_from (tuple): Iterable of options available to the filter. Defined here as a
        class attribute, but can be overridden as an instance attribute, property, or method.
        Options are expected to be tuples of the form (key, value). `key` is the part that will
        be validated on input and used in the filter query clause. `value` is displayed in UI.

    """

    operators = ops.is_, ops.not_is, ops.empty, ops.not_empty
    primary_op = ops.is_
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

    def serialize_filter_spec(self):
        base_spec = super().serialize_filter_spec()
        return types.OptionsFilterSpec(
            operators=base_spec.operators,
            primary_op=base_spec.primary_op,
            options=[
                self.serialize_filter_option(key, value)
                for key, value in self.options_seq],
        )

    def new_instance(self, **kwargs):
        filter = FilterBase.new_instance(self, **kwargs)
        filter.setup_validator()
        return filter

    @property
    def options_seq(self):
        """Resolver for `options_from` that caches the options values.

        Tries to treat `options_from` as a callable first, and if that fails, refers to it
        as an attribute/property value instead.
        """
        if self._options_seq is None:
            try:
                self._options_seq = self.options_from()
            except TypeError as e:
                if 'is not callable' not in str(e):
                    raise
                self._options_seq = self.options_from
        return self._options_seq

    @property
    def option_keys(self):
        """Extract a keys list from the options tuples."""
        if self._options_keys is None:
            self._options_keys = [k for k, v in self.options_seq]
        return self._options_keys

    def setup_validator(self):
        """Select a validator by type if `value_modifier` is "auto", or wrap a callable."""
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
        """Set the filter op/values to be used by query modifiers.

        Since this type of filter has only one input box, `value2` is ignored (present here for
        consistent API). Each of the items passed in the first filter value is processed with
        the selected/given validator. Any items that do not pass validation are ignored and left
        out of the query.

        Args:
            op (str): Operator key.
            values (iterable): List/tuple/iterable of values to be validated.
            value2 (Any, optional): Ignored. Defaults to None.
        """
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

        self.value1_set_with = values

    def process(self, value):
        """Apply the `value_modifier` to a value."""
        if self.value_modifier is not None:
            value = self.value_modifier.to_python(value)
            if value not in self.option_keys:
                return _NoValue
            if self.default_op and value == -1:
                return _NoValue
        return value

    def match_keys_for_value(self, value):
        """Used for single-search to match search value to part of an option's display string."""
        return [
            key for (key, _) in filter(
                lambda item: value.lower() in str(item[1]).lower(),
                self.options_seq
            )
        ]

    def get_search_expr(self):
        """Match up a search value to option display, grab the corresponding keys, and search."""
        # The important thing to remember here is that a user will be searching for the displayed
        # value, not the key that generated it. We need to do some prep work to search options
        # to get the keys needed for lookup into the data source.
        def search(value):
            matching_keys = self.match_keys_for_value(value)
            return self.sa_col.in_(matching_keys)
        return search

    def apply(self, query):
        """Query modifier to apply the needed clauses for filter inputs."""
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
    """Base class for filters having a list of options with integer keys.

    Shortcut for using `OptionsFilterBase` and supplying `formencode.validators.Int`
    as the `value_modifier`.

    """
    def __init__(self, sa_col, value_modifier=feval.Int, default_op=None, default_value1=None,
                 default_value2=None):
        OptionsFilterBase.__init__(self, sa_col, value_modifier, default_op, default_value1,
                                   default_value2)


class OptionsEnumFilter(OptionsFilterBase):
    """Options filter that pulls options from a python Enum.

    Most filters can be used in column definitions as a class or an instance. With
    this filter, an instance must be given, so the `enum_type` can be specified.

    Notable args:
        enum_type (Enum): Python Enum type to use for options list.
    """
    enum_type = None

    def __init__(
            self,
            sa_col,
            value_modifier=None,
            default_op=None,
            default_value1=None,
            default_value2=None,
            enum_type=None,
    ):
        self.enum_type = enum_type or self.__class__.enum_type

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
        """Generic `value_modifier` that validates an item in the given Enum."""
        if isinstance(value, self.enum_type):
            return value

        try:
            return self.enum_type[value]
        except KeyError:
            raise ValueError('Not a valid selection')

    def options_from(self):
        """Override as an instance method here, returns the options tuples from the Enum."""
        return [(x.name, x.value) for x in self.enum_type]

    def new_instance(self, **kwargs):
        new_inst = super(OptionsEnumFilter, self).new_instance(**kwargs)
        new_inst.enum_type = self.enum_type
        return new_inst

    def process(self, value):
        """Validate value using `value_modifier`."""
        if self.value_modifier is None:
            return value

        return self.value_modifier.to_python(value)


class OptionsEnumArrayFilter(OptionsEnumFilter):
    """Handle filtering array fields having an enum type.

    Uses SA's any/contains operators, while correcting for enum type discrepancy.

    Note, this is known to work with Postgres, but has not been tested on other platforms."""

    def get_search_expr(self):
        """Match up a search value to option display, grab the corresponding keys, and search."""
        # The important thing to remember here is that a user will be searching for the displayed
        # value, not the key that generated it. We need to do some prep work to search options
        # to get the keys needed for lookup into the data source.
        def search(value):
            matching_keys = self.match_keys_for_value(value)
            # contains doesn't have the same behavior as in_. In_ guards against empty sets
            # since no record is in the null set, but contains with an empty set will return
            # every record. Make sure we have something to contain, or else don't return an
            # expression at all.
            if matching_keys:
                return self.sa_col.contains(matching_keys)
            return None
        return search

    def apply(self, query):
        """Query modifier to apply the needed clauses for filter inputs."""
        if self.op == ops.is_:
            if len(self.value1) == 1 and self.value1[0]:
                return query.filter(self.sa_col.any(self.value1[0].name))
            elif len(self.value1) > 1:
                return query.filter(self.sa_col.contains(self.value1))
            else:
                return query
        if self.op == ops.not_is:
            if len(self.value1) == 1 and self.value1[0]:
                return query.filter(~self.sa_col.any(self.value1[0].name))
            elif len(self.value1) > 1:
                return query.filter(~self.sa_col.contains(self.value1))
            else:
                return query
        return super().apply(query)


class TextFilter(FilterBase):
    """Filter with single freeform text input."""
    operators = (ops.eq, ops.not_eq, ops.contains, ops.not_contains, ops.empty, ops.not_empty)
    primary_op = ops.contains

    @property
    def comparisons(self):
        """Handles the dialect-specific job of text comparisons.

        In a functional text filter, we want to be case-insensitive. The default behavior
        of some databases (such as postgresql) is to be case-sensitive for LIKE operations.
        We work around that for dialects known to have that complexity, and compare
        upper-case values or use the ILIKE operator.

        Some, like mssql, are normally case-insensitive for string comparisons, and we assume
        that is the case here. Obviously, the database can be set up differently. If it is,
        that case would need to be handled separately in a custom filter.
        """
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

    def get_search_expr(self):
        return lambda value: self.comparisons[ops.contains](self.sa_col, value)

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
    """Base class for filters taking one or two freeform inputs as numbers.

    Class attributes:
        validator (Validator): FormEncode validator to use on input values.
    """
    operators = (ops.eq, ops.not_eq, ops.less_than_equal, ops.greater_than_equal, ops.between,
                 ops.not_between, ops.empty, ops.not_empty)

    def process(self, value, is_value2):
        if self.op == self.default_op and not value:
            return None
        if self.op in (ops.eq, ops.not_eq, ops.less_than_equal,
                       ops.greater_than_equal) and not is_value2:
            return self.validator(not_empty=True).to_python(value)
        return self.validator.to_python(value)

    def get_search_expr(self):
        # This is a naive implementation that simply converts the number column to string and
        # uses a LIKE. We could go nuts with things like stripping thousands separators,
        # parenthesis, monetary symbols, etc. from the search value, but then we get to deal with
        # locale.
        return lambda value: sa.sql.cast(self.sa_col, sa.Unicode).like('%{}%'.format(value))

    def apply(self, query):
        filter_method = query.filter if not self.is_aggregate else query.having
        if self.op == ops.between:
            return filter_method(self.sa_col.between(self.value1, self.value2))
        if self.op == ops.not_between:
            return filter_method(~self.sa_col.between(self.value1, self.value2))
        return super().apply(query)


class IntFilter(NumberFilterBase):
    """Number filter validating inputs as integers."""
    validator = feval.Int


class AggregateIntFilter(IntFilter):
    """Number filter validating inputs as integers, for use on aggregate columns."""
    is_aggregate = True


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


class AggregateNumberFilter(NumberFilter):
    """Number filter validating inputs as Decimal, for use on aggregate columns."""
    is_aggregate = True


class _DateMixin(object):
    options_from = [
        (1, _('01-Jan')), (2, _('02-Feb')), (3, _('03-Mar')), (4, _('04-Apr')),
        (5, _('05-May')), (6, _('06-Jun')), (7, _('07-Jul')), (8, _('08-Aug')),
        (9, _('09-Sep')), (10, _('10-Oct')), (11, _('11-Nov')), (12, _('12-Dec')),
    ]
    op_to_date_range = ImmutableDict({
        # these filters can be set as default ops without input values, so don't ignore them
        ops.this_month: lambda self, today: (
            today + relativedelta(day=1),
            today + relativedelta(day=1, months=+1, days=-1),
        ),
        ops.last_month: lambda self, today: (
            today + relativedelta(day=1, months=-1),
            today + relativedelta(day=1, days=-1),
        ),
        ops.select_month: lambda self, today: self._select_month(today),
        ops.this_year: lambda self, today: (
            dt.date(today.year, 1, 1),
            dt.date(today.year, 12, 31),
        ),
        ops.this_week: lambda self, today: (
            today - relativedelta(weekday=SU(-1)),
            today + relativedelta(weekday=calendar.SATURDAY),
        ),
        ops.today: lambda self, today: (today, today),
        # ops with both dates populated
        ops.between: lambda self, today: self._between_range(),
        ops.not_between: lambda self, today: self._between_range(),
        # ops with single date populated
        ops.less_than_days_ago: lambda self, today: (
            today - dt.timedelta(days=self.value1),
            today,
        ) if self.value1 is not None else (None, None),
        ops.in_less_than_days: lambda self, today: (
            today,
            today + dt.timedelta(days=self.value1),
        ) if self.value1 is not None else (None, None),
        ops.days_ago: lambda self, today: (
            today - dt.timedelta(days=self.value1),
            today - dt.timedelta(days=self.value1),
        ) if self.value1 is not None else (None, None),
        ops.more_than_days_ago: lambda self, today: (
            None, today - dt.timedelta(days=self.value1)
        ) if self.value1 is not None else (None, None),
        ops.in_days: lambda self, today: self._in_days(today),
        ops.in_more_than_days: lambda self, today: self._in_days(today),
        ops.eq: lambda self, today: self._equality(),
        ops.not_eq: lambda self, today: self._equality(),
        ops.less_than_equal: lambda self, today: self._equality(),
        ops.greater_than_equal: lambda self, today: self._equality(),
    })

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
            self.value1_set_with = self.value1.strftime('%Y-%m-%d')
        if isinstance(self.value2, dt.date) and self.op in (
            ops.between.key,
            ops.not_between.key
        ):
            # !!!: localize
            self.value2_set_with = self.value2.strftime('%Y-%m-%d')

    def _between_range(self):
        if self.value1 is None:
            return None, None
        if self.value1 <= self.value2:
            first_day, last_day = self.value1, self.value2
        else:
            first_day, last_day = self.value2, self.value1
        return first_day, last_day

    def _in_days(self, today):
        if self.value1 is None:
            return None, None
        return today + dt.timedelta(days=self.value1), None

    def _equality(self):
        return self.value1, self.value1

    def _select_month(self, today):
        first_day = last_day = None
        if self.value2:
            month = self.value1 if self.value1 > 0 else 1
            first_day = dt.date(self.value2, month, 1)
            last_day = first_day + relativedelta(day=1, months=1, days=-1)
            if self.value1 == -1:
                last_day = dt.date(self.value2, 12, 31)
        return first_day, last_day

    def _description_data(self):
        today = self._get_today()

        first_day, last_day = self.op_to_date_range.get(
            self.op, lambda self, today: (None, None)
        )(self, today)

        prefix = {
            ops.more_than_days_ago: _('before '),
            ops.not_between: _('excluding '),
            ops.in_more_than_days: _('after '),
            ops.not_eq: _('excluding '),
            ops.less_than_equal: _('up to '),
            ops.greater_than_equal: _('beginning '),
        }.get(self.op, '')

        return first_day, last_day, prefix

    @property
    def description(self):
        """
            String description of the filter operation and values
            - Useful for Excel reports
        """

        # simple cases
        if self.error:
            return _('invalid')
        elif self.op == ops.select_month:
            if not (
                isinstance(self.value1, int) and isinstance(self.value2, int)
            ):
                return _('All')
            if self.value1 < 1 or self.value1 > 12:
                return self.value2
            # !!!: localize
            return dt.date(self.value2, self.value1, 1).strftime('%b %Y')
        elif self.op == ops.empty:
            return _('date not specified')
        elif self.op == ops.not_empty:
            return _('any date')

        first_day, last_day, prefix = self._description_data()

        if not first_day and (
            not self.op or (
                self.default_op == self.op and (
                    self.value2 is None and self.value1 is None
                )
            )
        ):
            return _('all')

        if self.op in (
            ops.today, ops.eq, ops.not_eq, ops.less_than_equal,
            ops.greater_than_equal, ops.days_ago,
        ):
            # !!!: localize
            return _('{descriptor}{date}',
                     descriptor=prefix,
                     date=first_day.strftime('%m/%d/%Y'))
        elif last_day and first_day:
            # !!!: localize dates
            return _('{descriptor}{first_date} - {second_date}',
                     descriptor=prefix,
                     first_date=first_day.strftime('%m/%d/%Y'),
                     second_date=last_day.strftime('%m/%d/%Y'))
        else:
            # !!!: localize
            target_date = first_day if first_day else last_day
            return _('{descriptor}{date}',
                     descriptor=prefix,
                     date=target_date.strftime('%m/%d/%Y'))

    def valid_date_for_backend(self, value):
        """
        Returns false if the given date or datetime is out of bounds for the backend dialect.
        If for any reason the value cannot be validated the value is presumed to be valid..
        """
        if not self.dialect:
            return True

        if not isinstance(value, (dt.datetime, dt.date)):
            return True

        def min_dt(*args):
            m = dt.datetime.min
            parts = [m.year, m.month, m.day, m.hour, m.minute, m.second, m.microsecond]
            return dt.datetime(*(max(a, m) for a, m in zip(args, parts)))

        def max_dt(*args):
            m = dt.datetime.max
            parts = [m.year, m.month, m.day, m.hour, m.minute, m.second, m.microsecond]
            return dt.datetime(*(min(a, m) for a, m in zip(args, parts)))

        if not isinstance(value, dt.datetime):
            value = dt.datetime.combine(value, dt.time.min)

        if self.dialect.name == 'postgresql':
            # https://www.enterprisedb.com/edb-docs/d/edb-postgres-advanced-server/user-guides/database-compatibility-for-oracle-developers-guide/9.4/Database_Compatibility_for_Oracle_Developers_Guide.1.038.html  # noqa
            return min_dt(-4713, 1, 1) <= value <= max_dt(294276, 12, 31, 23, 59, 59)
        elif self.dialect.name == 'sqlite':
            # https://www.sqlite.org/lang_datefunc.html
            return min_dt(0, 1, 1) <= value <= max_dt(9999, 12, 31, 23, 59, 59)
        elif self.dialect.name == 'mssql':
            # https://docs.microsoft.com/en-us/sql/t-sql/data-types/datetime-transact-sql?view=sql-server-ver15#datetime-description  # noqa
            return min_dt(1753, 1, 1) <= value <= max_dt(9999, 12, 31, 23, 59, 59, 997)
        return True

    def get_search_expr(self, date_comparator=None):
        # This is a naive implementation that simply converts the date/time column to string and
        # uses a LIKE. Only addition is to support a common month/day/year format, but only if
        # the value is easily parsible
        date_comparator = date_comparator or (lambda value: self.sa_col == value)

        def expr(value):
            base_expr = sa.sql.cast(self.sa_col, sa.Unicode).like('%{}%'.format(value))
            try:
                date_value = parse(value)
                if not self.valid_date_for_backend(date_value):
                    return base_expr
                return or_(
                    base_expr,
                    date_comparator(date_value)
                )
            except (ValueError, OverflowError):
                pass
            return base_expr
        return expr

    def serialize_filter_spec(self):
        base_spec = super().serialize_filter_spec()
        return types.OptionsFilterSpec(
            operators=base_spec.operators,
            primary_op=base_spec.primary_op,
            options=[
                self.serialize_filter_option(key, value)
                for key, value in self.options_seq],
        )


class _DateOpQueryMixin:
    op_to_query = ImmutableDict({
        ops.today: lambda self, query, today: query.filter(
            self.sa_col == today
        ),
        ops.this_week: lambda self, query, today: query.filter(self.sa_col.between(
            today - relativedelta(weekday=SU(-1)),
            today + relativedelta(weekday=calendar.SATURDAY),
        )),
        ops.select_month: lambda self, query, today: (
            self._month_year_filter(query) if self.value1 and self.value2 else query
        ),
        ops.this_month: lambda self, query, today: self._month_year_filter(query),
        ops.last_month: lambda self, query, today: self._month_year_filter(query),
        ops.this_year: lambda self, query, today: self._month_year_filter(query),
        ops.between: lambda self, query, today: query.filter(self._between_clause()),
        ops.not_between: lambda self, query, today: query.filter(~self._between_clause()),
        ops.days_ago: lambda self, query, today: query.filter(
            self.sa_col == today - dt.timedelta(days=self.value1)
        ),
        ops.less_than_days_ago: lambda self, query, today: query.filter(and_(
            self.sa_col > today - dt.timedelta(days=self.value1),
            self.sa_col <= today,
        )),
        ops.more_than_days_ago: lambda self, query, today: query.filter(
            self.sa_col < today - dt.timedelta(days=self.value1)
        ),
        ops.in_days: lambda self, query, today: query.filter(
            self.sa_col == today + dt.timedelta(days=self.value1)
        ),
        ops.in_less_than_days: lambda self, query, today: query.filter(and_(
            self.sa_col >= today,
            self.sa_col < today + dt.timedelta(days=self.value1),
        )),
        ops.in_more_than_days: lambda self, query, today: query.filter(
            self.sa_col > today + dt.timedelta(days=self.value1)
        ),
    })

    def _get_today(self):
        # this filter is date-only, so our "now" is a date without time
        return ensure_date(self._get_now())

    def _get_now(self):
        return self._now or dt.datetime.now()

    def _month_year_filter(self, query):
        return query.filter(self.sa_col.between(self.first_day, self.last_day))

    def _between_clause(self):
        if self.value1 <= self.value2:
            return self.sa_col.between(self.value1, self.value2)
        else:
            return self.sa_col.between(self.value2, self.value1)


class DateFilter(_DateOpQueryMixin, _DateMixin, FilterBase):
    """Complex date filter.

    Depending on the operator, inputs could be one or two freeform, or a select and freeform.

    Notable args:
        _now (datetime, optional): Useful for testing, supplies a date the filter will use instead
        of the true `datetime.now()`. Defaults to None.
    """
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
    html_input_types = {
        ops.eq: 'date',
        ops.not_eq: 'date',
        ops.less_than_equal: 'date',
        ops.greater_than_equal: 'date',
        ops.between: 'date',
        ops.not_between: 'date',
    }

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

        self.check_arrow_type()

    def check_arrow_type(self):
        """Verify that the expression given to the filter is not ArrowType. If it
        is, cast it to a date to avoid type problems in the date filter"""
        if arrow and ArrowType and isinstance(self.sa_col.type, ArrowType):
            self.sa_col = sa.sql.cast(self.sa_col, sa.Date)

    def set(self, op, value1, value2=None):
        super(DateFilter, self).set(op, value1, value2)
        self.format_display_vals()

        # store first/last day for customized usage
        today = self._get_today()
        self.first_day, self.last_day = self.op_to_date_range.get(
            self.op, lambda self, today: (None, None)
        )(self, today)

    def apply(self, query):
        query_function = self.op_to_query.get(self.op)
        if query_function:
            filtered_query = query_function(self, query, self._get_today())
        else:
            filtered_query = super().apply(query)

        # if function returns None rather than query, call super
        if filtered_query is None:
            filtered_query = super().apply(query)

        if self.op in (
            ops.today, ops.this_week, ops.select_month, ops.this_month,
            ops.last_month, ops.this_year,
        ):
            return filtered_query

        # filters above are handled specifically before this check because they do not require any
        #   input values (or selmonth, which is grouped and handled specially). Filters below this
        #   need at least one value to proceed, and if a default value is displayed but not
        #   populated, we need to ignore it
        if self.op == self.default_op and self.value1 is None:
            return query

        return filtered_query

    def _process_days_operator(self, value, is_value2):
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

    def _process_date(self, value, is_value2):
        try:
            d = ensure_date(parse(value))

            if isinstance(d, (dt.date, dt.datetime)) and d.year < 1900:
                return feval.Int(min=1900).to_python(d.year)

            return d
        except (ValueError, OverflowError):
            # allow open ranges when blanks are submitted as a second value
            if is_value2 and not value:
                return self._get_today()

            raise formencode.Invalid(gettext('invalid date'), value, self)

    def process(self, value, is_value2):
        # None is ok for default_ops
        if self.op == self.default_op and not value:
            return None

        # Subclass ops that do not require a value should be added to no_value_operators
        # to ensure empty values do not trigger a validation error
        if self.op in self.no_value_operators:
            return None

        if value is None:
            if is_value2:
                if self.op in (ops.between, ops.not_between):
                    value = ''
                else:
                    return None
            else:
                raise formencode.Invalid(gettext('invalid date'), value, self)

        if self.op == ops.select_month:
            if is_value2:
                return feval.Int(not_empty=False, min=1900, max=9999).to_python(value)
            return feval.Int(not_empty=False).to_python(value)

        if self.op in self.days_operators:
            return self._process_days_operator(value, is_value2)
        return self._process_date(value, is_value2)


class DateTimeFilter(DateFilter):
    """Complex datetime filter.

    Depending on the operator, inputs could be one or two freeform, or a select and freeform.

    Notable args:
        _now (datetime, optional): Useful for testing, supplies a date the filter will use instead
        of the true `datetime.now()`. Defaults to None.
    """
    html_input_types = {
        ops.eq: 'datetime-local',
        ops.not_eq: 'datetime-local',
        ops.less_than_equal: 'datetime-local',
        ops.greater_than_equal: 'datetime-local',
        ops.between: 'datetime-local',
        ops.not_between: 'datetime-local',
    }
    op_to_query = ImmutableDict({**DateFilter.op_to_query, **{
        ops.today: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today),
            ensure_datetime(today, time_part=dt.time(23, 59, 59, 999999)),
        )),
        ops.this_week: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today - relativedelta(weekday=SU(-1))),
            ensure_datetime(
                today + relativedelta(weekday=calendar.SATURDAY),
                time_part=dt.time(23, 59, 59, 999999)
            ),
        )),
        ops.this_month: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today + relativedelta(day=1)),
            today + relativedelta(day=1, months=+1, microseconds=-1),
        )),
        ops.last_month: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today + relativedelta(day=1, months=-1)),
            today + relativedelta(day=1, microseconds=-1),
        )),
        ops.this_year: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today + relativedelta(day=1, month=1)),
            today + relativedelta(day=31, month=12, days=1, microseconds=-1),
        )),
        ops.select_month: lambda self, query, today: (
            query.filter(self.sa_col.between(
                ensure_datetime(self.first_day),
                self.last_day + relativedelta(days=1, microseconds=-1),
            )) if self.value2 else query
        ),
        ops.days_ago: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today - dt.timedelta(days=self.value1)),
            ensure_datetime(
                today - dt.timedelta(days=self.value1),
                time_part=dt.time(23, 59, 59, 999999)
            ),
        )),
        ops.less_than_days_ago: lambda self, query, today: query.filter(and_(
            self.sa_col > ensure_datetime(today - dt.timedelta(days=self.value1),
                                          time_part=dt.time(23, 59, 59, 999999)),
            self.sa_col <= self._get_now()
        )),
        ops.more_than_days_ago: lambda self, query, today: query.filter(
            self.sa_col < ensure_datetime(today - dt.timedelta(days=self.value1))
        ),
        ops.in_days: lambda self, query, today: query.filter(self.sa_col.between(
            ensure_datetime(today + dt.timedelta(days=self.value1)),
            ensure_datetime(
                today + dt.timedelta(days=self.value1), time_part=dt.time(23, 59, 59, 999999)
            ),
        )),
        ops.in_less_than_days: lambda self, query, today: query.filter(and_(
            self.sa_col >= self._get_now(),
            self.sa_col < ensure_datetime(today + dt.timedelta(days=self.value1)),
        )),
        ops.in_more_than_days: lambda self, query, today: query.filter(
            self.sa_col > ensure_datetime(
                today + dt.timedelta(days=self.value1),
                time_part=dt.time(23, 59, 59, 999999)
            )
        ),
        ops.eq: lambda self, query, today: (
            query.filter(self._eq_clause())
        ),
        ops.not_eq: lambda self, query, today: (
            query.filter(~self._eq_clause())
        ),
        ops.less_than_equal: lambda self, query, today: query.filter(
            self.sa_col <= ensure_datetime(
                self.value1.date(), time_part=dt.time(23, 59, 59, 999999)
            )
        ) if self._has_date_only1 else None,
        ops.between: lambda self, query, today: query.filter(self._between_clause()),
        ops.not_between: lambda self, query, today: query.filter(~self._between_clause()),
    }})

    def __init__(self, sa_col, _now=None, default_op=None, default_value1=None,
                 default_value2=None):
        self._has_date_only1 = self._has_date_only2 = False
        super(DateTimeFilter, self).__init__(sa_col, _now=_now, default_op=default_op,
                                             default_value1=default_value1,
                                             default_value2=default_value2)

    def check_arrow_type(self):
        """DateTimeFilter has no problems with ArrowType. Pass this case through."""
        pass

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
            self.value1_set_with = self.value1.strftime('%Y-%m-%dT%H:%M')
            if self.op in ops_single_val and self._has_date_only1:
                # !!!: localize
                self.value1_set_with = self.value1.strftime('%Y-%m-%d')
        if isinstance(self.value2, dt.datetime) and self.op in ops_double_val:
            # !!!: localize
            self.value2_set_with = self.value2.strftime('%Y-%m-%dT%H:%M')
            if self._has_date_only2:
                # !!!: localize
                self.value2_set_with = self.value2.strftime('%Y-%m-%dT23:59')

    def _between_clause(self):
        if self._has_date_only2:
            right_side = ensure_datetime(self.value2.date(),
                                         time_part=dt.time(23, 59, 59, 999999))
        else:
            right_side = self.value2
        return self.sa_col.between(ensure_datetime(self.value1), right_side)

    def _eq_clause(self):
        if self._has_date_only1:
            left_side = ensure_datetime(self.value1.date())
            right_side = ensure_datetime(self.value1.date(), time_part=dt.time(23, 59, 59, 999999))
            return self.sa_col.between(left_side, right_side)
        if self.value1 and self.value1.microsecond == 0:
            left_side = self.value1
            right_side = self.value1 + dt.timedelta(microseconds=999999)
            return self.sa_col.between(left_side, right_side)

    def _process_datetime(self, value, is_value2):
        try:
            dt_value = parse(value)
        except (ValueError, OverflowError):
            # allow open ranges when blanks are submitted as a second value
            if is_value2 and not value:
                return self._get_now()
            raise formencode.Invalid(gettext('invalid date'), value, self)

        if is_value2:
            self._has_date_only2 = self._has_date_only(dt_value, value)
        else:
            self._has_date_only1 = self._has_date_only(dt_value, value)

        return dt_value

    def process(self, value, is_value2):
        # None is ok for default_ops
        if self.op == self.default_op and not value:
            return None

        # Subclass ops that do not require a value should be added to no_value_operators
        # to ensure empty values do not trigger a validation error
        if self.op in self.no_value_operators:
            return None

        if value is None:
            if is_value2:
                if self.op in (ops.between, ops.not_between):
                    value = ''
                else:
                    return None
            else:
                raise formencode.Invalid(gettext('invalid date'), value, self)

        if self.op == ops.select_month:
            if is_value2:
                return feval.Int(not_empty=False, min=1900, max=9999).to_python(value)
            return feval.Int(not_empty=False).to_python(value)

        if self.op in self.days_operators:
            return self._process_days_operator(value, is_value2)

        return self._process_datetime(value, is_value2)

    def _has_date_only(self, dt_value, value):
        return bool(
            dt_value.hour == 0
            and dt_value.minute == 0
            and dt_value.second == 0
            and '00:00' not in value
        )

    def get_search_expr(self):
        # This is a naive implementation that simply converts the date/time column to string and
        # uses a LIKE. Only addition is to support a common month/day/year format, but only if
        # the value is easily parsible
        def date_comparator(value):
            if self._has_date_only(value, ''):
                left_side = ensure_datetime(value.date())
                right_side = ensure_datetime(value.date(), time_part=dt.time(23, 59, 59, 999999))
                return self.sa_col.between(left_side, right_side)
            return self.sa_col == value

        return super().get_search_expr(date_comparator=date_comparator)


class TimeFilter(FilterBase):
    """Time filter with one or two freeform inputs."""
    operators = (ops.eq, ops.not_eq, ops.less_than_equal, ops.greater_than_equal, ops.between,
                 ops.not_between, ops.empty, ops.not_empty)
    input_types = 'input', 'input2'
    html_input_types = {
        ops.eq: 'time',
        ops.not_eq: 'time',
        ops.less_than_equal: 'time',
        ops.greater_than_equal: 'time',
        ops.between: 'time',
        ops.not_between: 'time',
    }

    # !!!: localize
    time_format = '%H:%M'

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
        endval = val = sa.cast(self.value1, sa.Time)
        if self.value1:
            endval = sa.cast(
                (
                    dt.datetime.combine(dt.date.today(), self.value1)
                    + dt.timedelta(seconds=59, microseconds=999999)
                ).time(),
                sa.Time
            )

        if self.op == ops.eq:
            query = query.filter(self.sa_col.between(val, endval))
        elif self.op == ops.not_eq:
            query = query.filter(~self.sa_col.between(val, endval))
        elif self.op == ops.less_than_equal:
            query = query.filter(self.sa_col <= endval)
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

    def get_search_expr(self, date_comparator=None):
        # This is a naive implementation that simply converts the time column to string and
        # uses a LIKE.
        return lambda value: sa.sql.cast(self.sa_col, sa.Unicode).like('%{}%'.format(value))


class YesNoFilter(FilterBase):
    """Simple "bool" filter designed for use with the YesNoColumn.

    No inputs, just the all/yes/no operators.
    """
    class ops(object):
        all = Operator('a', _('all'), None)
        yes = Operator('y', _('yes'), None)
        no = Operator('n', _('no'), None)

    operators = (
        ops.all,
        ops.yes,
        ops.no
    )
    primary_op = ops.yes

    def get_search_expr(self):
        def expr(value):
            if value.lower() in self.ops.yes.display:
                return self.sa_col == sa.true()
            elif value.lower() in self.ops.no.display:
                return self.sa_col == sa.false()
            return None
        return expr

    def apply(self, query):
        if self.op == self.ops.all:
            return query
        if self.op == self.ops.yes:
            return query.filter(self.sa_col == sa.true())
        if self.op == self.ops.no:
            return query.filter(self.sa_col == sa.false())
        return FilterBase.apply(self, query)
