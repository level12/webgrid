# WebGrid
[![nox](https://github.com/level12/webgrid/actions/workflows/nox.yaml/badge.svg)](https://github.com/level12/webgrid/actions/workflows/nox.yaml)
[![Codecov](https://codecov.io/gh/level12/webgrid/branch/master/graph/badge.svg)](https://codecov.io/gh/level12/webgrid)
[![AppVeyor Build Status](https://ci.appveyor.com/api/projects/status/6s1886gojqi9c8h6?svg=true)](https://ci.appveyor.com/project/level12/webgrid)


## Introduction

WebGrid is a datagrid library for Flask and other Python web frameworks designed to work with
SQLAlchemy ORM entities and queries.

With a grid configured from one or more entities, WebGrid provides these features for reporting:

- Automated SQL query construction based on specified columns and query join/filter/sort options
- Renderers to various targets/formats

  - HTML output paired with JS (jQuery) for dynamic features
  - Excel (XLSX)
  - CSV

- User-controlled data filters

  - Per-column selection of filter operator and value(s)
  - Generic single-entry search

- Session storage/retrieval of selected filter options, sorting, and paging


## Installation

Install via pip or uv:

```bash
# Just the package
pip install webgrid
uv pip install webgrid

# or, preferably in a uv project:
uv add webgrid
```

Some basic internationalization features are available via extra requirements:

```bash
pip install webgrid[i18n]
uv pip install webgrid[i18n]

# or, preferably in a uv project:
uv add webgrid --extra i18n
```


## Getting Started

For a quick start, see the [Getting Started guide](https://webgrid.readthedocs.io/en/stable/getting-started.html) in the docs.


## Links

* [Documentation](https://webgrid.readthedocs.io/en/stable/index.html)
* [Releases](https://pypi.org/project/WebGrid/)
* [Code](https://github.com/level12/webgrid)
* [Issue tracker](https://github.com/level12/webgrid/issues)
* [Questions & comments](https://github.com/level12/webgrid/discussions)


## Dev

### Copier Template

Project structure and tooling mostly derives from the [Coppy](https://github.com/level12/coppy),
see its documentation for context and additional instructions.

This project can be updated from the upstream repo, see
[Updating a Project](https://github.com/level12/coppy?tab=readme-ov-file#updating-a-project).


### Project Setup

From zero to hero (passing tests that is):

1. Ensure [host dependencies](https://github.com/level12/coppy/wiki/Mise) are installed

2. Start docker service dependencies (if needed):

   ```
   ❯ docker compose config --services
   mssql
   pg

   ❯ docker compose up -d ...
   ```

3. Sync [project](https://docs.astral.sh/uv/concepts/projects/) virtualenv w/ lock file:

   `uv sync`

4. Configure pre-commit:

   `pre-commit install`

5. Install mssql driver if intending to run mssql tests

   `mise odbc-driver-install`

6. View sessions then run sessions:

   ```
   ❯ nox --list

   # all sessions
   ❯ nox

   # selected sessions
   ❯ nox -e ...
   ```


### Versions

Versions are date based.  A `bump` action exists to help manage versions:

```shell
# Show current version
mise bump --show

# Bump version based on date, tag, and push:
mise bump

# See other options
mise bump -- --help
```


### PyPI Publishing

PyPI publishing is automated in the `nox.yaml` GitHub action:

- "v" tags will publish to pypi.org (production)
- Anything else that triggers the Nox GH action will publish to test.pypi.org

Auth for test.pypi.org is seprate from production so users who should be able to manage the PyPI
project need to be given access in both systems.


### Documentation

The [RTD project](https://app.readthedocs.org/projects/webgrid/) will automatically build on pushes
to master.
