from __future__ import absolute_import
from __future__ import print_function
import datetime as dt

from blazeutils.decorators import curry
from blazeutils.helpers import tolist
from blazeutils.strings import randchars
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect as sa_inspect
import sqlalchemy.orm as saorm
from sqlalchemy.orm.exc import NoResultFound
import sqlalchemy.sql as sasql
import sqlalchemy.util as sautil
import wrapt

from ..model import db
import six


class DefaultColsMixin(object):
    id = sa.Column(sa.Integer, primary_key=True)
    createdts = sa.Column(sa.DateTime, nullable=False, default=dt.datetime.now,
                          server_default=sasql.text('CURRENT_TIMESTAMP'))
    updatedts = sa.Column(sa.DateTime, nullable=False, default=dt.datetime.now,
                          server_default=sasql.text('CURRENT_TIMESTAMP'), onupdate=dt.datetime.now)


@curry
def is_unique_exc(exc):
    if not isinstance(exc, IntegrityError):
        return False
    return _is_unique_msg(db.engine.dialect.name, str(exc))


def _is_unique_msg(dialect, msg):
    """
        easier unit testing this way
    """
    if dialect == 'postgresql':
        if 'duplicate key value violates unique constraint' in msg:
            return True
    elif dialect == 'mssql':
        if 'Cannot insert duplicate key' in msg:
            return True
    elif dialect == 'sqlite':
        if 'is not unique' in msg or 'are not unique' in msg:
            return True
    else:
        raise ValueError('is_unique_exc() does not yet support dialect: %s' % dialect)
    return False


@curry
def is_check_const_exc(constraint_name, exc):
    if not isinstance(exc, IntegrityError):
        return False
    return _is_check_const(db.engine.dialect.name, str(exc), constraint_name)


def _is_check_const(dialect, msg, constraint_name):
    if dialect == 'mssql':
        if 'conflicted with the CHECK constraint' in msg and constraint_name in msg:
            return True
    elif dialect == 'sqlite':
        if 'constraint {} failed'.format(constraint_name) in msg:
            return True
    elif dialect == 'postgresql':
        if 'violates check constraint' in msg and constraint_name in msg:
            return True
    else:
        raise ValueError('is_constraint_exc() does not yet support dialect: %s' % dialect)
    return False


@curry
def is_null_exc(field_name, exc):
    if not isinstance(exc, IntegrityError):
        return False
    return _is_null_msg(db.engine.dialect.name, str(exc), field_name)


def _is_null_msg(dialect, msg, field_name):
    """
        easier unit testing this way
    """
    if dialect == 'mssql':
        if 'Cannot insert the value NULL into column \'%s\'' % field_name in msg:
            return True
    elif dialect == 'sqlite':
        if '.%s may not be NULL' % field_name in msg:
            return True
    elif dialect == 'postgresql':
        if 'null value in column "%s" violates not-null constraint' % field_name in msg:
            return True
    else:
        raise ValueError('is_null_exc() does not yet support dialect: %s' % dialect)
    return False


def _find_sa_sess(decorated_obj):
    """
        The decorators will by default use sqlalchemy.db to find the SQLAlchemy
        session.  However, if the function being decorated is a method of a
        a class and that class has a _sa_sess() method, it will be called
        to retrieve the SQLAlchemy session that should be used.

        This function determins where the SA session is.
    """
    # If the function being decorated is a classmethod, and the class
    # has an attribute _sa_sess,
    if hasattr(decorated_obj, '_sa_sess'):
        return decorated_obj._sa_sess()


@wrapt.decorator
def transaction(f, decorated_obj, args, kwargs):
    """
        decorates a function so that a DB transaction is always committed after
        the wrapped function returns and also rolls back the transaction if
        an unhandled exception occurs.

        'ncm' = non class method (version)
    """
    dbsess = _find_sa_sess(decorated_obj)

    try:
        retval = f(*args, **kwargs)
        dbsess.commit()
        return retval
    except Exception:
        dbsess.rollback()
        raise


def transaction_classmethod(f):
    """
        like transaction() but makes the function a class method
    """
    return transaction(classmethod(f))


@wrapt.decorator
def ignore_unique(f, decorated_obj, args, kwargs):
    """
        Ignores exceptions caused by unique constraints or
        indexes in the wrapped function.

        'ncm' = non class method (version)
    """
    dbsess = _find_sa_sess(decorated_obj)
    try:
        return f(*args, **kwargs)
    except Exception as e:
        dbsess.rollback()
        if is_unique_exc(e):
            return
        raise


def ignore_unique_classmethod(f):
    """
        like ignore_unique() but makes the decorated function a class method
    """
    return ignore_unique(classmethod(f))


@wrapt.decorator
def one_to_none(f, _, args, kwargs):
    """
        wraps a function that uses SQLAlahcemy's ORM .one() method and returns
        None instead of raising an exception if there was no record returned.
        If multiple records exist, that exception is still raised.
    """
    try:
        return f(*args, **kwargs)
    except NoResultFound as e:
        if 'No row was found for one()' != str(e):
            raise
        return None


def one_to_none_classmethod(f):
    """
        like one_to_none_ncm() but makes the decorated function a class method
    """
    return one_to_none(classmethod(f))


class MethodsMixin(object):
    # the object that the SA session should be pulled from
    mm_db_global = db
    # the name of the attribute representing the SA session
    mm_db_sess_attr = 'session'

    @classmethod
    def _sa_sess(cls):
        return getattr(cls.mm_db_global, cls.mm_db_sess_attr)

    @classmethod
    def query(cls, *args):
        if args:
            entities = [getattr(cls, aname) for aname in args]
        else:
            entities = [cls]
        return cls._sa_sess().query(*entities)

    @transaction_classmethod
    def add(cls, **kwargs):
        o = cls()
        o.from_dict(kwargs)
        cls._sa_sess().add(o)
        return o

    @ignore_unique_classmethod
    def add_iu(cls, **kwargs):
        """
            Add a record and ignore unique constrainted related
            exceptions if encountered
        """
        return cls.add(**kwargs)

    @transaction_classmethod
    def edit(cls, oid=None, **kwargs):
        try:
            oid = oid or kwargs.pop('id')
        except KeyError:
            raise ValueError('the id must be given to edit the record')
        o = cls.get(oid)
        o.from_dict(kwargs)
        return o

    @classmethod
    def update(cls, oid=None, **kwargs):
        """
            Add or edit depending on presence if 'id' field from oid or kwargs
        """
        oid = oid or kwargs.pop('id', None)
        if oid:
            return cls.edit(oid, **kwargs)
        return cls.add(**kwargs)

    @classmethod
    def get(cls, oid):
        return cls._sa_sess().query(cls).get(oid)

    @one_to_none_classmethod
    def get_by(cls, **kwargs):
        """
        Returns the instance of this class matching the given criteria or None
        if there is no record matching the criteria.

        If multiple records are returned, an exception is raised.
        """
        return cls._sa_sess().query(cls).filter_by(**kwargs).one()

    @one_to_none_classmethod
    def get_where(cls, clause, *extra_clauses):
        """
        Returns the instance of this class matching the given clause(s) or None
        if there is no record matching the criteria.

        If multiple records are returned, an exception is raised.
        """
        where_clause = cls.combine_clauses(clause, extra_clauses)
        return cls._sa_sess().query(cls).filter(where_clause).one()

    @classmethod
    def first(cls, order_by=None):
        return cls.order_by_helper(cls._sa_sess().query(cls), order_by).first()

    @classmethod
    def first_by(cls, order_by=None, **kwargs):
        return cls.order_by_helper(cls._sa_sess().query(cls), order_by).filter_by(**kwargs).first()

    @classmethod
    def first_where(cls, clause, *extra_clauses, **kwargs):
        order_by = kwargs.pop('order_by', None)
        if kwargs:
            raise ValueError('order_by is the only acceptable keyword arg')
        where_clause = cls.combine_clauses(clause, extra_clauses)
        return cls.order_by_helper(cls._sa_sess().query(cls), order_by).filter(where_clause).first()

    @classmethod
    def list(cls, order_by=None):
        return cls.order_by_helper(cls._sa_sess().query(cls), order_by).all()

    @classmethod
    def list_by(cls, order_by=None, **kwargs):
        return cls.order_by_helper(cls._sa_sess().query(cls), order_by).filter_by(**kwargs).all()

    @classmethod
    def list_where(cls, clause, *extra_clauses, **kwargs):
        order_by = kwargs.pop('order_by', None)
        if kwargs:
            raise ValueError('order_by is the only acceptable keyword arg')
        where_clause = cls.combine_clauses(clause, extra_clauses)
        return cls.order_by_helper(cls._sa_sess().query(cls), order_by).filter(where_clause).all()

    @classmethod
    def pairs(cls, fields, order_by=None, _result=None):
        """
            Returns a list of two element tuples.
            [
                (1, 'apple')
                (2, 'banana')
            ]

            fields: string with the name of the fields you want to pair with
                a ":" seperating them.  I.e.:

                Fruit.pairs('id:name')

            order_by = order_by clause or iterable of order_by clauses
        """
        key_field_name, value_field_name = fields.split(':')
        if _result is None:
            _result = cls.list(order_by)
        retval = []
        for obj in _result:
            retval.append((
                getattr(obj, key_field_name),
                getattr(obj, value_field_name)
            ))
        return retval

    @classmethod
    def pairs_by(cls, fields, order_by=None, **kwargs):
        result = cls.list_by(order_by, **kwargs)
        return cls.pairs(fields, _result=result)

    @classmethod
    def pairs_where(cls, fields, clause, *extra_clauses, **kwargs):
        result = cls.list_where(clause, *extra_clauses, **kwargs)
        pairs = cls.pairs(fields, _result=result)
        return pairs

    @transaction_classmethod
    def delete(cls, oid):
        o = cls.get(oid)
        if o is None:
            return False

        cls._sa_sess().delete(o)
        return True

    @transaction_classmethod
    def delete_where(cls, clause, *extra_clauses):
        where_clause = cls.combine_clauses(clause, extra_clauses)
        return cls._sa_sess().query(cls).filter(where_clause).delete()

    @transaction_classmethod
    def delete_all(cls):
        return cls._sa_sess().query(cls).delete()

    @classmethod
    def count(cls):
        return cls._sa_sess().query(cls).count()

    @classmethod
    def count_by(cls, **kwargs):
        return cls._sa_sess().query(cls).filter_by(**kwargs).count()

    @classmethod
    def count_where(cls, clause, *extra_clauses):
        where_clause = cls.combine_clauses(clause, extra_clauses)
        return cls._sa_sess().query(cls).filter(where_clause).count()

    def to_dict(self, exclude=[]):
        col_prop_names = self.sa_column_names()
        data = dict([(name, getattr(self, name))
                     for name in col_prop_names if name not in exclude])
        return data

    def from_dict(self, data):
        """
        Update a mapped class with data from a JSON-style nested dict/list
        structure.
        """
        # surrogate can be guessed from autoincrement/sequence but I guess
        # that's not 100% reliable, so we'll need an override

        mapper = saorm.object_mapper(self)

        for key, value in six.iteritems(data):
            if isinstance(value, dict):
                dbvalue = getattr(self, key)
                rel_class = mapper.get_property(key).mapper.class_
                pk_props = rel_class._descriptor.primary_key_properties

                # If the data doesn't contain any pk, and the relationship
                # already has a value, update that record.
                if not [1 for p in pk_props if p.key in data] and \
                   dbvalue is not None:
                    dbvalue.from_dict(value)
                else:
                    record = rel_class.update_or_create(value)
                    setattr(self, key, record)
            elif isinstance(value, list) and \
                    value and isinstance(value[0], dict):

                rel_class = mapper.get_property(key).mapper.class_
                new_attr_value = []
                for row in value:
                    if not isinstance(row, dict):
                        raise Exception(
                            'Cannot send mixed (dict/non dict) data '
                            'to list relationships in from_dict data.'
                        )
                    record = rel_class.update_or_create(row)
                    new_attr_value.append(record)
                setattr(self, key, new_attr_value)
            else:
                setattr(self, key, value)

    @classmethod
    def order_by_helper(cls, query, order_by):
        if order_by is not None:
            return query.order_by(*tolist(order_by))
        pk_cols = sa_inspect(cls).primary_key
        return query.order_by(*pk_cols)

    @classmethod
    def combine_clauses(cls, clause, extra_clauses):
        if not extra_clauses:
            return clause
        return sasql.and_(clause, *extra_clauses)

    @classmethod
    def sa_column_names(self):
        return [p.key for p in self.__mapper__.iterate_properties
                if isinstance(p, saorm.ColumnProperty)]

    @classmethod
    def delete_cascaded(cls):
        cls.delete_all()


class DefaultMixin(DefaultColsMixin, MethodsMixin):
    pass


# Lookup Functionality
class LookupMixin(DefaultMixin):
    @sautil.classproperty
    def label(cls):
        return sa.Column(sa.Unicode(255), nullable=False, unique=True)
    active_flag = sa.Column(sa.Boolean, nullable=False, default=True)

    @classmethod
    def testing_create(cls, label=None, active=True):
        if label is None:
            label = u'%s %s' % (cls.__name__, randchars(5))
        return cls.add(label=label, active_flag=active)

    @classmethod
    def list_active(cls, include_ids=None, order_by=None):
        if order_by is None:
            order_by = cls.label
        if include_ids:
            include_ids = tolist(include_ids)
            clause = sasql.or_(
                cls.active_flag == 1,
                cls.id.in_(include_ids)
            )
        else:
            clause = cls.active_flag == 1
        return cls.list_where(clause, order_by=order_by)

    @classmethod
    def pairs_active(cls, include_ids=None, order_by=None):
        result = cls.list_active(include_ids, order_by=order_by)
        return cls.pairs('id:label', _result=result)

    @classmethod
    def get_by_label(cls, label):
        return cls.get_by(label=label)

    def __repr__(self):
        return '<%s %s:%s>' % (self.__class__.__name__, self.id, self.label)


def clear_db():
    if db.engine.dialect.name == 'postgresql':
        sql = []
        sql.append('DROP SCHEMA public cascade;')
        sql.append('CREATE SCHEMA public AUTHORIZATION %s;' % db.engine.url.username)
        sql.append('GRANT ALL ON SCHEMA public TO %s;' % db.engine.url.username)
        sql.append('GRANT ALL ON SCHEMA public TO public;')
        sql.append("COMMENT ON SCHEMA public IS 'standard public schema';")
        for exstr in sql:
            try:
                db.engine.execute(exstr)
            except Exception as e:
                print(('WARNING: %s' % e))

    elif db.engine.dialect.name == 'sqlite':
        # drop the views
        sql = "select name from sqlite_master where type='view'"
        rows = db.engine.execute(sql)
        # need to get all views before start to try and delete them, otherwise
        # we will get "database locked" errors from sqlite
        records = rows.fetchall()
        for row in records:
            db.engine.execute('drop view %s' % row['name'])

        # drop the tables
        db.metadata.reflect(bind=db.engine)
        for table in reversed(db.metadata.sorted_tables):
            try:
                table.drop(db.engine)
            except Exception as e:
                if 'no such table' not in str(e):
                    raise

    elif db.engine.dialect.name == 'mssql':
        mapping = {
            'P': 'drop procedure [%(name)s]',
            'C': 'alter table [%(parent_name)s] drop constraint [%(name)s]',
            ('FN', 'IF', 'TF'): 'drop function [%(name)s]',
            'V': 'drop view [%(name)s]',
            'F': 'alter table [%(parent_name)s] drop constraint [%(name)s]',
            'U': 'drop table [%(name)s]',
        }
        delete_sql = []
        for type, drop_sql in six.iteritems(mapping):
            sql = 'select name, object_name( parent_object_id ) as parent_name '\
                'from sys.objects where type in (\'%s\')' % '", "'.join(type)
            rows = db.engine.execute(sql)
            for row in rows:
                delete_sql.append(drop_sql % dict(row))
        for sql in delete_sql:
            db.engine.execute(sql)
    else:
        return False
    return True
