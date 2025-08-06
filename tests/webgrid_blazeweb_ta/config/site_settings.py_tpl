from settings import Test

class TestMSSQL(Test):
    """ default profile when running tests """
    def init(self):
        # call parent init to setup default settings
        Test.init(self)
        self.db.url = 'mssql://user:pass@host.example.com:1435/dbname'
