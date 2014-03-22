"""
A simple-to-use configuration library.

    import fig
    cfg = fig.Config('server.cfg')
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
import itertools
import collections

__author__  = 'Miguel Turner'
__version__ = '0.2.5'

__all__ = [
    'Config',
    'FigFormat', 'JsonFormat', 'IniFormat', 'PickleFormat',
    'ConfigError',
    'Coercer', 'CoerceError',
    ]

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
        self._dirty = False
        self._parent = parent
        
        if parent is None:
            # root
            self._root = self
            self._key = None
        else:
            # child
            self._root = parent._root
            self._key = self._make_key(parent._key, name)
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
        return self._keystr(self._key)
    
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
    
    ## methods ##
    
    def sync(self, *sources, **kwargs):
        """Reads from sources and writes any changes back to the first source.

        If *sources* are provided, syncs only those sources. Otherwise,
        syncs the sources in :attr:`~config.Config.sources`.

        *include* or *exclude* can be used to filter the keys that
        are written."""
        
        format = kwargs.pop('format', None)
        include = kwargs.pop('include', None)
        exclude = kwargs.pop('exlude', None)
        
        # if caching, adapt cached values
        if self.cache_values:
            for child in self.children(recurse=True):
                child._adapt_cache()
        
        sources, format = self._process_sources(sources, format)
        
        # sync
        context = self._read(sources, format)
        self._write(sources[0], format, context, include, exclude)
    
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
    
    def write(self, source=None, format=None, include=None, exclude=None):
        """
        Writes config values.
        
        If *source* is provided, write only to that source. Otherwise, write to
        the first source in :attr:`~config.Config.sources`. A format for
        *source* can be set using *format*. *format* is otherwise ignored.
        """
        sources = [source] if source else []
        sources, format = self._process_sources(sources, format)
        self._write(sources[0], format, include, exclude)
    
    def init(self, key, default, type=None):
        """Initializes a key to the given default value. If *type* is not
        provided, the type of the default value will be used."""
        section = self._create_section(key)
        section._value = NoValue
        section._cache = NoValue
        section._type = type or default.__class__
        section._has_type = True
        section.set_default(default)
    
    def get(self, key, default=None, convert=True, type=None):
        """
        Return the value for key if key is in the dictionary,
        else default. If *default* is not given, it defaults to
        `None`, so that this method never raises an
        :exc:`~fig.InvalidSectionError`. If *type* is provided,
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
        return "{}('{}', value={!r}, keys={})".format(self.__class__.__name__,
            self.key, value, list(self))
    
    def as_dict(self, flat=False, recurse=True, convert=True,
        include=None, exclude=None, dict_type=None):
        """
        Returns the configuration's keys and values as a dictionary.
        
        If *flat* is `True`, returns a single-depth dict with :samp:`.`
        delimited keys.
        
        If *convert* is `True`, all values will be converted. Otherwise, their
        string representations will be returned.
        
        *include* and *exclude* should be lists of key prefixes used to filter
        the values that are returned.
        
        If *dict_type* is not `None`, it should be the mapping class to use
        for the result. Otherwise, the *dict_type* set by
        :meth:`~config.Config.__init__` will be used (the default is
        `OrderedDict`).
        """
        dtype = dict_type or self._root._dict_type
        valid = self is not self._root and self.valid and self._should_include(include, exclude)
        
        if flat:
            sections = ((k, self.section(k)) for k in self)
            return dtype((k, s.value(convert)) for k, s in sections
                if s._should_include(include, exclude))
        
        if recurse and self._children:
            d = dtype()
            if valid:
                d[''] = self.value(convert)
            for child in self.children():
                if child._should_include(include, exclude):
                    d.update(child.as_dict(convert=convert,
                        include=include, exclude=exclude, dict_type=dict_type))
            
            return d if self is self._root else dtype({self.name: d})
        elif valid:
            return dtype({self.name: self.value(convert)})
        else:
            return dtype()

    def section(self, key, create=True):
        """Returns a section object for *key*.
        
        If there is no existing section for *key*, and *create* is `False`, an
        :exc:`~fig.InvalidSectionError` is thrown."""
        
        section = self
        for name in self._make_key(key):
            try:
                section = section._children[name]
            except KeyError:
                if create:
                    return self._create_section(key)
                raise InvalidSectionError(key)
        return section
    
    def reset(self, recurse=True):
        """Resets this section to it's default value, leaving it
        in the same state as after a call to :meth:`ConfigSection.init`.
        If *recurse* is `True`, does the same to all the
        section's children."""
        if self is not self._root:
            self._reset()
        if recurse:
            for child in self.children(recurse):
                child._reset()
    
    def has_children(self, key=None):
        return self.section(key).has_children() if key else bool(self._children)

    def children(self, recurse=False):
        """Returns the sections that are children to this section.
        If *recurse* is `True`, returns grandchildren as well."""
        for child in self._children.values():
            yield child
            if recurse:
                for grand in child.children(recurse):
                    yield grand
    
    def set_dirty(self, keys, dirty=True):
        """Sets the :attr:`dirty` flag for *keys*, which, if
        `True`, will ensure that each key's value is synced.
        *keys* can be a single key or a sequence of keys."""
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            self.section(key)._dirty = dirty
    
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
            value = self._convert(self._value, type)
            self._cache = self._cache_value(value)
            return value
        
        return self.default(convert, type)
    
    def set_value(self, value):
        """Set the section's value."""
        if not isinstance(value, str):
            strvalue = self._adapt(value)
            if strvalue != self._value:
                self._value = strvalue
                self._cache = self._cache_value(value)
                self._dirty = True
        
        elif value != self._value:
            self._value = value
            self._cache = NoValue
            self._dirty = True
    
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
                value = self._convert(self._default, type)
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
            self._default = self._adapt(default)
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
    
    def adapt(self, value, type):
        return self._root.coercer.adapt(value, type)
    
    def convert(self, value, type):
        return self._root.coercer.convert(value, type)
    
    def clear_cache(self, recurse=False):
        """Clears cached values for this section. If *recurse* is
        `True`, clears the cache for child sections as well."""
        for section in self.children(recurse):
            section._cache = NoValue
    
    ## utilities ##
    
    def _read(self, sources, format):
        write_context = None
        
        # read unchanged values from sources
        for i, source in enumerate(reversed(sources)):
            try:
                file = format.open(source)
            except FileNotFoundError:
                continue
            
            # read file
            try:
                values, context = format.read(file)
            except IOError:
                # XXX: there should be a way of indicating that there
                # was an error without causing the sync to fail for
                # other sources
                continue
            finally:
                # only close files that were opened from the filesystem
                if isinstance(source, str):
                    file.close()
            
            # context
            if i == 0:
                write_context = context
            
            # process values
            for key, value in values.items():
                section = self._root._create_section(key)
                if not section._dirty:
                    section.set_value(value)
        
        return write_context
    
    def _write(self, source, format, context=None, include=None, exclude=None):
        # adjust for subsections
        if self is not self._root:
            sep = self.sep
            for clude in (include, exclude):
                for c in clude.copy():
                    clude.remove(c)
                    clude.add(sep.join([self.key, c]))
            # for subsections, use self as an include filter
            include.add(self.key)
        
        values = self.as_dict(flat=True, convert=False,
            include=include, exclude=exclude)
        
        file = format.open(source, 'w')
        try:
            format.write(file, values, context)
        finally:
            # only close files that were opened from the filesystem
            if isinstance(source, str):
                file.close()
            else:
                file.flush()
        
        # clean values
        self.set_dirty(values.keys(), False)
    
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
        for p in path:
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
            self._dirty = True
            if self._default is NoValue:
                self._type = None
    
    def _adapt(self, value):
        if self._root.coerce_values:
            if not self._has_type:
                self._type = value.__class__
            return self.adapt(value, self._type)
        else:
            return value
    
    def _convert(self, value, type=None):
        if self._root.coerce_values:
            return self.convert(value, type or self._type)
        else:
            return value
    
    def _adapt_cache(self):
        if self._cache is not NoValue:
            strvalue = self._adapt(self._cache)
            if strvalue != self.value(convert=False):
                self.set_value(strvalue)
                self._dirty = True
    
    def _should_include(self, include, exclude):
        # returns the length of the longest matching root
        def matchroot(roots):
            match = 0
            keylen = len(self._key)
            for root in roots:
                root = self._make_key(root)
                rootlen = len(root)
                if rootlen > keylen:
                    continue
                m = 0
                for i in range(rootlen):
                    if root[i] != self._key[i]:
                        m = 0
                        break
                    m += 1
                match = max(match, m)
            return match
        
        # now filter
        if include:
            imatch = matchroot(include)
            ematch = matchroot(exclude or [])
            return imatch > ematch
        elif exclude:
            ematch = matchroot(exclude)
            return not ematch
        else:
            return True
    
    def _cache_value(self, value):
        # no point in caching a string
        should_cache = self._root.cache_values and not isinstance(value, str)
        return value if should_cache else NoValue
    
    def _dump(self, indent=2): # pragma: no cover
        rootlen = len(self._key)
        for section in sorted(self.children(recurse=True)):
            spaces = ' ' * ((len(section._key) - rootlen) * indent - 1)
            print(spaces, repr(section))

class Config(ConfigSection):
    """
    The root configuration object.
    
    Any number of sources can be set using *sources*. These are the sources
    that will be using when calling :meth:`~fig.ConfigSection.sync`.
    
    The format of the sources can be set using *format*. This can be either
    the registered name of a format, such as "ini", or a
    :class:`~fig.Format` class or instance.
    
    The dict class used internally can be set using *dict_type*. By default
    an `OrderedDict` is used.
    
    This is a subclass of :class:`~fig.ConfigSection`.
    """
    
    _formats = {}
    
    def __init__(self, *sources, **kwargs):
        format = kwargs.pop('format', 'fig')
        self._dict_type = kwargs.pop('dict_type', collections.OrderedDict)
        
        self.coercer = Coercer()
        register_booleans(self.coercer)

        self.sources = list(sources)
        self.set_format(format)
        
        self.sep = '.'
        self.cache_values = True
        self.coerce_values = True
        
        super(Config, self).__init__(None, None)
    
    @classmethod
    def known_formats(cls):
        """Returns the formats registered with this class."""
        return tuple(cls._formats)
    
    def set_format(self, format):
        self._format = self._process_format(format)
    
    def _dump(self, indent=2): # pragma: no cover
        for section in self.children(recurse=True):
            spaces = ' ' * ((len(section._key) - 1) * indent)
            print(spaces, repr(section), sep='')
    
    def __repr__(self): # pragma: no cover
        return '{}(sources={}, keys={})'.format(self.__class__.__name__,
            self.sources, list(self))

## Config Formats ##

class MetaFormat(type):
    """
    Metaclass that registers a :class:`~fig.Format` with the
    :class:`~fig.Config` class.
    """
    def __init__(cls, name, bases, dct):
        if name not in ('BaseFormat', 'Format'):
            Config._formats[cls.name] = cls
        return super(MetaFormat, cls).__init__(name, bases, dct)

BaseFormat = MetaFormat('BaseFormat' if PY3 else b'BaseFormat', (object, ), {})

class Format(BaseFormat):
    name = None
    
    def __init__(self, config):
        self.config = config
        
        self.ensure_dirs = 0o744
        self.read_errors = 'error'
        self.write_errors = 'error'
    
    def read(self, file): # pragma: no cover
        """Reads *file* and returns a dict. Must be implemented
        in a subclass."""
        raise NotImplementedError('abstract')
    
    def write(self, file, values, context=None): # pragma: no cover
        """Writes the dict *values* to file. Must be implemented
        in a subclass."""
        raise NotImplementedError('abstract')
    
    def open(self, source, mode='r', *args):
        """Returns a file object.
        
        If *source* is a file object, returns *source*. If *mode* is 'w',
        The file object will be truncated.
        This method assumes either read or write/append access, but not both.
        """
        if isinstance(source, str):
            if self.ensure_dirs is not None and 'w' in mode:
                # ensure the path exists if any writing is to be done
                ensure_dirs(os.path.dirname(source), self.ensure_dirs)
            return open(source, mode, *args)
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

class FigFormat(Format):
    name = 'fig'
    
    def read(self, file):
        values = {}
        lines = []
        for i, orgline in enumerate(file, 1):
            line = orgline.strip()
            if not line or line.startswith('#'):
                # blank or comment line
                lines.append((orgline, False))
                continue
            
            # get the value
            try:
                key, value = line.split(':', 1)
            except ValueError:
                self._read_error(file, i, line)
                continue
            
            key = key.strip()
            values[key] = value.strip()
            lines.append(((key, orgline), True))
        
        return values, lines
    
    def write(self, file, values, context=None):
        # first write back values in the order they were read
        lines = context or []
        for line, iskey in lines:
            if iskey:
                key, line = line
                if key in values:
                    line = '{}: {}\n'.format(key, values[key])
                    del values[key]
            file.write(line)
        
        # now write remaining (ie. new) values
        for key, value in values.items():
            line = '{}: {}\n'.format(key, value)
            file.write(line)

class IniFormat(Format):
    name = 'ini'
    _rx_section_header = re.compile('\[(.*)\]')
    
    def read(self, file):
        section = None
        values = {}
        lines = []
        for i, orgline in enumerate(file, 1):
            line = orgline.strip()
            if not line or line.startswith('#'):
                # blank or comment line
                lines.append((orgline, False, False))
                continue
            else:
                match = IniFormat._rx_section_header.match(line)
                if match:
                    section = match.group(1)
                    if section.lower() == 'default':
                        section = ''
                    lines.append(((section, orgline), False, True))
                    continue
            
            if section is None:
                self._read_error(file, i, line)
            
            # get the value
            try:
                key, value = line.split('=', 1)
            except ValueError:
                self._read_error(file, i, line)
                continue
            
            key = key.strip()
            if section:
                key = self.config._make_key(section, key)
                key = self.config._keystr(key)
            values[key] = value.strip()
            
            # context
            if (section == '' and key in self.config and
                self.config.has_children(key)):
                # key no longer belongs to the defaults so skip
                continue
            lines.append(((key, orgline), True, False))
        
        return values, lines
    
    def write(self, file, values, context=None):
        stripbase = lambda k: self.config._keystr(self.config._make_key(k)[1:])
        
        # sort values by section
        dict_type = self.config._dict_type
        sections = dict_type()
        sep = self.config.sep
        for key, value in values.items():
            sec = key.partition(sep)
            section = sec[0] if sec[2] else ''
            if section.lower() == 'default':
                key = stripbase(key)
                section = ''
            elif section == '' and self.config.has_children(key):
                # fix key for section values
                section = key
            sections.setdefault(section, dict_type())[key] = value
        
        # first write back values in the order they were read
        section = None
        lines = context or []
        for i, (line, iskey, issection) in enumerate(lines):
            if issection:
                if section is not None:
                    # write remaining values from last section
                    sec = sections.get(section)
                    if sec:
                        for key, value in sec.items():
                            if section:
                                key = stripbase(key)
                            file.write('{} = {}\n'.format(key, value))
                        del sections[section]
                        file.write('\n')
                # new section
                section, line = line
                if section.lower() == 'default':
                    section = ''
                # this will continue unless we find a value
                # if there is no value, skip this section
                try:
                    j = 1
                    while not lines[i+j][2]:
                        if lines[i+j][1]:
                            break
                        j += 1
                    else:
                        continue
                except IndexError:
                    continue
            elif iskey:
                key, line = line
                sec = sections.get(section)
                if sec and key in sec:
                    wkey = key
                    if section:
                        wkey = stripbase(key)
                    line = '{} = {}\n'.format(wkey, values[key])
                    del sec[key]
                    if not sec:
                        del sections[section]
            file.write(line)
        
        # write remaining values
        if sections:
            last = section
            end = list(sections.keys())[-1]
            for section, values in sections.items():
                if section != last:
                    file.write('[{}]\n'.format(section or 'DEFAULT'))
                for key, value in values.items():
                    if section:
                        key = stripbase(key)
                    line = '{} = {}\n'.format(key, value)
                    file.write(line)
                if section != end:
                    file.write('\n')

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
        #: An adapter to fallback to when no other adapter is found.
        self.adapt_fallback = None
        #: An converter to fallback to when no other converter is found.
        self.convert_fallback = None
        
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
        
        if isinstance(type, tuple):
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
            err = "no adapter registered for '{}'"
            raise NotRegisteredError(err.format(type))
    
    def convert(self, value, type):
        """Convert a *value* to the given *type* (string to type)."""
        if isinstance(type, tuple):
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
            err = "no converter registered for '{}'"
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
        Values passed into :meth:`~fig.Coercer.adapt` or
        :meth:`~fig.Coercer.convert` for *type* will have to be one of the
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
