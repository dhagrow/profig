"""
A simple-to-use configuration management library.

    import config
    cfg = config.Config()
    cfg['server.host'] = '8.8.8.8'
    cfg['server.port'] = 8181
    cfg.sync()

"""

from __future__ import print_function

import io
import os
import re
import sys
import errno
import itertools
import collections

__author__  = 'Miguel Turner'
__version__ = '0.2.0'

__all__ = [
    'Config',
    'ConfigFormat', 'JsonFormat', 'IniFormat', 'PickleFormat',
    'ConfigError',
    'Coercer', 'CoerceError',
    ]

# the name *type* is used often so give type() an alias rather than use *typ*
_type = type

## Config ##

class SectionMixin(collections.MutableMapping):
    """Provides common methods to subclasses.

    The following attributes are required on subclasses of this mixin:
    
    _root
    _children
    """
    
    @property
    def root(self):
        return self._root
    
    def init(self, key, default, type=None):
        """Initializes a key to the given default value. If *type* is not
        provided, the type of the default value will be used."""
        section = self._create_section(key)
        section._value = NoValue
        section._cache = NoValue
        section._type = type or default.__class__
        section._has_type = True
        section.default = default
    
    def get(self, key, default=None, type=None):
        """Return the value for key if key is in the dictionary,
        else default. If *default* is not given, it defaults to
        `None`, so that this method never raises an
        :exc:`InvalidSectionError`. If *type* is provided,
        it will be used as the type to convert the value from text.
        This method does not use cached values."""
        try:
            section = self.section(key)
        except InvalidSectionError:
            return default
        if section._value is not NoValue:
            return section._convert(section._value, type)
        elif section._default is not NoValue:
            return section._convert(section._default, type)
        else:
            return default
    
    def __getitem__(self, key):
        return self.section(key).value
    
    def __setitem__(self, key, value):
        self._create_section(key).value = value
    
    def __delitem__(self, key):
        section = self.section(key)
        del section._parent._children[section.name]
    
    def __len__(self):
        return len(list(iter(self)))
    
    def __iter__(self):
        sep = self._root.sep
        for child in self._children.values():
            for key in child:
                if key:
                    yield sep.join([child._name, key])
                else:
                    yield child._name
    
    def asdict(self, flat=False, recurse=True, convert=False, include=None, exclude=None):
        if not self._children:
            return self._root._dict_type()
        if flat:
            sections = ((k, self.section(k)) for k in self)
            d = {k: (s.value if convert else s.strvalue) for k, s in sections}
            return self._root._dict_type(d)
        d = self._root._dict_type()
        for section in self.children():
            if section._should_include(include, exclude):
                d.update(section.asdict(
                    convert=convert, include=include, exclude=exclude))
        return d

    def section(self, key):
        """Returns a section object for *key*.
        If there is no existing section for *key*, and
        :exc:`InvalidSectionError` is thrown."""
        
        if not key:
            raise InvalidSectionError(key)
        
        config = self
        for name in self._make_key(key):
            if not name:
                # skip empty fields
                continue
            try:
                config = config._children[name]
            except KeyError:
                raise InvalidSectionError(key)
        return config
    
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
    
    def _create_section(self, key):
        if not key:
            raise InvalidSectionError(key)
        
        config = self
        for name in self._make_key(key):
            if not name:
                # skip empty fields
                continue
            try:
                config = config._children[name]
            except KeyError:
                config = ConfigSection(name, config)
        return config
    
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
                err = "invalid value for key: '{0}'"
                raise TypeError(err.format(p))
        return tuple(key)

class Config(SectionMixin):
    """Configuration Root object"""
    
    def __init__(self, *sources, format=None, dict_type=None):
        self._root = self
        self._key = None
        
        self._coercer = Coercer()
        self._dict_type = dict_type or collections.OrderedDict
        self._children = self._dict_type()

        self.sources = self._process_sources(sources)
        self.format = (format or ConfigFormat)(self)
        
        self.sep = '.'
        self.cache_values = True
        self.coerce_values = True
        self.interpolate_values = True
    
    def sync(self, *sources, format=None, include=None, exclude=None):
        """Writes changes to sources and reloads any external changes
        from sources.

        If *source* is provided, syncs only that source. Otherwise,
        syncs the sources in `self.sources`.

        *include* or *exclude* can be used to filter the keys that
        are written."""
        
        sources = self._process_sources(sources) if sources else self.sources
        if not sources:
            raise NoSourcesError()
        
        # if caching, adapt cached values
        if self.cache_values:
            for child in self.children(recurse=True):
                child._adapt_cache()
        
        # remove redundant entries
        def fix_clude(clude):
            clude = set(clude or [])
            if len(clude) < 2:
                return clude
            result = set()
            rejected = set()
            # get a set of unique pairs
            perms = set(frozenset(i) for i in itertools.permutations(clude, 2))
            for x, y in perms:
                result |= set([x, y])
                if x.startswith(y):
                    rejected.add(y)
                elif y.startswith(x):
                    rejected.add(x)
            return result - rejected
        
        include = fix_clude(include)
        exclude = fix_clude(exclude)
        
        # sync
        format = format(self) if format else self.format
        format.sync(sources, include, exclude)
    
    def _keystr(self, key):
        return self.sep.join(key)
    
    def _process_sources(self, sources):
        """Process user-entered paths and return absolute paths.
        
        If a source is not a string, assume it is a file object and return it.
        If a filename (has extension) or path is entered, return it.
        Otherwise, consider the source a base name and generate an
        OS-specific set of paths.
        """
        result = []
        for source in sources:
            if not isinstance(source, str):
                result.append(source)
                continue
            elif os.path.isabs(source) or '.' in source:
                result.append(source)
            else:
                fname = os.extsep.join([source, self.format.extension])
                scopes = ('script', 'user')
                result.extend(get_source(fname, scope) for scope in scopes)
        return result
    
    def _dump(self, indent=2): # pragma: no cover
        for section in sorted(self.children(recurse=True)):
            spaces = ' ' * ((len(section._key) - 1) * indent)
            print(spaces, repr(section), sep='')
    
    def __repr__(self):
        s = [self.__class__.__name__, '(']
        if self.sources:
            s.append('sources={}'.format(self._sources))
        s.append(')')
        return ''.join(s)

class ConfigSection(SectionMixin):
    """Configuration Section object"""
    
    _rx_can_interpolate = re.compile(r'{![^!]')
    
    def __init__(self, key, parent):
        self._name = key
        self._value = NoValue
        self._cache = NoValue
        self._default = NoValue
        self._type = None
        self._has_type = False
        self._dirty = False
        self._parent = parent
        
        self._root = parent._root
        self._key = self._make_key(parent._key, key)
        parent._children[self._name] = self
        
        self._children = self._root._dict_type()
    
    ## general properties ##
    
    @property
    def parent(self):
        """The section's parent or :keyword:`None`. Read-only."""
        return self._parent
    
    @property
    def key(self):
        """The section's key. Read-only."""
        return self._root._keystr(self._key)
    
    @property
    def name(self):
        """The section's name. Read-only."""
        return self._name
    
    @property
    def value(self):
        """The section's value."""
        if self._cache is not NoValue:
            return self._cache
        elif self._value is not NoValue:
            value = self._convert(self._value)
            if self._should_cache(value, self._value):
                self._cache = value
            return value
        else:
            return self.default
    
    @value.setter
    def value(self, value):
        strvalue = self._adapt(value)
        if strvalue != self._value:
            self._value = strvalue
            if self._should_cache(value, self._value):
                self._cache = value
            self._dirty = True
    
    @property
    def strvalue(self):
        """The section's unprocessed string value."""
        if self._value is not NoValue:
            return self._value
        else:
            return self.strdefault
    
    @strvalue.setter
    def strvalue(self, value):
        if value != self._value:
            self._value = value
            if self._cache is not NoValue:
                self._cache = NoValue
            self._dirty = True
    
    @property
    def default(self):
        """The section's default value."""
        if self._default is not NoValue:
            if self._value is NoValue and self._cache is not NoValue:
                # only use cache if self._value hasn't been set
                return self._cache
            else:
                value = self._convert(self._default)
                if (self._should_cache(value, self._default)
                    and self._value is NoValue):
                    # only set cache if self._value hasn't been set
                    self._cache = value
                return value
        else:
            raise InvalidSectionError(self.key)
    
    @default.setter
    def default(self, default):
        self._default = self._adapt(default)
        if (self._should_cache(default, self._default)
            and self._value is NoValue):
            # only set cache if self._value hasn't been set
            self._cache = default
    
    @property
    def strdefault(self):
        """The section's unprocessed default string value."""
        if self._default is not NoValue:
            return self._default
        else:
            raise InvalidSectionError(self.key)
    
    @strdefault.setter
    def strdefault(self, default):
        self._default = default
        # only clear cache if self._value hasn't been set
        if self._cache is not NoValue and self._value is NoValue:
            self._cache = NoValue
    
    @property
    def type(self):
        """The type used for coercing the value for this section.
        Read only."""
        return self._type
    
    @property
    def valid(self):
        """:keyword:`True` if this section has a valid value. Read-only."""
        return self._value is not NoValue or self._default is not NoValue
    
    def __lt__(self, other):
        if not isinstance(other, ConfigSection):
            return NotImplemented
        return self._key < other._key
    
    def __str__(self):
        return str(dict(self))
    
    def __repr__(self):
        return "{}('{}', {!r}, default={!r})".format(
            self.__class__.__name__, self.key, self._value, self._default)
    
    def __iter__(self):
        if self.valid:
            # an empty key so the section can find itself
            yield ''
        for key in super().__iter__():
            yield key
    
    def section(self, key):
        if not key:
            return self
        return super().section(key)
    
    def asdict(self, flat=False, recurse=True, convert=False, include=None, exclude=None):
        if not flat and not (self._children and recurse):
            d = {self.name: self.value if convert else self.strvalue}
            return self._root._dict_type(d)
        d = super().asdict(flat, recurse, convert, include, exclude)
        if self._value is not NoValue or self._default is not NoValue:
            d[''] = self.value if convert else self.strvalue
        return {self.name: d}
    
    def stritems(self):
        """Returns a (key, value) iterator over the unprocessed
        string values of this section."""
        for key in self:
            yield (key, self.section(key).strvalue)

    def sync(self, source=None, format=None, include=None, exclude=None):
        include = set(include or ())
        exclude = set(exclude or ())
        
        # adjust for subsections
        sep = self.sep
        for clude in (include, exclude):
            for c in clude.copy():
                clude.remove(c)
                clude.add(sep.join([self.key, c]))
        # for subsections, use self as an include filter
        include.add(self.key)

        self._root.sync(source, format, include, exclude)
    
    def reset(self, recurse=True):
        """Resets this section to it's default value, leaving it
        in the same state as after a call to :meth:`ConfigSection.init`.
        If *recurse* is :keyword:`True`, does the same to all the
        section's children."""
        def reset(s):
            if s._value is not NoValue:
                s._value = NoValue
                s._cache = NoValue
                s._dirty = True
                if s._default is NoValue:
                    s._type = None
        
        reset(self)
        if recurse:
            for child in self.children(recurse):
                reset(child)
    
    def adapt(self, value, type):
        return self._root._coercer.adapt(value, type)
    
    def convert(self, value, type):
        return self._root._coercer.convert(value, type)
    
    def interpolate(self, key, value, values):
        agraph = AcyclicGraph()
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
                        except CycleError:
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
            section._cache = NoValue
    
    def _adapt(self, value):
        if self._root.coerce_values:
            if not self._has_type:
                self._type = value.__class__
            return self.adapt(value, self._type)
        else:
            return value
    
    def _convert(self, value, type=None):
        if self._root.interpolate_values:
            # get a dict of the text values
            values = dict(self.stritems())
            value = self.interpolate(self.key, value, values)
        if self._root.coerce_values:
            return self.convert(value, type or self._type)
        else:
            return value
    
    def _adapt_cache(self):
        if self._cache is not NoValue:
            strvalue = self._adapt(self._cache)
            if strvalue != self.strvalue:
                self.strvalue = strvalue
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
            ematch = matchroot(exclude)
            return imatch > ematch
        elif exclude:
            ematch = matchroot(exclude)
            return not ematch
        else:
            return True
    
    def _should_cache(self, value, strvalue):
        # don't cache values that can be interpolated
        # also no point in caching a string
        return (self._root.cache_values and not isinstance(value, str)
            and not self._rx_can_interpolate.search(strvalue))
    
    def _dump(self, indent=2): # pragma: no cover
        rootlen = len(self._key)
        for section in sorted(self.children(recurse=True)):
            spaces = ' ' * ((len(section._key) - rootlen) * indent - 1)
            print(spaces, repr(section))

## Config Formats ##

class BaseFormat(object):
    extension = ''
    
    def __init__(self, config):
        self.config = config
        
        self.ensure_dirs = 0o744
        self.read_errors = 'error'
        self.write_errors = 'error'
    
    def sync(self, sources, include, exclude):
        """Performs a sync on *sources* with the values in a
        :class:`ConfigSection` instance. *include* and *exclude* must be
        lists of keys."""
        
        # read unchanged values from sources
        for source in reversed(sources):
            file = self._open(source)
            if file:
                # read file
                try:
                    values = self.read(file)
                except IOError:
                    # XXX: there should be a way of indicating that there
                    # was an error without causing the sync to fail for
                    # other sources
                    continue
                finally:
                    # only close files that were opened from the filesystem
                    if isinstance(source, str):
                        file.close()
                
                # process values
                for key, value in values.items():
                    section = config.root._create_section(key)
                    if not section._dirty:
                        section.strvalue = value
        
        values = self.filter_values(include, exclude)
        
        # write changed values to the first source
        source = sources[0]
        file = self._open(source, 'w')
        try:
            self.write(file, values)
        finally:
            # only close files that were opened from the filesystem
            if isinstance(source, str):
                file.close()
            else:
                file.flush()
        
        # clean values
        self.config.set_dirty(values.keys(), False)
    
    def filter_values(self, include, exclude):
        """
        Returns section values to be passed to :meth:`BaseFormat.write`.
        Also returns a list of keys that should have their dirty flags
        cleared after a successful write.
        """
        return self.config.asdict(flat=True, include=include, exclude=exclude)
    
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
        """Returns a file object.
        
        If *source* is a file object, returns *source*. If *mode* is 'w',
        The file object will be truncated.
        This method assumes either read or write/append access, but not both.
        """
        if isinstance(source, str):
            if self.ensure_dirs is not None and 'w' in mode:
                # ensure the path exists if any writing is to be done
                ensure_dirs(os.path.dirname(source), self.ensure_dirs)
            elif 'r' in mode and not os.path.exists(source):
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
    
    def sync(self, sources, include, exclude):
        self._source0 = True # False after the first pass through read
        self._lines = [] # line order for first source
        super().sync(sources, include, exclude)
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

class JsonFormat(BaseFormat):
    extension = 'json'
    
    def __init__(self, config):
        import json
        
        super().__init__(config)
        
        self._load = json.load
        self._dump = json.dump
    
    def filter_values(self, include, exclude):
        return self.config.asdict(flat=False, include=include, exclude=exclude)
    
    def read(self, file):
        try:
            return self._load(file)
        except ValueError:
            # file is empty, or invalid json
            return {}
    
    def write(self, file, values):
        if values:
            self._dump(values, file)
        else:
            file.write('')

class IniFormat(BaseFormat):
    extension = 'ini'
    _rx_section_header = re.compile('\[(.*)\]')
    
    def sync(self, sources, include, exclude):
        self._source0 = True # False after the first pass through read
        self._lines = [] # line order for first source
        super().sync(sources, include, exclude)
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
                key = self.config._make_key(section, key)
                key = self.config._keystr(key)
            values[key] = value.strip()
            if self._source0:
                if (section == '' and key in self.config and
                    self.config.has_children(key)):
                    # key no longer belongs to the defaults so skip
                    continue
                self._lines.append(((key, orgline), True, False))
        
        if self._source0:
            self._source0 = False
        return values
    
    def write(self, file, values):
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
    
    def __init__(self, protocol=None):
        import pickle
        self._load = pickle.load
        self._dump = pickle.dump
        self.protocol = protocol or pickle.HIGHEST_PROTOCOL
    
    def read(self, file):
        try:
            return self._load(file)
        except EOFError:
            # file is empty
            return {}
    
    def write(self, file, values):
        if values:
            self._dump(values, file, self.protocol)
        else:
            file.write(b'')
    
    def open(self, source, mode='r', *args):
        return open(source, mode + 'b', *args)

## Config Errors ##

class ConfigError(Exception):
    """Base exception class for all exceptions raised."""

class InvalidSectionError(KeyError, ConfigError):
    """Raised when a given section has never been given a value"""

class InterpolationError(ConfigError):
    """Raised when a value cannot be interpolated"""

class InterpolationCycleError(InterpolationError):
    """Raised when an interpolation would result in an infinite cycle"""

class SyncError(ConfigError):
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

class NoSourcesError(ConfigError):
    """Raised when there are no sources for a config object"""

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

## Acyclic ##

class CycleError(ConfigError):
    pass

class AcyclicGraph:
    """An acyclic graph.
    
    Raises a CycleError if any added edge would
    create a cycle.
    """
    def __init__(self):
        self._g = collections.defaultdict(set)
    
    def add_edge(self, u, v):
        if u in self._g[v]:
            raise CycleError
        
        self._g[u].add(v)
        self._g[u] |= self._g[v]
        
        for x in self._g.values():
            if u in x:
                x |= self._g[u]
    
    def __repr__(self):
        return repr(self._g)

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
            err = "no adapter registered for '{0}'"
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
