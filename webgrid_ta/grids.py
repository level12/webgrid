from __future__ import absolute_import
from webgrid import BaseGrid as BaseGrid, Column, LinkColumnBase, \
    YesNoColumn, DateTimeColumn, DateColumn, NumericColumn, EnumColumn
from webgrid.filters import TextFilter, OptionsFilterBase, Operator, \
    DateTimeFilter, ops, OptionsEnumFilter
from .model.entities import ArrowRecord, Person, Status, AccountType

from .app import webgrid
from webgrid.renderers import CSV
from webgrid_ta.extensions import lazy_gettext as _


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
    Column(_('Sort Order'), Person.sortorder, render_in='xls')
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
