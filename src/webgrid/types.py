from dataclasses import dataclass, field
from typing import Any


class ValidationError(Exception):
    pass


class FieldValidationError(ValidationError):
    def __init__(self, field, value, type_):
        message = f'Received {field}={value}; should be of type {type_}'
        super().__init__(message)


@dataclass
class Filter:
    op: str
    value1: str | list[str]
    value2: str | None = None


@dataclass
class Paging:
    pager_on: bool = False
    per_page: int | None = None
    on_page: int | None = None

    def __post_init__(self):
        if self.per_page is not None and not isinstance(self.per_page, int):
            raise FieldValidationError('per_page', self.per_page, 'int')
        if self.on_page is not None and not isinstance(self.on_page, int):
            raise FieldValidationError('on_page', self.on_page, 'int')


@dataclass
class Sort:
    key: str
    flag_desc: bool


@dataclass
class FilterOperator:
    key: str
    label: str
    field_type: str | None
    hint: str | None = None


@dataclass
class FilterOption:
    key: str
    value: str


@dataclass
class FilterSpec:
    operators: list[FilterOperator]
    primary_op: FilterOperator | None


@dataclass
class OptionsFilterSpec(FilterSpec):
    options: list[FilterOption]


@dataclass
class ColumnGroup:
    label: str
    columns: list[str]


@dataclass
class GridTotals:
    page: dict[str, Any] | None = None
    grand: dict[str, Any] | None = None


@dataclass
class GridSettings:
    search_expr: str | None = None
    filters: dict[str, Filter] = field(default_factory=dict)
    paging: Paging = field(default_factory=Paging)
    sort: list[Sort] = field(default_factory=list)
    export_to: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'GridSettings':
        """Create from deserialized json"""
        try:
            filters = {key: Filter(**filter_) for key, filter_ in data.get('filters', {}).items()}
        except TypeError as e:
            raise ValidationError(f'Filter: {e}') from e

        try:
            paging = Paging(**data.get('paging', {}))
        except TypeError as e:
            raise ValidationError(f'Paging: {e}') from e

        try:
            sort = [Sort(**sort) for sort in data.get('sort', [])]
        except TypeError as e:
            raise ValidationError(f'Sort: {e}') from e

        return cls(
            search_expr=data.get('search_expr'),
            filters=filters,
            paging=paging,
            sort=sort,
            export_to=data.get('export_to'),
        )

    def to_args(self) -> dict[str, Any]:
        """Convert grid parameters to request args format"""
        args = {
            'search': self.search_expr,
            'onpage': self.paging.on_page,
            'perpage': self.paging.per_page,
            'export_to': self.export_to,
        }

        for key, filter_ in self.filters.items():
            args[f'op({key})'] = filter_.op
            args[f'v1({key})'] = filter_.value1
            if filter_.value2:
                args[f'v2({key})'] = filter_.value2

        for i, s in enumerate(self.sort, 1):
            prefix = '-' if s.flag_desc else ''
            args[f'sort{i}'] = f'{prefix}{s.key}'

        return args


@dataclass
class GridSpec:
    columns: list[dict[str, str]]
    column_groups: list[ColumnGroup]
    column_types: list[dict[str, str]]
    export_targets: list[str]
    enable_search: bool
    enable_sort: bool
    sortable_columns: list[str]
    filters: dict[str, FilterSpec] = field(default_factory=dict)


@dataclass
class GridState:
    page_count: int
    record_count: int
    warnings: list[str]


@dataclass
class Grid:
    settings: GridSettings
    spec: GridSpec
    state: GridState
    records: list[dict[str, Any]]
    totals: GridTotals
    errors: list[str]
