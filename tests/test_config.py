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
    
    def test_no_section(self):
        c = config.Config()
        with self.assertRaises(config.InvalidSectionError):
            c.section('a')

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
