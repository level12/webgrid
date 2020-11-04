Test Usage
==========

What follows is a brief example of setting up filter/sort/content tests using `GridBase`::

    class TestTemporalGrid(webgrid.testing.GridBase):
        grid_cls = TemporalGrid

        sort_tests = (
            ('createdts', 'persons.createdts'),
            ('due_date', 'persons.due_date'),
            ('start_time', 'persons.start_time'),
        )

        @property
        def filters(self):
            # This could be assigned as a class attribute, or made into a method
            return (
                ('createdts', 'eq', dt.datetime(2018, 1, 1, 5, 30),
                "WHERE persons.createdts = '2018-01-01 05:30:00.000000'"),
                ('due_date', 'eq', dt.date(2018, 1, 1), "WHERE persons.due_date = '2018-01-01'"),
                ('start_time', 'eq', dt.time(1, 30).strftime('%I:%M %p'),
                "WHERE persons.start_time = CAST('01:30:00.000000' AS TIME)"),
            )

        def setup_method(self, _):
            Person.delete_cascaded()
            Person.testing_create(
                createdts=dt.datetime(2018, 1, 1, 5, 30),
                due_date=dt.date(2019, 5, 31),
                start_time=dt.time(1, 30),
            )

        def test_expected_rows(self):
            # Passing a tuple of tuples, since headers can be more than one row (i.e. grouped columns)
            self.expect_table_header((('Created', 'Due Date', 'Start Time'), ))

            self.expect_table_contents((('01/01/2018 05:30 AM', '05/31/2019', '01:30 AM'), ))
