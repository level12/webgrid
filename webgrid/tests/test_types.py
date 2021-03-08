import webgrid.types as types


class TestGridSettings:
    def ok_values(self):
        return {
            'search_expr': 'foo',
            'filters': {
                'test': {'op': 'eq', 'value1': 'toast', 'value2': 'taft'},
                'test2': {'op': 'in', 'value1': 'tarp', 'value2': None},
            },
            'paging': {'pager_on': True, 'on_page': 2, 'per_page': 20},
            'sort': [{'key': 'bar', 'flag_desc': False}, {'key': 'baz', 'flag_desc': True}],
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
