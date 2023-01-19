from __future__ import absolute_import

from webgrid import BaseGrid as BaseGrid
from webgrid import (
    Column,
    ColumnGroup,
    DateColumn,
    DateTimeColumn,
    EnumColumn,
    LinkColumnBase,
    NumericColumn,
    TimeColumn,
    YesNoColumn,
)
from webgrid.filters import (
    DateFilter,
    DateTimeFilter,
    IntFilter,
    Operator,
    OptionsEnumFilter,
    OptionsFilterBase,
    TextFilter,
    TimeFilter,
    ops,
)
from webgrid.renderers import CSV
from webgrid_ta.extensions import lazy_gettext as _

from .app import webgrid
from .model.entities import AccountType, ArrowRecord, Person, Radio, Status, Stopwatch


class Grid(BaseGrid):
    manager = webgrid


class FirstNameColumn(LinkColumnBase):
    def create_url(self, record):
        return '/person-edit/{0}'.format(record.id)


class FullNameColumn(LinkColumnBase):
    def extract_data(self, record):
        return _('{record.firstname} {record.lastname}', record=record)

    def create_url(self, record):
        return '/person-edit/{0}'.format(record.id)


class EmailsColumn(Column):
    def extract_data(self, recordset):
        return ', '.join([e.email for e in recordset.Person.emails])


class StatusFilter(OptionsFilterBase):
    operators = (
        Operator('o', _('open'), None),
        ops.is_,
        ops.not_is,
        Operator('c', _('closed'), None),
        ops.empty,
        ops.not_empty
    )
    options_from = Status.pairs


class PeopleGrid(Grid):
    session_on = True

    FirstNameColumn(_('First Name'), Person.firstname, TextFilter)
    FullNameColumn(_('Full Name'))
    YesNoColumn(_('Active'), Person.inactive, reverse=True)
    EmailsColumn(_('Emails'))
    Column(_('Status'), Status.label.label('status'), StatusFilter(Status.id))
    DateTimeColumn(_('Created'), Person.createdts, DateTimeFilter)
    DateColumn(_('Due Date'), 'due_date')
    Column(_('State'), Person.state, render_in='xlsx')
    NumericColumn(_('Number'), Person.numericcol, has_subtotal=True)
    EnumColumn(_('Account Type'), Person.account_type,
               OptionsEnumFilter(Person.account_type, enum_type=AccountType))

    def query_prep(self, query, has_sort, has_filters):
        query = query.add_columns(
            Person.id, Person.lastname, Person.due_date, Person.account_type,
        ).add_entity(Person).outerjoin(Person.status)

        # default sort
        if not has_sort:
            query = query.order_by(Person.id)

        return query


class PeopleGridByConfig(PeopleGrid):
    query_outer_joins = (Person.status, )
    query_default_sort = (Person.id, )

    def query_prep(self, query, has_sort, has_filters):
        query = query.add_columns(
            Person.id, Person.lastname, Person.due_date, Person.account_type,
        ).add_entity(Person)

        return query


class DefaultOpGrid(Grid):
    session_on = True

    FirstNameColumn(_('First Name'), Person.firstname,
                    TextFilter(Person.firstname, default_op=ops.eq))


class ArrowGrid(Grid):
    session_on = True

    DateTimeColumn(_('Created'), ArrowRecord.created_utc, DateTimeFilter)

    def query_prep(self, query, has_sort, has_filters):
        # default sort
        if not has_sort:
            query = query.order_by(ArrowRecord.id)

        return query


class ArrowCSVGrid(Grid):
    session_on = True
    allowed_export_targets = {'csv': CSV}
    DateTimeColumn(_('Created'), ArrowRecord.created_utc, DateTimeFilter)

    def query_prep(self, query, has_sort, has_filters):
        # default sort
        if not has_sort:
            query = query.order_by(ArrowRecord.id)

        return query


class StopwatchGrid(Grid):
    session_on = True

    class LapGroup1(ColumnGroup):
        label = 'Lap 1'
        class_ = 'lap-1'

    lap_group_2 = ColumnGroup('Lap 2', class_='lap-2')
    lap_group_3 = ColumnGroup('Lap 3', class_='lap-3')

    Column('ID', Stopwatch.id)
    Column('Label', Stopwatch.label, TextFilter)
    DateTimeColumn('Start Time', Stopwatch.start_time_lap1, group=LapGroup1)
    DateTimeColumn('Stop Time', Stopwatch.stop_time_lap1, group=LapGroup1)
    Column('Category', Stopwatch.category, TextFilter)
    DateTimeColumn('Start Time', Stopwatch.start_time_lap2, group=lap_group_2)
    DateTimeColumn('Stop Time', Stopwatch.stop_time_lap2, group=lap_group_2)
    DateTimeColumn('Start Time', Stopwatch.start_time_lap3, group=lap_group_3)
    DateTimeColumn('Stop Time', Stopwatch.stop_time_lap3, group=lap_group_3)

    def query_prep(self, query, has_sort, has_filters):
        # default sort
        if not has_sort:
            query = query.order_by(Stopwatch.id)

        return query


class TemporalGrid(Grid):
    session_on = True

    DateTimeColumn(_('Created'), Person.createdts, DateTimeFilter)
    DateColumn(_('Due Date'), Person.due_date, DateFilter)
    TimeColumn(_('Start Time'), Person.start_time, TimeFilter)


class RadioGrid(Grid):
    session_on = True

    Column('Make', Radio.make, TextFilter)
    Column('Model', Radio.model, TextFilter)
    Column('Year', Radio.year, IntFilter)
