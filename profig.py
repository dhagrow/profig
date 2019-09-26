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
import inspect
import logging
import itertools
import collections
try:
    from collections import abc
except ImportError:
    import collections as abc

__author__  = 'Miguel Turner'
__version__ = '0.5.0'
__license__ = 'MIT'

__all__ = ['Config', 'ConfigError', 'Coercer', 'CoerceError',
    'INIFormat', 'JSONFormat' 'TOMLFormat', 'YAMLFormat', 'MessagePackFormat']

PY3 = sys.version_info.major >= 3
# use str for unicode data and bytes for binary data
if not PY3:
    str = unicode

WIN = os.name == 'nt'
if WIN:
    import ntpath
    try:
        import winreg
    except ImportError:
        import _winreg as winreg
    __all__.append('RegistryFormat')

# keep a reference to the type builtin to free up the name 'type'
_type = type

log = logging.getLogger('profig')

## Config ##

class ConfigSection(abc.MutableMapping):
    """
    Represents a group of configuration options.

    This class is not meant to be instantiated directly.
    """

    def __init__(self, name, parent):
        self._name = name
        self._value = NoValue
        self._default = NoValue
        self._type = None
        self._parent = parent
        self._dirty = False

        self.comment = None

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
        """Returns the root :class:`~profig.ConfigSection` object. Read-only."""
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
    def dirty(self):
        """`True` if this section's value has changed since the last write. Read-only."""
        return self._dirty

    @property
    def is_default(self):
        """`True` if this section has a default value and its current value
        is equal to the default value. Read-only."""
        return (self._value is NoValue and self._default is not NoValue)

    @property
    def has_children(self):
        """`True` if this section has child sections. Read-only."""
        return bool(self._children)

    ## methods ##

    def sync(self, *sources, **kwargs):
        """Reads from sources and writes any changes back to the first source.

        If *sources* are provided, syncs only those sources. Otherwise,
        syncs the sources in :attr:`~config.Config.sources`.

        *format* can be used to override the format used to read/write from
        the sources.
        """
        format = kwargs.pop('format', None)
        kwargs_check('sync', kwargs)

        sources, format = self._process_sources(sources, format)

        # sync
        context = self._read(sources, format)
        self._write(sources[0], format, context)

    def read(self, *sources, **kwargs):
        """
        Reads config values.

        If *sources* are provided, read only from those sources. Otherwise,
        write to the sources in :attr:`~config.Config.sources`. A format for
        *sources* can be set using *format*.
        """
        format = kwargs.pop('format', None)
        kwargs_check('read', kwargs)

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

        If a value is already set for the section at *key*, it will be
        coerced to *type*.

        If a *comment* is provided, it may be written out to the config
        file in a manner consistent with the active :class:`~profig.Format`.
        """
        section = self._create_section(key)
        section._type = type or _type(default)
        if section._value is not NoValue and _type(section._value) is not section._type:
            try:
                section.convert(section._value)
            except ConvertError as e:
                self._root._format._error(e, key)
                section.set_value(default)
        section.set_default(default)
        section.comment = comment

    def get(self, key, default=None):
        """If *key* exists, returns the value. Otherwise, returns *default*.

        If *default* is not given, it defaults to `None`, so that this
        method never raises an exception.
        """
        try:
            return self.section(key, create=False).value()
        except (InvalidSectionError, NoValueError):
            return default

    def __getitem__(self, key):
        return self.section(key, create=False).value()

    def __setitem__(self, key, value):
        section = self.section(key)
        if isinstance(value, abc.Mapping):
            section.update(value)
        else:
            section.set_value(value)

    def __delitem__(self, key):
        section = self.section(key, create=False)
        del section._parent._children[section.name]

    def __bool__(self):
        return self.valid or len(self) > 0
    __nonzero__ = __bool__

    def __len__(self):
        return len(self._children)

    def __iter__(self):
        if self.valid:
            # an empty key so the section can find itself
            yield ''
        sep = self._root.sep
        for child in self._children.values():
            for key in child:
                yield sep.join([child._name, key]) if key else child._name

    def __repr__(self): # pragma: no cover
        try:
            value = self.value()
        except NoValueError:
            value = NoValue
        return "{}('{}', value={!r}, keys={}, comment={!r})".format(
            self.__class__.__name__, self.key, value, list(self), self.comment)

    def as_dict(self, flat=False, dict_type=None):
        """Returns the configuration's keys and values as a dictionary.

        If *flat* is `True`, returns a single-depth dict with :samp:`.`
        delimited keys.

        If *dict_type* is not `None`, it should be the mapping class to use
        for the result. Otherwise, the *dict_type* set by
        :meth:`~config.Config.__init__` will be used.
        """
        dtype = dict_type or self._root._dict_type
        valid = self is not self._root and self.valid

        if flat:
            sections = (self.section(k) for k in self)
            return dtype((s._key or '', s.value()) for s in sections)

        d = dtype()
        if valid:
            d[''] = self.value()
        for section in self.sections():
            if section._children:
                d[section.name] = section.as_dict(dict_type=dict_type)
            else:
                d[section.name] = section.value()

        return d

    def section(self, key, create=None):
        """Returns a section object for *key*.

        *create* will default to `False` when in strict mode. Otherwise it
        defaults to `True`.

        If there is no existing section for *key*, and *create* is `False`, an
        :exc:`~profig.InvalidSectionError` is thrown.
        """
        create = (not self._root.strict) if create is None else create

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

    def sections(self, recurse=False, only_valid=False):
        """Returns the sections that are children to this section.

        If *recurse* is `True`, returns grandchildren as well.
        If *only_valid* is `True`, returns only valid sections.
        """
        for child in self._children.values():
            if not only_valid or child.valid:
                yield child
            if recurse:
                for grand in child.sections(recurse):
                    if not only_valid or grand.valid:
                        yield grand

    def reset(self, recurse=True, clean=True):
        """Resets this section to it's default value, leaving it
        in the same state as after a call to :meth:`ConfigSection.init`.

        If *recurse* is `True`, does the same to all the section's children.
        If *clean* is `True`, also clears the dirty flag on all sections.
        """
        if self is not self._root:
            self._reset(clean)
        if recurse:
            for k in self:
                self.section(k)._reset(clean)

    def value(self):
        """Get the section's value."""
        if self._value is not NoValue:
            return self._value
        return self.default()

    def set_value(self, value):
        """Set the section's value."""
        self._value = value
        self._dirty = True

    def default(self):
        """Get the section's default value."""
        if self._default is not NoValue:
            return self._default
        raise NoValueError(self.key)

    def set_default(self, value):
        """Set the section's default value."""
        self._default = value

    def adapt(self, encode=True):
        """value -> str"""
        if not self._root.coercer:
            return value
        value = self._root.coercer.adapt(self.value(), self._type)
        if encode and isinstance(value, str):
            value = value.encode(self._root.encoding)
        return value

    def convert(self, string, decode=True):
        """str -> value"""
        if self._root.coercer:
            type = self._type
            # if we are converting a byte-string and the type is not bytes,
            # then we need to decode it
            if decode and isinstance(string, bytes) and not (
                inspect.isclass(type) and issubclass(type, bytes)
                ):
                string = string.decode(self._root.encoding)
            value = self._root.coercer.convert(string, type)
        else:
            value = string
        self.set_value(value)

    ## utilities ##

    def _read(self, sources, format):
        context = None
        # True if at least one source read something
        one_source_read = False

        # read unchanged values from sources
        for i, source in enumerate(reversed(sources)):
            try:
                file = format.open(self._root, source)
            except IOError as e:
                log.debug('%s: %s', source, e)
                continue

            # read file
            try:
                lines = format.read(self._root, file)
            except IOError as e:
                log.warning('%s: %s', source, e)
                continue
            finally:
                # only close files that were opened from the filesystem
                if isinstance(source, str):
                    format.close(file)

            one_source_read = True

            # return lines only for the first source
            if i == 0:
                context = lines

        if not one_source_read:
            log.debug('no config was read')

        return context

    def _write(self, source, format, context=None):
        file = format.open(self._root, source, 'w')
        try:
            format.write(self._root, file, context)
        finally:
            # only close files that were opened from the filesystem
            if isinstance(source, str):
                format.close(file)
            else:
                format.flush(file)

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
        if isinstance(format, bytes):
            format = format.decode('ascii')
        if isinstance(format, str):
            try:
                cls = Config._formats[format]
            except KeyError as e:
                raise UnknownFormatError(e)
            return cls()
        elif isinstance(format, Format):
            return format
        else:
            return format()

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
            elif isinstance(p, abc.Sequence):
                key.extend(p)
            elif p is None:
                pass
            else:
                err = "invalid value for key: '{}'"
                raise TypeError(err.format(p))
        return tuple(key)

    def _keystr(self, key):
        return self._root.sep.join(key)

    def _reset(self, clean):
        if self._value is not NoValue:
            self._value = NoValue
            self._dirty = not clean
        if self._default is NoValue:
            self._type = None

    def _dump(self, indent=2): # pragma: no cover
        rootlen = len(self._make_key(self._key))
        print(repr(self))
        for section in sorted(self.sections(recurse=True)):
            sectionlen = len(self._make_key(section._key))
            spaces = ' ' * ((sectionlen - rootlen) * indent - 1)
            print(spaces, repr(section))

class Config(ConfigSection):
    """The root configuration object.

    Any number of sources can be set using *sources*. These are the sources
    that will be using when calling :meth:`~profig.ConfigSection.sync`.

    The format of the sources can be set using *format*. This can be the
    registered name of a format, such as "ini", or a :class:`~profig.Format`
    class or instance.

    An encoding can be set using *encoding*. If *encoding* is not specified
    the encoding used is platform dependent: locale.getpreferredencoding(False).

    Strict mode can be enabled by setting *strict* to `True`. In strict mode,
    accessing keys that have not been initialized will raise an
    :exc:`~profig.InvalidSectionError`.

    The dict class used internally can be set using *dict_type*. By default
    an `OrderedDict` is used.

    A :class:`~profig.Coercer` can be set using *coercer*. If no coercer is
    passed in, a default will be created. If `None` is passed in, no coercer
    will be set and values will be read from and written to sources directly.

    This is a subclass of :class:`~profig.ConfigSection`.
    """

    _formats = {}

    def __init__(self, *sources, **kwargs):
        self._dict_type = kwargs.pop('dict_type', collections.OrderedDict)
        super(Config, self).__init__(None, None)

        self.sources = list(sources)
        self.encoding = kwargs.pop('encoding', locale.getpreferredencoding(False))
        self.strict = kwargs.pop('strict', False)

        format = kwargs.pop('format', 'ini')
        self.set_format(format)

        self.coercer = kwargs.pop('coercer', NoValue)
        if self.coercer is NoValue:
            self.coercer = Coercer()

        self.sep = '.'

        kwargs_check('__init__', kwargs)

    @property
    def format(self):
        """The :class:`~profig.Format` to use to process sources."""
        return self._format

    @classmethod
    def known_formats(cls):
        """Returns the formats registered with this class."""
        return tuple(cls._formats)

    def set_format(self, format):
        """Sets the format to use when processing sources.

        *format* can be the registered name of a format, such as
        "ini", or a :class:`~profig.Format` class or instance.
        """
        self._format = self._process_format(format)

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
        if isinstance(name, bytes):
            name = name.decode('ascii')
        if name not in ('BaseFormat', 'Format'):
            Config._formats[cls.name] = cls
        return super(MetaFormat, cls).__init__(name, bases, dct)

BaseFormat = MetaFormat('BaseFormat' if PY3 else b'BaseFormat', (object, ), {})

class Line(collections.namedtuple('Line', 'line name iskey issection')):
    __slots__ = ()
    def __new__(cls, line, name=None, iskey=False, issection=False):
        return super(Line, cls).__new__(cls, line, name, iskey, issection)

class Format(BaseFormat):
    #: A convenient name for the format.
    name = None
    #: The supported error modes.
    error_modes = frozenset(['ignore', 'warning', 'exception'])

    def __init__(self):
        self.ensure_dirs = 0o744
        self.error_mode = 'warning'

    @property
    def error_mode(self):
        """Specifies how the format should react to errors raised when
        processing a source.

        Must be one of the following:

        * ignore - Ignore all errors completely.
        * warning - Log a warning for any errors.
        * exception - Raise an exception for any error.

        Only 'exception' will cause the format to stop processing a source.
        """
        return self._error_mode

    @error_mode.setter
    def error_mode(self, mode):
        if mode not in self.error_modes:
            raise ValueError('invalid error_mode: {}'.format(mode))
        self._error_mode = mode

    def read(self, cfg, file): # pragma: no cover
        """Reads *file* to update *cfg*. Must be implemented in a subclass."""
        raise NotImplementedError('abstract')

    def write(self, cfg, file, values=None): # pragma: no cover
        """Writes *cfg* to file. Must be implemented in a subclass."""
        raise NotImplementedError('abstract')

    def open(self, cfg, source, mode='r', binary=True):
        """Returns a file object.

        If *source* is a file object, returns *source*.
        *mode* can be 'r' or 'w'. If *mode* is 'w', The file object will be
        truncated.
        If *binary* is `True`, the file will be opened in binary mode
        ('rb' or 'wb').
        """
        if mode not in 'rw':
            raise ValueError("*mode* argument must be either 'r' or 'w'")

        if isinstance(source, bytes):
            source = source.decode(cfg.root.encoding)

        if isinstance(source, str):
            source = os.path.expanduser(source)
            if self.ensure_dirs is not None and 'w' in mode:
                # ensure the path exists if any writing is to be done
                ensure_dirs(os.path.dirname(source), self.ensure_dirs)
            if binary:
                mode += 'b'
            return io.open(source, mode)
        else:
            source.seek(0)
            if 'w' in mode:
                source.truncate()
            return source

    def close(self, file):
        file.close()

    def flush(self, file):
        file.flush()

    def _error(self, exc, file, lineno=None, text=''):
        if self.error_mode == 'ignore':
            return

        name = file.name if hasattr(file, 'name') else file
        err = ["error reading '{}'".format(name)]
        if lineno is not None:
            err.append(', line {}'.format(lineno))
        err.append(': {}'.format(exc))
        if text:
            err.append('\n  {}'.format(text))
        message = ''.join(err)

        if self.error_mode == 'exception':
            log.error(message)
            raise exc
        elif self.error_mode == 'warning':
            log.warning(message)
        else:
            assert False

class INIFormat(Format):
    name = 'ini'
    delimeter = b' = '
    comment_char = b'; '
    default_section = b'default'
    _rx_section_header = re.compile(b'\[\s*(\S*)\s*\](\s*=\s*(.*))?')

    def read(self, cfg, file):
        encoding = cfg.root.encoding
        comment_char = self.comment_char.strip()
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
            if line.startswith(comment_char):
                flush_comment(lines, comment)
                comment_text = line.lstrip(comment_char).strip().decode(encoding)
                comment = Line(orgline, comment_text)
                continue

            # section header
            match = self._rx_section_header.match(line)
            if match:
                section_name, _, value = match.groups()

                # blank sections are set to default
                if not section_name or section_name.lower() == self.default_section:
                    section_name = self.default_section

                values[section_name] = value
                if comment:
                    comments[section_name] = comment.name
                comment = None

                section_name = section_name.decode(encoding)
                lines.append(Line(orgline, section_name, issection=True))
                continue

            # must be a value
            try:
                key, value = line.split(self.delimeter.strip(), 1)
            except ValueError:
                self._error(FormatError('invalid syntax'), file, i, line)
                continue

            key = cfg._keystr(cfg._make_key(section_name, key.strip()))
            values[key] = value.strip()
            if comment:
                comments[key] = comment.name
            comment = None

            lines.append(Line(orgline, key, iskey=True))

        # comment left over
        if comment:
            lines.append(comment)

        # file has been read. assign the values
        for i, (key, value) in enumerate(values.items(), 1):
            try:
                section = cfg.section(key)
            except InvalidSectionError as e:
                self._error(e, file, i, lines[i-1].line.strip())
                continue

            if not section._dirty and value is not None:
                section.convert(value, decode=True)
                section._dirty = False
            if key in comments:
                section.comment = comments[key]

        return lines

    def write_section(self, cfg, section, file, first=False):
        encoding = cfg.root.encoding
        write = lambda s: file.write(s.encode(encoding))

        if not first and section.parent is section.root:
            write('\n')

        if section.comment:
            file.write(self.comment_char)
            write(section.comment)
            write('\n')

        if section.parent is section.root:
            # header section
            if section.valid:
                value = section.adapt()
                write('[{}]'.format(section.name))
                file.write(self.delimeter)
                if isinstance(value, bytes):
                    file.write(value)
                else:
                    write(value)
                write('\n')
            else:
                write('[{}]\n'.format(section.name))

        elif section.valid:
            # value section
            key = cfg._keystr(cfg._make_key(section.key)[1:])
            write(key)
            file.write(self.delimeter)
            file.write(section.adapt(encode=True))
            write('\n')

        section._dirty = False

    def write(self, cfg, file, lines=None):
        # write back values in the order they were read
        seen = set()
        header = None
        lines = lines or []
        first = True
        for i, line in enumerate(lines, 1):
            if line.issection:
                if line.name in seen:
                    continue

                # if there is a previous header section, write it's
                # remaining values
                if header:
                    for sec in header.sections(recurse=True):
                        if sec.key not in seen:
                            self.write_section(cfg, sec, file)
                            seen.add(sec.key)

                # write current section header
                try:
                    header = cfg.section(line.name, create=False)
                except InvalidSectionError as e:
                    self._error(e, file, i, line.line.strip())
                    continue

                self.write_section(cfg, header, file, first)
                seen.add(header.key)
                first = False

            elif line.iskey:
                if line.name in seen:
                    continue

                try:
                    section = cfg.section(line.name, create=False)
                except InvalidSectionError as e:
                    self._error(e, file, i, line.line.strip())
                    continue

                self.write_section(cfg, section, file)
                seen.add(line.name)

            else:
                file.write(line.line)

        # if there is an incomplete header section, write it's remaining values
        if header:
            for sec in header.sections(recurse=True):
                if sec.key not in seen:
                    self.write_section(cfg, sec, file)
                    seen.add(sec.key)

        # write remaining values
        for section in cfg.sections(recurse=True):
            if section.key in seen:
                continue

            self.write_section(cfg, section, file, first)
            seen.add(section.key)
            first = False

class SerializeFormat(Format):
    """A `Format` class that offers support for serialization libraries.

    If a library provides both a "load" and a "dump" function, it can be passed
    in directly as *base*. Otherwise the "load"/"dump" functions can be passed
    in individually as *load* and *dump*,  respectively.

    *binary* should be set to specify whether the serialization dumper outputs
    unicode strings (`False`) or bytes (`True`).
    """
    def __init__(self, base=None, load=None, dump=None, binary=False):
        super(SerializeFormat, self).__init__()
        if base:
            self.load = base.load
            self.dump = base.dump
        if load:
            self.load = load
        if dump:
            self.dump = dump
        self.binary = binary

    def open(self, cfg, source, mode='r'):
        return super(SerializeFormat, self).open(cfg,  source, mode,
            binary=self.binary)

    def read(self, cfg, file):
        d = self.load(file)
        if d:
            cfg.update(d)

    def write(self, cfg, file, values=None):
        self.dump(cfg.as_dict(dict_type=dict), file)

class JSONFormat(SerializeFormat):
    name = 'json'

    def __init__(self):
        import json
        dump = (json.dump if PY3 else
            lambda o, f: f.write(unicode(json.dumps(o, ensure_ascii=False))))
        super(JSONFormat, self).__init__(json, dump=dump)

    def read(self, cfg, file):
        # quick test to see if the file is empty, which json does not like
        file.seek(0, io.SEEK_END)
        if file.tell() == 0:
            return
        file.seek(0)
        super(JSONFormat, self).read(cfg, file)

class TOMLFormat(SerializeFormat):
    name = 'toml'

    def __init__(self):
        import toml
        super(TOMLFormat, self).__init__(toml)

class YAMLFormat(SerializeFormat):
    name = 'yaml'

    def __init__(self):
        import yaml
        super(YAMLFormat, self).__init__(yaml)
        self.load = lambda file: yaml.load(file, Loader=yaml.FullLoader)

class MessagePackFormat(SerializeFormat):
    name = 'msgpack'

    def __init__(self):
        import msgpack
        super(MessagePackFormat, self).__init__(msgpack, binary=True)

    def read(self, cfg, file):
        # quick test to see if the file is empty, which msgpack does not like
        file.seek(0, io.SEEK_END)
        if file.tell() == 0:
            return
        file.seek(0)
        super(MessagePackFormat, self).read(cfg, file)

if WIN:
    class RegistryFormat(Format):
        name = 'registry'
        base_key = winreg.HKEY_CURRENT_USER
        types = {
            str: winreg.REG_SZ,
            bytes: winreg.REG_BINARY,
            int: winreg.REG_DWORD,
            }

        def read(self, cfg, key):
            n_subkeys, n_values, _ = winreg.QueryInfoKey(key)

            # read values from this subkey
            for i in range(n_values):
                name, value, reg_type = winreg.EnumValue(key, i)

                try:
                    section = cfg.section(name)
                except InvalidSectionError as e:
                    self._error(e, name)
                    continue

                if section._dirty:
                    # don't overwrite dirty sections
                    continue

                section.convert(value, decode=True)
                section._dirty = False

            # read values from next subkeys
            for i in range(n_subkeys):
                name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKeyEx(key, name)
                try:
                    section = cfg.section(name)
                except InvalidSectionError as e:
                    self._error(e, name)
                    continue
                self.read(section, subkey)

        def write(self, cfg, key, context=None):
            for k in cfg:
                section = cfg.section(k)
                # determine the registry key/name
                section_key = cfg._make_key(section.key)
                if section.has_children:
                    rkey = ntpath.sep.join(section_key)
                    name = ''
                else:
                    rkey = ntpath.sep.join(section_key[:-1])
                    name = section_key[-1]

                # get a supported type for the value
                reg_type = self.types.get(type(section.value()))
                if reg_type is None:
                    # not a type supported by the registry, so adapt it
                    reg_type = winreg.REG_BINARY
                    value = section.adapt(encode=True)
                else:
                    value = section.value()

                # write the value
                subkey = winreg.CreateKeyEx(key, rkey)
                winreg.SetValueEx(subkey, name, 0, reg_type, value)

        def open(self, cfg, source, mode='r'):
            if 'r' in mode:
                try:
                    return winreg.OpenKeyEx(self.base_key, source)
                except WindowsError as e:
                    raise IOError(e)
            elif 'w' in mode:
                return winreg.CreateKeyEx(self.base_key, source)
            else:
                raise ValueError('invalid mode: {}'.format(mode))

        def close(self, key):
            winreg.CloseKey(key)

        def flush(self, key):
            winreg.FlushKey(key)

        def delete(self, key):
            """Deletes all keys and values recursively from *key*."""
            for subkey in list(self.all_keys(key)):
                winreg.DeleteKey(subkey, '')

        def all_keys(self, key):
            """Generates all keys descending from *key*.

            The deepest is returned first, then the rest, all the way
            back to *key*
            """
            n_subkeys, n_values, t = winreg.QueryInfoKey(key)
            for i in range(n_subkeys):
                name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKeyEx(key, name)
                for subsubkey in self.all_keys(subkey):
                    yield subsubkey

            yield key

## Config Errors ##

class ConfigError(Exception):
    """Base exception class for all exceptions raised."""

class UnknownFormatError(ConfigError):
    """Raised when a format is set that has not been registered."""

class InvalidSectionError(KeyError, ConfigError):
    """Raised when a section was never created."""

class NoValueError(ValueError, ConfigError):
    """Raised when a section has no set value or default value."""

class FormatError(ConfigError):
    """Raised for errors when reading/writing with a Format."""

class NoSourcesError(ConfigError):
    """Raised when there are no sources for a config object."""

## Config Utilities ##

class NoValue:
    def __repr__(self):
        return '{}'.format(self.__class__.__name__)
NoValue = NoValue()

def kwargs_check(name, kwargs):
    if kwargs:
        err = "{}() got an unexpected keyword argument '{}'"
        raise TypeError(err.format(name, kwargs.popitem()[0]))

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
        def verify(x, c):
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
        elif isinstance(type, abc.Sequence):
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
    import base64
    import binascii
    import datetime as dt

    # None as the type does not change the value
    coercer.register(None, lambda x: x, lambda x: x)
    # NoneType as the type assumes the value is None
    coercer.register(type(None), lambda x: '', lambda x: None)
    coercer.register(int, str, int)
    coercer.register(float, str, float)
    coercer.register(complex, str, complex)
    coercer.register(str, str, str)
    coercer.register(bytes, bytes, bytes)
    coercer.register('hex',
        lambda x: binascii.hexlify(x),
        lambda x: binascii.unhexlify(x))
    coercer.register('base64',
        lambda x: base64.b64encode(x),
        lambda x: base64.b64decode(x))

    # boolean coercers
    _boolean_states = {'1': True, 'yes': True, 'true': True, 'on': True,
        '0': False, 'no': False, 'false': False, 'off': False}
    coercer.register_adapter(bool, lambda x: 'true' if x else 'false')
    coercer.register_converter(bool, lambda x: _boolean_states[x.lower()])

    # datetime coercers
    dt_date_fmt = '%Y-%m-%d' if PY3 else b'%Y-%m-%d'
    coercer.register(dt.date,
        lambda x: x.isoformat(),
        lambda x: dt.datetime.strptime(x, dt_date_fmt).date())
    dt_time_fmt = '%H:%M:%S.%f' if PY3 else b'%H:%M:%S.%f'
    coercer.register(dt.time,
        lambda x: x.isoformat(),
        lambda x: dt.datetime.strptime(x, dt_time_fmt).time())
    dt_datetime_fmt = '%Y-%m-%d %H:%M:%S.%f' if PY3 else b'%Y-%m-%d %H:%M:%S.%f'
    coercer.register(dt.datetime,
        lambda x: x.isoformat(' ' if PY3 else b' '),
        lambda x: dt.datetime.strptime(x, dt_datetime_fmt))

    # collection coercers, simply comma delimited
    split = lambda x: [s.strip() for s in x.split(',')] if x else []
    coercer.register(list, lambda x: ', '.join(x), split)
    coercer.register(set, lambda x: ', '.join(x), lambda x: set(split(x)))
    coercer.register(tuple, lambda x: ', '.join(x), lambda x: tuple(split(x)))

    # path coercers, os.pathsep delimited
    sep = os.pathsep
    pathsplit = lambda x: x.split(sep) if x else []
    coercer.register('path_list', lambda x: sep.join(x), pathsplit)
    coercer.register('path_set', lambda x: sep.join(x), lambda x: set(pathsplit(x)))
    coercer.register('path_tuple', lambda x: sep.join(x), lambda x: tuple(pathsplit(x)))

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
