from os import environ

# Default URLs works for Docker compose and CI
db_kind = environ.get('WEBTEST_DB', 'pg')

if db_kind == 'pg':
    db_port = environ.get('DC_POSTGRES_PORT', '5432')
    default_url = f'postgresql+psycopg://postgres@127.0.0.1:{db_port}/postgres'
elif db_kind == 'mssql':
    # https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
    db_port = environ.get('DC_MSSQL_PORT', '1433')
    default_url = f"mssql+pyodbc://SA:Docker-sa-password@127.0.0.1:{db_port}/tempdb?driver=ODBC+Driver+18+for+SQL+Server&trustservercertificate=yes"
else:
    assert db_kind == 'sqlite'
    default_url = 'sqlite:///'

db_url = environ.get('SQLALCHEMY_DATABASE_URI', default_url)
print('Webgrid tests database URL', db_url)

def pytest_configure(config):
    from webgrid_ta.app import create_app
    app = create_app(config='Test', database_url=db_url)
    app.app_context().push()

    from webgrid_ta.model import load_db
    load_db()
