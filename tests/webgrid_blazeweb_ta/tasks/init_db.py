import datetime as dt
from decimal import Decimal as D

from blazeweb.tasks import attributes
from sqlalchemybwc import db

from webgrid_blazeweb_ta.model.orm import Email, Person, Status


@attributes('~dev')
def action_40_base_data():
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
        db.sess.add(p)
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

    db.sess.commit()
