"""Implements a simple, dynamic type system for API generation.

:author: Anthony Scopatz <scopatz@gmail.com>

Introduction
============

This module provides a suite of tools for denoting, describing, and converting
between various data types and the types coming from various systems.  This is
achieved by providing canonical abstractions of various kinds of types:

* Base types (int, str, float, non-templated classes)
* Refined types (even or odd ints, strings containing the letter 'a')
* Dependent types (templates such arrays, maps, sets, vectors)

All types are known by their name (a string identifier) and may be aliased with
other names.  However, the string id of a type is not sufficient to fully describe
most types.  The system here implements a canonical form for all kinds of types.
This canonical form is itself hashable, being comprised only of strings, ints,
and tuples.

Canonical Forms
---------------
First, let us examine the base types and the forms that they may take.  Base types
are fiducial.  The type system itself may not make any changes (refinements,
template filling) to types of this kind.  They are basically a collection of bits.
(The job of ascribing meaning to these bits falls on someone else.)  Thus base types
may be referred to simply by their string identifier.  For example::

    'str'
    'int32'
    'float64'
    'MyClass'

Aliases to these -- or any -- type names are given in the type_aliases dictionary::

    type_aliases = {
        'i': 'int32',
        'i4': 'int32',
        'int': 'int32',
        'complex': 'complex128',
        'b': 'bool',
        }

Furthermore, length-2 tuples are used to denote a type and the name or flag of its
predicate.  A predicate is a function or transformation that may be applied to
verify, validate, cast, coerce, or extend a variable of the given type.  A common
usage is to declare a pointer or reference of the underlying type.  This is done with
the string flags '*' and '&'::

    ('char', '*')
    ('float64', '&')

If the predicate is a positive integer, then this is interpreted as a
homogeneous array of the underlying type with the given length.  If this length
is zero, then the tuple is often interpreted as a scalar of this type, equivalent
to the type itself.  The length-0 scalar interpretation depends on context.  Here
are some examples of array types::

    ('char', 42)  # length-42 character array
    ('bool', 1)   # length-1 boolean array
    ('f8', 0)     # scalar 64-bit float

.. note::

    length-1 tuples are converted to length-2 tuples with a 0 predicate,
    i.e. ``('char',)`` will become ``('char', 0)``.

The next kind of type are **refinement types** or **refined types**.  A refined type
is a sub-type of another type but restricts in some way what constitutes a valid
element.  For example, if we first take all integers, the set of all positive
integers is a refinement of the original.  Similarly, starting with all possible
strings the set of all strings starting with 'A' is a refinement.

In the system here, refined types are given their own unique names (e.g. 'posint'
and 'astr').  The type system has a mapping (``refined_types``) from all refinement
type names to the names of their super-type.  The user may refer to refinement types
simply by their string name.  However the canonical form refinement types is to use
the refinement as the predicate of the super-type in a length-2 tuple, as above::

    ('int32', 'posint')  # refinement of integers to positive ints
    ('str', 'astr')      # refinement of strings to str starting with 'A'

It is these refinement types that give the second index in the tuple its 'predicate'
name.  Additionally, the predicate is used to look up the converter and validation
functions when doing code generation or type verification.

The last kind of types are known as **dependent types** or **template types**,
similar in concept to C++ template classes.  These are meta-types whose
instantiation requires one or more parameters to be filled in by further values or
types. Dependent types may nest with themselves or other dependent types.  Fully
qualifying a template type requires the resolution of all dependencies.

Classic examples of dependent types include the C++ template classes.  These take
other types as their dependencies.  Other cases may require only values as
their dependencies.  For example, suppose we want to restrict integers to various
ranges.  Rather than creating a refinement type for every combination of integer
bounds, we can use a single 'intrange' type that defines high and low dependencies.

The ``template_types`` mapping takes the dependent type names (e.g. 'map')
to a tuple of their dependency names ('key', 'value').   The ``refined_types``
mapping also accepts keys that are tuples of the following form::

    ('<type name>', '<dep0-name>', ('dep1-name', 'dep1-type'), ...)

Note that template names may be reused as types of other template parameters::

    ('name', 'dep0-name', ('dep1-name', 'dep0-name'))

As we have seen, dependent
types may either be base types (when based off of template classes), refined types,
or both.  Their canonical form thus follows the rules above with some additional
syntax.  The first element of the tuple is still the type name and the last
element is still the predicate (default 0).  However the type tuples now have a
length equal to 2 plus the number of dependencies.  These dependencies are
placed between the name and the predicate: ``('<name>', <dep0>, ..., <predicate>)``.
These dependencies, of course, may be other type names or tuples!  Let's see
some examples.

In the simplest case, take analogies to C++ template classes::

    ('set', 'complex128', 0)
    ('map', 'int32', 'float64', 0)
    ('map', ('int32', 'posint'), 'float64', 0)
    ('map', ('int32', 'posint'), ('set', 'complex128', 0), 0)

Now consider the intrange type from above.  This has the following definition and
canonical form::

    refined_types = {('intrange', ('low', 'int32'), ('high', 'int32')): 'int32'}

    # range from 1 -> 2
    ('int32', ('intrange', ('low', 'int32', 1), ('high', 'int32', 2)))

    # range from -42 -> 42
    ('int32', ('intrange', ('low', 'int32', -42), ('high', 'int32', 42)))

Note that the low and high dependencies here are length three tuples of the form
``('<dep-name>', <dep-type>, <dep-value>)``.  How the dependency values end up
being used is solely at the discretion of the implementation.  These values may
be anything, though they are most useful when they are easily convertible into
strings in the target language.

.. warning::

    Do not confuse length-3 dependency tuples with length-3 type tuples!
    The last element here is a value, not a predicate.

Next, consider a 'range' type which behaves similarly to 'intrange' except that
it also accepts the type as dependency.  This has the following definition and
canonical form::

    refined_types = {('range', 'vtype', ('low', 'vtype'), ('high', 'vtype')): 'vtype'}

    # integer range from 1 -> 2
    ('int32', ('range', 'int32', ('low', 'int32', 1), ('high', 'int32', 2)))

    # positive integer range from 42 -> 65
    (('int32', 'posint'), ('range', ('int32', 'posint'),
                                    ('low', ('int32', 'posint'), 42),
                                    ('high', ('int32', 'posint'), 65)))

Shorthand Forms
---------------
The canonical forms for types contain all the information needed to fully describe
different kinds of types.  However, as human-facing code, they can be exceedingly
verbose.  Therefore there are number of shorthand techniques that may be used to
also denote the various types.  Converting from these shorthands to the fully
expanded version may be done via the the ``canon(t)`` function.  This function
takes a single type and returns the canonical form of that type.  The following
are operations that ``canon()``  performs:

* Base type are returned as their name::

    canon('str') == 'str'

* Aliases are resolved::

    canon('f4') == 'float32'

* Expands length-1 tuples to scalar predicates::

    t = ('int32',)
    canon(t) == ('int32', 0)

* Determines the super-type of refinements::

    canon('posint') == ('int32', 'posint')

* Applies templates::

    t = ('set', 'float')
    canon(t) == ('set', 'float64', 0)

* Applies dependencies::

    t = ('intrange', 1, 2)
    canon(t) = ('int32', ('intrange', ('low', 'int32', 1), ('high', 'int32', 2)))

    t = ('range', 'int32', 1, 2)
    canon(t) = ('int32', ('range', 'int32', ('low', 'int32', 1), ('high', 'int32', 2)))

* Performs all of the above recursively::

    t = (('map', 'posint', ('set', ('intrange', 1, 2))),)
    canon(t) == (('map',
                 ('int32', 'posint'),
                 ('set', ('int32',
                    ('intrange', ('low', 'int32', 1), ('high', 'int32', 2))), 0)), 0)

These shorthands are thus far more useful and intuitive than canonical form described
above.  It is therefore recommended that users and developers write code that uses
the shorter versions, Note that ``canon()`` is guaranteed to return strings, tuples,
and integers only -- making the output of this function hashable.

Built-in Template Types
-----------------------
Template type definitions that come stock with xdress::

    template_types = {
        'map': ('key_type', 'value_type'),
        'dict': ('key_type', 'value_type'),
        'pair': ('key_type', 'value_type'),
        'set': ('value_type',),
        'list': ('value_type',),
        'tuple': ('value_type',),
        'vector': ('value_type',),
        }

Built-in Refined Types
-----------------------
Refined type definitions that come stock with xdress::

    refined_types = {
        'nucid': 'int32',
        'nucname': 'str',
        ('enum', ('name', 'str'), ('aliases', ('dict', 'str', 'int32', 0))): 'int32',
        ('function', ('arguments', ('list', ('pair', 'str', 'type'))), ('returns', 'type')): 'void',
        ('function_pointer', ('arguments', ('list', ('pair', 'str', 'type'))), ('returns', 'type')): ('void', '*'),
        }

Major Classes Overview
----------------------
Holistically, the following classes are important to type system:

* ``TypeSystem``:  This *is* the type system.
* ``TypeMatcher``: An imutable type for matching types against a pattern.
* ``MatchAny``: A singleton used to denote patterns.
* ``typestr``: Various string representations of a type as properties.

Type System API
===============

"""
from __future__ import print_function
import os
import io
import sys
from contextlib import contextmanager
from collections import Sequence, Set, Iterable, Mapping
from numbers import Number
from pprint import pformat
from warnings import warn
import gzip
try:
    import cPickle as pickle
except ImportError:
    import pickle

from xdress.utils import Arg, memoize_method, infer_format
from .containers import (_LazyConfigDict, _LazyConverterDict,
                              _LazyImportDict)
from .defaults import get_defaults

if sys.version_info[0] >= 3:
    basestring = str

class TypeSystem(object):
    """A class representing a type system.
    """

    datafields = set(['base_types', 'template_types', 'refined_types', 'humannames',
        'extra_types', 'dtypes', 'stlcontainers', 'argument_kinds',
        'variable_namespace', 'type_aliases', 'cpp_types',
        'numpy_types', 'from_pytypes', 'cython_ctypes', 'cython_cytypes',
        'cython_pytypes', 'cython_cimports', 'cython_cyimports', 'cython_pyimports',
        'cython_functionnames', 'cython_classnames', 'cython_c2py_conv',
        'cython_py2c_conv'])

    def __init__(self, base_types=None, template_types=None, refined_types=None,
                 humannames=None, extra_types='xdress_extra_types', dtypes='dtypes',
                 stlcontainers='stlcontainers', argument_kinds=None,
                 variable_namespace=None, type_aliases=None, cpp_types=None,
                 numpy_types=None, from_pytypes=None, cython_ctypes=None,
                 cython_cytypes=None, cython_pytypes=None, cython_cimports=None,
                 cython_cyimports=None, cython_pyimports=None,
                 cython_functionnames=None, cython_classnames=None,
                 cython_c2py_conv=None, cython_py2c_conv=None, typestring=None):
        """Parameters
        ----------
        base_types : set of str, optional
            The base or primitive types in the type system.
        template_types : dict, optional
            Template types are types whose instantiations are based on meta-types.
            this dict maps their names to meta-type names in order.
        refined_types : dict, optional
            This is a mapping from refinement type names to the parent types.
            The parent types may either be base types, compound types, template
            types, or other refined types!
        humannames : dict, optional
            The human readable names for types.
        extra_types : str, optional
            The name of the xdress extra types module.
        dtypes : str, optional
            The name of the xdress numpy dtypes wrapper module.
        stlcontainers : str, optional
            The name of the xdress C++ standard library containers wrapper module.
        argument_kinds : dict, optional
            Templates types have arguments. This is a mapping from type name to a
            tuple of utils.Arg kind flags.  The order in the tuple matches the value
            in template_types. This is only vaid for concrete types, ie
            ('vector', 'int', 0) and not just 'vector'.
        variable_namespace : dict, optional
            Templates arguments may be variables. These variables may live in a
            namespace which is required for specifiying the type.  This is a
            dictionary mapping variable names to thier namespace.
        type_aliases : dict, optional
            Aliases that may be used to substitute one type name for another.
        cpp_types : dict, optional
            The C/C++ representation of the types.
        numpy_types : dict, optional
            NumPy's Cython representation of the types.
        from_pytypes : dict, optional
            List of Python types which match may be converted to these types.
        cython_ctypes : dict, optional
            Cython's C/C++ representation of the types.
        cython_cytypes : dict, optional
            Cython's Cython representation of the types.
        cython_pytypes : dict, optional
            Cython's Python representation of the types.
        cython_cimports : dict, optional
            A sequence of tuples representing cimports that are needed for Cython
            to represent C/C++ types.
        cython_cyimports : dict, optional
            A sequence of tuples representing cimports that are needed for Cython
            to represent Cython types.
        cython_pyimports : dict, optional
            A sequence of tuples representing imports that are needed for Cython
            to represent Python types.
        cython_functionnames : dict, optional
            Cython alternate name fragments used for mangling function and
            variable names.  These should try to adhere to a lowercase_and_underscore
            convention.  These may contain template argument namess as part of a
            format string, ie ``{'map': 'map_{key_type}_{value_type}'}``.
        cython_classnames : dict, optional
            Cython alternate name fragments used for mangling class names.
            These should try to adhere to a CapCase convention.  These may contain
            template argument namess as part of a format string,
            ie ``{'map': 'Map{key_type}{value_type}'}``.
        cython_c2py_conv : dict, optional
            Cython convertors from C/C++ types to the representative Python types.
        cython_py2c_conv : dict, optional
            Cython convertors from Python types to the representative C/C++ types.
            Valuse are tuples with the form of ``(body or return, return or False)``.
        typestring : typestr or None, optional
            An type that is used to format types to strings in conversion routines.

        """
        defaults = get_defaults()

        self.base_types = base_types if base_types is not None else defaults['base_types']
        self.template_types = template_types if template_types is not None else defaults['template_types']
        self.refined_types = refined_types if refined_types is not None else defaults['refined_types']
        self.humannames = humannames if humannames is not None else defaults['humannames']
        self.extra_types = extra_types
        self.dtypes = dtypes
        self.stlcontainers = stlcontainers
        self.argument_kinds = argument_kinds if argument_kinds is not None else defaults['argument_kinds']
        self.variable_namespace = variable_namespace if \
                                  variable_namespace is not None else {}
        self.type_aliases = _LazyConfigDict(type_aliases if type_aliases is not None
                                            else defaults['type_aliases'], self)

        self.cpp_types = _LazyConfigDict(cpp_types if cpp_types is not None
                                         else defaults['cpp_types'], self)

        self.numpy_types = _LazyConfigDict(numpy_types if numpy_types is not None
                                           else defaults['numpy_types'], self)

        self.from_pytypes = from_pytypes if from_pytypes is not None else defaults['from_pytypes']

        self.cython_ctypes = _LazyConfigDict(cython_ctypes if cython_ctypes is not None
                                             else defaults['cython_ctypes'], self)

        self.cython_cytypes = _LazyConfigDict(cython_cytypes if cython_cytypes is not None
                                              else defaults['cython_cytypes'], self)

        self.cython_pytypes = _LazyConfigDict(cython_pytypes if cython_pytypes is not None
                                              else defaults['cython_pytypes'], self)

        self.cython_cimports = _LazyImportDict(cython_cimports if cython_cimports is not None
                                               else defaults['cython_cimports'], self)

        self.cython_cyimports = _LazyImportDict(cython_cyimports if cython_cyimports is not None
                                                else defaults['cython_cyimports'], self)

        self.cython_pyimports = _LazyImportDict(cython_pyimports if cython_pyimports is not None
                                                else defaults['cython_pyimports'], self)

        self.cython_functionnames = _LazyConfigDict(cython_functionnames if cython_functionnames is not None
                                                    else defaults['cython_functionnames'], self)

        self.cython_classnames = _LazyConfigDict(cython_classnames if cython_classnames is not None
                                                 else defaults['cython_classnames'], self)

        self.cython_c2py_conv = _LazyConverterDict(cython_c2py_conv if cython_c2py_conv is not None
                                                   else defaults['cython_c2py_conv'], self)

        self.cython_py2c_conv = _LazyConverterDict(cython_py2c_conv if cython_py2c_conv is not None
                                                   else defaults['cython_py2c_conv'], self)

        self.typestr = typestring or typestr

    @classmethod
    def empty(cls):
        """This is a class method which returns an empty type system."""
        x = cls(base_types=set(), template_types={}, refined_types={}, humannames={},
                type_aliases={}, cpp_types={}, numpy_types={}, from_pytypes={},
                cython_ctypes={}, cython_cytypes={}, cython_pytypes={},
                cython_cimports={}, cython_cyimports={}, cython_pyimports={},
                cython_functionnames={}, cython_classnames={}, cython_c2py_conv={},
                cython_py2c_conv={})
        del x.extra_types
        del x.dtypes
        del x.stlcontainers
        return x

    @classmethod
    def load(cls, filename, format=None, mode='rb'):
        """Loads a type system from disk into a new type system instance.
        This is a class method.

        Parameters
        ----------
        filename : str
            Path to file.
        format : str, optional
            The file format to save the type system as.  If this is not provided,
            it is infered from the filenme.  Options are:

            * pickle ('.pkl')
            * gzipped pickle ('.pkl.gz')

        mode : str, optional
            The mode to open the file with.

        """
        format = infer_format(filename, format)
        if not os.path.isfile(filename):
            raise RuntimeError("{0!r} not found.".format(filename))
        if format == 'pkl.gz':
            f = gzip.open(filename, 'rb')
            data = pickle.loads(f.read())
            f.close()
        elif format == 'pkl':
            with io.open(filename, 'rb') as f:
                data = pickle.loads(f.read())
        x = cls(**data)
        return x

    def dump(self, filename, format=None, mode='wb'):
        """Saves a type system out to disk.

        Parameters
        ----------
        filename : str
            Path to file.
        format : str, optional
            The file format to save the type system as.  If this is not provided,
            it is infered from the filenme.  Options are:

            * pickle ('.pkl')
            * gzipped pickle ('.pkl.gz')

        mode : str, optional
            The mode to open the file with.

        """
        data = dict([(k, getattr(self, k, None)) for k in self.datafields])
        format = infer_format(filename, format)
        if format == 'pkl.gz':
            f = gzip.open(filename, mode)
            f.write(pickle.dumps(data, pickle.HIGHEST_PROTOCOL))
            f.close()
        elif format == 'pkl':
            with io.open(filename, mode) as f:
                f.write(pickle.dumps(data, pickle.HIGHEST_PROTOCOL))

    def update(self, *args, **kwargs):
        """Updates the type system in-place. Only updates the data attributes
        named in 'datafields'.  This may be called with any of the following
        signatures::

            ts.update(<TypeSystem>)
            ts.update(<dict-like>)
            ts.update(key1=value1, key2=value2, ...)

        Valid keyword arguments are the same here as for the type system
        constructor.  See this documentation for more detail.
        """
        datafields = self.datafields
        # normalize arguments
        if len(args) == 1 and len(kwargs) == 0:
            toup = args[0]
            if isinstance(toup, TypeSystem):
                toup = dict([(k, getattr(toup, k)) for k in datafields \
                              if hasattr(toup, k)])
            elif not isinstance(toup, Mapping):
                toup = dict(toup)
        elif len(args) == 0:
            toup = kwargs
        else:
            msg = "invalid siganture: args={0!r}, kwargs={1!0}"
            raise TypeError(msg.fomat(args, kwargs))
        # verify keys
        for k in toup:
            if k not in datafields:
                msg = "{0} is not a member of {1}"
                raise AttributeError(msg.format(k, self.__class__.__name__))
        # perform the update
        for k, v in toup.items():
            x = getattr(self, k)
            if isinstance(v, Mapping):
                x.update(v)
            elif isinstance(v, Set):
                x.update(v)
            else:
                setattr(self, k, v)

    def __str__(self):
        s = pformat(dict([(k, getattr(self, k, None)) for k in \
                                                      sorted(self.datafields)]))
        return s

    def __repr__(self):
        s = self.__class__.__name__ + "("
        s += ", ".join(["{0}={1!r}".format(k, getattr(self, k, None)) \
                        for k in sorted(self.datafields)])
        s += ")"
        return s

    #################### Important Methods below ###############################

    @memoize_method
    def istemplate(self, t):
        """Returns whether t is a template type or not."""
        if isinstance(t, basestring):
            return t in self.template_types
        if isinstance(t, Sequence):
            return self.istemplate(t[0])
        return False

    @memoize_method
    def isenum(self, t):
        try:
            t = self.canon(t)
        except TypeError:
            return False
        return isinstance(t, Sequence) and t[0] == 'int32' and \
           isinstance(t[1], Sequence) and t[1][0] == 'enum'

    @memoize_method
    def isfunctionpointer(self, t):
        t = self.canon(t)
        return isinstance(t, Sequence) and t[0] == ('void', '*') and \
               isinstance(t[1], Sequence) and t[1][0] == 'function_pointer'

    @memoize_method
    def humanname(self, t, hnt=None):
        """Computes human names for types."""
        if hnt is None:
            t = self.canon(t)
            if isinstance(t, basestring):
                return t, self.humannames[t]
            elif t[0] in self.base_types:
                return t, self.humannames[t[0]]
            return self.humanname(t, self.humannames[t[0]])
        d = {}
        for key, x in zip(self.template_types[t[0]], t[1:-1]):
            if isinstance(x, basestring):
                val = self.humannames[x]
            elif isinstance(x, int):
                val = x
            elif x[0] in self.base_types:
                val = self.humannames[x[0]]
            else:
                val, _ = self.humanname(x, self.humannames[x[0]])
            d[key] = val
        return t, hnt.format(**d)

    @memoize_method
    def isdependent(self, t):
        """Returns whether t is a dependent type or not."""
        deptypes = set([k[0] for k in self.refined_types \
                        if not isinstance(k, basestring)])
        if isinstance(t, basestring):
            return t in deptypes
        if isinstance(t, Sequence):
            return self.isdependent(t[0])
        return False

    @memoize_method
    def isrefinement(self, t):
        """Returns whether t is a refined type."""
        if isinstance(t, basestring):
            return t in self.refined_types
        return self.isdependent(t)

    @memoize_method
    def _resolve_dependent_type(self, tname, tinst=None):
        depkey = [k for k in self.refined_types if k[0] == tname][0]
        depval = self.refined_types[depkey]
        istemplated = self.istemplate(depkey)
        if tinst is None:
            return depkey
        elif istemplated:
            assert len(tinst) == len(depkey)
            typemap = dict([(k, tinst[i]) for i, k in enumerate(depkey[1:], 1) \
                                                   if isinstance(k, basestring)])
            for k in typemap:
                if k in self.type_aliases:
                    raise TypeError('template type {0} already exists'.format(k))
            self.type_aliases.update(typemap)
            resotype = self.canon(depval), (tname,) + \
                        tuple([self.canon(k) for k in depkey[1:] if k in typemap]) + \
                        tuple([(k[0], self.canon(k[1]), instval) \
                            for k, instval in zip(depkey[1:], tinst[1:])
                            if k not in typemap])
            for k in typemap:
                del self.type_aliases[k]
                self.delmemo('canon', k)
            return resotype
        else:
            assert len(tinst) == len(depkey)
            return self.canon(depval), (tname,) + tuple([(kname, self.canon(ktype),
                instval) for (kname, ktype), instval in zip(depkey[1:], tinst[1:])])

    @memoize_method
    def canon(self, t):
        """Turns the type into its canonical form. See module docs for more information."""
        if isinstance(t, basestring):
            if t in self.base_types:
                return t
            elif t in self.type_aliases:
                return self.canon(self.type_aliases[t])
            elif t in self.refined_types:
                return (self.canon(self.refined_types[t]), t)
            elif self.isdependent(t):
                return self._resolve_dependent_type(t)
            else:
                _raise_type_error(t)
                # BELOW this would be for complicated string representations,
                # such as 'char *' or 'map<nucid, double>'.  Would need to write
                # the parse_type() function and that might be a lot of work.
                #parse_type(t)
        elif isinstance(t, Sequence):
            t0 = t[0]
            tlen = len(t)
            if 0 == tlen:
                _raise_type_error(t)
            last_val = 0 if tlen == 1 else t[-1]
            if not isinstance(t0, basestring) and not isinstance(t0, Sequence):
                _raise_type_error(t)
            if self.isdependent(t0):
                return self._resolve_dependent_type(t0, t)
            elif t0 in self.template_types:
                templen = len(self.template_types[t0])
                last_val = 0 if tlen == 1 + templen else t[-1]
                filledt = [t0]
                for tt in t[1:1+templen]:
                    
                    if isinstance(tt, Number):  # includes bool!
                        filledt.append(tt)
                    elif isinstance(tt, basestring):
                        try:
                            canontt = self.canon(tt)
                        except TypeError:
                            canontt = tt
                        except:
                            raise
                        filledt.append(canontt)
                    elif isinstance(tt, Sequence):
                        if len(tt) == 2 and tt[0] in Arg:
                            filledt.append(self.canon(tt[1]))
                        else:
                            filledt.append(self.canon(tt))
                    else:
                        _raise_type_error(tt)
                filledt.append(last_val)
                return tuple(filledt)
            else:
                return (self.canon(t0), last_val)
        else:
            _raise_type_error(t)

    @memoize_method
    def strip_predicates(self, t):
        """Removes all outer predicates from a type."""
        t = self.canon(t)
        if isinstance(t, basestring):
            return t
        elif isinstance(t, Sequence):
            tlen = len(t)
            if tlen == 2:
                sp0 = self.strip_predicates(t[0])
                return (sp0, 0) if t[1] == 0 else sp0
            else:
                return t[:-1] + (0,)
        else:
            _raise_type_error(t)

    @memoize_method
    def basename(self, t):
        """Retrieves basename from a type, e.g. 'map' in ('map', 'int', 'float')."""
        t = self.canon(t)
        if isinstance(t, basestring):
            return t
        elif isinstance(t, Sequence):
            t0 = t
            while not isinstance(t0, basestring):
                t0 = t0[0]
            return t0
        else:
            _raise_type_error(t)

    ###########################   C/C++ Methods   #############################

    def _cpp_type_add_predicate(self, t, last):
        """Adds a predicate to a C++ type"""
        if last == 'const':
            x, y = last, t
        else:
            x, y = t, last
        return '{0} {1}'.format(x, y)

    def _cpp_var_name(self, var):
        ns = self.variable_namespace.get(var, '')
        if len(ns) > 0:
            name = ns + "::" + var
        else:
            name = var
        return name

    @memoize_method
    def cpp_type(self, t):
        """Given a type t, returns the corresponding C++ type declaration."""
        t = self.canon(t)
        if isinstance(t, basestring):
            if t in self.base_types:
                return self.cpp_types[t]
        # must be tuple below this line
        tlen = len(t)
        if 2 == tlen:
            if 0 == t[1]:
                return self.cpp_type(t[0])
            elif self.isrefinement(t[1]):
                if t[1][0] in self.cpp_types:
                    subtype = self.cpp_types[t[1][0]]
                    if callable(subtype):
                        subtype = subtype(t[1], self)
                    return subtype
                else:
                    return self.cpp_type(t[0])
            else:
                last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
                return self._cpp_type_add_predicate(self.cpp_type(t[0]), last)
        elif 3 <= tlen:
            assert t[0] in self.template_types
            assert len(t) == len(self.template_types[t[0]]) + 2
            template_name = self.cpp_types[t[0]]
            assert template_name is not NotImplemented
            template_filling = []
            kinds = self.argument_kinds.get(t, ((Arg.NONE,),)*(tlen-2))
            for x, kind in zip(t[1:-1], kinds):
                if kind is Arg.LIT:
                    x = self.cpp_literal(x)
                elif kind is Arg.TYPE:
                    x = self.cpp_type(x)
                elif kind is Arg.VAR:
                    x = self._cpp_var_name(x)
                elif isinstance(x, bool):
                    x = self.cpp_types[x]
                elif isinstance(x, Number):
                    x = str(x)
                else:
                    try:
                        x = self.cpp_type(x)  # Guess it is a type?
                    except TypeError:
                        x = self._cpp_var_name(x)  # Guess it is a variable
                template_filling.append(x)
            cppt = '{0}< {1} >'.format(template_name, ', '.join(template_filling))
            if 0 != t[-1]:
                last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
                cppt = self._cpp_type_add_predicate(cppt, last)
            return cppt

    @memoize_method
    def cpp_literal(self, lit):
        """Converts a literal value to it C++ form.
        """
        if isinstance(lit, bool):
            cpp_lit = self.cpp_types[lit]
        elif isinstance(lit, Number):
            cpp_lit = str(lit)
        elif isinstance(lit, basestring):
            cpp_lit = repr(lit)
        return cpp_lit

    @memoize_method
    def cpp_funcname(self, name, argkinds=None):
        """This returns a name for a function based on its name, rather than
        its type.  The name may be either a string or a tuple of the form
        ('name', template_arg1, template_arg2, ...). The argkinds argument here
        refers only to the template arguments, not the function signature default
        arguments. This is not meant to replace cpp_type(), but complement it.
        """
        if isinstance(name, basestring):
            return name
        if argkinds is None:
            argkinds = [(Arg.NONE, None)] * (len(name) - 1)
        fname = name[0]
        cts = []
        for x, (argkind, argvalue) in zip(name[1:], argkinds):
            if argkind is Arg.TYPE:
                ct = self.cpp_type(x)
            elif argkind is Arg.LIT:
                ct = self.cpp_literal(x)
            elif isinstance(x, Number):
                ct = self.cpp_literal(x)
            else:
                try:
                    ct = self.cpp_type(x)  # guess it is a type
                except TypeError:
                    ct = x  # guess it is a variable
            cts.append(ct)
        fname += '' if 0 == len(cts) else "< " + ", ".join(cts) + " >"
        return fname

    @memoize_method
    def gccxml_type(self, t):
        """Given a type t, returns the corresponding GCC-XML type name."""
        cppt = self.cpp_type(t)
        gxt = cppt.replace('< ', '<').replace(' >', '>').\
                   replace('>>', '> >').replace(', ', ',')
        return gxt

    @memoize_method
    def cython_nptype(self, t, depth=0):
        """Given a type t, returns the corresponding numpy type.  If depth is
        greater than 0 then this returns of a list of numpy types for all internal
        template types, ie the float in ('vector', 'float', 0).

        """
        if isinstance(t, Number):
            return 'np.NPY_OBJECT'
        t = self.canon(t)
        if isinstance(t, basestring):
            return self.numpy_types[t] if t in self.numpy_types else 'np.NPY_OBJECT'
        # must be tuple below this line
        tlen = len(t)
        if t in self.numpy_types and depth < 1:
            return self.numpy_types[t]
        elif 2 == tlen:
            if 0 == t[1]:
                return self.cython_nptype(t[0])
            elif self.isrefinement(t[1]):
                return self.cython_nptype(t[0])
            else:
                # FIXME last is ignored for strings, but what about other types?
                #last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
                #return cython_pytype(t[0]) + ' {0}'.format(last)
                return self.cython_nptype(t[0])
        elif 0 < depth and self.istemplate(t):
            depth -= 1
            return [self.cython_nptype(u, depth=depth) for u in t[1:-1]]
        elif 3 == tlen and self.istemplate(t):
            return self.cython_nptype(t[1])
        else:  # elif 3 <= tlen:
            return 'np.NPY_OBJECT'

    #########################   Cython Functions   ############################

    def _cython_ctype_add_predicate(self, t, last):
        """Adds a predicate to a ctype"""
        if last == 'const':
            x, y = last, t
        else:
            x, y = t, last
        return '{0} {1}'.format(x, y)

    @memoize_method
    def cython_ctype(self, t):
        """Given a type t, returns the corresponding Cython C/C++ type declaration.
        """
        t = self.canon(t)
        if t in self.cython_ctypes:
            return self.cython_ctypes[t]
        if isinstance(t, basestring):
            if t in self.base_types:
                return self.cython_ctypes[t]
        # must be tuple below this line
        tlen = len(t)
        if 2 == tlen:
            if 0 == t[1]:
                return self.cython_ctype(t[0])
            elif self.isrefinement(t[1]):
                if t[1][0] in self.cython_ctypes:
                    subtype = self.cython_ctypes[t[1][0]]
                    if callable(subtype):
                        subtype = subtype(t[1], self)
                    return subtype
                else:
                    return self.cython_ctype(t[0])
            else:
                last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
                return self._cython_ctype_add_predicate(self.cython_ctype(t[0]), last)
        elif 3 <= tlen:
            assert t[0] in self.template_types
            assert len(t) == len(self.template_types[t[0]]) + 2
            template_name = self.cython_ctypes.get(t[0], NotImplemented)
            if template_name is NotImplemented:
                msg = 'The Cython C-type {0!r} for type {1!r} has not been implemented.'
                raise NotImplementedError(msg.format(t[0], t))
            template_filling = []
            for x in t[1:-1]:
                #if isinstance(x, bool):
                #    x = _cython_ctypes[x]
                #elif isinstance(x, Number):
                if isinstance(x, Number):
                    x = str(x)
                else:
                    x = self.cython_ctype(x)
                template_filling.append(x)
            cyct = '{0}[{1}]'.format(template_name, ', '.join(template_filling))
            if 0 != t[-1]:
                last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
                cyct = self._cython_ctype_add_predicate(cyct, last)
            return cyct

    @memoize_method
    def _fill_cycyt(self, cycyt, t):
        """Helper for cython_cytype()."""
        d = {}
        for key, x in zip(self.template_types[t[0]], t[1:-1]):
            if isinstance(x, basestring):
                val = self.cython_classnames[x]
            elif isinstance(x, Number):
                val = str(x)
            elif x[0] in self.base_types:
                val = self.cython_classnames[x[0]]
            else:
                val, _ = self._fill_cycyt(self.cython_classnames[x[0]], x)
            d[key] = val
        return cycyt.format(**d), t

    def _cython_cytype_add_predicate(self, t, last):
        """Adds a predicate to a cytype"""
        if last == '*':
            return '{0} {1}'.format(t, last)
        elif isinstance(last, int) and 0 < last:
            return '{0} [{1}]'.format(t, last)
        else:
            return t

    @memoize_method
    def cython_cytype(self, t):
        """Given a type t, returns the corresponding Cython type."""
        t = self.canon(t)
#        if t in self.cython_cytypes:
#            return self.cython_cytypes[t]
        if isinstance(t, basestring):
            if t in self.base_types or t in self.cython_cytypes:
                return self.cython_cytypes[t]
        # must be tuple below this line
        tlen = len(t)
        if 2 == tlen:
            if 0 == t[1]:
                return self.cython_cytype(t[0])
            elif self.isrefinement(t[1]):
                if t[1][0] in self.cython_cytypes:
                    subtype = self.cython_cytypes[t[1][0]]
                    if callable(subtype):
                        subtype = subtype(t[1], self)
                    return subtype
                else:
                    return self.cython_cytype(t[0])
            else:
                return self._cython_cytype_add_predicate(self.cython_cytype(t[0]),
                                                         t[-1])
        elif 3 <= tlen:
            if t in self.cython_cytypes:
                return self.cython_cytypes[t]
            assert t[0] in self.template_types
            assert len(t) == len(self.template_types[t[0]]) + 2
            template_name = self.cython_cytypes[t[0]]
            assert template_name is not NotImplemented
            cycyt = self.cython_cytypes[t[0]]
            cycyt, t = self._fill_cycyt(cycyt, t)
            cycyt = self._cython_cytype_add_predicate(cycyt, t[-1])
            return cycyt

    @memoize_method
    def _fill_cypyt(self, cypyt, t):
        """Helper for cython_pytype()."""
        d = {}
        for key, x in zip(self.template_types[t[0]], t[1:-1]):
            if isinstance(x, basestring):
                val = self.cython_classnames[x]
            elif isinstance(x, Number):
                val = str(x)
            elif x[0] in self.base_types:
                val = self.cython_classnames[x[0]]
            else:
                val, _ = self._fill_cypyt(self.cython_classnames[x[0]], x)
            d[key] = val
        return cypyt.format(**d), t

    @memoize_method
    def cython_pytype(self, t):
        """Given a type t, returns the corresponding Python type."""
        if isinstance(t, Number):
            return str(t)
        t = self.canon(t)
        if t in self.cython_pytypes:
            return self.cython_pytypes[t]
        if isinstance(t, basestring):
            if t in self.base_types:
                return self.cython_pytypes[t]
        # must be tuple below this line
        tlen = len(t)
        if 2 == tlen:
            if 0 == t[1]:
                return self.cython_pytype(t[0])
            elif self.isrefinement(t[1]):
                return self.cython_pytype(t[0])
            else:
                # FIXME last is ignored for strings, but what about other types?
                #last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
                #return cython_pytype(t[0]) + ' {0}'.format(last)
                return self.cython_pytype(t[0])
        elif 3 <= tlen:
            if t in self.cython_pytypes:
                return self.cython_pytypes[t]
            assert t[0] in self.template_types
            assert len(t) == len(self.template_types[t[0]]) + 2
            template_name = self.cython_pytypes[t[0]]
            assert template_name is not NotImplemented
            cypyt = self.cython_pytypes[t[0]]
            cypyt, t = self._fill_cypyt(cypyt, t)
            # FIXME last is ignored for strings, but what about other types?
            #if 0 != t[-1]:
            #    last = '[{0}]'.format(t[-1]) if isinstance(t[-1], int) else t[-1]
            #    cypyt += ' {0}'.format(last)
            return cypyt

    @memoize_method
    def cython_cimport_tuples(self, t, seen=None, inc=frozenset(['c', 'cy'])):
        """Given a type t, and possibly previously seen cimport tuples (set),
        return the set of all seen cimport tuples.  These tuple have four possible
        interpretations based on the length and values:

        * ``(module-name,)`` becomes ``cimport {module-name}``
        * ``(module-name, var-or-mod)`` becomes
          ``from {module-name} cimport {var-or-mod}``
        * ``(module-name, var-or-mod, alias)`` becomes
          ``from {module-name} cimport {var-or-mod} as {alias}``
        * ``(module-name, 'as', alias)`` becomes ``cimport {module-name} as {alias}``

        """
        t = self.canon(t)
        if seen is None:
            seen = set()
        if isinstance(t, basestring):
            if t in self.base_types:
                if 'c' in inc:
                    seen.update(self.cython_cimports[t])
                if 'cy' in inc:
                    seen.update(self.cython_cyimports[t])
                seen -= set((None, (None,)))
                return seen
        # must be tuple below this line
        tlen = len(t)
        if 2 == tlen:
            if 'c' in inc:
                if self.isrefinement(t[1]) and t[1][0] in self.cython_cimports:
                    f = self.cython_cimports[t[1][0]]
                    if callable(f):
                        f(t[1], self, seen)
                seen.update(self.cython_cimports.get(t[0], (None,)))
                seen.update(self.cython_cimports.get(t[1], (None,)))
            if 'cy' in inc:
                if self.isrefinement(t[1]) and t[1][0] in self.cython_cyimports:
                    f = self.cython_cyimports[t[1][0]]
                    if callable(f):
                        f(t[1], self, seen)
                seen.update(self.cython_cyimports.get(t[0], (None,)))
                seen.update(self.cython_cyimports.get(t[1], (None,)))
            seen -= set((None, (None,)))
            return self.cython_cimport_tuples(t[0], seen, inc)
        elif 3 <= tlen:
            assert t[0] in self.template_types
            if 'c' in inc:
                seen.update(self.cython_cimports[t[0]])
            if 'cy' in inc:
                seen.update(self.cython_cyimports[t[0]])
            for x in t[1:-1]:
                if isinstance(x, Number):
                    continue
                elif isinstance(x, basestring) and x not in self.cython_cimports:
                    continue
                self.cython_cimport_tuples(x, seen, inc)
            seen -= set((None, (None,)))
            return seen

    _cython_cimport_cases = {
        1: lambda tup: "cimport {0}".format(*tup),
        2: lambda tup: "from {0} cimport {1}".format(*tup),
        3: lambda tup: ("cimport {0} as {2}".format(*tup) if tup[1] == 'as' else \
                        "from {0} cimport {1} as {2}".format(*tup)),
        }

    @memoize_method
    def cython_cimport_lines(self, x, inc=frozenset(['c', 'cy'])):
        """Returns the cimport lines associated with a type or a set of seen tuples.
        """
        if not isinstance(x, Set):
            x = self.cython_cimport_tuples(x, inc=inc)
        return set([self._cython_cimport_cases[len(tup)](tup) for tup in x \
                                                              if 0 != len(tup)])

    @memoize_method
    def cython_import_tuples(self, t, seen=None):
        """Given a type t, and possibly previously seen import tuples (set),
        return the set of all seen import tuples.  These tuple have four possible
        interpretations based on the length and values:

        * ``(module-name,)`` becomes ``import {module-name}``
        * ``(module-name, var-or-mod)`` becomes
          ``from {module-name} import {var-or-mod}``
        * ``(module-name, var-or-mod, alias)`` becomes
          ``from {module-name} import {var-or-mod} as {alias}``
        * ``(module-name, 'as', alias)`` becomes ``import {module-name} as {alias}``

        Any of these may be used.
        """
        t = self.canon(t)
        if seen is None:
            seen = set()
        if isinstance(t, basestring):
            if t in self.base_types:
                seen.update(self.cython_pyimports[t])
                seen -= set((None, (None,)))
                return seen
        # must be tuple below this line
        tlen = len(t)
        if 2 == tlen:
            if self.isrefinement(t[1]) and t[1][0] in self.cython_pyimports:
                f = self.cython_pyimports[t[1][0]]
                if callable(f):
                    f(t[1], self, seen)
            seen.update(self.cython_pyimports.get(t[0], (None,)))
            seen.update(self.cython_pyimports.get(t[1], (None,)))
            seen -= set((None, (None,)))
            return self.cython_import_tuples(t[0], seen)
        elif 3 <= tlen:
            assert t[0] in self.template_types
            seen.update(self.cython_pyimports[t[0]])
            for x in t[1:-1]:
                if isinstance(x, Number):
                    continue
                elif isinstance(x, basestring) and x not in self.cython_cimports:
                    continue
                self.cython_import_tuples(x, seen)
            seen -= set((None, (None,)))
            return seen

    _cython_import_cases = {
        1: lambda tup: "import {0}".format(*tup),
        2: lambda tup: "from {0} import {1}".format(*tup),
        3: lambda tup: ("import {0} as {2}".format(*tup) if tup[1] == 'as' else \
                        "from {0} import {1} as {2}".format(*tup)),
        }

    @memoize_method
    def cython_import_lines(self, x):
        """Returns the import lines associated with a type or a set of seen tuples.
        """
        if not isinstance(x, Set):
            x = self.cython_import_tuples(x)
        x = [tup for tup in x if 0 < len(tup)]
        return set([self._cython_import_cases[len(tup)](tup) for tup in x])

    @memoize_method
    def cython_literal(self, lit):
        """Converts a literal to a Cython compatible form.
        """
        if isinstance(lit, Number):
            cy_lit = str(lit).replace('-', 'Neg').replace('+', 'Pos')\
                             .replace('.', 'point')
        elif isinstance(lit, basestring):
            cy_lit = repr(lit)
        return cy_lit


    @memoize_method
    def cython_funcname(self, name, argkinds=None):
        """This returns a name for a function based on its name, rather than
        its type.  The name may be either a string or a tuple of the form
        ('name', template_arg1, template_arg2, ...). The argkinds argument here
        refers only to the template arguments, not the function signature default
        arguments. This is not meant to replace cython_functionname(), but
        complement it.
        """
        if isinstance(name, basestring):
            return name
        if argkinds is None:
            argkinds = [(Arg.NONE, None)] * (len(name) - 1)
        fname = name[0]
        cfs = []
        for x, (argkind, argvalue) in zip(name[1:], argkinds):
            if argkind is Arg.TYPE:
                cf = self.cython_functionname(x)[1]
            elif argkind is Arg.LIT:
                cf = self.cython_literal(x)
            elif argkind is Arg.VAR:
                cf = x
            elif isinstance(x, Number):
                cf = self.cython_literal(x)
            else:
                try:
                    cf = self.cython_functionname(x)[1]  # guess type
                except TypeError:
                    cf = x  # guess variable
            cfs.append(cf)
        fname += '' if 0 == len(cfs) else "_" + "_".join(cfs)
        return fname

    @memoize_method
    def cython_functionname(self, t, cycyt=None):
        """Computes variable or function names for cython types."""
        if cycyt is None:
            t = self.canon(t)
            if isinstance(t, basestring):
                return t, self.cython_functionnames[t]
            elif t[0] in self.base_types:
                return t, self.cython_functionnames[t[0]]
            return self.cython_functionname(t, self.cython_functionnames[t[0]])
        d = {}
        for key, x in zip(self.template_types[t[0]], t[1:-1]):
            if isinstance(x, basestring):
                val = self.cython_functionnames[x] if x in self.cython_functionnames \
                                                   else x
            elif isinstance(x, Number):
                val = str(x).replace('-', 'Neg').replace('+', 'Pos')\
                            .replace('.', 'point')
            elif x[0] in self.base_types:
                val = self.cython_functionnames[x[0]]
            else:
                _, val = self.cython_functionname(x, self.cython_functionnames[x[0]])
            d[key] = val
        return t, cycyt.format(**d)

    cython_variablename = cython_functionname

    @memoize_method
    def cython_classname(self, t, cycyt=None):
        """Computes classnames for cython types."""
        if cycyt is None:
            t = self.canon(t)
            if isinstance(t, basestring):
                return t, self.cython_classnames[t]
            elif t[0] in self.base_types:
                return t, self.cython_classnames[t[0]]
            return self.cython_classname(t, self.cython_classnames[t[0]])
        d = {}
        for key, x in zip(self.template_types[t[0]], t[1:-1]):
            if isinstance(x, basestring):
                val = self.cython_classnames[x] if x in self.cython_classnames else x
            elif isinstance(x, Number):
                val = str(x).replace('-', 'Neg').replace('+', 'Pos')\
                            .replace('.', 'point')
            elif x[0] in self.base_types:
                val = self.cython_classnames[x[0]]
            else:
                _, val = self.cython_classname(x, self.cython_classnames[x[0]])
            d[key] = val
        return t, cycyt.format(**d)

    @memoize_method
    def cython_c2py_getitem(self, t):
        """Helps find the approriate c2py value for a given concrete type key."""
        tkey = t = self.canon(t)
        while tkey not in self.cython_c2py_conv and not isinstance(tkey, basestring):
            #tkey = tkey[0]
            tkey = tkey[1] if (0 < len(tkey) and self.isrefinement(tkey[1])) else \
                                                                             tkey[0]
        if tkey not in self.cython_c2py_conv:
            tkey = t
            while tkey not in self.cython_c2py_conv and \
                       not isinstance(tkey, basestring):
                tkey = tkey[0]
        c2pyt = self.cython_c2py_conv[tkey]
        if callable(c2pyt):
            self.cython_c2py_conv[t] = c2pyt(t, self)
            c2pyt = self.cython_c2py_conv[t]
        return c2pyt

    @memoize_method
    def cython_c2py(self, name, t, view=True, cached=True, inst_name=None,
                    proxy_name=None, cache_name=None, cache_prefix='self',
                    existing_name=None):
        """Given a variable name and type, returns cython code (declaration, body,
        and return statements) to convert the variable from C/C++ to Python."""
        t = self.canon(t)
        c2pyt = self.cython_c2py_getitem(t)
        ind = int(view) + int(cached)
        if cached and not view:
            raise ValueError('cached views require view=True.')
        if c2pyt is NotImplemented:
            raise NotImplementedError('conversion from C/C++ to Python for ' + \
                                      t + 'has not been implemented for when ' + \
                                      'view={0}, cached={1}'.format(view, cached))
        var = name if inst_name is None else "{0}.{1}".format(inst_name, name)
        var = existing_name or var
        cache_name = "_{0}".format(name) if cache_name is None else cache_name
        cache_name = cache_name if cache_prefix is None else "{0}.{1}".format(
                                                            cache_prefix, cache_name)
        proxy_name = "{0}_proxy".format(name) if proxy_name is None else proxy_name
        iscached = False
        tstr = self.typestr(t, self)
        template_kw = dict(var=var, cache_name=cache_name, proxy_name=proxy_name,
                           t=tstr)
#        if callable(c2pyt):
#            import pdb; pdb.set_trace()
        if 1 == len(c2pyt) or ind == 0:
            if "{proxy_name}" in c2pyt[0]:
                decl = None
                body = c2pyt[0].format(**template_kw)
                rtn = proxy_name
            else:
                decl = body = None
                rtn = c2pyt[0].format(**template_kw)
        elif ind == 1:
            decl = "cdef {0} {1}".format(tstr.cython_cytype, proxy_name)
            body = c2pyt[1].format(**template_kw)
            rtn = proxy_name
        elif ind == 2:
            decl = "cdef {0} {1}".format(tstr.cython_cytype, proxy_name)
            body = c2pyt[2].format(**template_kw)
            rtn = cache_name
            iscached = True
        if body is not None and 'np.npy_intp' in body:
            decl = decl or ''
            decl += "\ncdef np.npy_intp {proxy_name}_shape[1]".format(
                                                                proxy_name=proxy_name)
        if decl is not None and body is not None:
            newdecl = '\n'+"\n".join([l for l in body.splitlines() \
                                              if l.startswith('cdef')])
            body = "\n".join([l for l in body.splitlines() \
                                              if not l.startswith('cdef')])
            proxy_in_newdecl = proxy_name in [l.split()[-1] for l in \
                                              newdecl.splitlines() if 0 < len(l)]
            if proxy_in_newdecl:
                for d in decl.splitlines():
                    if d.split()[-1] != proxy_name:
                        newdecl += '\n' + d
                decl = newdecl
            else:
                decl += newdecl
        return decl, body, rtn, iscached

    @memoize_method
    def cython_py2c(self, name, t, inst_name=None, proxy_name=None):
        """Given a variable name and type, returns cython code (declaration, body,
        and return statement) to convert the variable from Python to C/C++."""
        t = self.canon(t)
        if isinstance(t, basestring) or 0 == t[-1] or self.isrefinement(t[-1]):
            last = ''
        elif isinstance(t[-1], int):
            last = ' [{0}]'.format(t[-1])
        else:
            last = ' ' + t[-1]
        tkey = t
        tinst = None
        while tkey not in self.cython_py2c_conv and not isinstance(tkey, basestring):
            tinst = tkey
            tkey = tkey[1] if (0 < len(tkey) and self.isrefinement(tkey[1])) else tkey[0]
        if tkey not in self.cython_py2c_conv:
            tkey = t
            while tkey not in self.cython_py2c_conv and \
                       not isinstance(tkey, basestring):
                tkey = tkey[0]
        py2ct = self.cython_py2c_conv[tkey]
        if callable(py2ct):
            self.cython_py2c_conv[t] = py2ct(t, self)
            py2ct = self.cython_py2c_conv[t]
        if py2ct is NotImplemented or py2ct is None:
            raise NotImplementedError('conversion from Python to C/C++ for ' + \
                                  str(t) + ' has not been implemented.')
        body_template, rtn_template = py2ct
        var = name if inst_name is None else "{0}.{1}".format(inst_name, name)
        proxy_name = "{0}_proxy".format(name) if proxy_name is None else proxy_name
        tstr = self.typestr(t, self)
        template_kw = dict(var=var, proxy_name=proxy_name, last=last, t=tstr)
        nested = False
        if self.isdependent(tkey):
            tsig = [ts for ts in self.refined_types if ts[0] == tkey][0]
            for ts, ti in zip(tsig[1:], tinst[1:]):
                if isinstance(ts, basestring):
                    template_kw[ts] = self.cython_ctype(ti)
                else:
                    template_kw[ti[0]] = ti[2]
            vartype = self.refined_types[tsig]
            if vartype in tsig[1:]:
                vartype = tinst[tsig.index(vartype)][1]
            if self.isrefinement(vartype):
                nested = True
                vdecl, vbody, vrtn = self.cython_py2c(var, vartype)
                template_kw['var'] = vrtn
        body_filled = body_template.format(**template_kw)
        if rtn_template:
            if '{t.cython_ctype}'in body_template:
                deft = tstr.cython_ctype
            elif '{t.cython_ctype_nopred}'in body_template:
                deft = tstr.cython_ctype_nopred
            elif '{t.cython_cytype_nopred}'in body_template:
                deft = tstr.cython_cytype_nopred
            else:
                deft = tstr.cython_cytype
            decl = "cdef {0} {1}".format(deft, proxy_name)
            body = body_filled
            rtn = rtn_template.format(**template_kw)
            decl += '\n'+"\n".join([l for l in body.splitlines() \
                                            if l.startswith('cdef')])
            body = "\n".join([l for l in body.splitlines() \
                                      if not l.startswith('cdef')])
        else:
            decl = body = None
            rtn = body_filled
        if nested:
            decl = '' if decl is None else decl
            vdecl = '' if vdecl is None else vdecl
            decl = (vdecl + '\n' + decl).strip()
            decl = None if 0 == len(decl) else decl
            body = '' if body is None else body
            vbody = '' if vbody is None else vbody
            body = (vbody + '\n' + body).strip()
            body = None if 0 == len(body) else body
        return decl, body, rtn

    #################  Some utility functions for the typesystem #############

    def register_class(self, name=None, template_args=None, cython_c_type=None,
                       cython_cimport=None, cython_cy_type=None, cython_py_type=None,
                       cython_template_class_name=None,
                       cython_template_function_name=None, cython_cyimport=None,
                       cython_pyimport=None, cython_c2py=None,
                       cython_py2c=None, cpp_type=None, human_name=None,
                       from_pytype=None):
        """Classes are user specified types.  This function will add a class to
        the type system so that it may be used normally with the rest of the
        type system.

        """
        # register the class name
        isbase = True
        if template_args is None:
            self.base_types.add(name)  # normal class
        elif isinstance(template_args, Sequence):
            if 0 == len(template_args):
                self.base_types.add(name)  # normal class
            elif isinstance(template_args, basestring):
                _raise_type_error(name)
            else:
                self.template_types[name] = tuple(template_args)  # templated class...
                isbase = False

        # Register with Cython C/C++ types
        if (cython_c_type is not None):
            self.cython_ctypes[name] = cython_c_type
        if (cython_cy_type is not None):
            self.cython_cytypes[name] = cython_cy_type
        if (cython_py_type is not None):
            self.cython_pytypes[name] = cython_py_type
        if (from_pytype is not None):
            self.from_pytypes[name] = from_pytype
        if cpp_type is not None:
            self.cpp_types[name] = cpp_type
        if human_name is not None:
            self.humannames[name] = human_name

        if (cython_cimport is not None):
            cython_cimport = _ensure_importable(cython_cimport)
            self.cython_cimports[name] = cython_cimport
        if (cython_cyimport is not None):
            cython_cyimport = _ensure_importable(cython_cyimport)
            self.cython_cyimports[name] = cython_cyimport
        if (cython_pyimport is not None):
            cython_pyimport = _ensure_importable(cython_pyimport)
            self.cython_pyimports[name] = cython_pyimport

        if (cython_c2py is not None):
            if isinstance(cython_c2py, basestring):
                cython_c2py = (cython_c2py,)
            cython_c2py = None if cython_c2py is None else tuple(cython_c2py)
            self.cython_c2py_conv[name] = cython_c2py
        if (cython_py2c is not None):
            if isinstance(cython_py2c, basestring):
                cython_py2c = (cython_py2c, False)
            self.cython_py2c_conv[name] = cython_py2c
        if (cython_template_class_name is not None):
            self.cython_classnames[name] = cython_template_class_name
        if (cython_template_function_name is not None):
            self.cython_functionnames[name] = cython_template_function_name

    def deregister_class(self, name):
        """This function will remove a previously registered class from
        the type system.
        """
        isbase = name in self.base_types
        if not isbase and name not in self.template_types:
            _raise_type_error(name)
        if isbase:
            self.base_types.remove(name)
        else:
            self.template_types.pop(name, None)

        self.cython_ctypes.pop(name, None)
        self.cython_cytypes.pop(name, None)
        self.cython_pytypes.pop(name, None)
        self.from_pytypes.pop(name, None)
        self.cpp_types.pop(name, None)
        self.humannames.pop(name, None)
        self.cython_cimports.pop(name, None)
        self.cython_cyimports.pop(name, None)
        self.cython_pyimports.pop(name, None)

        self.cython_c2py_conv.pop(name, None)
        self.cython_py2c_conv.pop(name, None)
        self.cython_classnames.pop(name, None)

        self.clearmemo()

    def register_classname(self, classname, package, pxd_base, cpppxd_base,
                           cpp_classname=None, make_dtypes=True):
        """Registers a class with the type system from only its name,
        and relevant header file information.

        Parameters
        ----------
        classname : str or tuple
        package : str
            Package name where headers live.
        pxd_base : str
            Base name of the pxd file to cimport.
        cpppxd_base : str
            Base name of the cpppxd file to cimport.
        cpp_classname : str or tuple, optional
            Name of class in C++, equiv. to apiname.srcname. Defaults to classname.
        make_dtypes : bool, optional
            Flag for registering dtypes for this class simeltaneously with
            registering the class itself.
        """
        # target classname
        baseclassname = classname
        if isinstance(classname, basestring):
            template_args = None
            templateclassname = baseclassname
            templatefuncname = baseclassname.lower()
        else:
            template_args = ['T{0}'.format(i) for i in range(len(classname)-2)]
            template_args = tuple(template_args)
            while not isinstance(baseclassname, basestring):
                baseclassname = baseclassname[0]  # hack version of ts.basename()
            templateclassname = baseclassname
            templateclassname = templateclassname + \
                                ''.join(["{"+targ+"}" for targ in template_args])
            templatefuncname = baseclassname.lower() + '_' + \
                               '_'.join(["{"+targ+"}" for targ in template_args])

        # source classname
        if cpp_classname is None:
            cpp_classname = classname
        cpp_baseclassname = cpp_classname
        if not isinstance(cpp_classname, basestring):
            while not isinstance(cpp_baseclassname, basestring):
                cpp_baseclassname = cpp_baseclassname[0]
            if template_args is None:
                template_args = ['T{0}'.format(i) for i in range(len(cpp_classname)-2)]
                template_args = tuple(template_args)

        # register regular class
        class_c2py = ( # '{t.cython_pytype}({var})',
                      ('{proxy_name} = {t.cython_pytype}()\n'
                       '(<{t.cython_ctype_nopred} *> {proxy_name}._inst)[0] = {var}'),
                      ('{proxy_name} = {t.cython_pytype}()\n'
                       '(<{t.cython_ctype_nopred} *> {proxy_name}._inst)[0] = {var}'),
                      ('if {cache_name} is None:\n'
                       '    {proxy_name} = {t.cython_pytype}()\n'
                       '    {proxy_name}._free_inst = False\n'
                       '    {proxy_name}._inst = &{var}\n'
                       '    {cache_name} = {proxy_name}\n')
                     )
        class_py2c = ('{proxy_name} = <{t.cython_cytype_nopred}> {var}',
                      '(<{t.cython_ctype_nopred} *> {proxy_name}._inst)[0]')
        class_cimport = ((package, cpppxd_base),)
        kwclass = dict(
            name=baseclassname,                              # FCComp
            template_args=template_args,
            cython_c_type=cpppxd_base + '.' + cpp_baseclassname, # cpp_fccomp.FCComp
            cython_cimport=class_cimport,
            cython_cy_type=pxd_base + '.' + baseclassname,      # fccomp.FCComp
            cython_py_type=pxd_base + '.' + baseclassname,      # fccomp.FCComp
            from_pytype=[pxd_base + '.' + baseclassname],      # fccomp.FCComp
            cpp_type=cpp_baseclassname,
            human_name=templateclassname,
            cython_template_class_name=templateclassname,
            cython_template_function_name=templatefuncname,
            cython_cyimport=((pxd_base,),),                       # fccomp
            cython_pyimport=((pxd_base,),),                       # fccomp
            cython_c2py=class_c2py,
            cython_py2c=class_py2c,
            )
        self.register_class(**kwclass)
        canonname = classname if isinstance(classname, basestring) \
                              else self.canon(classname)
        if template_args is not None:
            specname = classname if isinstance(classname, basestring) \
                                 else self.cython_classname(classname)[1]
            kwclassspec = dict(
                name=classname,
                cython_c_type=cpppxd_base + '.' + specname,
                cython_cy_type=pxd_base + '.' + specname,
                cython_py_type=pxd_base + '.' + specname,
                cpp_type=self.cpp_type(cpp_classname),
                )
            self.register_class(**kwclassspec)
            kwclassspec['name'] = canonname
            self.register_class(**kwclassspec)
            kwclassspec['name'] = self.canon(cpp_classname)
            self.register_class(**kwclassspec)
        # register numpy type
        if make_dtypes:
            self.register_numpy_dtype(classname,
                cython_cimport=class_cimport,
                cython_cyimport=pxd_base,
                cython_pyimport=pxd_base,
                )
        # register vector
        class_vector_py2c = ((
            '# {var} is a {t.type}\n'
            'cdef int i{var}\n'
            'cdef int {var}_size\n'
            'cdef {t.cython_npctypes[0]} * {var}_data\n'
            '{var}_size = len({var})\n'
            'if isinstance({var}, np.ndarray) and (<np.ndarray> {var}).descr.type_num == {t.cython_nptype}:\n'
            '    {var}_data = <{t.cython_npctypes[0]} *> np.PyArray_DATA(<np.ndarray> {var})\n'
            '    {proxy_name} = {t.cython_ctype_nopred}(<size_t> {var}_size)\n'
            '    for i{var} in range({var}_size):\n'
            '        {proxy_name}[i{var}] = {var}_data[i{var}]\n'
            'else:\n'
            '    {proxy_name} = {t.cython_ctype_nopred}(<size_t> {var}_size)\n'
            '    for i{var} in range({var}_size):\n'
            '        {proxy_name}[i{var}] = (<{t.cython_npctypes_nopred[0]} *> (<{t.cython_npcytypes_nopred[0]}> {var}[i{var}])._inst)[0]\n'),
            '{proxy_name}')
        self.register_class(('vector', canonname, 0), cython_py2c=class_vector_py2c)
        self.register_class(('vector', classname, 0), cython_py2c=class_vector_py2c)
        self.register_class((('vector', canonname, 0), '&'), cython_py2c=class_vector_py2c)
        self.register_class((('vector', classname, 0), '&'), cython_py2c=class_vector_py2c)
        self.register_class(((('vector', canonname, 0), 'const'), '&'), cython_py2c=class_vector_py2c)
        self.register_class(((('vector', classname, 0), 'const'), '&'), cython_py2c=class_vector_py2c)
        # register pointer to class
        class_ptr_c2py = ('{t.cython_pytype}({var})',
                         ('cdef {t.cython_pytype} {proxy_name} = {t.cython_pytype}()\n'
                          'if {proxy_name}._free_inst:\n'
                          '    free({proxy_name}._inst)\n'
                          '(<{t.cython_ctype}> {proxy_name}._inst) = {var}'),
                         ('if {cache_name} is None:\n'
                          '    {proxy_name} = {t.cython_pytype}()\n'
                          '    {proxy_name}._free_inst = False\n'
                          '    {proxy_name}._inst = {var}\n'
                          '    {cache_name} = {proxy_name}\n')
                          )
        class_ptr_py2c = ('{proxy_name} = <{t.cython_cytype_nopred}> {var}',
                          '(<{t.cython_ctype_nopred} *> {proxy_name}._inst)')
        kwclassptr = dict(
            name=(classname, '*'),
            template_args=template_args,
            cython_py_type=pxd_base + '.' + baseclassname,
            cython_cy_type=pxd_base + '.' + baseclassname,
            cpp_type=cpp_baseclassname,
            cython_c2py=class_ptr_c2py,
            cython_py2c=class_ptr_py2c,
            cython_cimport=kwclass['cython_cimport'] ,
            cython_cyimport=kwclass['cython_cyimport'] + (('libc.stdlib','free'),),
            cython_pyimport=kwclass['cython_pyimport'],
            )
        self.register_class(**kwclassptr)
        kwclassref = dict(kwclassptr)
        # Register reference to class
        kwclassref['name'] = (classname, '&')
        kwclassref['cython_c2py'] = class_c2py
        kwclassref['cython_py2c'] = class_py2c
        #ts.register_class(**kwclassref)
        # register doublepointer to class
        class_dblptr_c2py = ('{t.cython_pytype}({var})',
                            ('{proxy_name} = {proxy_name}_obj._inst\n'
                             '(<{t.cython_ctype} *> {proxy_name}._inst) = {var}'),
                            ('if {cache_name} is None:\n'
                             '    {proxy_name} = {t.cython_pytype}()\n'
                             '    {proxy_name}._free_inst = False\n'
                             '    {proxy_name}._inst = {var}\n'
                             '    {proxy_name}_list = [{proxy_name}]\n'
                             '    {cache_name} = {proxy_name}_list\n')
                             )
        class_dblptr_py2c = ('{proxy_name} = <{t.cython_cytype_nopred}> {var}[0]',
                             '(<{t.cython_ctype_nopred} **> {proxy_name}._inst)')
        kwclassdblptr = dict(
            name=((classname, '*'), '*'),
            template_args=template_args,
            cython_c2py=class_dblptr_c2py,
            cython_py2c=class_dblptr_py2c,
            cython_cimport=kwclass['cython_cimport'],
            cython_cyimport=kwclass['cython_cyimport'],
            cython_pyimport=kwclass['cython_pyimport'],
            )
        self.register_class(**kwclassdblptr)

    def register_refinement(self, name, refinementof, cython_cimport=None,
                            cython_cyimport=None, cython_pyimport=None,
                            cython_c2py=None, cython_py2c=None):
        """This function will add a refinement to the type system so that it
        may be used normally with the rest of the type system.
        """
        self.refined_types[name] = refinementof

        cyci = _ensure_importable(cython_cimport)
        self.cython_cimports[name] = cyci

        cycyi = _ensure_importable(cython_cyimport)
        self.cython_cyimports[name] = cycyi

        cypyi = _ensure_importable(cython_pyimport)
        self.cython_pyimports[name] = cypyi

        if isinstance(cython_c2py, basestring):
            cython_c2py = (cython_c2py,)
        cython_c2py = None if cython_c2py is None else tuple(cython_c2py)
        if cython_c2py is not None:
            self.cython_c2py_conv[name] = cython_c2py

        if isinstance(cython_py2c, basestring):
            cython_py2c = (cython_py2c, False)
        if cython_py2c is not None:
            self.cython_py2c_conv[name] = cython_py2c

    def deregister_refinement(self, name):
        """This function will remove a previously registered refinement from
        the type system.
        """
        self.refined_types.pop(name, None)
        self.cython_c2py_conv.pop(name, None)
        self.cython_py2c_conv.pop(name, None)
        self.cython_cimports.pop(name, None)
        self.cython_cyimports.pop(name, None)
        self.cython_pyimports.pop(name, None)
        self.clearmemo()

    def register_specialization(self, t, cython_c_type=None, cython_cy_type=None,
                                cython_py_type=None, cython_cimport=None,
                                cython_cyimport=None, cython_pyimport=None):
        """This function will add a template specialization so that it may be used
        normally with the rest of the type system.
        """
        t = self.canon(t)
        if cython_c_type is not None:
            self.cython_ctypes[t] = cython_c_type
        if cython_cy_type is not None:
            self.cython_cytypes[t] = cython_cy_type
        if cython_py_type is not None:
            self.cython_pytypes[t] = cython_py_type
        if cython_cimport is not None:
            self.cython_cimports[t] = cython_cimport
        if cython_cyimport is not None:
            self.cython_cyimports[t] = cython_cyimport
        if cython_pyimport is not None:
            self.cython_pyimports[t] = cython_pyimport

    def deregister_specialization(self, t):
        """This function will remove previously registered template specialization."""
        t = self.canon(t)
        self.cython_ctypes.pop(t, None)
        self.cython_cytypes.pop(t, None)
        self.cython_pytypes.pop(t, None)
        self.cython_cimports.pop(t, None)
        self.cython_cyimports.pop(t, None)
        self.cython_pyimports.pop(t, None)
        self.clearmemo()

    def register_numpy_dtype(self, t, cython_cimport=None, cython_cyimport=None,
                             cython_pyimport=None):
        """This function will add a type to the system as numpy dtype that lives in
        the dtypes module.
        """
        t = self.canon(t)
        if t in self.numpy_types:
            return
        varname = self.cython_variablename(t)[1]
        self.numpy_types[t] = '{dtypes}xd_' + varname + '.num'
        self.type_aliases[self.numpy_types[t]] = t
        self.type_aliases['xd_' + varname] = t
        self.type_aliases['xd_' + varname + '.num'] = t
        self.type_aliases['{dtypes}xd_' + varname] = t
        self.type_aliases['{dtypes}xd_' + varname + '.num'] = t
        if cython_cimport is not None:
            x = _ensure_importable(self.cython_cimports._d.get(t, None))
            x = x + _ensure_importable(cython_cimport)
            self.cython_cimports[t] = x
        # cython imports
        x = (('{dtypes}',),)
        x = x + _ensure_importable(self.cython_cyimports._d.get(t, None))
        x = x + _ensure_importable(cython_cyimport)
        self.cython_cyimports[t] = x
        # python imports
        x = (('{dtypes}',),)
        x = x + _ensure_importable(self.cython_pyimports._d.get(t, None))
        x = x + _ensure_importable(cython_pyimport)
        self.cython_pyimports[t] = x

    def register_argument_kinds(self, t, argkinds):
        """Registers an argument kind tuple into the type system for a template type.
        """
        t = self.canon(t)
        if t in self.argument_kinds:
            old = self.argument_kinds[t]
            if old != argkinds:
                msg = ("overwriting argument kinds for type {0}:\n"
                       "  old: {1}\n"
                       "  new: {2}")
                warn(msg.format(t, old, argkinds), RuntimeWarning)
        self.argument_kinds[t] = argkinds

    def deregister_argument_kinds(self, t):
        """Removes a type and its argument kind tuple from the type system."""
        t = self.canon(t)
        if t in self.argument_kinds:
            del self.argument_kinds[t]

    def register_variable_namespace(self, name, namespace, t=None):
        """Registers a variable and its namespace in the typesystem.
        """
        if name in self.variable_namespace:
            old = self.variable_namespace[name]
            if old != namespace:
                msg = ("overwriting namespace for variable {0}:\n"
                       "  old: {1}\n"
                       "  new: {2}")
                warn(msg.format(name, old, namespace), RuntimeWarning)
        self.variable_namespace[name] = namespace
        if self.isenum(t):
            t = self.canon(t)
            for n, _ in t[1][2][2]:
                self.register_variable_namespace(n, namespace)


    #################### Type system helpers ###################################

    def clearmemo(self):
        """Clears all method memoizations on this type system instance."""
        # see utils.memozie_method
        if hasattr(self, '_cache'):
            self._cache.clear()

    def delmemo(self, meth, *args, **kwargs):
        """Deletes a single key from a method on this type system instance."""
        # see utils.memozie_method
        if hasattr(self, '_cache'):
            meth = getattr(self, meth )if isinstance(meth, basestring) else meth
            del self._cache[meth.func.meth, args, tuple(sorted(kwargs.items()))]

    @contextmanager
    def swap_dtypes(self, s):
        """A context manager for temporarily swapping out the dtypes value
        with a new value and replacing the original value before exiting."""
        old = self.dtypes
        self.dtypes = s
        self.clearmemo()
        yield
        self.clearmemo()
        self.dtypes = old

    @contextmanager
    def swap_stlcontainers(self, s):
        """A context manager for temporarily swapping out the stlcontainer value
        with a new value and replacing the original value before exiting."""
        old = self.stlcontainers
        self.stlcontainers = s
        self.clearmemo()
        yield
        self.clearmemo()
        self.stlcontainers = old

    @contextmanager
    def local_classes(self, classnames, typesets=frozenset(['cy', 'py'])):
        """A context manager for making sure the given classes are local."""
        saved = {}
        for name in classnames:
            if 'c' in typesets and name in self.cython_ctypes:
                saved[name, 'c'] = _undot_class_name(name, self.cython_ctypes)
            if 'cy' in typesets and name in self.cython_cytypes:
                saved[name, 'cy'] = _undot_class_name(name, self.cython_cytypes)
            if 'py' in typesets and name in self.cython_pytypes:
                saved[name, 'py'] = _undot_class_name(name, self.cython_pytypes)
        self.clearmemo()
        yield
        for name in classnames:
            if 'c' in typesets and name in self.cython_ctypes:
                _redot_class_name(name, self.cython_ctypes, saved[name, 'c'])
            if 'cy' in typesets and name in self.cython_cytypes:
                _redot_class_name(name, self.cython_cytypes, saved[name, 'cy'])
            if 'py' in typesets and name in self.cython_pytypes:
                _redot_class_name(name, self.cython_pytypes, saved[name, 'py'])
        self.clearmemo()

#################### Type System Above This Line ##############################


#################### Type string for formatting ################################

class typestr(object):
    """This is class whose attributes are properties that expose various
    string representations of a type.  This is useful for the Python string
    formatting mini-language where attributes of an object may be accessed.
    For example:

        "This is the Cython C/C++ type: {t.cython_ctype}".format(t=typestr(t, ts))

    This mechanism is used for accessing type information in conversion strings.
    """

    def __init__(self, t, ts):
        """Parameters
        ----------
        t : str or tuple
            A valid repesentation of a type in the type systems
        ts : TypeSystem
            A type system to generate the string representations with.
        """
        self.ts = ts
        self.t = ts.canon(t)
        self.t_nopred = ts.strip_predicates(t)

    _type = None

    @property
    def type(self):
        """This is a repr string of the raw type (self.t), mostly useful for
        comments."""
        if self._type is None:
            self._type = repr(self.t)
        return self._type

    _cython_ctype = None

    @property
    def cython_ctype(self):
        """The Cython C/C++ representation of the type.
        """
        if self._cython_ctype is None:
            self._cython_ctype = self.ts.cython_ctype(self.t)
        return self._cython_ctype

    _cython_cytype = None

    @property
    def cython_cytype(self):
        """The Cython Cython representation of the type.
        """
        if self._cython_cytype is None:
            self._cython_cytype = self.ts.cython_cytype(self.t)
        return self._cython_cytype

    _cython_pytype = None

    @property
    def cython_pytype(self):
        """The Cython Python representation of the type.
        """
        if self._cython_pytype is None:
            self._cython_pytype = self.ts.cython_pytype(self.t)
        return self._cython_pytype

    _cython_nptype = None

    @property
    def cython_nptype(self):
        """The Cython NumPy representation of the type.
        """
        if self._cython_nptype is None:
            self._cython_nptype = self.ts.cython_nptype(self.t)
        return self._cython_nptype

    _cython_npctype = None

    @property
    def cython_npctype(self):
        """The Cython C/C++ representation of NumPy type.
        """
        if self._cython_npctype is None:
            npt = self.ts.cython_nptype(self.t)
            npct = self.ts.cython_ctype(npt)
            self._cython_npctype = npct
        return self._cython_npctype

    _cython_npcytype = None

    @property
    def cython_npcytype(self):
        """The Cython Cython representation of NumPy type.
        """
        if self._cython_npcytype is None:
            npt = self.ts.cython_nptype(self.t)
            npcyt = self.ts.cython_cytype(npt)
            self._cython_npcytype = npcyt
        return self._cython_npcytype

    _cython_nppytype = None

    @property
    def cython_nppytype(self):
        """The Cython Python representation of NumPy type.
        """
        if self._cython_nppytype is None:
            npt = self.ts.cython_nptype(self.t)
            nppyt = self.ts.cython_pytype(npt)
            self._cython_nppytype = nppyt
        return self._cython_nppytype

    _cython_nptypes = None

    @property
    def cython_nptypes(self):
        """The expanded Cython NumPy representation of the type.
        """
        if self._cython_nptypes is None:
            npts = self.ts.cython_nptype(self.t, depth=1)
            npts = [npts] if isinstance(npts, basestring) else npts
            self._cython_nptypes = npts
        return self._cython_nptypes

    _cython_npctypes = None

    @property
    def cython_npctypes(self):
        """The expanded Cython C/C++ representation of the NumPy types.
        """
        if self._cython_npctypes is None:
            npts = self.ts.cython_nptype(self.t, depth=1)
            npts = [npts] if isinstance(npts, basestring) else npts
            npcts = _maprecurse(self.ts.cython_ctype, npts)
            self._cython_npctypes = npcts
        return self._cython_npctypes

    _cython_npcytypes = None

    @property
    def cython_npcytypes(self):
        """The expanded Cython Cython representation of the NumPy types.
        """
        if self._cython_npcytypes is None:
            npts = self.ts.cython_nptype(self.t, depth=1)
            npts = [npts] if isinstance(npts, basestring) else npts
            npcyts = _maprecurse(self.ts.cython_cytype, npts)
            self._cython_npcytypes = npcyts
        return self._cython_npcytypes

    _cython_nppytypes = None

    @property
    def cython_nppytypes(self):
        """The expanded Cython Cython representation of the NumPy types.
        """
        if self._cython_nppytypes is None:
            npts = self.ts.cython_nptype(self.t, depth=1)
            npts = [npts] if isinstance(npts, basestring) else npts
            nppyts = _maprecurse(self.ts.cython_pytype, npts)
            self._cython_nppytypes = nppyts
        return self._cython_nppytypes

    _type_nopred = None

    @property
    def type_nopred(self):
        """This is a repr string of the raw type (self.t) without predicates."""
        if self._type_nopred is None:
            self._type_nopred = repr(self.t_nopred)
        return self._type_nopred

    _cython_ctype_nopred = None

    @property
    def cython_ctype_nopred(self):
        """The Cython C/C++ representation of the type without predicates.
        """
        if self._cython_ctype_nopred is None:
            self._cython_ctype_nopred = self.ts.cython_ctype(self.t_nopred)
        return self._cython_ctype_nopred

    _cython_cytype_nopred = None

    @property
    def cython_cytype_nopred(self):
        """The Cython Cython representation of the type without predicates.
        """
        if self._cython_cytype_nopred is None:
            self._cython_cytype_nopred = self.ts.cython_cytype(self.t_nopred)
        return self._cython_cytype_nopred

    _cython_pytype_nopred = None

    @property
    def cython_pytype_nopred(self):
        """The Cython Python representation of the type without predicates.
        """
        if self._cython_pytype_nopred is None:
            self._cython_pytype_nopred = self.ts.cython_pytype(self.t_nopred)
        return self._cython_pytype_nopred

    _cython_nptype_nopred = None

    @property
    def cython_nptype_nopred(self):
        """The Cython NumPy representation of the type without predicates.
        """
        if self._cython_nptype_nopred is None:
            self._cython_nptype_nopred = self.ts.cython_nptype(self.t_nopred)
        return self._cython_nptype_nopred

    _cython_npctype_nopred = None

    @property
    def cython_npctype_nopred(self):
        """The Cython C/C++ representation of the NumPy type without predicates.
        """
        if self._cython_npctype_nopred is None:
            npt_nopred = self.ts.cython_nptype(self.t_nopred)
            npct_nopred = self.cython_ctype(npt_nopred)
            self._cython_npctype_nopred = npct_nopred
        return self._cython_npctype_nopred

    _cython_npcytype_nopred = None

    @property
    def cython_npcytype_nopred(self):
        """The Cython Cython representation of the NumPy type without predicates.
        """
        if self._cython_npcytype_nopred is None:
            npt_nopred = self.ts.cython_nptype(self.t_nopred)
            npcyt_nopred = self.cython_cytype(npt_nopred)
            self._cython_npcytype_nopred = npcyt_nopred
        return self._cython_npcytype_nopred

    _cython_nppytype_nopred = None

    @property
    def cython_nppytype_nopred(self):
        """The Cython Python representation of the NumPy type without predicates.
        """
        if self._cython_nppytype_nopred is None:
            npt_nopred = self.ts.cython_nptype(self.t_nopred)
            nppyt_nopred = self.cython_pytype(npt_nopred)
            self._cython_nppytype_nopred = nppyt_nopred
        return self._cython_nppytype_nopred

    _cython_nptypes_nopred = None

    @property
    def cython_nptypes_nopred(self):
        """The Cython NumPy representation of the types without predicates.
        """
        if self._cython_nptypes_nopred is None:
            self._cython_nptypes_nopred = self.ts.cython_nptype(self.t_nopred, depth=1)
        return self._cython_nptypes_nopred

    _cython_npctypes_nopred = None

    @property
    def cython_npctypes_nopred(self):
        """The Cython C/C++ representation of the NumPy types without predicates.
        """
        if self._cython_npctypes_nopred is None:
            npts_nopred = self.ts.cython_nptype(self.t_nopred, depth=1)
            npts_nopred = [npts_nopred] if isinstance(npts_nopred, basestring) \
                                        else npts_nopred
            npcts_nopred = _maprecurse(self.ts.cython_ctype, npts_nopred)
            self._cython_npctypes_nopred = npcts_nopred
        return self._cython_npctypes_nopred

    _cython_npcytypes_nopred = None

    @property
    def cython_npcytypes_nopred(self):
        """The Cython Cython representation of the NumPy types without predicates.
        """
        if self._cython_npcytypes_nopred is None:
            npts_nopred = self.ts.cython_nptype(self.t_nopred, depth=1)
            npts_nopred = [npts_nopred] if isinstance(npts_nopred, basestring) \
                                        else npts_nopred
            npcyts_nopred = _maprecurse(self.ts.cython_cytype, npts_nopred)
            self._cython_npcytypes_nopred = npcyts_nopred
        return self._cython_npcytypes_nopred

    _cython_nppytypes_nopred = None

    @property
    def cython_nppytypes_nopred(self):
        """The Cython Python representation of the NumPy types without predicates.
        """
        if self._cython_nppytypes_nopred is None:
            npts_nopred = self.ts.cython_nptype(self.t_nopred, depth=1)
            npts_nopred = [npts_nopred] if isinstance(npts_nopred, basestring) \
                                        else npts_nopred
            nppyts_nopred = _maprecurse(self.ts.cython_pytype, npts_nopred)
            self._cython_nppytypes_nopred = nppyts_nopred
        return self._cython_nppytypes_nopred


#################### Type system helpers #######################################

def _raise_type_error(t):
    raise TypeError("type of {0!r} could not be determined".format(t))

def _undot_class_name(name, d):
    value = d[name]
    if '.' not in value:
        return ''
    v1, v2 = value.rsplit('.', 1)
    d[name] = v2
    return v1

def _redot_class_name(name, d, value):
    if 0 == len(value):
        return
    d[name] = value + '.' + d[name]

def _maprecurse(f, x):
    if not isinstance(x, list):
        return [f(x)]
    #return [_maprecurse(f, y) for y in x]
    l = []
    for y in x:
        l += _maprecurse(f, y)
    return l

def _ensure_importable(x):
    if isinstance(x, basestring) or x is None:
        r = ((x,),)
    elif isinstance(x, Iterable) and (isinstance(x[0], basestring) or x[0] is None):
        r = (x,)
    else:
        r = x
    return r
