from blazeweb.views import View

from webgrid import NumericColumn
from webgrid_blazeweb_ta.extensions import lazy_gettext as _
from webgrid_blazeweb_ta.tests.grids import PeopleGrid as PGBase
from webgrid_blazeweb_ta.model.orm import Person


class CurrencyCol(NumericColumn):
    def format_data(self, data):
        return data if int(data) % 2 else data * -1


class PeopleGrid(PGBase):
    CurrencyCol(_('Currency'), Person.numericcol, format_as='percent', places=5)
    CurrencyCol(_('C2'), Person.numericcol.label('n2'), format_as='accounting')


class ManagePeople(View):
    def default(self):
        pg = PeopleGrid()
        pg.apply_qs_args()
        if pg.export_to:
            pg.export_as_response()
        self.assign('people_grid', pg)
        self.render_template()
