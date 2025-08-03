MORPHI_PACKAGE_NAME = 'webgrid_ta'

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
