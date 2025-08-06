"""
This conftest mostly for handling warnings.  Use the other conftest.py files for app/test config.

- Filters for warnings that are triggered during import go at the top level.
- Filters for warnings thrown during test runs goes in pytest_configure() below.

Having two conftest.py files is necessary because the warning configuration needs to happen before
the application's tests and/or code have a chance to import other libraries which may trigger
warnings.  So this file remains a filesystem level above the "real" conftest.py which does all the
imports.
"""

import warnings


# Treat any warning issued in a test as an exception so we are forced to explicitly handle or
# ignore it.
warnings.filterwarnings('error')
# Examples:
# warnings.filterwarnings(
#     'ignore',
#     "'cgi' is deprecated and slated for removal in Python 3.13",
#     category=DeprecationWarning,
#     module='webob.compat',
# )
# warnings.filterwarnings(
#     'ignore',
#     "'crypt' is deprecated and slated for removal in Python 3.13",
#     category=DeprecationWarning,
#     module='passlib.utils',
# )
###########
# REMINDER: when adding an ignore, add an issue to track it
###########


def pytest_configure(config):
    """
    You may be able to do all your ignores above.  If you find some warnings need to be ignored
    in pytest, you can do that with something like:

        config.addinivalue_line(
            'filterwarnings',
            # Note the lines that follow are implicitly concatinated, no "," at the end
            'ignore'
            ':pythonjsonlogger.jsonlogger has been moved to pythonjsonlogger.json'
            ':DeprecationWarning'
            ':wtforms.meta',
        )
    """
