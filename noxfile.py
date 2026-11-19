from os import environ
from pathlib import Path

import nox


package_path = Path(__file__).parent
tests_dpath = package_path / 'tests'
docs_dpath = package_path / 'docs'
is_circleci = 'CIRCLECI' in environ

py_all = ['3.12', '3.13', '3.14', '3.15']
py_single = py_all[-1:]

nox.options.default_venv_backend = 'uv'


@nox.session(python=py_all)
@nox.parametrize('db', ['pg', 'sqlite'])
def pytest(session: nox.Session, db: str):
    uv_sync(session, 'pytest')
    pytest_run(session, WEBTEST_DB=db)


@nox.session(python=py_single)
def pytest_mssql(session: nox.Session):
    uv_sync(session, 'pytest', 'mssql')
    pytest_run(session, WEBTEST_DB='mssql')


@nox.session(python=py_single)
def pytest_i18n(session: nox.Session):
    uv_sync(session, 'pytest', extra='i18n')
    pytest_run(session, WEBTEST_DB='sqlite')


@nox.session
def prek(session: nox.Session):
    uv_sync(session)
    session.run('prek', 'run', '--all-files')


@nox.session
def audit(session: nox.Session):
    uv_sync(session)
    session.run('pip-audit', '--desc', '--skip-editable', *pip_audit_ignore_args())


@nox.session
def build(session: nox.Session):
    uv_sync(session, 'build')
    output_dir = Path(environ.get('WEBGRID_DIST_DIR', Path(session.create_tmp()) / 'dist'))
    session.run('python', '-m', 'build', '--outdir', output_dir)
    session.run('twine', 'check', *output_dir.glob('*'))
    (wheel_path,) = output_dir.glob('*.whl')
    session.run(
        'uv',
        'pip',
        'install',
        '--python',
        session.virtualenv.location,
        '--reinstall',
        '--no-deps',
        wheel_path,
    )
    session.run(
        'python',
        '-c',
        'import webgrid; print(f"Imported installed wheel from {webgrid.__file__}")',
    )


@nox.session(python=py_single)
def translations(session: nox.Session):
    uv_sync(session, 'pytest', project=True, extra='i18n')
    session.run(
        'python',
        'tests/webgrid_ta/manage.py',
        'verify-translations',
        env={'PYTHONPATH': tests_dpath},
    )


@nox.session(python=py_single)
def docs(session: nox.Session):
    uv_sync(session, 'pytest', 'docs', project=True)
    session.run('make', '-C', docs_dpath, 'html', external=True)


def pytest_run(session: nox.Session, *args, **env):
    junit_opt = f'--junit-xml={package_path}/ci/test-reports/{session.name}.pytests.xml'
    junit_args = (junit_opt,) if is_circleci else ()
    test_args = session.posargs or (package_path / 'tests' / 'webgrid_tests',)
    session.run(
        'pytest',
        '-rA',
        '--tb=native',
        '--strict-markers',
        '--cov',
        '--cov-report=xml',
        '--no-cov-on-fail',
        *junit_args,
        *args,
        *test_args,
        env=env,
    )


def uv_sync(session: nox.Session, *groups, project=False, extra=None):
    if not groups:
        groups = (session.name,)
    project_args = () if project or session.name.startswith('pytest') else ('--no-install-project',)
    group_args = [arg for group in groups for arg in ('--group', group)]
    extra_args = ('--extra', extra) if extra else ()
    session.run(
        'uv',
        'sync',
        '--active',
        '--frozen',
        '--exact',
        '--no-default-groups',
        *project_args,
        *group_args,
        *extra_args,
    )


def pip_audit_ignore_args() -> list | tuple:
    ignore_fpath = package_path / 'pip-audit-ignore.txt'
    if not ignore_fpath.exists():
        return ()
    vuln_ids = [
        line
        for line in ignore_fpath.read_text().strip().splitlines()
        if line.strip() and not line.startswith('#')
    ]
    return [arg for vuln_id in vuln_ids for arg in ('--ignore-vuln', vuln_id)]
