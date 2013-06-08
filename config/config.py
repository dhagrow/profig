"""config

Store an application's configuration.
"""

import io
import os
import re
import sys
import errno
import pickle
import itertools
import collections

# don't require coerce
try:
    from . import coerce
except ImportError:
    coerce = None
else:
    ## override boolean coercers ##
    _boolean_states = {'1': True, 'yes': True, 'true': True, 'on': True,
        '0': False, 'no': False, 'false': False, 'off': False}
    coerce.register_adapter(bool, lambda x: 'true' if x else 'false')
    coerce.register_converter(bool, lambda x: _boolean_states[x.lower()])

def canonpath(path):
    p = os.path.normcase(
        os.path.realpath(os.path.expanduser(os.path.expandvars(path))))
    if os.path.isdir(p) and p[-1] != os.pathsep:
        p += '/'
    return p

class InvalidSectionError(KeyError):
    """Raised when a given section has never been given a value"""

class InterpolationError(Exception):
    """Raised when a value cannot be interpolated"""

class InterpolationCycleError(InterpolationError):
    """Raised when an interpolation would result in an infinite cycle"""

class SyncError(Exception):
    """Base class for errors that can occur when syncing"""
    def __init__(self, filename=None, message=''):
        self.filename = filename
        self.message = message
    
    def __str__(self):
        if self.filename:
            err = ["error reading '{0}'".format(self.filename)]
            if self.message:
                err.extend([': ', self.message])
            return ''.join(err)
        else:
            return self.message

class ReadError(SyncError):
    """Raised when a value could not be read from a source"""
    def __init__(self, filename=None, lineno=None, text='', message=''):
        super().__init__(filename, message)
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
    """Raised when a value could not be written to a source"""

class NoSourcesError(Exception):
    """Raised when there are no sources for a config object"""

class ConfigSection(collections.MutableMapping):
    _rx_can_interpolate = re.compile(r'{![^!]')
    
    def __init__(self, key, parent, sync_format=None, **kwargs):
        self._name = key
        self._value = None
        self._cache = None
        self._default = None
        self._type = None
        self._has_value = False
        self._has_cache = False
        self._has_default = False
        self._has_type = False
        self._dirty = False
        self._parent = parent
        
        if parent is not None:
            self._root = parent._root
            self._key = self._make_key(parent._key, key)
            parent._children[self._name] = self
        else:
            self._root = self
            self._sep = kwargs.pop('sep', '.')
            self._key = self._make_key(key)
            
            # root-only properties
            self._format = sync_format
            self._sources = kwargs.pop('sources', None) or []
            self._write_unset_values = kwargs.pop('write_unset_values', True)
            self._cache_values = kwargs.pop('cache_values', True)
            self._coerce_values = kwargs.pop('coerce_values', True)
            self._interpolate_values = kwargs.pop('interpolate_values', True)
            self._dict_type = kwargs.pop('dict_type', collections.OrderedDict)
            self._get_methods = set()
        
        self._children = self.dict_type()
            
        if kwargs:
            err = "__init__() got an unexpected keyword argument: '{0}'"
            raise TypeError(err.format(kwargs.popitem()[0]))
    
    ## root-only properties ##
    
    @property
    def sep(self):
        """The separator to use for keys."""
        return self._root._sep
    
    @sep.setter
    def sep(self, sep):
        self._root._sep = sep
    
    @property
    def sources(self):
        """The sources to use for syncing all sections."""
        return self._root._sources
    
    @sources.setter
    def sources(self, sources):
        self._root._sources = sources
    
    @property
    def format(self):
        """The file format to use when syncing."""
        return self._root._format
    
    @format.setter
    def format(self, format):
        self._root._format = format
    
    @property
    def write_unset_values(self):
        """bool indicating whether or not to write unset values on sync."""
        return self._root._write_unset_values
    
    @write_unset_values.setter
    def write_unset_values(self, write):
        self._root._write_unset_values = write
    
    @property
    def dict_type(self):
        """The type of dict to use to store values."""
        return self._root._dict_type
    
    @dict_type.setter
    def dict_type(self, type):
        self._root._dict_type = type
    
    @property
    def cache_values(self):
        """If :keyword:`True`, converted values will be kept to avoid
        having to convert on each access."""
        return self._root._cache_values
    
    @cache_values.setter
    def cache_values(self, cache):
        self._root._cache_values = cache
        if not cache:
            self._root.clear_cache(recurse=True)
    
    @property
    def coerce_values(self):
        """If :keyword:`True`, values will be automatically converted
        and adapted."""
        return self._root._coerce_values
    
    @coerce_values.setter
    def coerce_values(self, coerce):
        self._root._coerce_values = coerce
    
    @property
    def interpolate_values(self):
        """If :keyword:`True`, values will be interpolated on access."""
        return self._root._interpolate_values
    
    @interpolate_values.setter
    def interpolate_values(self, interpolate):
        self._root._interpolate_values = interpolate
    
    ## general properties ##
    
    @property
    def root(self):
        """The root section object. Read-only."""
        return self._root
    
    @property
    def parent(self):
        """The section's parent or :keyword:`None`. Read-only."""
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
    def value(self):
        """The section's value."""
        if self._has_cache:
            return self._cache
        elif self._has_value:
            value = self._convert(self._value)
            if self._should_cache(value, self._value):
                self._cache = value
                self._has_cache = True
            return value
        else:
            return self.default
    
    @value.setter
    def value(self, value):
        strvalue = self._adapt(value)
        if strvalue != self._value:
            self._value = strvalue
            self._has_value = True
            if self._should_cache(value, self._value):
                self._cache = value
                self._has_cache = True
            self._dirty = True
    
    @property
    def strvalue(self):
        """The section's unprocessed string value."""
        if self._has_value:
            return self._value
        else:
            return self.strdefault
    
    @strvalue.setter
    def strvalue(self, value):
        if value != self._value:
            self._value = value
            self._has_value = True
            if self._has_cache:
                self._cache = None
                self._has_cache = False
            self._dirty = True
    
    @property
    def default(self):
        """The section's default value."""
        if self._has_default:
            if not self._has_value and self._has_cache:
                # only use cache if self._value hasn't been set
                return self._cache
            else:
                value = self._convert(self._default)
                if (self._should_cache(value, self._default)
                    and not self._has_value):
                    # only set cache if self._value hasn't been set
                    self._cache = value
                    self._has_cache = True
                return value
        else:
            raise InvalidSectionError(self.key)
    
    @default.setter
    def default(self, default):
        self._default = self._adapt(default)
        self._has_default = True
        if (self._should_cache(default, self._default)
            and not self._has_value):
            # only set cache if self._value hasn't been set
            self._cache = default
            self._has_cache = True
    
    @property
    def strdefault(self):
        """The section's unprocessed default string value."""
        if self._has_default:
            return self._default
        else:
            raise InvalidSectionError(self.key)
    
    @strdefault.setter
    def strdefault(self, default):
        self._default = default
        self._has_default = True
        # only clear cache if self._value hasn't been set
        if self._has_cache and not self._has_value:
            self._cache = None
            self._has_cache = False
    
    @property
    def type(self):
        """The type used for coercing the value for this section.
        Read only."""
        return self._type
    
    @property
    def valid(self):
        """:keyword:`True` if this section has a valid value. Read-only."""
        return self._has_value or self._has_default
    
    @property
    def dirty(self):
        """:keyword:`True` if the value has changed since the last sync."""
        return self._dirty
    
    @dirty.setter
    def dirty(self, dirty):
        self._dirty = dirty
    
    def init(self, key, default, type=None):
        """Initializes a key to the given default value. If *type* is not
        provided, the type of the default value will be used."""
        section = self.section(key)
        section._value = None
        section._has_value = False
        section._cache = None
        section._has_cache = False
        section._type = type or default.__class__
        section._has_type = True
        section.default = default
    
    def get(self, key, default=None, type=None):
        """Return the value for key if key is in the dictionary,
        else default. If *default* is not given, it defaults to
        :keyword:`None`, so that this method never raises an
        :exception:`InvalidSectionError`. If *type* is provided,
        it will be used as the type to convert the value from text.
        This method does not use cached values."""
        try:
            section = self.section(key, build=False)
        except InvalidSectionError:
            return default
        if section._has_value:
            return section._convert(section._value, type)
        elif section._has_default:
            return section._convert(section._default, type)
        else:
            return default
    
    def __getitem__(self, key):
        return self.section(key, build=False).value
    
    def __setitem__(self, key, value):
        self.section(key).value = value
    
    def __delitem__(self, key):
        section = self.section(key, build=False)
        if section._parent:
            del section._parent._children[section.name]
        else:
            # can't just delete the root section
            section.reset()
            section._default = None
            section._has_default = False
            section._type = None
            section._has_type = False
    
    def __lt__(self, other):
        if not isinstance(other, ConfigSection):
            return NotImplemented
        return self._key < other._key
    
    def __str__(self):
        return str(self.dict_type(self))
    
    def __repr__(self):
        return "{0}(key={1}, value={2!r}, default={3!r})".format(
            self.__class__.__name__, self.key, self._value, self._default)
    
    def __len__(self):
        return len(list(iter(self)))
    
    def __iter__(self):
        if self.valid:
            # an empty key so the section can find itself
            yield ''
        sep = self._root._sep
        for child in self._children.values():
            for key in child:
                if key:
                    yield sep.join([child._name, key])
                else:
                    yield child._name
    
    def stritems(self):
        """Returns a (key, value) iterator over the unprocessed
        string values of this section."""
        for key in self:
            yield (key, self.section(key, build=False).strvalue)
    
    def children(self, recurse=False):
        """Returns the sections that are children to this section.
        If *recurse* is :keyword:`True`, returns grandchildren as well."""
        for child in self._children.values():
            yield child
            if recurse:
                for grand in child.children(recurse):
                    yield grand
    
    def has_children(self):
        return bool(self._children)
    
    def section(self, key, *, build=True):
        """Returns a section object for *key*"""
        config = self
        for name in self._make_key(key):
            if not name:
                # skip empty fields
                continue
            try:
                config = config._children[name]
            except KeyError:
                if build:
                    config = ConfigSection(name, config)
                else:
                    raise InvalidSectionError(key)
        return config
    
    def reset(self, recurse=True):
        """Resets this section to it's default value, leaving it
        in the same state as after a call to :meth:`ConfigSection.init`.
        If *recurse* is :keyword:`True`, does the same to all the
        section's children."""
        def reset(s):
            if s._has_value:
                s._value = None
                s._has_value = False
                s._cache = None
                s._has_cache = False
                s._dirty = True
                if not s._has_default:
                    s._type = None
        
        reset(self)
        if recurse:
            for child in self.children(recurse):
                reset(child)
    
    def is_default(self, key):
        section = self.section(key)
        return not section._has_value
    
    def set_dirty(self, keys, dirty=True):
        """Sets the :attr:`dirty` flag for *keys*, which, if
        :keyword:`True`, will ensure that each key's value is synced.
        *keys* can be a single key or a sequence of keys."""
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            self.section(key, build=False)._dirty = dirty
    
    def get_setter(self, key):
        """Returns a function that can be used to set the value for *key*."""
        return lambda x: setattr(self.section(key, build=False), 'value', x)
    
    def sync(self, source=None, include=None, exclude=None):
        """Writes changes to sources and reloads any external changes
        from sources. If *source* is provided, sync only that source.
        Otherwise, sync the sources in self.sources."""
        
        sources = [source] if source else self.sources
        if not sources:
            raise NoSourcesError()
        
        # update values from registered methods
        rootlen = len(self.key)
        for key, get in self._root._get_methods:
            # adjust for subsections
            key = key[rootlen:]
            section = self.section(key, build=False)
            section.value = get()
        
        # if caching, adapt cached values
        if self.cache_values:
            self._adapt_cache()
            for child in self.children(recurse=True):
                child._adapt_cache()
        
        include = set(include or ())
        exclude = set(exclude or ())
        if not self.is_root():
            # adjust for subsections
            for clude in (include, exclude):
                for c in clude.copy():
                    clude.remove(c)
                    clude.add(self.sep.join([self.key, c]))
            # for subsections, use self as an include filter
            include.add(self.key)
        # remove redundant entries
        include = self._fix_include(include)
        exclude = self._fix_include(exclude)
        
        # sync
        self.format.sync(sources, self, include, exclude)
    
    def adapt(self, value, type):
        return coerce.adapt(value, type) if coerce else value
    
    def convert(self, value, type):
        return coerce.convert(value, type) if coerce else value
    
    def interpolate(self, key, value, values):
        agraph = _AcyclicGraph()
        in_field = False
        field_map = {}
        
        while self._rx_can_interpolate.search(value):
            field = []
            result = []
            
            # escape user str.format brackets and grab keys
            for i, c in enumerate(value):
                if i in field_map:
                    key = field_map.pop(i)
                
                if c == '{':
                    if in_field:
                        raise InterpolationError("keys cannot contain '{'")
                    elif value[i+1] == '!' and value[i+2] != '!':
                        # we're in a field if there's just one '!'
                        in_field = True
                        # we add '0[' so str.format can accept
                        # dotted dict keys
                        field.append(c + '0[')
                    else:
                        result.append(c)
                
                elif c == '}':
                    if in_field:
                        in_field = False
                        # again, ']' added for str.format
                        field.append(']' + c)
                        
                        newkey = ''.join(field[1:-1])
                        try:
                            agraph.add_edge(key, newkey)
                        except _CycleError:
                            raise InterpolationCycleError()
                        
                        index = sum(len(x) for x in result) - 1
                        field_map[index] = newkey
                        
                        # here we do the actual substitution
                        try:
                            field = ''.join(field).format(values)
                        except KeyError as exc:
                            err = "invalid key: {0}".format(exc)
                            raise InterpolationError(err)
                        result.append(field)
                        field = []
                    else:
                        result.append(c)
                
                elif in_field:
                    if c == '!':
                        continue
                    field.append(c)
                
                else:
                    result.append(c)
            
            if in_field:
                raise InterpolationError("missing terminating '}'")
            
            value = ''.join(result)
        
        return value
    
    def clear_cache(self, recurse=False):
        """Clears cached values for this section. If *recurse* is
        :keyword:`True`, clears the cache for child sections as well."""
        for section in self.children(recurse):
            section._cache = None
            section._has_cache = None
    
    def is_root(self):
        """Returns :keyword:`True` if this is the root section"""
        return self is self._root
    
    def _make_key(self, *path):
        key = []
        for p in path:
            if p and isinstance(p, str):
                key.extend(p.split(self.sep))
            elif isinstance(p, collections.Sequence):
                key.extend(p)
            elif p is None:
                pass
            else:
                err = "invalid value for key: '{0}'"
                raise TypeError(err.format(p))
        return tuple(key)
    
    def _keystr(self, key):
        return self.sep.join(key)
    
    def _adapt(self, value):
        if self.coerce_values:
            if not self._has_type:
                self._type = value.__class__
            return self.adapt(value, self._type)
        else:
            return value
    
    def _convert(self, value, type=None):
        if self.interpolate_values:
            # get a dict of the text values
            values = dict(self._root.stritems())
            value = self.interpolate(self.key, value, values)
        if self.coerce_values:
            return self.convert(value, type or self._type)
        else:
            return value
    
    def _matchroot(self, roots):
        """Returns the length of the longest matching root."""
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
    
    def _should_include(self, include, exclude):
        # first check if the section itself should be included
        if self._value == self._default and not self.write_unset_values:
            return False
        
        # now filter
        if include:
            imatch = self._matchroot(include)
            ematch = self._matchroot(exclude)
            return imatch > ematch
        elif exclude:
            ematch = self._matchroot(exclude)
            return not ematch
        else:
            return True
    
    def _fix_include(self, include):
        if len(include) < 2:
            return include
        result = set()
        rejected = set()
        # get a set of unique pairs
        perms = set(frozenset(i) for i in itertools.permutations(include, 2))
        for x, y in perms:
            result |= set([x, y])
            if x.startswith(y):
                rejected.add(y)
            elif y.startswith(x):
                rejected.add(x)
        return result - rejected
    
    def _should_cache(self, value, strvalue):
        # don't cache values that can be interpolated
        # also no point in caching a string
        return (self.cache_values and not isinstance(value, str)
            and not self._rx_can_interpolate.search(strvalue))
    
    def _adapt_cache(self):
        if self._has_cache:
            strvalue = self._adapt(self._cache)
            if strvalue != self.strvalue:
                self.strvalue = strvalue
                self._dirty = True
    
    def _dump(self, indent=2): # pragma: no cover
        rootlen = len(self._key)
        for section in sorted(self.children(recurse=True)):
            spaces = ' ' * ((len(section._key) - rootlen) * indent - 1)
            print(spaces, repr(section))

def get_source(filename, scope='script'):
    """Returns a path for *filename* in the given *scope*.
    *scope* must be one of the following:
    
    * script - the running script's directory
    * user - the current user's settings directory
    """
    # adapted from pyglet
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

class Config(ConfigSection):
    """Root Config object"""
    
    def __init__(self, sources=None, **kwargs):
        for key in ['key', 'parent']:
            if key in kwargs:
                err = "__init__() got an unexpected keyword argument '{}'"
                raise TypeError(err.format(key))
        
        sync_format = kwargs.pop('format', None)
        if not sync_format:
            sync_format = ConfigFormat()
        
        if isinstance(sources, str):
            if os.path.isabs(sources) or '.' in sources:
                sources = [sources]
            else:
                fname = os.extsep.join([sources, sync_format.extension])
                scopes = ('script', 'user')
                sources = [get_source(fname, scope) for scope in scopes]
        kwargs['sources'] = [canonpath(s) for s in sources]
        
        super().__init__('', None, sync_format, **kwargs)

class BaseFormat(object):
    extension = ''
    
    def __init__(self, *, read_errors='error', write_errors='error'):
        self.read_errors = read_errors
        self.write_errors = write_errors
        # only valid during sync
        self._config = None
    
    @property
    def read_errors(self):
        """The action to take when there is an error when
        reading a config file. Must be one of 'exception',
        'error', or 'ignore'."""
        return self._read_errors
    
    @read_errors.setter
    def read_errors(self, errors):
        if not errors in ('exception', 'error', 'ignore'):
            err = "value must be 'exception', 'error', or 'ignore'"
            raise ValueError(err)
        self._read_errors = errors
    
    @property
    def write_errors(self):
        """The action to take when there is an error when
        writing to a config file. Must be one of 'exception',
        'error', or 'ignore'."""
        return self._write_errors
    
    @write_errors.setter
    def write_errors(self, errors):
        if not errors in ('exception', 'error', 'ignore'):
            err = "value must be 'exception', 'error', or 'ignore'"
            raise ValueError(err)
        self._write_errors = errors
    
    def sync(self, sources, config, include, exclude):
        """Performs a sync on *sources* with the values in *config*,
        which is a :class:`ConfigSection` instance. *include* and
        *exclude* must be lists of keys."""
        
        # only valid during sync
        self._config = config.root
        
        # read unchanged values from sources
        for source in sources:
            file = self._open(source)
            if file:
                # read file
                try:
                    values = self.read(file)
                except IOError:
                    continue
                finally:
                    # only close files that were opened from the filesystem
                    if isinstance(source, str):
                        file.close()
                
                # process values
                for key, value in values.items():
                    section = config.root.section(key)
                    if not section._dirty:
                        section.strvalue = value
        
        # filter sections
        keys = [] # keys to clean after (diff from keys to write)
        values = config._root._dict_type()
        for key in config:
            section = config.section(key, build=False)
            if section._should_include(include, exclude):
                # use section.key so we get the full key
                values[section.key] = section.strvalue
                keys.append(key)
        
        # write changed values to the first source
        source = sources[0]
        file = self._open(source, 'w+')
        if file:
            try:
                self.write(file, values)
            finally:
                # only close files that were opened from the filesystem
                if isinstance(source, str):
                    file.close()
                else:
                    file.flush()
        
        # clean values
        config.set_dirty(keys, False)
        # clear sync config
        self._config = None
    
    def read(self, file): # pragma: no cover
        """Reads *file* and returns a dict. Must be implemented
        in a subclass."""
        raise NotImplementedError('abstract')
    
    def write(self, file, values): # pragma: no cover
        """Writes the dict *values* to file. Must be implemented
        in a subclass."""
        raise NotImplementedError('abstract')
    
    def open(self, source, mode='r', *args):
        """Opens a source. Arguments are the same as those accepted
        by :func:`io.open`."""
        return open(source, mode, *args)
    
    def _open(self, source, mode='r', *args):
        if isinstance(source, str):
            if not 'r' in mode or '+' in mode:
                # ensure the path exists if any writing is to be done
                _ensuredirs(os.path.dirname(source))
            elif not os.path.exists(source):
                # if reading and path doesn't exist
                return None
            
            return self.open(source, mode, *args)
        else:
            if 'w' in mode:
                source.seek(0)
                source.truncate()
            else:
                source.seek(0)
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

class ConfigFormat(BaseFormat):
    extension = 'cfg'
    
    def sync(self, sources, config, include, exclude):
        self._source0 = True # False after the first pass through read
        self._lines = [] # line order for first source
        super().sync(sources, config, include, exclude)
        del self._source0
        del self._lines
    
    def read(self, file):
        values = {}
        for i, orgline in enumerate(file, 1):
            line = orgline.strip()
            if not line or line.startswith('#'):
                # blank or comment line
                if self._source0:
                    self._lines.append((orgline, False))
                continue
            
            # get the value
            try:
                key, value = line.split(':', 1)
            except ValueError:
                self._read_error(file, i, line)
                continue
            
            key = key.strip()
            values[key] = value.strip()
            if self._source0:
                self._lines.append(((key, orgline), True))
        
        if self._source0:
            self._source0 = False
        return values
    
    def write(self, file, values):
        # first write back values in the order they were read
        for line, iskey in self._lines:
            if iskey:
                key, line = line
                if key in values:
                    line = '{0}: {1}\n'.format(key, values[key])
                    del values[key]
            file.write(line)
        
        # now write remaining (ie. new) values
        for key, value in values.items():
            line = '{0}: {1}\n'.format(key, value)
            file.write(line)

class IniFormat(BaseFormat):
    extension = 'ini'
    _rx_section_header = re.compile('\[(.*)\]')
    
    def sync(self, sources, config, include, exclude):
        self._source0 = True # False after the first pass through read
        self._lines = [] # line order for first source
        super().sync(sources, config, include, exclude)
        del self._source0
        del self._lines
    
    def read(self, file):
        section = None
        values = {}
        for i, orgline in enumerate(file, 1):
            line = orgline.strip()
            if not line or line.startswith('#'):
                # blank or comment line
                if self._source0:
                    self._lines.append((orgline, False, False))
                continue
            else:
                match = IniFormat._rx_section_header.match(line)
                if match:
                    section = match.group(1)
                    if section.lower() == 'default':
                        section = ''
                    if self._source0:
                        self._lines.append(((section, orgline), False, True))
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
                key = self._config._make_key(section, key)
                key = self._config._keystr(key)
            values[key] = value.strip()
            if self._source0:
                if (section == '' and key in self._config and
                    self._config.section(key, build=False).has_children()):
                    # key no longer belongs to the defaults so skip
                    continue
                self._lines.append(((key, orgline), True, False))
        
        if self._source0:
            self._source0 = False
        return values
    
    def write(self, file, values):
        stripbase = lambda k: self._config._keystr(self._config._make_key(k)[1:])
        
        # sort values by section
        dict_type = self._config.dict_type
        sections = dict_type()
        for key, value in values.items():
            sec = key.partition(self._config.sep)
            section = sec[0] if sec[2] else ''
            if section.lower() == 'default':
                key = stripbase(key)
                section = ''
            elif section == '' and self._config.section(key, build=False).has_children():
                # fix key for section values
                section = key
            sections.setdefault(section, dict_type())[key] = value
        
        # first write back values in the order they were read
        section = None
        for i, (line, iskey, issection) in enumerate(self._lines):
            if issection:
                if section is not None:
                    # write remaining values from last section
                    sec = sections.get(section)
                    if sec:
                        for key, value in sec.items():
                            if section:
                                key = stripbase(key)
                            file.write('{0} = {1}\n'.format(key, value))
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
                    while not self._lines[i+j][2]:
                        if self._lines[i+j][1]:
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
                    line = '{0} = {1}\n'.format(wkey, values[key])
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
                    file.write('[{0}]\n'.format(section or 'DEFAULT'))
                for key, value in values.items():
                    if section:
                        key = stripbase(key)
                    line = '{0} = {1}\n'.format(key, value)
                    file.write(line)
                if section != end:
                    file.write('\n')

class PickleFormat(BaseFormat):
    extension = 'pkl'
    
    def __init__(self, protocol=pickle.HIGHEST_PROTOCOL):
        self.protocol = protocol
    
    def read(self, file):
        try:
            return pickle.load(file)
        except EOFError:
            # file is empty
            return {}
    
    def write(self, file, values):
        if values:
            pickle.dump(values, file, self.protocol)
        else:
            file.write(b'')
    
    def open(self, source, mode='r', *args):
        return open(source, mode + 'b', *args)

def _ensuredirs(path, mode=0o777):
    """Like makedirs, but doesn't raise en exception if the dirs exist"""
    if path:
        try:
            os.makedirs(path, mode)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

class _CycleError(Exception):
    pass

class _AcyclicGraph:
    """An acyclic graph.
    
    Raises a CycleError if any added edge would
    create a cycle.
    """
    def __init__(self):
        self._g = collections.defaultdict(set)
    
    def add_edge(self, u, v):
        if u in self._g[v]:
            raise _CycleError
        
        self._g[u].add(v)
        self._g[u] |= self._g[v]
        
        for x in self._g.values():
            if u in x:
                x |= self._g[u]
    
    def __repr__(self):
        return repr(self._g)
