
def pytest_configure(config):
    from webgrid_ta.app import create_app
    app = create_app(config='Test')
    app.test_request_context().push()

    from webgrid_ta.model import load_db
    load_db()
