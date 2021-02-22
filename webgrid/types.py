from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class Filter:
    op: str
    value1: str
    value2: Optional[str] = None


@dataclass
class Paging:
    per_page: int
    on_page: int


@dataclass
class Sort:
    key: str
    flag_desc: bool


@dataclass
class Meta:
    search_expr: str
    filters: Dict[str, Filter]
    paging: Paging
    sort: List[Sort]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Meta':
        """Create from deserialized json"""
        return cls(
            search_expr=data['search_expr'],
            filters={key: Filter(**filter_) for key, filter_ in data['filters'].items()},
            paging=Paging(**data['paging']),
            sort=[Sort(**sort) for sort in data['sort']],
        )

    def to_args(self) -> Dict[str, Any]:
        """Convert grid parameters to request args format"""
        args = {
            'search': self.search_expr,
            'onpage': self.paging.on_page,
            'perpage': self.paging.per_page,
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
class Grid:
    meta: Meta
    columns: List[Dict[str, str]]
    records: List[Dict[str, Any]]
