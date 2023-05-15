from abc import ABC, abstractmethod
import decimal

from blazeutils import tolist

from .extensions import gettext as _


class ValueInvalid(Exception):
    def __init__(self, msg, value, instance):
        self.msg = msg
        self.value = value
        self.instance = instance

    def __str__(self):
        return self.msg


class Validator(ABC):
    @abstractmethod
    def process(self, value):
        pass


class StringValidator(Validator):
    def process(self, value):
        if value is None or value == '':
            return None
        if not isinstance(value, str):
            return str(value)
        return value


class RequiredValidator(Validator):
    def process(self, value):
        if (
            value is None
            or value == ''
        ):
            raise ValueInvalid(_('Please enter a value.'), value, self)
        return value


class IntValidator(Validator):
    def process(self, value):
        if value is None or value == '':
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            raise ValueInvalid(_('Please enter an integer value.'), value, self)


class FloatValidator(Validator):
    def process(self, value):
        if value is None or value == '':
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            raise ValueInvalid(_('Please enter a number.'), value, self)


class DecimalValidator(Validator):
    def process(self, value):
        if value is None or value == '':
            return None
        try:
            return decimal.Decimal(value)
        except decimal.InvalidOperation:
            raise ValueInvalid(_('Please enter a number.'), value, self)


class RangeValidator(Validator):
    def __init__(self, min=None, max=None):
        if min is None and max is None:
            raise Exception(_('must specify either min or max for range validation'))
        self.min = min
        self.max = max

    def process(self, value):
        if self.min is not None and value is not None and value < self.min:
            raise ValueInvalid(
                _('Value must be greater than or equal to {}.').format(self.min), value, self)
        if self.max is not None and value is not None and value > self.max:
            raise ValueInvalid(
                _('Value must be less than or equal to {}.').format(self.max), value, self)
        return value


class OneOfValidator(Validator):
    def __init__(self, allowed_values):
        self.allowed_values = tuple(tolist(allowed_values))

    def process(self, value):
        if value is None or value == '':
            return None
        if value not in self.allowed_values:
            raise ValueInvalid(
                _('Value must be one of {}.').format(self.allowed_values), value, self)
        return value


class CustomValidator(Validator):
    def __init__(self, processor=None):
        if not callable(processor):
            raise Exception(_('Processor should be callable and take a value argument'))
        self.processor = processor

    def process(self, value):
        return self.processor(value)
