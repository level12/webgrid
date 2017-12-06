import inspect


def enumerate_class_attributes(cls_or_instance):
    """
    Returns a sorted list of the class's attributes

    This method will not return any attribute whose name
    begins with an underscore.

    :return:
    """

    if inspect.isclass(cls_or_instance):
        cls = cls_or_instance
    else:
        cls = cls_or_instance.__class__

    members = inspect.getmembers(cls, lambda attr: not inspect.isroutine(attr))
    return sorted(
        attribute
        for (attribute, _) in members
        if not attribute.startswith('_')
    )


def current_url(manager, root_only=False, host_only=False, strip_querystring=False,
                strip_host=False, https=None):
    """
    Returns strings based on the current URL.  Assume a request with path:

        /news/list?param=foo

    to an application mounted at:

        http://localhost:8080/script

    Then:
    :param root_only: set `True` if you only want the root URL.
        http://localhost:8080/script/
    :param host_only: set `True` if you only want the scheme, host, & port.
        http://localhost:8080/
    :param strip_querystring: set to `True` if you don't want the querystring.
        http://localhost:8080/script/news/list
    :param strip_host: set to `True` you want to remove the scheme, host, & port:
        /script/news/list?param=foo
    :param https: None = use schem of current environ; True = force https
        scheme; False = force http scheme.  Has no effect if strip_host = True.
    :param environ: the WSGI environment to get the current URL from.  If not
        given, the environement from the current request will be used.  This
        is mostly for use in our unit tests and probably wouldn't have
        much application in normal use.
    """
    retval = ''

    ro = manager.request()

    if root_only:
        retval = ro.url_root
    elif host_only:
        retval = ro.host_url
    else:
        if strip_querystring:
            retval = ro.base_url
        else:
            retval = ro.url
    if strip_host:
        retval = retval.replace(ro.host_url.rstrip('/'), '', 1)
    if not strip_host and https is not None:
        if https and retval.startswith('http://'):
            retval = retval.replace('http://', 'https://', 1)
        elif not https and retval.startswith('https://'):
            retval = retval.replace('https://', 'http://', 1)

    return retval


class OverridableAttributeProperty(object):
    """
    Create an overridable attribute property.

    Say you have a class wherein you'd like to have some data
    defined via class attributes. However, you also need to be
    able to validate the data that is set on that attribute.
    Further, you wish to have the name of the attribute "plain"
    (that is, you don't want to have an internal value of `_foo`,
    you just want that attribute `foo`).

    This class provides custom setter capabilities while allowing
    you to maintain the standard non-internal name.

    This class performs a small bit of magic; of note, you should
    be aware that setting a value on one of these properties will
    create a instance value (currently named `_{name}_instance_value`)

    Example:
        class Foo:
            foo = 123

            . . .

            # create the attribute property
            # we need to pass the name (for the 'instance_value'),
            # and the current value
            foo = OverridableAttributeProperty('foo', foo)

            # create the setter
            # note that the setter takes an additional parameter `name`.
            # This name should be used when setting the value
            @foo.setter
            def foo(self, name, value):
                # validate `value`
                value = . . .

                # save to the internal name
                setattr(self, name, value)

    """
    def __init__(self, name, class_value, fset=None):
        self.name = name
        self.class_value = class_value
        self.fset = fset

    @property
    def instance_value_name(self):
        return '_{}_instance_value'.format(self.name)

    def __get__(self, obj, objtype):
        if obj is None:
            return self.class_value

        return getattr(obj, self.instance_value_name, self.class_value)

    def __set__(self, obj, value):
        if self.fset is None:
            setattr(obj, self.instance_value_name, value)

        else:
            self.fset(obj, self.instance_value_name, value)

    def setter(self, fset):
        return type(self)(self.name, self.class_value, fset)
