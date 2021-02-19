import webgrid.types as types


class TestMeta:
    def ok_values(self):
        return {
            'search_expr': 'foo',
            'filters': {
                'test': {'op': 'eq', 'value1': 'toast', 'value2': 'taft'},
                'test2': {'op': 'in', 'value1': 'tarp', 'value2': None},
            },
            'paging': {'on_page': 2, 'per_page': 20},
            'sort': [{'key': 'bar', 'flag_desc': False}, {'key': 'baz', 'flag_desc': True}],
        }

    def test_from_dict(self):
        data = self.ok_values()
        assert types.Meta.from_dict(data) == types.Meta(
            search_expr='foo',
            filters={
                'test': types.Filter(op='eq', value1='toast', value2='taft'),
                'test2': types.Filter(op='in', value1='tarp')
            },
            paging=types.Paging(on_page=2, per_page=20),
            sort=[types.Sort(key='bar', flag_desc=False), types.Sort(key='baz', flag_desc=True)],
        )

    def test_to_args(self):
        data = self.ok_values()
        assert types.Meta.from_dict(data).to_args() == {
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
        }
