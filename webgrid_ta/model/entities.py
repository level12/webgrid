from __future__ import absolute_import

import enum

import arrow
from blazeutils.strings import randchars
import sqlalchemy as sa
import sqlalchemy.orm as saorm
from sqlalchemy_utils import ArrowType

from ..model import db

from .helpers import DefaultMixin


class Radio(db.Model, DefaultMixin):
    __tablename__ = 'sabwp_radios'

    make = sa.Column(sa.Unicode(255), nullable=False)
    model = sa.Column(sa.Unicode(255), nullable=False)
    year = sa.Column(sa.Integer, nullable=False)


class Car(db.Model, DefaultMixin):
    __tablename__ = 'sabwp_cars'

    make = sa.Column(sa.Unicode(255), nullable=False)
    model = sa.Column(sa.Unicode(255), nullable=False)
    year = sa.Column(sa.Integer, nullable=False)

    radio_id = sa.Column(sa.Integer, sa.ForeignKey(Radio.id), nullable=False)
    radio = sa.orm.relation(Radio, lazy=False)

    def __repr__(self):
        return '<Car %s, %s, %s>' % (self.make, self.model, self.year)


class AccountType(enum.Enum):
    admin = 'Admin'
    manager = 'Manager'
    employee = 'Employee'


class Person(db.Model, DefaultMixin):
    __tablename__ = 'persons'

    id = sa.Column(sa.Integer, primary_key=True)
    firstname = sa.Column(sa.String(50))
    lastname = sa.Column('last_name', sa.String(50))
    inactive = sa.Column(sa.SmallInteger)
    state = sa.Column(sa.String(50))
    status_id = sa.Column(sa.Integer, sa.ForeignKey('statuses.id'))
    address = sa.Column(sa.Integer)
    createdts = sa.Column(sa.DateTime)
    sortorder = sa.Column(sa.Integer)
    floatcol = sa.Column(sa.Float)
    # must specify precision here, as mssql defaults to (18, 0)
    numericcol = sa.Column(sa.Numeric(9, 2))
    boolcol = sa.Column(sa.Boolean)
    due_date = sa.Column(sa.Date)
    start_time = sa.Column(sa.Time)
    legacycol1 = sa.Column('LegacyColumn1', sa.String(50), key='legacycolumn')
    legacycol2 = sa.Column('LegacyColumn2', sa.String(50))
    account_type = sa.Column(sa.Enum(AccountType, name='person_account_type'))

    status = saorm.relationship('Status')

    def __repr__(self):
        return '<Person: "%s, created: %s">' % (self.id, self.createdts)

    @classmethod
    def testing_create(cls, firstname=None, **kwargs):
        firstname = firstname or randchars()
        return cls.add(firstname=firstname, **kwargs)

    @classmethod
    def delete_cascaded(cls):
        Email.delete_all()
        cls.delete_all()


class ArrowRecord(db.Model, DefaultMixin):
    __tablename__ = 'arrow_records'
    created_utc = sa.Column(ArrowType, default=arrow.now)

    @classmethod
    def testing_create(cls, **kwargs):
        return cls.add(**kwargs)


class Email(db.Model, DefaultMixin):
    __tablename__ = 'emails'

    id = sa.Column(sa.Integer, primary_key=True)
    person_id = sa.Column(sa.Integer, sa.ForeignKey(Person.id), nullable=False)
    email = sa.Column(sa.String(50), nullable=False)

    person = saorm.relationship(Person, backref='emails')


class Status(db.Model, DefaultMixin):
    __tablename__ = 'statuses'

    id = sa.Column(sa.Integer, primary_key=True)
    label = sa.Column(sa.String(50), nullable=False, unique=True)
    flag_closed = sa.Column(sa.Integer, default=0)

    @classmethod
    def pairs(cls):
        return db.session.query(cls.id, cls.label).order_by(cls.label)

    @classmethod
    def delete_cascaded(cls):
        Person.delete_cascaded()
        cls.delete_all()

    @classmethod
    def testing_create(cls, label=None):
        label = label or randchars()
        return cls.add(label=label)


class Stopwatch(db.Model, DefaultMixin):
    __tablename__ = 'stopwatches'

    id = sa.Column(sa.Integer, primary_key=True)
    label = sa.Column(sa.String(20))
    category = sa.Column(sa.String(20))
    start_time_lap1 = sa.Column(sa.DateTime)
    stop_time_lap1 = sa.Column(sa.DateTime)
    start_time_lap2 = sa.Column(sa.DateTime)
    stop_time_lap2 = sa.Column(sa.DateTime)
    start_time_lap3 = sa.Column(sa.DateTime)
    stop_time_lap3 = sa.Column(sa.DateTime)
