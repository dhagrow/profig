"""
A simple-to-use configuration library.

    import profig
    cfg = profig.Config('server.cfg')
    cfg['server.host'] = '8.8.8.8'
    cfg['server.port'] = 8181
    cfg.sync()

"""

from __future__ import print_function, unicode_literals

import io
import os
import re
import sys
import errno
import locale
import itertools
import collections

__author__  = 'Miguel Turner'
__version__ = '0.2.9'
__license__ = 'MIT'

__all__ = ['Config', 'IniFormat', 'ConfigError', 'Coercer', 'CoerceError']

PY3 = sys.version_info.major >= 3

# use str for unicode data and bytes for binary data
if not PY3:
    str = unicode

# the name *type* is used often so give type() an alias rather than use *typ*
_type = type

## Config ##

class ConfigSection(collections.MutableMapping):
    """
    Represents a group of configuration options.
    
    This class is not meant to be instantiated directly.
    """
    
    def __init__(self, name, parent):
        self._name = name
        self._value = NoValue
        self._cache = NoValue
        self._default = NoValue
        self._type = None
        self._has_type = False
        self._parent = parent
        
        self.comment = None
        self.dirty = False
        
        if parent is None:
            # root
            self._root = self
            self._key = None
        else:
            # child
            self._root = parent._root
            self._key = self._keystr(self._make_key(parent._key, name))
            parent._children[name] = self
        
        self._children = self._root._dict_type()
    
    ## properties ##
    
    @property
    def root(self):
        return self._root
    
    @property
    def parent(self):
        """The section's parent or `None`. Read-only."""
        return self._parent
    
    @property
    def key(self):
        """The section's key. Read-only."""
        return self._key
    
    @property
    def name(self):
        """The section's name. Read-only."""
        return self._name
    
    @property
    def type(self):
        """The type used for coercing the value for this section.
        Read only."""
        return self._type
    
    @property
    def valid(self):
        """`True` if this section has a valid value. Read-only."""
        return not (self._value is NoValue and self._default is NoValue)
    
    @property
    def is_default(self):
        return (self._value is NoValue and self._default is not NoValue)
    
    @property
    def has_children(self):
        return bool(self._children)
    
    ## methods ##
    
    def sync(self, *sources, **kwargs):
        """Reads from sources and writes any changes back to the first source.

        If *sources* are provided, syncs only those sources. Otherwise,
        syncs the sources in :attr:`~config.Config.sources`.
        """
        
        format = kwargs.pop('format', None)
        
        # if caching, adapt cached values
        if self.cache_values:
            for section in self.sections(recurse=True):
                section._adapt_cache()
        
        sources, format = self._process_sources(sources, format)
        
        # sync
        lines = self._read(sources, format)
        self._write(sources[0], format, lines)
    
    def read(self, *sources, **kwargs):
        """
        Reads config values.
        
        If *sources* are provided, read only from those sources. Otherwise,
        write to the sources in :attr:`~config.Config.sources`. A format for
        *sources* can be set using *format*.
        """
        format = kwargs.pop('format', None)
        sources, format = self._process_sources(sources, format)
        self._read(sources, format)
    
    def write(self, source=None, format=None):
        """
        Writes config values.
        
        If *source* is provided, write only to that source. Otherwise, write to
        the first source in :attr:`~config.Config.sources`. A format for
        *source* can be set using *format*. *format* is otherwise ignored.
        """
        sources = [source] if source else []
        sources, format = self._process_sources(sources, format)
        self._write(sources[0], format)
    
    def init(self, key, default, type=None, comment=None):
        """Initializes *key* to the given *default* value.
        
        If *type* is not provided, the type of the default value will be used.
        
        If a *comment* is provided, it may be written out to the config
        file in a manner consistent with the active :class:`~profig.Format`.
        """
        section = self._create_section(key)
        section._cache = NoValue
        section._type = type or default.__class__
        section._has_type = True
        section.set_default(default)
        section.comment = comment
    
    def get(self, key, default=None, convert=True, type=None):
        """
        Return the value for key if key is in the dictionary,
        else default. If *default* is not given, it defaults to
        `None`, so that this method never raises an
        :exc:`~profig.InvalidSectionError`. If *type* is provided,
        it will be used as the type to convert the value from text.
        If *convert* is `False`, *type* will be ignored.
        """
        try:
            section = self.section(key, create=False)
            return section.value(convert, type)
        except (InvalidSectionError, NoValueError):
            return default
    
    def __getitem__(self, key):
        return self.section(key, create=False).value()
    
    def __setitem__(self, key, value):
        section = self._create_section(key)
        if isinstance(value, collections.Mapping):
            section.update(value)
        else:
            section.set_value(value)
    
    def __delitem__(self, key):
        section = self.section(key)
        del section._parent._children[section.name]
    
    def __bool__(self):
        return True
    
    def __nonzero__(self):
        return True
    
    def __len__(self):
        return len(self._children)
    
    def __iter__(self):
        if self.valid:
            # an empty key so the section can find itself
            yield ''
        sep = self._root.sep
        for child in self._children.values():
            for key in child:
                if key:
                    yield sep.join([child._name, key])
                else:
                    yield child._name
    
    def __repr__(self): # pragma: no cover
        try:
            value = self.value()
        except NoValueError:
            value = NoValue
        return "{}('{}', value={!r}, keys={}, comment={!r})".format(
            self.__class__.__name__, self.key, value, list(self), self.comment)
    
    def as_dict(self, flat=False, recurse=True, convert=True, dict_type=None):
        """Returns the configuration's keys and values as a dictionary.
        
        If *flat* is `True`, returns a single-depth dict with :samp:`.`
        delimited keys.
        
        If *convert* is `True`, all values will be converted. Otherwise, their
        string representations will be returned.
        
        If *dict_type* is not `None`, it should be the mapping class to use
        for the result. Otherwise, the *dict_type* set by
        :meth:`~config.Config.__init__` will be used (the default is
        `OrderedDict`).
        """
        dtype = dict_type or self._root._dict_type
        valid = self is not self._root and self.valid
        
        if flat:
            sections = ((k, self.section(k)) for k in self)
            return dtype((k, s.value(convert)) for k, s in sections)
        
        if recurse and self._children:
            d = dtype()
            if valid:
                d[''] = self.value(convert)
            for section in self.sections():
                d.update(section.as_dict(convert=convert, dict_type=dict_type))
            
            return d if self is self._root else dtype({self.name: d})
        elif valid:
            return dtype({self.name: self.value(convert)})
        else:
            return dtype()

    def section(self, key, create=True):
        """Returns a section object for *key*.
        
        If there is no existing section for *key*, and *create* is `False`, an
        :exc:`~profig.InvalidSectionError` is thrown."""
        
        if key is None:
            raise InvalidSectionError(key)
        section = self
        for name in self._make_key(key):
            try:
                section = section._children[name]
            except KeyError:
                if create:
                    return self._create_section(key)
                raise InvalidSectionError(key)
        return section

    def sections(self, recurse=False):
        """Returns the sections that are children to this section.
        
        If *recurse* is `True`, returns grandchildren as well.
        """
        for child in self._children.values():
            yield child
            if recurse:
                for grand in child.sections(recurse):
                    yield grand
    
    def reset(self, recurse=True):
        """Resets this section to it's default value, leaving it
        in the same state as after a call to :meth:`ConfigSection.init`.
        If *recurse* is `True`, does the same to all the
        section's children."""
        if self is not self._root:
            self._reset()
        if recurse:
            for section in self.sections(recurse):
                section._reset()
    
    def value(self, convert=True, type=None):
        """
        Get the section's value.
        To get the underlying string value, set *convert* to `False`.
        If *convert* is `False`, *type* will be ignored.
        """
        if not convert:
            if self._value is not NoValue:
                return self._value
        elif type is None and self._cache is not NoValue:
            return self._cache
        elif self._value is not NoValue:
            value = self.convert(self._value, type)
            self._cache = self._cache_value(value)
            return value
        
        return self.default(convert, type)
    
    def set_value(self, value):
        """Set the section's value."""
        if not isinstance(value, str):
            strvalue = self.adapt(value)
            if strvalue != self._value:
                self._value = strvalue
                self._cache = self._cache_value(value)
                self.dirty = True
        
        elif value != self._value:
            self._value = value
            self._cache = NoValue
            self.dirty = True
    
    def default(self, convert=True, type=None):
        """
        Get the section's default value.
        To get the underlying string value, set *convert* to `False`.
        If *convert* is `False`, *type* will be ignored.
        """
        if not convert:
            if self._default is not NoValue:
                return self._default
        elif self._default is not NoValue:
            if type is None and self._value is NoValue and self._cache is not NoValue:
                # only use cache if self._value hasn't been set
                return self._cache
            else:
                value = self.convert(self._default, type)
                # only set cache if self._value hasn't been set
                if self._value is NoValue:
                    self._cache = self._cache_value(value)
                return value
        
        raise NoValueError(self.key)
    
    def set_default(self, default):
        """
        Set the section's default value.
        """
        if not isinstance(default, str):
            self._default = self.adapt(default)
            # only set cache if self._value hasn't been set
            if self._value is NoValue:
                self._cache = self._cache_value(default)
        else:
            self._default = default
            # only clear cache if self._value hasn't been set
            if self._value is NoValue:
                self._cache = NoValue
    
    def items(self, convert=True):
        """Returns a (key, value) iterator over the unprocessed values of
        this section."""
        for key in self:
            yield (key, self.section(key).value(convert))
    
    def adapt(self, value):
        if self._root.coerce_values:
            if not self._has_type:
                self._type = value.__class__
            return self._root.coercer.adapt(value, self._type)
        else:
            return value
    
    def convert(self, value, type):
        if self._root.coerce_values:
            return self._root.coercer.convert(value, type or self._type)
        else:
            return value
    
    def clear_cache(self, recurse=False):
        """Clears cached values for this section. If *recurse* is
        `True`, clears the cache for child sections as well."""
        for section in self.sections(recurse):
            section._cache = NoValue
    
    ## utilities ##
    
    def _read(self, sources, format):
        write_lines = None
        
        # read unchanged values from sources
        for i, source in enumerate(reversed(sources)):
            try:
                file = format.open(source)
            except IOError:
                continue
            
            # read file
            try:
                lines = format.read(file)
            except IOError:
                # XXX: there should be a way of indicating that there
                # was an error without causing the sync to fail for
                # other sources
                continue
            finally:
                # only close files that were opened from the filesystem
                if isinstance(source, str):
                    file.close()
            
            # return lines only for the first source
            if i == 0:
                write_lines = lines
        
        return write_lines
    
    def _write(self, source, format, lines=None):
        file = format.open(source, 'w')
        try:
            format.write(file, lines)
        finally:
            # only close files that were opened from the filesystem
            if isinstance(source, str):
                file.close()
            else:
                file.flush()
    
    def _process_sources(self, sources, format):
        sources = sources or self.sources
        if not sources:
            raise NoSourcesError()
        format = self._process_format(format)
        return sources, format
    
    def _process_format(self, format):
        """
        Returns a :class:`~config.Format` instance.
        Accepts a name, class, or instance as the *format* argument.
        """
        if not format:
            return self._format
        elif isinstance(format, str):
            try:
                cls = Config._formats[format]
            except KeyError as e:
                raise UnknownFormatError(e)
            return cls(self)
        elif isinstance(format, Format):
            return format
        else:
            return format(self)
    
    def _create_section(self, key):
        section = self
        for name in self._make_key(key):
            if not name:
                # skip empty fields
                continue
            try:
                section = section._children[name]
            except KeyError:
                section = ConfigSection(name, section)
        return section
    
    def _make_key(self, *path):
        key = []
        sep = self._root.sep
        encoding = self._root.encoding
        for p in path:
            if p and isinstance(p, bytes):
                p = p.decode(encoding)
            if p and isinstance(p, str):
                key.extend(p.split(sep))
            elif isinstance(p, collections.Sequence):
                key.extend(p)
            elif p is None:
                pass
            else:
                err = "invalid value for key: '{}'"
                raise TypeError(err.format(p))
        return tuple(key)
    
    def _keystr(self, key):
        return self._root.sep.join(key)
    
    def _reset(self):
        if self._value is not NoValue:
            self._value = NoValue
            self._cache = NoValue
            self.dirty = True
            if self._default is NoValue:
                self._type = None
    
    def _adapt_cache(self):
        if self._cache is not NoValue:
            strvalue = self.adapt(self._cache)
            if strvalue != self.value(convert=False):
                self.set_value(strvalue)
                self.dirty = True
    
    def _cache_value(self, value):
        # no point in caching a string
        should_cache = self._root.cache_values and not isinstance(value, str)
        return value if should_cache else NoValue
    
    def _dump(self, indent=2): # pragma: no cover
        rootlen = len(self._make_key(self._key))
        for section in sorted(self.sections(recurse=True)):
            sectionlen = len(self._make_key(section._key))
            spaces = ' ' * ((sectionlen - rootlen) * indent - 1)
            print(spaces, repr(section))

class Config(ConfigSection):
    """
    The root configuration object.
    
    Any number of sources can be set using *sources*. These are the sources
    that will be using when calling :meth:`~profig.ConfigSection.sync`.
    
    The format of the sources can be set using *format*. This can be either
    the registered name of a format, such as "ini", or a
    :class:`~profig.Format` class or instance.
    
    An encoding can be set using *encoding*. If *encoding* is not specified
    the encoding used is platform dependent: locale.getpreferredencoding(False).
    
    The dict class used internally can be set using *dict_type*. By default
    an `OrderedDict` is used.
    
    This is a subclass of :class:`~profig.ConfigSection`.
    """
    
    _formats = {}
    
    def __init__(self, *sources, **kwargs):
        self._dict_type = kwargs.pop('dict_type', collections.OrderedDict)
        super(Config, self).__init__(None, None)

        self.sources = list(sources)
        self.encoding = kwargs.pop('encoding', locale.getpreferredencoding(False))
        
        format = kwargs.pop('format', 'ini')
        self.set_format(format)
        
        self.coercer = Coercer()
        register_booleans(self.coercer)
        
        self.sep = '.'
        self.cache_values = True
        self.coerce_values = True
    
    @classmethod
    def known_formats(cls):
        """Returns the formats registered with this class."""
        return tuple(cls._formats)
    
    def set_format(self, format):
        self._format = self._process_format(format)
    
    def _dump(self, indent=2): # pragma: no cover
        for section in self.sections(recurse=True):
            sectionlen = len(self._make_key(section._key))
            spaces = ' ' * ((sectionlen - 1) * indent)
            print(spaces, repr(section), sep='')
    
    def __repr__(self): # pragma: no cover
        return '{}(sources={}, keys={})'.format(self.__class__.__name__,
            self.sources, list(self))

## Config Formats ##

class MetaFormat(type):
    """
    Metaclass that registers a :class:`~profig.Format` with the
    :class:`~profig.Config` class.
    """
    def __init__(cls, name, bases, dct):
        if name not in ('BaseFormat', 'Format'):
            Config._formats[cls.name] = cls
        return super(MetaFormat, cls).__init__(name, bases, dct)

BaseFormat = MetaFormat('BaseFormat' if PY3 else b'BaseFormat', (object, ), {})

class Line(collections.namedtuple('Line', 'line name iskey issection')):
    __slots__ = ()
    def __new__(cls, line, name=None, iskey=False, issection=False):
        return super(Line, cls).__new__(cls, line, name, iskey, issection)

class Format(BaseFormat):
    name = None
    
    def __init__(self, config):
        self.config = config
        
        self.encoding = config.root.encoding
        self.ensure_dirs = 0o744
        self.read_errors = 'exception'
        self.write_errors = 'exception'
    
    def read(self, file): # pragma: no cover
        """Reads *file* and returns a dict. Must be implemented
        in a subclass."""
        raise NotImplementedError('abstract')
    
    def write(self, file, values, lines=None): # pragma: no cover
        """Writes the dict *values* to file. Must be implemented
        in a subclass."""
        raise NotImplementedError('abstract')
    
    def open(self, source, mode='r', *args):
        """Returns a file object.
        
        If *source* is a file object, returns *source*. If *mode* is 'w',
        The file object will be truncated.
        This method assumes either read or write/append access, but not both.
        """
        if isinstance(source, bytes):
            source = source.decode(self.encoding)
        
        if isinstance(source, str):
            if self.ensure_dirs is not None and 'w' in mode:
                # ensure the path exists if any writing is to be done
                ensure_dirs(os.path.dirname(source), self.ensure_dirs)
            return io.open(source, mode, *args, encoding=self.encoding)
        else:
            source.seek(0)
            if 'w' in mode:
                source.truncate()
            return source
    
    def _read_error(self, file, lineno=None, text='', message=''):
        if self.read_errors != 'ignore':
            name = file.name if hasattr(file, 'name') else '<???>'
            exc = ReadError(name, lineno, text, message)
            if self.read_errors == 'exception':
                raise exc
            elif self.read_errors == 'error':
                print(str(exc), file=sys.stderr)
            else:
                assert False
    
    def _write_error(self, file, message=''):
        if self.write_errors != 'ignore':
            name = file.name if hasattr(file, 'name') else '<???>'
            exc = WriteError(name, message)
            if self.write_errors == 'exception':
                raise exc
            elif self.write_errors == 'error':
                print(str(exc), file=sys.stderr)
            else:
                assert False

class IniFormat(Format):
    name = 'ini'
    delimeter = '='
    comment_char = ';'
    default_section = 'default'
    _rx_section_header = re.compile('\[\s*(\S*)\s*\](\s*=\s*(\S*))?')
    
    def read(self, file):
        cfg = self.config
        section_name = self.default_section
        comment = None
        lines = []
        values = cfg._dict_type()
        comments = {}
        
        def flush_comment(lines, comment):
            if comment:
                lines.append(comment)
        
        for i, orgline in enumerate(file, 1):
            line = orgline.strip()
            
            # blank line
            if not line:
                comment = flush_comment(lines, comment)
                continue
            
            # comment line
            if line.startswith(self.comment_char):
                flush_comment(lines, comment)
                comment = Line(orgline, line.lstrip(self.comment_char).strip())
                continue
            
            # section header
            match = self._rx_section_header.match(line)
            if match:
                section_name, _, value = match.groups()
                
                # blank sections are set to default
                if not section_name or section_name.lower() == self.default_section:
                    section_name = self.default_section
                
                values[section_name] = value
                comments[section_name] = comment.name if comment else None
                comment = None
                
                lines.append(Line(orgline, section_name, issection=True))
                continue
            
            # must be a value
            try:
                key, value = line.split(self.delimeter, 1)
            except ValueError:
                self._read_error(file, i, line)
                continue
            
            key = cfg._keystr(cfg._make_key(section_name, key.strip()))
            values[key] = value.strip()
            comments.setdefault(key, comment.name if comment else None)
            comment = None
            
            lines.append(Line(orgline, key, iskey=True))
        
        # comment left over
        if comment:
            lines.append(comment)
        
        # file has been read. assign the values
        for key, value in values.items():
            section = cfg.section(key)
            if not section.dirty and value is not None:
                section.set_value(value)
            if key in comments:
                section.comment = comments[key]
        
        return lines
    
    def write_section(self, section, file, first=False):
        if not first and section.parent is section.root:
            file.write('\n')
        
        if section.comment:
            file.write('{} {}\n'.format(self.comment_char, section.comment))
        
        if section.parent is section.root:
            # header section
            if section.valid:
                value = section.value(convert=False)
                file.write('[{}] = {}\n'.format(section.name, value))
            else:
                file.write('[{}]\n'.format(section.name))
        elif section.valid:
            # value section
            cfg = self.config
            key = cfg._keystr(cfg._make_key(section.key)[1:])
            value = section.value(convert=False)
            
            file.write('{} {} {}\n'.format(key, self.delimeter, value))
        
        section.dirty = False
    
    def write(self, file, lines=None):
        cfg = self.config
        
        # write back values in the order they were read
        seen = set()
        header = None
        lines = lines or []
        first = True
        for i, line in enumerate(lines):
            if line.issection:
                if line.name in seen:
                    continue
                
                # if there is a previous header section, write it's remaining values
                if header:
                    for sec in header.sections(recurse=True):
                        if sec.key not in seen:
                            self.write_section(sec, file)
                            seen.add(sec.key)
                
                # write current section header
                header = cfg.section(line.name)
                self.write_section(header, file, first)
                seen.add(header.key)
                first = False
            
            elif line.iskey:
                if line.name in seen:
                    continue
                self.write_section(cfg.section(line.name), file)
                seen.add(line.name)
            
            else:
                file.write(line.line)
        
        # if there is a previous header section, write it's remaining values
        if header:
            for sec in header.sections(recurse=True):
                if sec.key not in seen:
                    self.write_section(sec, file)
                    seen.add(sec.key)
        
        # write remaining values
        for section in cfg.sections(recurse=True):
            if section.key in seen:
                continue
            
            self.write_section(section, file, first)
            seen.add(section.key)
            first = False

## Config Errors ##

class ConfigError(Exception):
    """Base exception class for all exceptions raised."""

class UnknownFormatError(ConfigError):
    """Raised when a format is set that has not been registered."""

class InvalidSectionError(KeyError, ConfigError):
    """Raised when a section was never created."""

class NoValueError(ValueError, ConfigError):
    """Raised when a section has no set value or default value."""

class SyncError(ConfigError):
    """Base class for errors that can occur when syncing."""
    def __init__(self, filename=None, message=''):
        self.filename = filename
        self.message = message
    
    def __str__(self):
        if self.filename:
            err = ["error reading '{}'".format(self.filename)]
            if self.message:
                err.extend([': ', self.message])
            return ''.join(err)
        else:
            return self.message

class ReadError(SyncError):
    """Raised when a value could not be read from a source."""
    def __init__(self, filename=None, lineno=None, text='', message=''):
        super(ReadError, self).__init__(filename, message)
        self.lineno = lineno
        self.text = text
    
    def __str__(self):
        if self.filename:
            msg = "error reading '{}', line {}"
            err = [msg.format(self.filename, self.lineno)]
            if self.message:
                err.extend([': ', self.message])
            if self.text:
                err.extend(['\n  ', self.text])
            return ''.join(err)
        else:
            return self.message

class WriteError(SyncError):
    """Raised when a value could not be written to a source."""

class NoSourcesError(ConfigError):
    """Raised when there are no sources for a config object."""

## Config Utilities ##

class NoValue:
    def __repr__(self):
        return '{}'.format(self.__class__.__name__)
NoValue = NoValue()

# adapted from pyglet
def get_source(filename, scope='script'):
    """Returns a path for *filename* in the given *scope*.
    *scope* must be one of the following:
    
    * script - the running script's directory
    * user - the current user's settings directory
    """
    if scope == 'script':
        script = ''
        frozen = getattr(sys, 'frozen', None)
        if frozen == 'macosx_app':
            script = os.environ['RESOURCEPATH']
        elif frozen:
            script = sys.executable
        else:
            main = sys.modules['__main__']
            if hasattr(main, '__file__'):
                script = main.__file__
        base = os.path.dirname(script)

    elif scope == 'user':
        base = ''
        if sys.platform in ('cygwin', 'win32'):
            if 'APPDATA' in os.environ:
                base = os.environ['APPDATA']
            else:
                base = '~/'
        elif sys.platform == 'darwin':
            base = '~/Library/Application Support/'
        else:
            base = '~/.config/'

    return os.path.join(base, filename)

def ensure_dirs(path, mode=0o744):
    """Like makedirs, but doesn't raise en exception if the dirs exist"""
    if not path:
        return
    try:
        os.makedirs(path, mode)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

## Coercer ##

class Coercer:
    """
    The coercer class, with which adapters and converters can be registered.
    """
    def __init__(self, register_defaults=True, register_qt=None):
        self._adapters = {}
        self._converters = {}
        
        if register_defaults:
            register_default_coercers(self)
        if register_qt is None:
            # only load Qt coercers if PyQt/PySide has already been imported
            register_qt = bool({'PyQt4', 'PySide'} & set(sys.modules))
        if register_qt:
            register_qt_coercers(self)
    
    def adapt(self, value, type=None):
        """Adapt a *value* from the given *type* (type to string). If
        *type* is not provided the type of the value will be used."""
        
        if not type:
            type = _type(value)
        
        try:
            func = self._adapters[self._typename(type)]
        except KeyError:
            err = 'no adapter for: {}'
            raise NotRegisteredError(err.format(type))
        
        try:
            return func(value)
        except Exception as e:
            raise AdaptError(e)
    
    def convert(self, value, type):
        """Convert a *value* to the given *type* (string to type)."""
        
        try:
            func = self._converters[self._typename(type)]
        except KeyError:
            err = "no converter for: {}"
            raise NotRegisteredError(err.format(type))
        
        try:
            return func(value)
        except Exception as e:
            raise ConvertError(e)
    
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
        Values passed into :meth:`~profig.Coercer.adapt` or
        :meth:`~profig.Coercer.convert` for *type* will have to be one of the
        choices. *choices* must be a dict that maps converted->adapted
        representations."""
        def verify(x, c=choices):
            if x not in c:
                err = "invalid choice {!r}, must be one of: {}"
                raise ValueError(err.format(x, c))
            return x
        
        values = {value: key for key, value in choices.items()}
        adapt = lambda x: choices[verify(x, choices.keys())]
        convert = lambda x: values[verify(x, values.keys())]
        
        self.register_adapter(type, adapt)
        self.register_converter(type, convert)
    
    def _typename(self, type):
        if isinstance(type, bytes):
            type = type.decode('utf-8')
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

## Coercer Errors ##

class CoerceError(Exception):
    """Base class for coerce exceptions"""

class AdaptError(CoerceError):
    """Raised when a value cannot be adapted"""

class ConvertError(CoerceError):
    """Raised when a value cannot be converted"""

class NotRegisteredError(CoerceError, KeyError):
    """Raised when an unknown type is passed to adapt or convert"""

## Coercer Registries ##

def register_default_coercers(coercer):
    """Registers adapters and converters for common types."""
    import binascii
    
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
        lambda x: binascii.unhexlify(x.encode('ascii')))
    
    # collection coercers, simply comma delimited
    split = lambda x: x.split(',') if x else []
    coercer.register(list, lambda x: ','.join(x), split)
    coercer.register(set, lambda x: ','.join(x), lambda x: set(split(x)))
    coercer.register(tuple, lambda x: ','.join(x), lambda x: tuple(split(x)))
    
    # path coercers, os.pathsep delimited
    sep = os.pathsep
    pathsplit = lambda x: x.split(sep) if x else []
    coercer.register('path_list', lambda x: sep.join(x), pathsplit)
    coercer.register('path_set', lambda x: sep.join(x), lambda x: set(pathsplit(x)))
    coercer.register('path_tuple', lambda x: sep.join(x), lambda x: tuple(pathsplit(x)))

def register_booleans(coercer):
    ## override boolean coercers ##
    _boolean_states = {'1': True, 'yes': True, 'true': True, 'on': True,
        '0': False, 'no': False, 'false': False, 'off': False}
    coercer.register_adapter(bool, lambda x: 'true' if x else 'false')
    coercer.register_converter(bool, lambda x: _boolean_states[x.lower()])

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
        lambda x: '{},{}'.format(x.x(), x.y()),
        lambda x: QtCore.QPoint(*[int(i) for i in x.split(',')]))
    coercer.register(QtCore.QPointF,
        lambda x: '{},{}'.format(x.x(), x.y()),
        lambda x: QtCore.QPointF(*[float(i) for i in x.split(',')]))
    coercer.register(QtCore.QSize,
        lambda x: '{},{}'.format(x.width(), x.height()),
        lambda x: QtCore.QSize(*[int(i) for i in x.split(',')]))
    coercer.register(QtCore.QSizeF,
        lambda x: '{},{}'.format(x.width(), x.height()),
        lambda x: QtCore.QSizeF(*[float(i) for i in x.split(',')]))
    coercer.register(QtCore.QRect,
        lambda x: '{},{},{},{}'.format(x.x(), x.y(), x.width(), x.height()),
        lambda x: QtCore.QRect(*[int(i) for i in x.split(',')]))
    coercer.register(QtCore.QRectF,
        lambda x: '{},{},{},{}'.format(x.x(), x.y(), x.width(), x.height()),
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
