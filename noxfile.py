from pathlib import Path

from nox import Session, options, parametrize
from nox_uv import session


package_path = Path.cwd()
tests_dpath = package_path / 'tests'
docs_dpath = package_path / 'docs'

py_all = ['3.10', '3.11', '3.12', '3.13']
py_single = py_all[-1:]
py_311 = ['3.11']

options.default_venv_backend = 'uv'


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


@session(py=py_all, uv_groups=['tests'])
@parametrize('db', ['pg', 'sqlite', 'mssql'])
def pytest(session: Session, db: str):
    pytest_run(session, WEBTEST_DB=db)


@session(py=py_single, uv_groups=['tests'], uv_no_install_project=True)
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


@session(py=py_single, uv_groups=['pre-commit'], uv_no_install_project=True)
def precommit(session: Session):
    session.run(
        'pre-commit',
        'run',
        '--all-files',
    )


# Python 3.11 is required due to: https://github.com/level12/morphi/issues/11
# TODO: default=False since this currently fails.  Make default once it's passing.
@session(python=py_311, uv_groups=['tests'], uv_extras=['i18n'], default=False)
def translations(session: Session):
    # This is currently failing due to missing translations
    # https://github.com/level12/webgrid/issues/194
    session.run(
        'python',
        'tests/webgrid_ta/manage.py',
        'verify-translations',
        env={'PYTHONPATH': tests_dpath},
    )
