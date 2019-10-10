import os.path as osp
try:
    from setuptools import setup, find_packages
except ImportError:
    from ez_setup import use_setuptools
    use_setuptools()
    from setuptools import setup


# pip install -e .[develop]
develop_requires = [
    'arrow',
    'BlazeWeb',
    'coverage',
    # tests rely on SQL string comparison which fails with SA < 0.9
    'SQLAlchemy>=0.9.0'
    'SQLAlchemyBWC',
    'mock',
    'nose',
    'Flask',
    'Flask-Bootstrap',
    'Flask-Script',
    'Flask-SQLAlchemy',
    'Flask-WebTest',
    'sqlalchemy_utils',
    'sqlalchemybwc',
    'wrapt',
    'xlrd',
    'xlsxwriter',
    'xlwt',
]

cdir = osp.abspath(osp.dirname(__file__))
README = open(osp.join(cdir, 'readme.rst')).read()
CHANGELOG = open(osp.join(cdir, 'changelog.rst')).read()

version_fpath = osp.join(cdir, 'webgrid', 'version.py')
version_globals = {}
with open(version_fpath) as fo:
    exec(fo.read(), version_globals)

setup(
    name="WebGrid",
    version=version_globals['VERSION'],
    description="A library for rendering HTML tables and Excel files from SQLAlchemy models.",
    long_description='\n\n'.join((README, CHANGELOG)),
    author="Randy Syring",
    author_email="randy.syring@level12.io",
    url='https://github.com/level12/webgrid',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    license='BSD-3-Clause',
    packages=['webgrid'],
    extras_require={
        'develop': develop_requires,
        'i18n': [
            'morphi'
        ]
    },
    zip_safe=False,
    include_package_data=True,
    setup_requires=[
        'Babel'
    ],
    install_requires=[
        'BlazeUtils',
        'FormEncode',
        'SQLAlchemy',
        'jinja2',
        'python-dateutil',
        'webhelpers2',
        'Werkzeug',
    ],
    entry_points="""
        [console_scripts]
        webgrid_ta = webgrid_ta.manage:script_entry
        [nose.plugins]
        webgridta_initapp = webgrid.webgrid_nose:WebGridNosePlugin
    """,
)
