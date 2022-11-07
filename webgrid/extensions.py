from abc import ABC, abstractmethod
import datetime
from decimal import Decimal
import json
from pathlib import Path
import re
from typing import Any, Dict
import warnings

import arrow
import jinja2 as jinja
from werkzeug.datastructures import MultiDict

from . import types

MORPHI_PACKAGE_NAME = 'webgrid'

# begin morphi boilerplate
try:
    import morphi
except ImportError:
    morphi = None

if morphi:
    from morphi.messages import Manager
    from morphi.registry import default_registry

    translation_manager = Manager(package_name=MORPHI_PACKAGE_NAME)
    default_registry.subscribe(translation_manager)

    gettext = translation_manager.gettext
    lazy_gettext = translation_manager.lazy_gettext
    lazy_ngettext = translation_manager.lazy_ngettext
    ngettext = translation_manager.ngettext

else:
    translation_manager = None

    def gettext(message, **variables):
        if variables:
            return message.format(**variables)

        return message

    def ngettext(singular, plural, num, **variables):
        variables.setdefault('num', num)

        if num == 1:
            return gettext(singular, **variables)

        return gettext(plural, **variables)

    lazy_gettext = gettext
    lazy_ngettext = ngettext


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.date) or isinstance(obj, arrow.Arrow):
            return obj.isoformat()
        elif isinstance(obj, Decimal):
            return float(obj)

        try:
            return super().default(obj)
        except TypeError:
            return str(obj)


class ArgsLoader(ABC):
    """ Base args loader class.

    When a grid calls for its args, it requests them from the manager. The manager will have one
    or more args loaders to be run in order. Each loader fetches its args from the request,
    then ensuing loaders have the opportunity to modify or perform other operations as needed.
    """
    def __init__(self, manager):
        self.manager = manager

    @abstractmethod
    def get_args(self, grid, previous_args):
        pass


class GridPrefixBase(ArgsLoader):
    def sanitize_arg_name(self, arg_name, qs_prefix):
        if qs_prefix and arg_name.startswith(qs_prefix):
            return arg_name[len(qs_prefix):]
        return arg_name

    def get_sanitized_args(self, grid, args):
        incoming_args = []
        if grid.qs_prefix:
            for key, values in MultiDict(args).lists():
                # Only include args that start with the grid's prefix
                if not key.startswith(grid.qs_prefix):
                    continue
                key = self.sanitize_arg_name(key, grid.qs_prefix)
                for single_val in values:
                    incoming_args.append((key, single_val))
        else:
            incoming_args = args

        return MultiDict(incoming_args)

    def get_args(self, grid, previous_args):
        request_args = self.get_args_from_request()
        if 'dgreset' in request_args:
            if 'session_key' in request_args:
                return MultiDict(dict(dgreset=1, session_key=request_args['session_key']))
            return MultiDict(dict(dgreset=1))

        request_args = self.get_sanitized_args(grid, request_args)
        request_args.update(previous_args)
        return request_args

    @abstractmethod
    def get_args_from_request(self):
        pass


class RequestArgsLoader(GridPrefixBase, ArgsLoader):
    """ Simple args loader for web request.

    Args are usually passed through directly from the request. If the grid has a query string
    prefix, the relevant args will be namespaced - sanitize them here and return the subset
    needed for the given grid.

    In the reset case, ignore most args, and return only the reset flag and session key (if any).
    """
    def get_args_from_request(self):
        return self.manager.request_url_args()


class RequestFormLoader(GridPrefixBase, ArgsLoader):
    """ Simple form loader for web request.

    Form values are usually passed through directly from the request. If the grid has a prefix, the
    relevant args will be namespaced - sanitize them here and return the subset needed for the given
    grid.

    In the reset case, ignore most args, and return only the reset flag and session key (if any).
    """
    def get_args_from_request(self):
        return self.manager.request_form_args()


class RequestJsonLoader(ArgsLoader):
    """ JSON loader for web request.

    See :meth:`webgrid.types.GridSettings` for the expected JSON structure. The parsed arguments
    are converted to the querystring arg format and merged with any previous args.
    """
    def json_to_args(self, data: Dict[str, Any]):
        meta = types.GridSettings.from_dict(data)
        return MultiDict(meta.to_args())

    def get_args(self, grid, previous_args):
        data = self.manager.request_json()
        if data:
            current_args = self.json_to_args(data)
        else:
            current_args = MultiDict()
        current_args.update(previous_args)
        return current_args


class WebSessionArgsLoader(ArgsLoader):
    """ Session manager for grid args.

    Args are assumed to have been sanitized from the request already. But, args may be combined
    from the request and the session store for a number of cases.

    - If session_override or no filter ops, load args from session store
    - Having filter ops present will reset session store unless session_override is present
    - Page/sort args will always take precedence over stored args, but not reset the store
    - Export argument is handled outside of the session store

    In the reset case, ignore most args, and return only the reset flag and session key (if any).
    And clear the session store for the given grid.
    """
    _session_exclude_keys = (
        '__foreign_session_loaded__',
        'apply',
        'dgreset',
        'export_to',
        'session_key',
        'session_override',
    )

    def args_have_op(self, args):
        """Check args for containing any filter operators.

        Args:
            args (MultiDict): Request args.

        Returns:
            bool: True if at least one op is present.
        """
        regex = re.compile(r'(op\(.*\))')
        return any(regex.match(a) for a in args.keys())

    def args_have_page(self, args):
        """Check args for containing any page args.

        Args:
            args (MultiDict): Request args.

        Returns:
            bool: True if at least one page arg is present.
        """
        regex = re.compile('(onpage|perpage)')
        return any(regex.match(a) for a in args.keys())

    def args_have_sort(self, args):
        """Check args for containing any sort keys.

        Args:
            args (MultiDict): Request args.

        Returns:
            List[str]: all args matching as sort args.
        """
        regex = re.compile('(sort[1-9][0-9]*)')
        return [
            arg.string for arg in filter(
                lambda match: match is not None,
                [regex.match(a) for a in args],
            )
        ]

    def remove_grid_session(self, session_key):
        # Remove a grid session from the cookie entirely
        if 'dgsessions' not in self.manager.web_session():
            return
        if session_key not in self.manager.web_session()['dgsessions']:
            return

        self.manager.web_session()['dgsessions'].pop(session_key)
        self.manager.persist_web_session()

    def apply_session_overrides(self, session_args, previous_args):
        """ Update session args as needed from the incoming request.

        If session override case, wholesale update from the incoming request. This
        is useful if a single filter needs to be changed via the URL, but we don't
        want to dump the rest of the stored filters from the session.

        Otherwise, apply only page/sort if available in the request.

        Export directive is passed through from the request, so a session store never
        triggers an export by itself.

        Args:
            session_args (MultiDict): Args loaded from the session store.
            previous_args (MultiDict): Args that came into this args loader.

        Returns:
            MultiDict: Args to be used in grid operations.
        """
        is_override = 'session_override' in previous_args

        if is_override:
            session_args.update(previous_args)
        else:
            # Some types of args always get passed through from request_args.
            # Override paging if it exists in the query
            if self.args_have_page(previous_args):
                session_args['onpage'] = previous_args.get('onpage')
                session_args['perpage'] = previous_args.get('perpage')
            # Override sorting if it exists in the query
            for sort_arg in self.args_have_sort(previous_args):
                session_args[sort_arg] = previous_args.get(sort_arg)

        if 'export_to' in previous_args:
            # Export directive gets left out of the session storage, since a request may
            # have session key and export, and filter/sort must be loaded.
            session_args['export_to'] = previous_args['export_to']

        return session_args

    def cleanup_expired_sessions(self):
        """Remove sessions older than a certain number of hours.

        Configurable at the manager level, with the session_max_hours attribute. If
        None, cleanup is disabled.
        """
        if self.manager.session_max_hours is None:
            return

        cutoff = arrow.utcnow().shift(hours=-self.manager.session_max_hours)
        modified = False

        web_session = self.manager.web_session()
        for session_key in tuple(web_session.get('dgsessions', {}).keys()):
            grid_session = self.get_session_store(None, {'session_key': session_key})
            if arrow.get(grid_session.get('session_timestamp', cutoff)) < cutoff:
                modified = True
                web_session['dgsessions'].pop(session_key, None)

        if modified:
            self.manager.persist_web_session()

    def get_session_store(self, grid, args):
        """Load args from session by session_key, and return as MultiDict.

        Args:
            grid (BaseGrid): Grid used to get default grid key (based on grid class name).
            args (MultiDict): Request args used for session key.

        Returns:
            MultiDict: Args to be used in grid operations.
        """
        # check args for a session key. If the key is present,
        #   look it up in the session and use the saved args
        #   (if they have been saved under that key). If not,
        #   look up the class name for a default arg store.
        web_session = self.manager.web_session()
        if 'dgsessions' not in web_session:
            return args
        dgsessions = web_session['dgsessions']

        # session is stored as a JSON-serialized list of tuples, which we can turn into MultiDict
        session_key = grid.default_session_key if grid else None
        grid_session_key = args.get('session_key', None)
        if grid_session_key and dgsessions.get(grid_session_key):
            session_key = grid_session_key
        stored_args_json = dgsessions.get(session_key, '[]')
        if isinstance(stored_args_json, MultiDict):
            stored_args_json = json.dumps(list(stored_args_json.items(multi=True)))
        elif isinstance(stored_args_json, dict):
            stored_args_json = json.dumps(list(stored_args_json.items()))
        return MultiDict(json.loads(stored_args_json))

    def save_session_store(self, grid, args):
        """Save the args in the session under the session key and as defaults for this grid.

        Note, export and reset args are ignored for storage.

        Args:
            args (MultiDict): Request args to be loaded in next session store retrieval.
        """
        # save the args in the session under the session key
        #   and also as the default args for this grid
        web_session = self.manager.web_session()
        if 'dgsessions' not in web_session:
            web_session['dgsessions'] = dict()
        dgsessions = web_session['dgsessions']
        grid_session_key = args.get('session_key') or grid.session_key
        # work with a copy here
        args = MultiDict(args)
        # remove keys that should not be stored
        for key in self._session_exclude_keys:
            args.pop(key, None)

        existing_default_store = self.get_session_store(grid, MultiDict([]))

        # if we're only storing the bare minimal case, remove the store, including the default
        if not args:
            dgsessions.pop(grid_session_key, None)
            dgsessions.pop(grid.default_session_key, None)
            return self.manager.persist_web_session()

        args['datagrid'] = grid.default_session_key
        args['session_timestamp'] = existing_default_store['session_timestamp'] \
            = arrow.utcnow().isoformat()

        # if we're pulling a grid matching the default session, but with a different key,
        # no need to store the sepearate session
        if args == existing_default_store:
            dgsessions.pop(grid_session_key, None)
            return self.manager.persist_web_session()

        # serialize the args so we can enforce the correct MultiDict type on the other side
        args_json = json.dumps(list(args.items(multi=True)))
        # save in store under grid default and session key
        dgsessions[grid_session_key] = args_json
        dgsessions[grid.default_session_key] = args_json

        # some frameworks/sessions need these changes manually persisted
        self.manager.persist_web_session()

    def get_args(self, grid, previous_args):
        """ Retrieve args from session and override as appropriate.

        Submitting the header form flushes all args to the URL, so no need to load them
        from session.

        If that is not the path, then we either have filtering args on the URL, or not. Default
        behavior is currently to consider filtering args to be comprehensive and authoritative,
        UNLESS a session_override arg is present.

        The special session_override arg causes the store to overlay request args against an
        existing session, and return the combination.

        Args:
            grid (BaseGrid): Grid used to get default grid key (based on grid class name).
            previous_args (MultiDict): Incoming args, assumed to be sanitized already.

        Returns:
            MultiDict: Args to be used in grid operations.
        """
        self.cleanup_expired_sessions()

        if not grid.session_on:
            # Shouldn't be a normal case anymore. But if the grid has session store disabled,
            # honor that and just return the args that came in.
            return previous_args

        if 'dgreset' in previous_args:
            # Request has a reset. Do nothing else.
            if grid.session_on:
                self.remove_grid_session(previous_args.get('session_key') or grid.session_key)
                self.remove_grid_session(grid.default_session_key)
            return MultiDict(dict(dgreset=1, session_key=previous_args.get('session_key')))

        # From here on, work with a copy so as not to mutate the incoming args
        request_args = previous_args.copy()

        is_override = 'session_override' in request_args
        is_apply = 'apply' in request_args
        if (not self.args_have_op(request_args) and not is_apply) or is_override:
            # We are in a session-loading case.
            session_args = self.apply_session_overrides(
                self.get_session_store(grid, request_args), request_args
            )

            # Flag a foreign session if loading from another grid's session.
            session_args['__foreign_session_loaded__'] = (
                session_args.get('datagrid', grid.default_session_key) != grid.default_session_key
            )

            # No further need to treat args lists separately.
            request_args = session_args

        self.save_session_store(grid, request_args)
        return request_args


class FrameworkManager(ABC):
    """Grid manager base class for connecting grids to webapps.

    Provides common framework-related properties and methods.

    Class Attributes:
        jinja_loader (jinja.Loader): Template loader to use for HTML rendering, or a lambda
        function to create one

        args_loaders (ArgsLoader[]): Iterable of classes to use for loading grid args, in order
        of priority

        session_max_hours (int): Hours to hold a given grid session in storage. Set to None to
        disable. Default 12.

    """
    jinja_loader = lambda self: jinja.PackageLoader('webgrid', 'templates')
    args_loaders = (
        RequestArgsLoader,
        WebSessionArgsLoader,
    )
    session_max_hours = 12

    def __init__(self, db=None, jinja_loader=None, args_loaders=None, session_max_hours=None):
        self.init_db(db)

        self.jinja_loader = jinja_loader or self.jinja_loader
        if not isinstance(self.jinja_loader, jinja.BaseLoader) and callable(self.jinja_loader):
            self.jinja_loader = self.jinja_loader()
        self.args_loaders = args_loaders or self.args_loaders
        if session_max_hours is not None:
            # condition must account for possibility of 0 being passed in
            self.session_max_hours = session_max_hours

        self.init_jinja()

        if callable(getattr(self, 'init', False)):
            self.init()

    def init_db(self, db):
        """Set the db connector."""
        self.db = db

    def init_jinja(self):
        """Configure grid-specific jinja environment."""
        self.jinja_environment = jinja.Environment(
            loader=self.jinja_loader,
            finalize=lambda x: x if x is not None else '',
            autoescape=True
        )

    def static_path(self):
        """Path where static files are located on the filesystem."""
        return str(Path(__file__).resolve().parent / 'static')

    def get_args(self, grid):
        args = MultiDict()
        """Run request args through manager's args loaders, and return the result."""
        for loader in self.args_loaders:
            args = loader(self).get_args(grid, args)

        return args

    @abstractmethod
    def test_request_context(self, url='/'):
        """Get request context for tests."""

    def request_args(self):
        warnings.warn(
            'request_args is deprecated and will be removed in a future version.',
            DeprecationWarning, 2
        )
        return self.request_url_args()

    @abstractmethod
    def request_json(self):
        """Return json body of request."""

    @abstractmethod
    def request_form_args(self):
        """Return GET request args."""

    @abstractmethod
    def request_url_args(self):
        """Return POST request args."""

    @abstractmethod
    def csrf_token(self):
        """Return a CSRF token for POST."""
