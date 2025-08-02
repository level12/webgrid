# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.
#
# import os
# import sys
# sys.path.insert(0, os.path.abspath('.'))

import configparser
import datetime as dt

import webgrid


# -- Project information -----------------------------------------------------

project = 'WebGrid'
copyright = f'{dt.datetime.utcnow().year} Level 12'


cfg = configparser.SafeConfigParser()
cfg.read('../../setup.cfg')

tag = cfg.get('egg_info', 'tag_build')

html_context = {
    'prerelease': bool(tag),  # True if tag is not the empty string
}

# The full version, including alpha/beta/rc tags.
release = webgrid.__version__ + tag


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    'sphinx.ext.intersphinx',
    'sphinx.ext.autodoc',
    'sphinx.ext.viewcode',
]

# Add any paths that contain templates here, relative to this directory.
templates_path = ['_templates']

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = []

master_doc = 'index'


# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.
#
html_theme = 'alabaster'

html_theme_options = {
    'github_user': 'level12',
    'github_repo': 'webgrid',
    'github_banner': False,
    'github_button': True,
    'codecov_button': True,
    'extra_nav_links': {
        'Level 12': 'https://www.level12.io',
        'File an Issue': 'https://github.com/level12/webgrid/issues/new',
    },
    'show_powered_by': True,
}

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ['_static']
html_css_files = ['css/custom.css']
