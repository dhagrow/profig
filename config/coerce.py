"""
Functions for coercing objects to different types.
"""

import os
import sys
import binascii
import itertools
import collections

# the name 'type' is used often so give type() an alias rather than use 'typ'
_type = type

def _issequence(obj):
    """Returns True if *obj* is a Sequence but not a str."""
    return isinstance(obj, collections.Sequence) and not isinstance(obj, str)

class CoerceError(Exception):
    """Base class for coerce exceptions"""

class AdaptError(CoerceError):
    """Raised when a value cannot be adapted"""

class ConvertError(CoerceError):
    """Raised when a value cannot be converted"""

class NotRegisteredError(CoerceError, KeyError):
    """Raised when an unknown type is passed to adapt or convert"""

class Coercer:
    """
    The coercer class, with which adapters and converters can be registered.
    """
    def __init__(self, register_defaults=True, register_qt=False):
        #: An adapter to fallback to when no other adapter is found.
        self.adapt_fallback = None
        #: An converter to fallback to when no other converter is found.
        self.convert_fallback = None
        
        self._adapters = {}
        self._converters = {}
        
        if register_defaults:
            register_default_coercers(self)
        if register_qt:
            register_qt_coercers(self)
    
    def adapt(self, value, type=None):
        """Adapt a *value* from the given *type* (type to string). If
        *type* is not provided the type of the value will be used."""
        if not type:
            type = _type(value)
        
        if _issequence(type):
            try:
                try:
                    # try and get an adapter for the full type sequence
                    seq_adapter = self._get_adapter(type)
                except KeyError:
                    # otherwise use the first type to get the adapter
                    seq_adapter = self._get_adapter(type[0])
                
                # str is default if no other type is given
                seq_types = type[1:]
                if not seq_types:
                    seq_types = [str]
                
                ads = itertools.cycle(self._get_adapter(t) for t in seq_types)
            except KeyError:
                # fallback
                pass
            else:
                try:
                    return seq_adapter(next(ads)(v) for v in value)
                except Exception as e:
                    raise AdaptError(e)
        else:
            try:
                func = self._get_adapter(type)
            except KeyError:
                # fallback
                pass
            else:
                try:
                    return func(value)
                except Exception as e:
                    raise AdaptError(e)
        
        if self.adapt_fallback:
            try:
                return self.adapt_fallback(value)
            except Exception as e:
                raise AdaptError(e)
        else:
            err = "no adapter registered for '{0}'"
            raise NotRegisteredError(err.format(type))
    
    def convert(self, value, type):
        """Convert a *value* to the given *type* (string to type)."""
        if _issequence(type):
            try:
                try:
                    # try and get a converter for the full type sequence
                    seq_converter = self._get_converter(type)
                except KeyError:
                    # otherwise try the first type to get the converter
                    seq_converter = self._get_converter(type[0])
                
                # str is default if no other type is given
                seq_types = type[1:]
                if not seq_types:
                    seq_types = [str]
                
                cons = itertools.cycle(self._get_converter(t) for t in seq_types)
            except KeyError:
                # fallback
                pass
            else:
                try:
                    return type[0](next(cons)(v) for v in seq_converter(value))
                except Exception as e:
                    raise ConvertError(e)
        else:
            try:
                func = self._get_converter(type)
            except KeyError:
                # fallback
                pass
            else:
                try:
                    return func(value)
                except Exception as e:
                    raise ConvertError(e)
        
        if self.convert_fallback:
            try:
                return self.convert_fallback(value)
            except Exception as e:
                raise ConvertError(e)
        else:
            err = "no converter registered for '{0}'"
            raise NotRegisteredError(err.format(type))
    
    def register(self, type, adapter, converter):
        """Register an adapter and converter for the given type."""
        self.register_adapter(type, adapter)
        self.register_converter(type, converter)
    
    def register_adapter(self, type, adapter):
        """Register an adapter (type to string) for the given type."""
        self._adapters[self._typename(type)] = adapter
    
    def register_converter(self, type, converter):
        """Register a converter (string to type) for the given type."""
        self._converters[self._typename(type)] = converter
    
    def register_choice(self, type, choices):
        """Registers an adapter and converter for a choice of values.
        Values passed into :meth:`adapt` or :meth:`convert` for *type* will
        have to be one of the choices. *choices* must be a dict that maps
        converted->adapted representations."""
        def verify(x, c=choices):
            if x not in c:
                err = "invalid choice {0!r}, must be one of: {1}"
                raise ValueError(err.format(x, c))
            return x
        
        values = {value: key for key, value in choices.items()}
        adapt = lambda x: choices[verify(x, choices.keys())]
        convert = lambda x: values[verify(x, values.keys())]
        
        self.register_adapter(type, adapt)
        self.register_converter(type, convert)
    
    def clear_coercers(self):
        """Clears all registered adapters and converters."""
        self.unregister_adapters()
        self.unregister_converters()
    
    def unregister_adapters(self, *types):
        """
        Unregister one or more adapters.
        Unregisters all adapters if no arguments are given.
        """
        if not types:
            self._adapters.clear()
        else:
            for type in types:
                del self._adapters[self._typename(type)]
    
    def unregister_converters(self, *types):
        """
        Unregister one or more converters.
        Unregisters all converters if no arguments are given.
        """
        if not types:
            self._converters.clear()
        else:
            for type in types:
                del self._converters[self._typename(type)]
    
    def _typename(self, type):
        if isinstance(type, str):
            if '.' in type:
                return tuple(type.rsplit('.', 1))
            else:
                return type
        elif isinstance(type, collections.Sequence):
            return tuple(self._typename(t) for t in type)
        elif isinstance(type, _type):
            return (type.__module__, type.__name__)
        elif type is None:
            t = _type(type)
            return (t.__module__, 'None')
        else:
            t = _type(type)
            return (t.__module__, t.__name__)
    
    def _get_adapter(self, type):
        return self._adapters[self._typename(type)]
    
    def _get_converter(self, type):
        return self._converters[self._typename(type)]

## default coercer ##

_default_coercer = None

def get_default_coercer():
    """Returns the default :class:`Coercer` object."""
    global _default_coercer
    if not _default_coercer:
        # only load Qt coercers if PyQt/PySide has already been imported
        register_qt = bool({'PyQt4', 'PySide'} & set(sys.modules))
        _default_coercer = Coercer(register_qt=register_qt)
    return _default_coercer

def set_default_coercer(coercer):
    """Sets the default :class:`Coercer` object to *coercer*."""
    global _default_coercer
    _default_coercer = coercer

def adapt(value, type=None):
    '''See :meth:`Coercer.adapt`.'''
    return get_default_coercer().adapt(value, type)

def convert(value, type):
    '''See :meth:`Coercer.convert`.'''
    return get_default_coercer().convert(value, type)

## register defaults ##

def register_default_coercers(coercer):
    """Registers adapters and converters for common types."""
    
    # None as the type does not change the value
    coercer.register(None, lambda x: x, lambda x: x)
    # NoneType as the type assumes the value is None
    coercer.register(type(None), lambda x: '', lambda x: None)
    coercer.register(bool, lambda x: str(int(x)), lambda x: bool(int(x)))
    coercer.register(int, str, int)
    coercer.register(float, str, float)
    coercer.register(complex, str, complex)
    coercer.register(str, str, str)
    coercer.register(bytes,
        lambda x: binascii.hexlify(x).decode('ascii'),
        lambda x: binascii.unhexlify(x).encode('ascii'))
    
    # collection coercers, simply comma delimited
    split = lambda x: x.split(',') if x else []
    coercer.register(list, lambda x: ','.join(x), split)
    coercer.register(set, lambda x: ','.join(x), lambda x: set(split(x)))
    coercer.register(tuple, lambda x: ','.join(x), lambda x: tuple(split(x)))
    coercer.register(collections.deque, lambda x: ','.join(x),
        lambda x: collections.deque(split(x)))
    
    # path coercers, os.pathsep delimited
    coercer.register('path', str, str)
    sep = os.pathsep
    pathsplit = lambda x: x.split(sep) if x else []
    coercer.register((list, 'path'), lambda x: sep.join(x), pathsplit)
    coercer.register((set, 'path'), lambda x: sep.join(x), lambda x: set(pathsplit(x)))
    coercer.register((tuple, 'path'), lambda x: sep.join(x),
        lambda x: tuple(pathsplit(x)))
    coercer.register((collections.deque, 'path'), lambda x: sep.join(x),
        lambda x: collections.deque(pathsplit(x)))

def register_qt_coercers(coercer):
    if 'PyQt4' in sys.modules:
        from PyQt4 import QtCore, QtGui
    elif 'PySide' in sys.modules:
        from PySide import QtCore, QtGui
    else:
        err = 'A Qt library must be imported before registering Qt coercers'
        raise ImportError(err)
    
    def fontFromString(s):
        font = QtGui.QFont()
        font.fromString(s)
        return font
    
    coercer.register(QtCore.QByteArray,
        lambda x: str(x.toHex()),
        lambda x: QtCore.QByteArray.fromHex(x))
    coercer.register(QtCore.QPoint,
        lambda x: '{0},{1}'.format(x.x(), x.y()),
        lambda x: QtCore.QPoint(*[int(i) for i in x.split(',')]))
    coercer.register(QtCore.QPointF,
        lambda x: '{0},{1}'.format(x.x(), x.y()),
        lambda x: QtCore.QPointF(*[float(i) for i in x.split(',')]))
    coercer.register(QtCore.QSize,
        lambda x: '{0},{1}'.format(x.width(), x.height()),
        lambda x: QtCore.QSize(*[int(i) for i in x.split(',')]))
    coercer.register(QtCore.QSizeF,
        lambda x: '{0},{1}'.format(x.width(), x.height()),
        lambda x: QtCore.QSizeF(*[float(i) for i in x.split(',')]))
    coercer.register(QtCore.QRect,
        lambda x: '{0},{1},{2},{3}'.format(x.x(), x.y(), x.width(), x.height()),
        lambda x: QtCore.QRect(*[int(i) for i in x.split(',')]))
    coercer.register(QtCore.QRectF,
        lambda x: '{0},{1},{2},{3}'.format(x.x(), x.y(), x.width(), x.height()),
        lambda x: QtCore.QRectF(*[float(i) for i in x.split(',')]))
    coercer.register(QtGui.QColor, lambda x: str(x.name()), QtGui.QColor)
    coercer.register(QtGui.QFont,
        lambda x: str(x.toString()),
        lambda x: fontFromString(x))
    coercer.register(QtGui.QKeySequence,
        lambda x: str(QtGui.QKeySequence(x).toString()), QtGui.QKeySequence)
    coercer.register(QtCore.Qt.WindowStates,
        lambda x: str(int(x)),
        lambda x: QtCore.Qt.WindowState(int(x)))
