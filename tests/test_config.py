import io
import unittest

import config

class TestBasic(unittest.TestCase):
    def test_init(self):
        c = config.Config()

        self.assertEqual(dict(c), {})
        self.assertEqual(c.sources, [])

class TestConfigFormat(unittest.TestCase):
    def setUp(self):
        self.c = config.Config()

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)

    def test_basic(self):
        buf = io.StringIO()
        self.c.sync(buf)

        self.assertEqual(buf.getvalue(), """\
a: 1
a.1: 2
b: value
""")

class TestIniFormat(unittest.TestCase):
    def setUp(self):
        self.c = config.Config()
        self.c.format = config.IniFormat()

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
        self.c = config.Config()
        self.c.format = config.JsonFormat()

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)

    def test_basic(self):
        del self.c['a.1']

        buf = io.StringIO()
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), """\
{"a": "1", "b": "value"}""")

if __name__ == '__main__':
    unittest.main()
