import datetime as dt
from decimal import Decimal as D

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


def load_db():
    from webgrid_ta.model.entities import Email, Person, Status, Stopwatch

    db.create_all()

    stat_open = Status.add_iu(label='open')
    stat_pending = Status.add_iu(label='pending')
    stat_closed = Status.add_iu(label='closed', flag_closed=1)

    for x in range(1, 50):
        p = Person()
        p.firstname = f'fn{x:03d}'
        p.lastname = f'ln{x:03d}'
        p.sortorder = x
        p.numericcol = D('29.26') * x / D('.9')
        if x < 90:
            p.createdts = dt.datetime.now()
        db.session.add(p)
        p.emails.append(Email(email=f'email{x:03d}@example.com'))
        p.emails.append(Email(email=f'email{x:03d}@gmail.com'))
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
        s.label = f'Watch {x}'
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
