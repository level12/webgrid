from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class Filter:
    op: str
    value1: str
    value2: str


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
    filters: List[Filter]
    paging: Paging
    sort: Dict[str, Sort]

    @classmethod
    def from_dict(cls, data):
        return cls(
            search_expr=data['search_expr'],
            filters=[Filter(**filter) for filter in data['filters']],
            paging=Paging(**data['paging']),
            sort={key: Sort(**sort) for (key, sort) in data['sort'].items()},
        )


@dataclass
class Grid:
    meta: Meta
    records: List[Dict[str, Any]]

    @classmethod
    def from_dict(cls, data):
        return cls(meta=Meta.from_dict(data['meta']), records=data['records'])
