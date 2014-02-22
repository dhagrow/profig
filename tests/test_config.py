import io
import unittest

import config

class TestBasic(unittest.TestCase):
    def test_init(self):
        c = config.Config()

        self.assertEqual(dict(c), {})
        self.assertEqual(c.sources, [])
    
    def test_root(self):
        c = config.Config()
        c['a'] = 1
        
        self.assertEqual(c.root, c)
        
        s = c.section('a')
        self.assertEqual(s.root, c)
        self.assertNotEqual(s.root, s)
    
    def test_sync(self):
        c = config.Config()
        with self.assertRaises(config.NoSourcesError):
            c.sync()
    
    def test_len(self):
        c = config.Config()
        self.assertEqual(len(c), 0)
        
        c['a'] = 1
        self.assertEqual(len(c), 1)
        
        c['a.1'] = 1
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c.section('a')), 1)
    
    def test_get(self):
        c = config.Config()
        c['a'] = 1
        c.init('a.1', 1)
        
        self.assertEqual(c.get('a'), 1)
        self.assertEqual(c.get('a.1'), 1)
        self.assertEqual(c.get('a', type=str), '1')
        self.assertEqual(c.get('a.2'), None)
        self.assertEqual(c.get('a.2', 2), 2)
    
    def test_get_value(self):
        c = config.Config()
        c['a'] = 1
        c.init('b', 1)
        
        for key in ['a', 'b']:
            s = c.section(key)
            self.assertEqual(s.get_value(), 1)
            self.assertEqual(s.get_value(convert=False), '1')
            self.assertEqual(s.get_value(type=str), '1')
    
    def test_get_default(self):
        c = config.Config()
        c['a'] = 1
        c.init('b', 1)
        
        s = c.section('a')
        with self.assertRaises(config.NoDefaultError):
            s.get_default()
        
        s = c.section('b')
        self.assertEqual(s.get_default(), 1)
        self.assertEqual(s.get_default(convert=False), '1')
        self.assertEqual(s.get_default(type=str), '1')
    
    def test_section(self):
        c = config.Config()
        
        with self.assertRaises(config.InvalidSectionError):
            c.section('a')
        
        c['a'] = 1
        self.assertIs(c.section('a'), c._children['a'])
        
        c['a.a.a'] = 1
        child = c._children['a']._children['a']._children['a']
        self.assertIs(c.section('a.a.a'), child)
        self.assertIs(c.section('a').section('a').section('a'), child)
    
    def test_as_dict(self):
        c = config.Config(dict_type=dict)
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
        c = config.Config(dict_type=dict)
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
    
    def test_interpolate(self):
        c = config.Config()
        c['a'] = 1
        c['b.a'] = '{!a}value{!a}'
        c['c'] = '{x}'
        c['d'] = '{!b.a}value'
        c['e'] = '{!f}'
        c['f'] = '{!e}'
        
        self.assertEqual(c['b.a'], '1value1')
        self.assertEqual(c['c'], '{x}')
        self.assertEqual(c['d'], '1value1value')
        with self.assertRaises(config.InterpolationCycleError):
            c['e']
    
    def test_filter(self):
        c = config.Config(dict_type=dict)
        c['a'] = 1
        c['a.a'] = 1
        c['a.b'] = 2
        c['b.a'] = 1
        
        self.assertEqual(c.as_dict(flat=True, include=['a']), {'a': 1, 'a.a': 1, 'a.b': 2})
        self.assertEqual(c.as_dict(include=['a']), {'a': {'': 1, 'a': 1, 'b': 2}})
        self.assertEqual(c.as_dict(flat=True, exclude=['b']), {'a': 1, 'a.a': 1, 'a.b': 2})
        self.assertEqual(c.as_dict(exclude=['b']), {'a': {'': 1, 'a': 1, 'b': 2}})

class TestConfigFormat(unittest.TestCase):
    def setUp(self):
        self.c = config.Config()

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)

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
        c = config.Config()
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
        self.c = config.Config(format=config.IniFormat)

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

class TestJsonFormat(unittest.TestCase):
    def setUp(self):
        self.c = config.Config(format=config.JsonFormat)

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)

        self.b = io.StringIO()

    def test_basic(self):
        del self.c['a.1']

        self.c.sync(self.b)
        
        self.assertEqual(self.b.getvalue(), """\
{"a": "1", "b": "value"}""")

    def test_subsection(self):
        self.c.sync(self.b)
        
        self.assertEqual(self.b.getvalue(), """\
{"a": {"": "1", "1": "2"}, "b": "value"}""")

if __name__ == '__main__':
    unittest.main()
