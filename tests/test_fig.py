import io
import os
import unittest

import fig

class TestBasic(unittest.TestCase):
    def test_init(self):
        c = fig.Config()

        self.assertEqual(dict(c), {})
        self.assertEqual(c.sources, [])
    
    def test_root(self):
        c = fig.Config()
        c['a'] = 1
        
        self.assertEqual(c.root, c)
        
        s = c.section('a')
        self.assertEqual(s.root, c)
        self.assertNotEqual(s.root, s)
    
    def test_sync(self):
        c = fig.Config()
        with self.assertRaises(fig.NoSourcesError):
            c.sync()
    
    def test_len(self):
        c = fig.Config()
        self.assertEqual(len(c), 0)
        
        c['a'] = 1
        self.assertEqual(len(c), 1)
        
        c['a.1'] = 1
        self.assertEqual(len(c), 1)
        self.assertEqual(len(c.section('a')), 1)
    
    def test_get(self):
        c = fig.Config()
        c['a'] = 1
        c.init('a.1', 1)
        
        self.assertEqual(c.get('a'), 1)
        self.assertEqual(c.get('a.1'), 1)
        self.assertEqual(c.get('a', type=str), '1')
        self.assertEqual(c.get('a.2'), None)
        self.assertEqual(c.get('a.2', 2), 2)
    
    def test_value(self):
        c = fig.Config()
        c['a'] = 1
        c.init('b', 1)
        
        for key in ['a', 'b']:
            s = c.section(key)
            self.assertEqual(s.value(), 1)
            self.assertEqual(s.value(convert=False), '1')
            self.assertEqual(s.value(type=str), '1')
    
    def test_default(self):
        c = fig.Config()
        c['a'] = 1
        c.init('b', 1)
        
        s = c.section('a')
        with self.assertRaises(fig.NoDefaultError):
            s.default()
        
        s = c.section('b')
        self.assertEqual(s.default(), 1)
        self.assertEqual(s.default(convert=False), '1')
        self.assertEqual(s.default(type=str), '1')
    
    def test_section(self):
        c = fig.Config()
        
        with self.assertRaises(fig.InvalidSectionError):
            c.section('a')
        
        c['a'] = 1
        self.assertIs(c.section('a'), c._children['a'])
        
        c['a.a.a'] = 1
        child = c._children['a']._children['a']._children['a']
        self.assertIs(c.section('a.a.a'), child)
        self.assertIs(c.section('a').section('a').section('a'), child)
    
    def test_as_dict(self):
        c = fig.Config(dict_type=dict)
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
        c = fig.Config(dict_type=dict)
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
        c = fig.Config(dict_type=dict)
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
        self.c = fig.Config()

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
        c = fig.Config()
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
        self.c = fig.Config(format='ini')

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
        c = fig.Config(format=fig.IniFormat)
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

class TestJsonFormat(unittest.TestCase):
    def setUp(self):
        self.c = fig.Config(format='json')

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
        
        self.assertEqual(self.b.getvalue(),
            """{"a": {"": "1", "1": "2"}, "b": "value"}""")

class TestErrors(unittest.TestCase):
    def test_ReadError(self):
        c = fig.Config()
        c._format.read_errors = 'exception'
        
        buf = io.StringIO("""a""")
        with self.assertRaises(fig.ReadError):
            c.sync(buf)

class TestMisc(unittest.TestCase):
    def test_NoValue(self):
        self.assertEqual(repr(fig.NoValue), 'NoValue')
    
    def test_get_source(self):
        path = os.path.dirname(__file__)
        self.assertEqual(fig.get_source('test'), os.path.join(path, 'test'))
        
        path = '~/.config'
        self.assertEqual(fig.get_source('test', 'user'), os.path.join(path, 'test'))

if __name__ == '__main__':
    unittest.main()
