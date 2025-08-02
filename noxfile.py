from pathlib import Path
from nox import Session, options, parametrize
from nox_uv import session

options.default_venv_backend = 'uv'

package_path = Path.cwd()
py_versions = ['3.10', '3.11', '3.12', '3.13']


def pytest_run(session: Session, **env):
    session.run(
        'pytest',
        '-ra',
        '--tb=native',
        '--strict-markers',
        '--cov=webgrid',
        '--cov-config=.coveragerc',
        '--cov-report=xml',
        '--no-cov-on-fail',
        f'--junit-xml={package_path}/ci/test-reports/{session.name}.pytests.xml',
        'src/webgrid_tests',
        *session.posargs,
        env=env,
    )


@session(python=py_versions, uv_groups=['tests'])
@parametrize('db', ['pg', 'sqlite'])
def tests(session: Session, db: str):
    pytest_run(session, WEBTEST_DB=db)


@session(python=py_versions, uv_groups=['tests', 'mssql'])
def tests_mssql(session: Session):
    pytest_run(session, WEBTEST_DB='mssql')


@session(python=[py_versions[-1]], uv_groups=['tests'], uv_no_install_project=True)
def wheel_tests(session: Session):
    """
    Package the wheel, install in the venv, and then run the tests for one version of Python.
    Helps ensure nothing is wrong with how we package the wheel.
    """
    session.install('hatch', 'check-wheel-contents')
    session.run('hatch', 'build', '--clean')

    version = session.run('hatch', 'version', silent=True).strip()
    wheel_fpath = package_path / 'tmp' / 'dist' / f'webgrid-{version}-py3-none-any.whl'

    session.run('check-wheel-contents', wheel_fpath)

    session.run('uv', 'pip', 'install', wheel_fpath)
    pytest_run(session)


@session(uv_groups=['pre-commit'])
def precommit(session: Session):
    session.run(
        'pre-commit',
        'run',
        '--all-files',
    )

