from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Filter:
    op: str
    value1: str
    value2: Optional[str] = None


@dataclass
class Paging:
    pager_on: bool = False
    per_page: Optional[int] = None
    on_page: Optional[int] = None


@dataclass
class Sort:
    key: str
    flag_desc: bool


@dataclass
class GridSettings:
    search_expr: str
    filters: Dict[str, Filter]
    paging: Paging
    sort: List[Sort]
    export_to: str

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GridSettings':
        """Create from deserialized json"""
        return cls(
            search_expr=data.get('search_expr'),
            filters={key: Filter(**filter_) for key, filter_ in data.get('filters', {}).items()},
            paging=Paging(**data.get('paging', {})),
            sort=[Sort(**sort) for sort in data.get('sort', [])],
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
    export_targets: List[str]
    enable_search: bool
    enable_sort: bool


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
    errors: List[str]
