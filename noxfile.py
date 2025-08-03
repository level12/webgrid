from pathlib import Path

from nox import Session, options, parametrize
from nox_uv import session


options.default_venv_backend = 'uv'

package_path = Path.cwd()
tests_dpath = package_path / 'tests'
py_versions = ['3.10', '3.11', '3.12', '3.13']


def pytest_run(session: Session, *args, **env):
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
        'tests/webgrid_tests',
        *args,
        *session.posargs,
        env=env,
    )


@session(python=py_versions, uv_groups=['tests'])
@parametrize('db', ['pg', 'sqlite', 'mssql'])
def pytest(session: Session, db: str):
    pytest_run(session, WEBTEST_DB=db)


@session(uv_groups=['tests'], uv_no_install_project=True)
def wheel(session: Session):
    """
    Package the wheel, install in the venv, and then run the tests for one version of Python.
    Helps ensure nothing is wrong with how we package the wheel.
    """
    session.install('hatch', 'check-wheel-contents')
    version = session.run('hatch', 'version', silent=True).strip()
    wheel_fpath = package_path / 'tmp' / 'dist' / f'webgrid-{version}-py3-none-any.whl'

    if wheel_fpath.exists():
        wheel_fpath.unlink()

    session.run('hatch', 'build', '--clean')
    session.run('check-wheel-contents', wheel_fpath)
    session.run('uv', 'pip', 'install', wheel_fpath)

    out = session.run('python', '-c', 'import webgrid; print(webgrid.__file__)', silent=True)
    assert 'site-packages/webgrid/__init__.py' in out
    pytest_run(session)


@session(uv_groups=['pre-commit'])
def precommit(session: Session):
    session.run(
        'pre-commit',
        'run',
        '--all-files',
    )


@session(python=['3.11'], uv_groups=['tests'], uv_extras=['i18n'], default=False)
def translations(session: Session):
    # This is currently failing due to missing translations
    # https://github.com/level12/webgrid/issues/194
    session.run(
        'python',
        'tests/webgrid_ta/manage.py',
        'verify-translations',
        env={'PYTHONPATH': tests_dpath},
    )
