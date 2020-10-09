from __future__ import absolute_import
from flask import Blueprint, render_template

from webgrid_ta.extensions import gettext as _


main = Blueprint('main', __name__)


@main.route('/')
def index():
    from webgrid import NumericColumn
    from webgrid_ta.grids import PeopleGrid as PGBase
    from webgrid_ta.model.entities import Person

    class CurrencyCol(NumericColumn):
        def format_data(self, data):
            if data is None:
                return data
            return data if int(data) % 2 else data * -1

    class PeopleGrid(PGBase):
        CurrencyCol(_('Currency'), Person.numericcol, format_as='percent', places=5)
        CurrencyCol(_('C2'), Person.numericcol.label('n2'), format_as='accounting')

    pg = PeopleGrid(class_='datagrid')
    pg.apply_qs_args()
    if pg.export_to:
        pg.export_as_response()
    return render_template('index.html', people_grid=pg)


@main.route('/groups')
def grid_with_groups():
    from webgrid_ta.grids import StopwatchGrid
    grid = StopwatchGrid()
    return render_template('groups.html', grid=grid)
