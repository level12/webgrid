from decimal import Decimal as D
import datetime as dt
from blazeweb.tasks import attributes

from webgrid_blazeweb_ta.model.orm import Status, Person, Email
from sqlalchemybwc import db


@attributes('~dev')
def action_40_base_data():
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
        db.sess.add(p)
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

    db.sess.commit()
