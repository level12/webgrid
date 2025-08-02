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
