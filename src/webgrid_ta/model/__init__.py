from __future__ import absolute_import
import datetime as dt
from decimal import Decimal as D

from flask_sqlalchemy import SQLAlchemy
from six.moves import range

db = SQLAlchemy()


def load_db():
    from webgrid_ta.model.entities import Status, Person, Email, Stopwatch

    db.create_all()

    stat_open = Status.add_iu(label=u'open')
    stat_pending = Status.add_iu(label=u'pending')
    stat_closed = Status.add_iu(label=u'closed', flag_closed=1)

    for x in range(1, 50):
        p = Person()
        p.firstname = 'fn%03d' % x
        p.lastname = 'ln%03d' % x
        p.sortorder = x
        p.numericcol = D('29.26') * x / D('.9')
        if x < 90:
            p.createdts = dt.datetime.now()
        db.session.add(p)
        p.emails.append(Email(email='email%03d@example.com' % x))
        p.emails.append(Email(email='email%03d@gmail.com' % x))
        if x % 4 == 1:
            p.status = stat_open
        elif x % 4 == 2:
            p.status = stat_pending
        elif x % 4 == 0:
            p.status = None
        else:
            p.status = stat_closed

    for x in range(1, 10):
        s = Stopwatch()
        s.label = 'Watch {}'.format(x)
        s.category = 'Sports'
        base_date = dt.datetime(year=2019, month=1, day=1)
        s.start_time_lap1 = base_date + dt.timedelta(hours=x)
        s.stop_time_lap1 = base_date + dt.timedelta(hours=x + 1)
        s.start_time_lap2 = base_date + dt.timedelta(hours=x + 2)
        s.stop_time_lap2 = base_date + dt.timedelta(hours=x + 3)
        s.start_time_lap3 = base_date + dt.timedelta(hours=x + 4)
        s.stop_time_lap3 = base_date + dt.timedelta(hours=x + 5)
        db.session.add(s)

    db.session.commit()
