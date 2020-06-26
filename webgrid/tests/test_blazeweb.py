from os import path

from blazeutils import tolist
from blazeweb.events import signal
from blazeweb.globals import ag, settings, user
from blazeweb.hierarchy import findobj
from blazeweb.scripting import load_current_app
from blazeweb.testing import inrequest
from sqlalchemy.orm.session import Session as SASession
import mock

from webgrid.renderers import HTML


class TestBlazeWeb(object):
    @classmethod
    def setup_class(cls):
        from blazeweb.testing import TestApp

        # these lines necessary because we are sharing test space with a Flask
        #   app built with FlaskSQLAlchemy. That lib places listeners on the
        #   session class but expects its own code will run to set up a session
        SASession._model_changes = mock.Mock()
        SASession.app = mock.Mock()

        _, _, _, wsgiapp = load_current_app('webgrid_blazeweb_ta', 'Test')

        # make the app available to the tests
        ag.wsgi_test_app = wsgiapp

        # an application can define functions to be called after the app
        # is initialized but before any test inspection is done or tests
        # are ran.  We call those functions here:
        for callstring in tolist(settings.testing.init_callables):
            tocall = findobj(callstring)
            tocall()

        # we also support events for pre-test setup
        signal('blazeweb.pre_test_init').send()

        cls.ta = TestApp(ag.wsgi_test_app)

    def test_xls_as_response(self):
        r = self.ta.get('/people/manage?export_to=xls')
        assert r.headers['Content-Type'] == 'application/vnd.ms-excel'

    def test_xlsx_as_response(self):
        r = self.ta.get('/people/manage?export_to=xlsx')
        assert (
            r.headers['Content-Type']
            == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_csv_as_response(self):
        r = self.ta.get('/people/manage?export_to=csv')
        assert r.headers['Content-Type'] == 'text/csv'

    @inrequest('/')
    def test_nonstandard_templating(self):
        from webgrid_blazeweb_ta.views import PeopleGrid as PGBase

        class PeopleGridHTML(HTML):
            def header(self):
                return self.load_content(
                    'nonstandard_header.html',
                    session_key=self.grid.session_key,
                    renderer=self,
                )

        class PeopleGrid(PGBase):
            def set_renderers(self):
                self.html = PeopleGridHTML(self)

        g = PeopleGrid()
        g.apply_qs_args()
        assert '#something' in g.html().data['text/css'][0]

    @inrequest('/path?session_key=123456')
    def test_session(self):
        from webgrid_blazeweb_ta.views import PeopleGrid
        g = PeopleGrid()
        g.apply_qs_args()
        assert '123456' in user.dgsessions

    @inrequest('/path?session_key=123456')
    def test_static_path(self):
        from webgrid_blazeweb_ta.views import PeopleGrid
        g = PeopleGrid()
        assert g.manager.static_path().endswith('webgrid{}static'.format(path.sep))
