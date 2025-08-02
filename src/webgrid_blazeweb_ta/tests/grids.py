from webgrid import Column, DateColumn, DateTimeColumn, LinkColumnBase, NumericColumn, YesNoColumn
from webgrid.blazeweb import Grid
from webgrid.filters import DateTimeFilter, Operator, OptionsFilterBase, TextFilter, ops
from webgrid.renderers import CSV, XLS, XLSX
from webgrid_blazeweb_ta.model.orm import Person, Status


class FirstNameColumn(LinkColumnBase):
    def create_url(self, record):
        return f'/person-edit/{record.id}'


class FullNameColumn(LinkColumnBase):
    def extract_data(self, record):
        return f'{record.firstname} {record.lastname}'

    def create_url(self, record):
        return f'/person-edit/{record.id}'


class EmailsColumn(Column):
    def extract_data(self, recordset):
        return ', '.join([e.email for e in recordset.Person.emails])


class StatusFilter(OptionsFilterBase):
    operators = (
        Operator('o', 'open', None),
        ops.is_,
        ops.not_is,
        Operator('c', 'closed', None),
        ops.empty,
        ops.not_empty,
    )
    options_from = Status.pairs


class PeopleGrid(Grid):
    session_on = True
    allowed_export_targets = {'csv': CSV, 'xls': XLS, 'xlsx': XLSX}
    FirstNameColumn('First Name', Person.firstname, TextFilter)
    FullNameColumn('Full Name')
    YesNoColumn('Active', Person.inactive, reverse=True)
    EmailsColumn('Emails')
    Column('Status', Status.label.label('status'), StatusFilter(Status.id))
    DateTimeColumn('Created', Person.createdts, DateTimeFilter)
    DateColumn('Due Date', 'due_date')
    NumericColumn('Number', Person.numericcol, has_subtotal=True)

    def query_prep(self, query, has_sort, has_filters):
        query = (
            query.add_columns(Person.id, Person.lastname, Person.due_date)
            .add_entity(Person)
            .outerjoin(Person.status)
        )

        # default sort
        if not has_sort:
            query = query.order_by(Person.id)

        return query
