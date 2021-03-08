import re

import pytest

import webgrid.types as types


class TestGridSettings:
    def ok_values(self, **kwargs):
        return {
            'search_expr': 'foo',
            'filters': {
                'test': {'op': 'eq', 'value1': 'toast', 'value2': 'taft'},
                'test2': {'op': 'in', 'value1': 'tarp', 'value2': None},
            },
            'paging': {'pager_on': True, 'on_page': 2, 'per_page': 20},
            'sort': [{'key': 'bar', 'flag_desc': False}, {'key': 'baz', 'flag_desc': True}],
            **kwargs,
        }

    def test_from_dict(self):
        data = self.ok_values()
        assert types.GridSettings.from_dict(data) == types.GridSettings(
            search_expr='foo',
            filters={
                'test': types.Filter(op='eq', value1='toast', value2='taft'),
                'test2': types.Filter(op='in', value1='tarp')
            },
            paging=types.Paging(pager_on=True, on_page=2, per_page=20),
            sort=[types.Sort(key='bar', flag_desc=False), types.Sort(key='baz', flag_desc=True)],
            export_to=None,
        )

    def test_from_dict_missing_keys(self):
        assert types.GridSettings.from_dict({}) == types.GridSettings(
            search_expr=None,
            filters={},
            paging=types.Paging(pager_on=False, on_page=None, per_page=None),
            sort=[],
            export_to=None,
        )

    def test_from_dict_invalid_values(self):
        data = self.ok_values(paging={'per_page': 'foo'})
        with pytest.raises(
            types.ValidationError, match='Received per_page=foo; should be of type int'
        ):
            types.GridSettings.from_dict(data)

    @pytest.mark.parametrize('subobject,input_data', (
        ('Sort', {'sort': [{'key': 'foo', 'flag_desc': False, 'bar': 'baz'}]}),
        ('Paging', {'paging': {'bar': 'baz'}}),
        ('Filter', {'filters': {'test': {'op': 'eq', 'value1': 'foo', 'bar': 'baz'}}}),
    ))
    def test_from_dict_extra_values(self, subobject, input_data):
        data = self.ok_values(**input_data)
        with pytest.raises(
            types.ValidationError,
            match=re.escape(f"{subobject}: __init__() got an unexpected keyword argument 'bar'"),
        ):
            types.GridSettings.from_dict(data)

    def test_from_dict_missing_values(self):
        data = self.ok_values(sort=[{'flag_desc': False}])
        with pytest.raises(
            types.ValidationError,
            match=re.escape("Sort: __init__() missing 1 required positional argument: 'key'"),
        ):
            types.GridSettings.from_dict(data)

    def test_to_args(self):
        data = self.ok_values()
        assert types.GridSettings.from_dict(data).to_args() == {
            'search': 'foo',
            'onpage': 2,
            'perpage': 20,
            'op(test)': 'eq',
            'v1(test)': 'toast',
            'v2(test)': 'taft',
            'op(test2)': 'in',
            'v1(test2)': 'tarp',
            'sort1': 'bar',
            'sort2': '-baz',
            'export_to': None,
        }
