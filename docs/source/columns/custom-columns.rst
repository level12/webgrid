.. _custom-columns:

Custom Columns
==============

The basic WebGrid Column is flexible enough to handle a great deal of data. With the other
supplied built-in columns for specific data types (boolean, date, float/decimal, int, etc.),
the most common scenarios are covered. However, any of these supplied column classes may
be extended for application-specific scenarios.

Below are some examples of common customizations on grid columns.


Rendered value::

    class AgeColumn(Column):
        def extract_data(self, record):
            # All rendered targets will show this output instead of the actual data value
            if record.age < 18:
                return 'Under 18'
            return 'Over 18'


Render specialized for single target::

    class AgeColumn(Column):
        def render_html(self, record, hah):
            # Only the HTML output will show this instead of the actual data value.
            if record.age < 18:
                # Add a CSS class to this cell for further styling.
                hah.class_ = 'under-18'
                return 'Under 18'
            return 'Over 18'


Sorting algorithm::

    class ShipmentReceived(Column):
        def apply_sort(self, query, flag_desc):
            # Always sort prioritized shipments first
            if flag_desc:
                return query.order_by(
                    priority_col.asc(),
                    self.expr.desc(),
                )
            return query.order_by(
                priority_col.asc(),
                self.expr.asc(),
            )


XLSX formula::

    class ConditionalFormulaColumn(Column):
        xlsx_formula = '=IF(AND(K{0}<>"",C{0}<>""),(K{0}-C{0})*24,"")'

        def render_xlsx(self, record, rownum=0):
            return self.xlsx_formula.format(rownum)


Value links to another view::

    class ProjectColumn(LinkColumnBase):
        def create_url(self, record):
            return flask.url_for(
                'admin.project-view',
                objid=record.id,
            )
