from blazeutils.strings import randchars
import sqlalchemy as sa
import sqlalchemy.orm as saorm
from sqlalchemybwc import db
from sqlalchemybwc.lib.declarative import DefaultMixin, declarative_base


Base = declarative_base()


class Person(Base, DefaultMixin):
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
    numericcol = sa.Column(sa.Numeric)
    boolcol = sa.Column(sa.Boolean)
    due_date = sa.Column(sa.Date)
    legacycol1 = sa.Column('LegacyColumn1', sa.String(50), key='legacycolumn')
    legacycol2 = sa.Column('LegacyColumn2', sa.String(50))

    status = saorm.relationship('Status')

    def __repr__(self):
        return '<Person: "%s, created: %s">' % (self.id, self.createdts)

    @classmethod
    def testing_create(cls, firstname=None):
        firstname = firstname or randchars()
        return cls.add(firstname=firstname)

    @classmethod
    def delete_cascaded(cls):
        Email.delete_all()
        cls.delete_all()


class Email(Base, DefaultMixin):
    __tablename__ = 'emails'

    id = sa.Column(sa.Integer, primary_key=True)
    person_id = sa.Column(sa.Integer, sa.ForeignKey(Person.id), nullable=False)
    email = sa.Column(sa.String(50), nullable=False)

    person = saorm.relationship(Person, backref='emails')


class Status(Base, DefaultMixin):
    __tablename__ = 'statuses'

    id = sa.Column(sa.Integer, primary_key=True)
    label = sa.Column(sa.String(50), nullable=False, unique=True)
    flag_closed = sa.Column(sa.Integer, default=0)

    @classmethod
    def pairs(cls):
        return db.sess.query(cls.id, cls.label).order_by(cls.label)

    @classmethod
    def delete_cascaded(cls):
        Person.delete_cascaded()
        cls.delete_all()

    @classmethod
    def testing_create(cls, label=None):
        label = label or randchars()
        return cls.add(label=label)
