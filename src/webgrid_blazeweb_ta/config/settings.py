from os import path
import warnings

from blazeweb.config import DefaultSettings


basedir = path.dirname(path.dirname(__file__))  # noqa: PTH120
app_package = path.basename(basedir)  # noqa: PTH119


class Default(DefaultSettings):
    def init(self):
        self.dirs.base = basedir
        self.app_package = app_package
        DefaultSettings.init(self)

        self.init_routing()

        self.add_component(app_package, 'sqlalchemy', 'sqlalchemybwc')
        self.add_component(app_package, 'webgrid', 'webgrid')
        self.add_component(app_package, 'templating', 'templatingbwc')

        self.name.full = 'WebGrid'
        self.name.short = 'WebGrid'

        # ignore the really big SA warning about lossy numeric types & sqlite
        warnings.filterwarnings('ignore', '.*support Decimal objects natively.*')

    def init_routing(self):
        self.add_route('/people/manage', endpoint='ManagePeople')


class Dev(Default):
    def init(self):
        Default.init(self)
        self.apply_dev_settings()

        self.db.url = 'sqlite://'

        # uncomment this if you want to use a database you can inspect
        # from os import path
        # self.db.url = 'sqlite:///%s' % path.join(self.dirs.data, 'test_application.db')


class Test(Default):
    def init(self):
        Default.init(self)
        self.apply_test_settings()

        self.db.url = 'sqlite://'

        # uncomment this if you want to use a database you can inspect
        # from os import path
        # self.db.url = 'sqlite:///%s' % path.join(self.dirs.data, 'test_application.db')


try:
    from site_settings import *  # noqa
except ImportError as e:
    if "No module named 'site_settings'" not in str(e):
        raise
