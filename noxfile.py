from pathlib import Path

from nox import Session, options, parametrize, session


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
        '--cov',
        '--cov-config=.coveragerc',
        f'--cov-report=xml:{package_path}/ci/coverage/{session.name}.xml',
        '--no-cov-on-fail',
        'tests/webgrid_tests',
        *args,
        *session.posargs,
        env=env,
    )


def uv_sync(session: Session, *groups, project, extra=None):
    project_args = () if project else ('--no-install-project',)
    group_args = [arg for group in groups for arg in ('--group', group)]
    extra_args = ('--extra', extra) if extra else ()
    run_args = (
        'uv',
        'sync',
        '--active',
        '--no-default-groups',
        *project_args,
        *group_args,
        *extra_args,
    )
    session.run(*run_args)


@session(py=py_all)
@parametrize('db', ['pg', 'sqlite'])
def pytest(session: Session, db: str):
    uv_sync(session, 'tests', project=True)
    pytest_run(session, WEBTEST_DB=db)


@session(py=py_single)
def pytest_mssql(session: Session):
    uv_sync(session, 'tests', 'mssql', project=True)
    pytest_run(session, WEBTEST_DB='mssql')


@session(py=py_single)
def pytest_i18n(session: Session):
    uv_sync(session, 'tests', project=True, extra='i18n')
    pytest_run(session, WEBTEST_DB='sqlite')


@session(py=py_single)
def wheel(session: Session):
    """
    Package the wheel, install in the venv, and then run the tests for one version of Python.
    Helps ensure nothing is wrong with how we package the wheel.
    """
    uv_sync(session, 'tests', project=False)

    session.install('hatch', 'check-wheel-contents')
    version = session.run('hatch', 'version', silent=True, stderr=None).strip()
    wheel_fpath = package_path / 'tmp' / 'dist' / f'webgrid-{version}-py3-none-any.whl'

    if wheel_fpath.exists():
        wheel_fpath.unlink()

    session.run('hatch', 'build', '--clean')
    session.run('check-wheel-contents', wheel_fpath)
    session.run('uv', 'pip', 'install', wheel_fpath)

    out = session.run('python', '-c', 'import webgrid; print(webgrid.__file__)', silent=True)
    assert 'site-packages/webgrid/__init__.py' in out

    pytest_run(session, WEBTEST_DB='sqlite')


@session(py=py_single)
def precommit(session: Session):
    uv_sync(session, 'pre-commit', project=False)
    session.run(
        'pre-commit',
        'run',
        '--all-files',
    )


# Python 3.11 is required due to: https://github.com/level12/morphi/issues/11
@session(python=py_311)
def translations(session: Session):
    uv_sync(session, 'tests', project=True, extra='i18n')
    # This is currently failing due to missing translations
    # https://github.com/level12/webgrid/issues/194
    session.run(
        'python',
        'tests/webgrid_ta/manage.py',
        'verify-translations',
        env={'PYTHONPATH': tests_dpath},
    )


@session(py=py_single)
def docs(session: Session):
    uv_sync(session, 'tests', 'docs', project=True)
    session.run('make', '-C', docs_dpath, 'html', external=True)
