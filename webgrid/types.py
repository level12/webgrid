from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union


class ValidationError(Exception):
    pass


class FieldValidationError(ValidationError):
    def __init__(self, field, value, type_):
        message = f'Received {field}={value}; should be of type {type_}'
        super().__init__(message)


@dataclass
class Filter:
    op: str
    value1: Union[str, List[str]]
    value2: Optional[str] = None


@dataclass
class Paging:
    pager_on: bool = False
    per_page: Optional[int] = None
    on_page: Optional[int] = None

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
    field_type: Optional[str]
    hint: Optional[str] = None


@dataclass
class FilterOption:
    key: str
    value: str


@dataclass
class FilterSpec:
    operators: List[FilterOperator]
    primary_op: Optional[FilterOperator]


@dataclass
class OptionsFilterSpec(FilterSpec):
    options: List[FilterOption]


@dataclass
class ColumnGroup:
    label: str
    columns: List[str]


@dataclass
class GridTotals:
    page: Optional[Dict[str, Any]] = None
    grand: Optional[Dict[str, Any]] = None


@dataclass
class GridSettings:
    search_expr: Optional[str] = None
    filters: Dict[str, Filter] = field(default_factory=dict)
    paging: Paging = field(default_factory=Paging)
    sort: List[Sort] = field(default_factory=list)
    export_to: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GridSettings':
        """Create from deserialized json"""
        try:
            filters = {key: Filter(**filter_) for key, filter_ in data.get('filters', {}).items()}
        except TypeError as e:
            raise ValidationError(f'Filter: {e}')

        try:
            paging = Paging(**data.get('paging', {}))
        except TypeError as e:
            raise ValidationError(f'Paging: {e}')

        try:
            sort = [Sort(**sort) for sort in data.get('sort', [])]
        except TypeError as e:
            raise ValidationError(f'Sort: {e}')

        return cls(
            search_expr=data.get('search_expr'),
            filters=filters,
            paging=paging,
            sort=sort,
            export_to=data.get('export_to'),
        )

    def to_args(self) -> Dict[str, Any]:
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
    columns: List[Dict[str, str]]
    column_groups: List[ColumnGroup]
    column_types: List[Dict[str, str]]
    export_targets: List[str]
    enable_search: bool
    enable_sort: bool
    sortable_columns: List[str]
    filters: Dict[str, FilterSpec] = field(default_factory=dict)


@dataclass
class GridState:
    page_count: int
    record_count: int
    warnings: List[str]


@dataclass
class Grid:
    settings: GridSettings
    spec: GridSpec
    state: GridState
    records: List[Dict[str, Any]]
    totals: GridTotals
    errors: List[str]
