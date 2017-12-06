from nose.tools import eq_

from webgrid.utils import (
    enumerate_class_attributes,
    OverridableAttributeProperty
)


class Test_enumerate_class_attributes(object):
    def test_attribute_enumeration(self):
        class A:
            a = 123
            b = 456

        a = A()

        eq_(enumerate_class_attributes(A), ['a', 'b'])
        eq_(enumerate_class_attributes(a), ['a', 'b'])

    def test_subclass_attributes(self):
        class A:
            a = 123

        class B(A):
            b = 456

        eq_(enumerate_class_attributes(B), ['a', 'b'])

    def test_methods_not_enumerated(self):
        class A:
            def foo(self):
                pass

        assert 'foo' not in enumerate_class_attributes(A)

    def test_private_members_not_enumerated(self):
        class A:
            foo = 123
            _bar = 456

        eq_(enumerate_class_attributes(A), ['foo'])

    def test_sorting(self):
        class A:
            b = 456
            a = 123

        eq_(enumerate_class_attributes(A), ['a', 'b'])

    def test_properties(self):
        class A:
            a = 123
            b = 456

            @property
            def c(self):
                return 789

        eq_(enumerate_class_attributes(A), ['a', 'b', 'c'])

    def test_instance_variables_not_enumerated(self):
        class A:
            a = 123

            def __init__(self):
                self.b = 456

        a = A()

        eq_(enumerate_class_attributes(a), ['a'])


class Test_OverridableAttributeProperty(object):
    def test_class_value(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

        eq_(Foo.bar, 123)

    def test_default_instance_value(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

        foo = Foo()
        eq_(foo.bar, 123)

    def test_class_value_writable_by_default(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

        Foo.bar = 345
        eq_(Foo.bar, 345)

    def test_instance_value_writable_by_default(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

        foo = Foo()
        foo.bar = 999
        eq_(foo.bar, 999)

        eq_(Foo.bar, 123)

    def test_setter(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

            @bar.setter
            def bar(self, name, value):
                setattr(self, name, 1000 - value)

        foo = Foo()
        eq_(foo.bar, 123)
        foo.bar = 999
        eq_(foo.bar, 1)

    def test_instance_values_are_per_instance(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

            @bar.setter
            def bar(self, name, value):
                setattr(self, name, 1000 - value)

        a = Foo()
        b = Foo()

        a.bar = 10
        eq_(a.bar, 990)
        eq_(b.bar, 123)

    def test_behaves_in_init(self):
        class Foo(object):
            bar = 123

            def __init__(self):
                self.bar = 200

            bar = OverridableAttributeProperty('bar', bar)

            @bar.setter
            def bar(self, name, value):
                setattr(self, name, value * 2)

        foo = Foo()
        eq_(foo.bar, 400)

    def test_property_inherits_properly(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

            @bar.setter
            def bar(self, name, value):
                setattr(self, name, value * 2)

        class Bar(Foo):
            pass

        bar = Bar()
        eq_(bar.bar, 123)
        bar.bar = 200
        eq_(bar.bar, 400)

    def test_overriden_attribute_is_plain(self):
        class Foo(object):
            bar = 123

            bar = OverridableAttributeProperty('bar', bar)

            @bar.setter
            def bar(self, name, value):
                setattr(self, name, value * 2)

        class Bar(Foo):
            bar = 500

        bar = Bar()
        eq_(bar.bar, 500)
        bar.bar = 200
        eq_(bar.bar, 200)
