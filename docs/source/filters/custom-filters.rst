Custom Filters
==============

The basic requirements for a custom filter are to supply the operators, the query modifier
for applying the filter, and a search expression for single-search. A few examples are
here.

Simple custom filter::

    class ActivityStatusFilter(FilterBase):
        # operators are declared as Operator(<key>, <display>, <field-type>)
        operators = (
            Operator('all', 'all', None),
            Operator('pend', 'pending', None),
            Operator('comp', 'completed', None),
        )

        def get_search_expr(self):
            status_col = sa.sql.case(
                [(Activity.flag_completed == sa.true(), 'completed')],
                else_='pending'
            )
            # Could use ilike here, depending on the target DBMS
            return lambda value: status_col.like('%{}%'.format(value))

        def apply(self, query):
            if self.op == 'all':
                return query
            if self.op == 'comp':
                return query.filter(Activity.flag_completed == sa.true())
            if self.op == 'pend':
                return query.filter(Activity.flag_completed == sa.false())
            return super().apply(self, query)


Options filter for INT foreign key lookup::

    class VendorFilter(OptionsIntFilterBase):
        def options_from(self):
            # Expected to return a list of tuples (id, label).
            # In this case, we're retrieving options from the database.
            return db.session.query(Vendor.id, Vendor.label).select_from(
                Vendor
            ).filter(
                Vendor.active_flag == sa.true()
            ).order_by(
                Vendor.label
            ).all()
