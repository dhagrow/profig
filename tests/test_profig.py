from __future__ import unicode_literals

import io
import os
import sys
import unittest

# attempt Qt coercer testing
try:
    import PySide
except ImportError:
    pass

import profig

# use str for unicode data and bytes for binary data
if sys.version_info.major < 3:
    str = unicode

class TestBasic(unittest.TestCase):
    def test_init(self):
        c = profig.Config()

        self.assertEqual(dict(c), {})
        self.assertEqual(c.sources, [])
    
    def test_root(self):
        c = profig.Config()
        c['a'] = 1
        
        self.assertEqual(c.root, c)
        
        s = c.section('a')
        self.assertEqual(s.root, c)
        self.assertNotEqual(s.root, s)
    
    def test_formats(self):
        self.assertEqual(sorted(profig.Config.known_formats()), ['profig', 'ini'])
        
        c = profig.Config()
        self.assertIsInstance(c._format, profig.FigFormat)
        
        c = profig.Config(format='profig')
        self.assertIsInstance(c._format, profig.FigFormat)
        
        c = profig.Config(format='ini')
        self.assertIsInstance(c._format, profig.IniFormat)
        
        c = profig.Config(format=profig.IniFormat)
        self.assertIsInstance(c._format, profig.IniFormat)
        
        c = profig.Config()
        c.set_format(profig.IniFormat(c))
        self.assertIsInstance(c._format, profig.IniFormat)
        
        with self.assertRaises(profig.UnknownFormatError):
            c = profig.Config(format='marshmallow')
    
    def test_keys(self):
        c = profig.Config()
        c['a'] = 1
        c['a.a'] = 1
        c[('a', 'a')] = 1
        c[('a', ('a', 'a'))] = 1
        
        with self.assertRaises(TypeError):
            c[1] = 1
    
    def test_sync(self):
        c = profig.Config()
        with self.assertRaises(profig.NoSourcesError):
            c.sync()
    
    def test_len(self):
        c = profig.Config()
        self.assertEqual(len(c), 0)
        
        c['a'] = 1
        self.assertEqual(len(c), 1)
        
        c['a.1'] = 1
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c.section('a')), 1)
    
    def test_get(self):
        c = profig.Config()
        c['a'] = 1
        c.init('a.1', 1)
        
        self.assertEqual(c.get('a'), 1)
        self.assertEqual(c.get('a.1'), 1)
        self.assertEqual(c.get('a', type=str), '1')
        self.assertEqual(c.get('a.2'), None)
        self.assertEqual(c.get('a.2', 2), 2)
    
    def test_value(self):
        c = profig.Config()
        c['a'] = 1
        c.init('b', 1)
        
        s = c.section('c')
        with self.assertRaises(profig.NoValueError):
            s.value()
        
        for key in ['a', 'b']:
            s = c.section(key)
            self.assertEqual(s.value(), 1)
            self.assertEqual(s.value(convert=False), '1')
            self.assertEqual(s.value(type=str), '1')
    
    def test_default(self):
        c = profig.Config()
        c['a'] = 1
        c.init('b', 1)
        
        s = c.section('a')
        with self.assertRaises(profig.NoValueError):
            s.default()
        
        s = c.section('b')
        self.assertEqual(s.default(), 1)
        self.assertEqual(s.default(convert=False), '1')
        self.assertEqual(s.default(type=str), '1')
    
    def test_set_value(self):
        c = profig.Config()
        c.init('c', 1)
        
        c.section('a').set_value(2)
        self.assertEqual(c['a'], 2)
        
        c.section('b').set_value('3')
        self.assertEqual(c['b'], '3')
        
        c.section('c').set_value('4')
        self.assertEqual(c['c'], 4)
    
    def test_set_value(self):
        c = profig.Config()
        c.init('c', 1)
        
        c.section('a').set_default(2)
        self.assertEqual(c['a'], 2)
        
        c.section('b').set_default('3')
        self.assertEqual(c['b'], '3')
        
        c.section('c').set_default('4')
        self.assertEqual(c['c'], 4)
    
    def test_section(self):
        c = profig.Config()
        
        with self.assertRaises(profig.InvalidSectionError):
            c.section('a', create=False)
        
        self.assertIs(c.section('a'), c._children['a'])
        
        c['a.a.a'] = 1
        child = c._children['a']._children['a']._children['a']
        self.assertIs(c.section('a.a.a'), child)
        self.assertIs(c.section('a').section('a').section('a'), child)
    
    def test_as_dict(self):
        c = profig.Config(dict_type=dict)
        self.assertEqual(c.as_dict(), {})
        
        c['a'] = 1
        self.assertEqual(c.as_dict(), {'a': 1})
        
        c['b'] = 1
        c['a.a'] = 1
        self.assertEqual(c.as_dict(), {'a': {'': 1, 'a': 1}, 'b': 1})
        self.assertEqual(c.as_dict(convert=False),
            {'a': {'': '1', 'a': '1'}, 'b': '1'})
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 1, 'b': 1})
        self.assertEqual(c.as_dict(flat=True, convert=False),
            {'a': '1', 'a.a': '1', 'b': '1'})
    
    def test_reset(self):
        c = profig.Config(dict_type=dict)
        c.init('a', 1)
        c.init('a.a', 1)
        c['a'] = 2
        c['a.a'] = 2
        
        c.section('a').reset(recurse=False)
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 2})
        
        c.section('a').reset()
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 1})
        
        c['a'] = 2
        c['a.a'] = 2
        
        c.reset()
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 1})
    
    def test_filter(self):
        c = profig.Config(dict_type=dict)
        c['a'] = 1
        c['a.a'] = 1
        c['a.b'] = 2
        c['b.a'] = 1
        
        self.assertEqual(c.as_dict(flat=True, include=['a']), {'a': 1, 'a.a': 1, 'a.b': 2})
        self.assertEqual(c.as_dict(include=['a']), {'a': {'': 1, 'a': 1, 'b': 2}})
        self.assertEqual(c.as_dict(flat=True, exclude=['b']), {'a': 1, 'a.a': 1, 'a.b': 2})
        self.assertEqual(c.as_dict(exclude=['b']), {'a': {'': 1, 'a': 1, 'b': 2}})

class TestFigFormat(unittest.TestCase):
    def setUp(self):
        self.c = profig.Config()

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)
    
    def test_read(self):
        buf = io.StringIO("""\
a: 2
a.1: 3
b: newvalue
""")
        c = profig.Config(buf)
        c.read()
        
        self.assertEqual(c['a'], '2')
        self.assertEqual(c['b'], 'newvalue')
        self.assertEqual(c['a.1'], '3')
    
    def test_write(self):
        buf = io.StringIO()
        c = profig.Config(buf)
        
        c.init('a', 1)
        c.init('b', 'value')
        c.init('a.1', 2)
        
        c.write()

        self.assertEqual(buf.getvalue(), """\
a: 1
a.1: 2
b: value
""")

    def test_sync_read(self):
        buf = io.StringIO("""\
a: 2
a.1: 3
b: newvalue
""")
        self.c.sync(buf)
        
        self.assertEqual(self.c['a'], 2)
        self.assertEqual(self.c['b'], 'newvalue')
        self.assertEqual(self.c['a.1'], 3)

    def test_sync_read_blank(self):
        c = profig.Config()
        buf = io.StringIO("""\
a: 2
a.1: 3
b: newvalue
""")
        c.sync(buf)
        
        self.assertEqual(c['a'], '2')
        self.assertEqual(c['b'], 'newvalue')
        self.assertEqual(c['a.1'], '3')

    def test_sync_write(self):
        buf = io.StringIO()
        self.c.sync(buf)

        self.assertEqual(buf.getvalue(), """\
a: 1
a.1: 2
b: value
""")

class TestIniFormat(unittest.TestCase):
    def setUp(self):
        self.c = profig.Config(format='ini')

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)

    def test_basic(self):
        del self.c['a.1']

        buf = io.StringIO()
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), """\
[DEFAULT]
a = 1
b = value
""")
    
    def test_sync_read_blank(self):
        c = profig.Config(format='ini')
        buf = io.StringIO("""\
[DEFAULT]
b = value

[a]
 = 1
1 = 2
""")
        c.sync(buf)
        
        self.assertEqual(c['a'], '1')
        self.assertEqual(c['b'], 'value')
        self.assertEqual(c['a.1'], '2')

    # XXX: disabled. by default, DEFAULT should be the first section
    def xtest_subsection(self):
        buf = io.StringIO()
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), """\
[DEFAULT]
b = value

[a]
 = 1
1 = 2
""")

class TestCoercer(unittest.TestCase):
    def test_list_value(self):
        c = profig.Config()
        c.init('colors', ['red', 'blue'])
        
        buf = io.StringIO()
        c.sync(buf)
        
        self.assertEqual(buf.getvalue(), """\
colors: red,blue
""")
    
    def test_tuple_type(self):
        c = profig.Config()
        c.init('paths', ['path1', 'path2'], (list, 'path'))
        
        buf = io.StringIO()
        c.sync(buf)
        
        self.assertEqual(buf.getvalue(), """\
paths: path1:path2
""")
        
        buf = io.StringIO("""\
paths: path1:path2:path3
""")
        c.sync(buf)
        self.assertEqual(c['paths'], ['path1', 'path2', 'path3'])
    
    def test_choice(self):
        c = profig.Config()
        c.coercer.register_choice('color', {1: 'red', 2: 'green', 3: 'blue'})
        c.init('color', 1, 'color')
        
        buf = io.StringIO()
        c.sync(buf)
        self.assertEqual(buf.getvalue(), """\
color: red
""")
        
        buf = io.StringIO("""\
color: blue
""")
        c.sync(buf)
        self.assertEqual(c['color'], 3)

class TestErrors(unittest.TestCase):
    def test_ReadError(self):
        c = profig.Config()
        c._format.read_errors = 'exception'
        
        buf = io.StringIO("""a""")
        with self.assertRaises(profig.ReadError):
            c.sync(buf)

class TestMisc(unittest.TestCase):
    def test_NoValue(self):
        self.assertEqual(repr(profig.NoValue), 'NoValue')
    
    def test_get_source(self):
        path = os.path.dirname(__file__)
        self.assertEqual(profig.get_source('test'), os.path.join(path, 'test'))
        
        path = '~/.config'
        self.assertEqual(profig.get_source('test', 'user'), os.path.join(path, 'test'))

if __name__ == '__main__':
    unittest.main()