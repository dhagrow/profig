from __future__ import unicode_literals

import io
import os
import tempfile
import unittest

# attempt Qt coercer testing
try:
    import PySide
except ImportError:
    pass

import profig

# use str for unicode data and bytes for binary data
if not profig.PY3:
    str = unicode

if profig.WIN:
    try:
        import winreg
    except ImportError:
        import _winreg as winreg

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
        self.assertIn('ini', profig.Config.known_formats())
        
        c = profig.Config()
        self.assertIsInstance(c._format, profig.IniFormat)
        
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
    
    def test_unicode_keys(self):
        c = profig.Config(encoding='shiftjis')
        c[b'\xdc'] = 1
        c[b'\xdc.\xdc'] = '\uff9c'
        
        self.assertEqual(c[b'\xdc'], c['\uff9c'], 1)
        self.assertEqual(c[b'\xdc.\xdc'], c['\uff9c.\uff9c'], '\uff9c')
    
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
    
    def test_default(self):
        c = profig.Config()
        c['a'] = 1
        c.init('b', 1)
        
        s = c.section('a')
        with self.assertRaises(profig.NoValueError):
            s.default()
        
        s = c.section('b')
        self.assertEqual(s.default(), 1)
    
    def test_set_value(self):
        c = profig.Config()
        c.init('c', 1)
        
        c.section('a').set_value(2)
        self.assertEqual(c['a'], 2)
        
        c.section('b').set_value('3')
        self.assertEqual(c['b'], '3')
        
        # .init does not enforce types
        c.section('c').set_value('4')
        self.assertEqual(c['c'], '4')
    
    def test_set_default(self):
        c = profig.Config()
        c.init('c', 1)
        
        c.section('a').set_default(2)
        self.assertEqual(c['a'], 2)
        
        c.section('b').set_default('3')
        self.assertEqual(c['b'], '3')
        
        # .init does not enforce types
        c.section('c').set_default('4')
        self.assertEqual(c['c'], '4')
    
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
        #self.assertEqual(c.as_dict(convert=False),
            #{'a': {'': '1', 'a': '1'}, 'b': '1'})
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 1, 'b': 1})
        #self.assertEqual(c.as_dict(flat=True, convert=False),
            #{'a': '1', 'a.a': '1', 'b': '1'})
    
    def test_reset(self):
        c = profig.Config(dict_type=dict)
        c.init('a', 1)
        c.init('a.a', 1)
        c['a'] = 2
        c['a.a'] = 2
        
        self.assertEqual(c.as_dict(flat=True), {'a': 2, 'a.a': 2})
        
        c.section('a').reset(recurse=False)
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 2})
        
        c.section('a').reset()
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 1})
        
        c['a'] = 2
        c['a.a'] = 2
        
        c.reset()
        self.assertEqual(c.as_dict(flat=True), {'a': 1, 'a.a': 1})

class TestIniFormat(unittest.TestCase):
    def setUp(self):
        self.c = profig.Config(format='ini')

        self.c.init('a', 1)
        self.c.init('b', 'value')
        self.c.init('a.1', 2)

    def test_basic(self):
        del self.c['a.1']

        buf = io.BytesIO()
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), b"""\
[a] = 1

[b] = value
""")
    
    def test_sync_read_blank(self):
        c = profig.Config(format='ini')
        buf = io.BytesIO(b"""\
[b] = value

[a] = 1
1 = 2
""")
        c.sync(buf)
        
        self.assertEqual(c['a'], '1')
        self.assertEqual(c['b'], 'value')
        self.assertEqual(c['a.1'], '2')
    
    def test_subsection(self):
        buf = io.BytesIO()
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), b"""\
[a] = 1
1 = 2

[b] = value
""")

    def test_preserve_order(self):
        buf = io.BytesIO(b"""\
[a] = 1
1 = 2

[b] = value
""")
        self.c['a.1'] = 3
        self.c['a'] = 2
        self.c['b'] = 'test'
        
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), b"""\
[a] = 2
1 = 3

[b] = test
""")
    
    def test_preserve_comments(self):
        buf = io.BytesIO(b"""\
;a comment
[a] = 1
; another comment
1 = 2

; yet more comments?
[b] = value
;arrrrgh!
""")
        self.c['a.1'] = 3
        self.c['a'] = 2
        self.c['b'] = 'test'
        
        self.c.sync(buf)
        
        self.assertEqual(buf.getvalue(), b"""\
; a comment
[a] = 2
; another comment
1 = 3

; yet more comments?
[b] = test
;arrrrgh!
""")
    
    def test_binary_read(self):
        fd, temppath = tempfile.mkstemp()
        try:
            with io.open(fd, 'wb') as file:
                file.write(b"""\
[a] = \x00binary\xff
b = also\x00binary\xff
""")
            
            c = profig.Config(temppath, format='ini')
            c.init('a', b'')
            c.init('a.b', b'')
            c.read()
            
            self.assertEqual(c['a'], b'\x00binary\xff')
            self.assertEqual(c['a.b'], b'also\x00binary\xff')
        finally:
            os.remove(temppath)
    
    def test_binary_write(self):
        fd, temppath = tempfile.mkstemp()
        try:
            c = profig.Config(temppath, format='ini')
            
            c['a'] = b'\x00binary\xff'
            c.write()
            
            with io.open(fd, 'rb') as file:
                result = file.read()
            
            self.assertEqual(result, b"""\
[a] = \x00binary\xff
""")
        finally:
            os.remove(temppath)
    
    def test_unicode_read(self):
        fd, temppath = tempfile.mkstemp()
        try:
            with io.open(fd, 'wb') as file:
                file.write(b"""\
[\xdc] = \xdc
""")
            
            c = profig.Config(temppath, format='ini', encoding='shiftjis')
            c.read()
            
            self.assertEqual(c['\uff9c'], '\uff9c')
        finally:
            os.remove(temppath)
    
    def test_unicode_write(self):
        fd, temppath = tempfile.mkstemp()
        try:
            c = profig.Config(temppath, format='ini', encoding='shiftjis')
            
            c['\uff9c'] = '\uff9c'
            c.write()
            
            with io.open(fd, 'rb') as file:
                result = file.read()
            
            self.assertEqual(result, b"""\
[\xdc] = \xdc
""")
        finally:
            os.remove(temppath)
    
    def test_repeated_values(self):
        c = profig.Config(format='ini')
        buf = io.BytesIO(b"""\
[a]
b = 1
b = 2
""")
        c.sync(buf)
        
        self.assertEqual(c['a.b'], '2')
        self.assertEqual(buf.getvalue(), b"""\
[a]
b = 2
""")
        
        c['a.b'] = '3'
        c.sync(buf)
        
        self.assertEqual(buf.getvalue(), b"""\
[a]
b = 3
""")
    
    def test_repeated_sections(self):
        c = profig.Config(format='ini')
        buf = io.BytesIO(b"""\
[a]
b = 1
b = 2

[b]
a = 1

[a]
b = 3
""")
        c.sync(buf)
        
        self.assertEqual(c['a.b'], '3')    
        self.assertEqual(buf.getvalue(), b"""\
[a]
b = 3

[b]
a = 1
""")

class TestCoercer(unittest.TestCase):
    def test_list_value(self):
        c = profig.Config()
        c.init('colors', ['red', 'blue'])
        
        buf = io.BytesIO()
        c.sync(buf)
        
        self.assertEqual(buf.getvalue(), b"""\
[colors] = red,blue
""")
    
    def test_path_value(self):
        c = profig.Config()
        c.init('paths', ['path1', 'path2'], 'path_list')
        
        buf = io.BytesIO()
        c.sync(buf)
        
        self.assertEqual(buf.getvalue(), """\
[paths] = path1{sep}path2
""".format(sep=os.pathsep).encode('ascii'))
        
        buf = io.BytesIO("""\
[paths] = path1{sep}path2{sep}path3
""".format(sep=os.pathsep).encode('ascii'))
        c.sync(buf)
        self.assertEqual(c['paths'], ['path1', 'path2', 'path3'])
    
    def test_choice(self):
        c = profig.Config()
        c.coercer.register_choice('color', {1: 'red', 2: 'green', 3: 'blue'})
        c.init('color', 1, 'color')
        
        buf = io.BytesIO()
        c.sync(buf)
        self.assertEqual(buf.getvalue(), b"""\
[color] = red
""")
        
        buf = io.BytesIO(b"""\
[color] = blue
""")
        c.sync(buf)
        self.assertEqual(c['color'], 3)
        
        c['color'] = 4
        with self.assertRaises(profig.AdaptError):
            c.write(buf)
    
    def test_not_exist_error(self):
        c = profig.Config()
        c.init('value', [], 'notexist')
        
        buf = io.BytesIO()
        with self.assertRaises(profig.NotRegisteredError):
            c.write(buf)
        
        c.init('value', [])
        c['value'] = 3
        with self.assertRaises(profig.AdaptError):
            c.write(buf)
        
        c.reset(clean=True)
        c.init('value', 1)
        buf = io.BytesIO(b"""[value] = badvalue""")
        with self.assertRaises(profig.ConvertError):
            c.read(buf)

class TestErrors(unittest.TestCase):
    def test_ReadError(self):
        c = profig.Config()
        c._format.read_errors = 'exception'
        
        buf = io.BytesIO(b"""a""")
        with self.assertRaises(profig.ReadError):
            c.sync(buf)

class TestMisc(unittest.TestCase):
    def test_NoValue(self):
        self.assertEqual(repr(profig.NoValue), 'NoValue')
    
    def test_get_source(self):
        path = os.path.dirname(__file__)
        self.assertEqual(profig.get_source('test'), os.path.join(path, 'test'))

if profig.WIN:
    class TestRegistryFormat(unittest.TestCase):
        def setUp(self):
            self.base_key = winreg.HKEY_CURRENT_USER
            self.path = r'Software\_profig_test'
            self.key = winreg.CreateKeyEx(self.base_key, self.path, 0,
                winreg.KEY_ALL_ACCESS)
            
            self.c = profig.Config(self.path, format='registry')
        
        def tearDown(self):
            self.c._format.delete(self.key)
    
        def test_basic(self):
            c = self.c
            c.init('a', 1)
            c.init('a.a', 2)
            c.init('c', u'str')
            
            c.sync()
            
            k = winreg.OpenKeyEx(self.base_key, self.path)
            self.assertEqual(winreg.QueryValueEx(k, 'c')[0], u'str')
            
            k = winreg.OpenKeyEx(k, 'a')
            self.assertEqual(winreg.QueryValueEx(k, '')[0], 1)
            self.assertEqual(winreg.QueryValueEx(k, 'a')[0], 2)
        
        def test_sync_read_blank(self):
            key = winreg.CreateKeyEx(self.key, 'a')
            winreg.SetValueEx(key, '', 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, '1', 0, winreg.REG_DWORD, 2)
            key = winreg.CreateKeyEx(self.key, 'b')
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'value')
            
            c = self.c
            c.read()
            
            self.assertEqual(c['a'], 1)
            self.assertEqual(c['a.1'], 2)
            self.assertEqual(c['b'], 'value')
        
        def test_sync_blank(self):
            # in this test, the value for b will be read from
            # '_profig_test\b\(Default)', but will be written back
            # to '_profig_test\b'. 'b' has no children, so it's considered
            # a root-level value.
            key = winreg.CreateKeyEx(self.key, 'a')
            winreg.SetValueEx(key, '', 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, '1', 0, winreg.REG_DWORD, 2)
            key = winreg.CreateKeyEx(self.key, 'b')
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, 'value')
            
            c = self.c
            c.sync()
            
            self.assertEqual(c['a'], 1)
            self.assertEqual(c['a.1'], 2)
            self.assertEqual(c['b'], 'value')
        
        def test_binary_read(self):
            key = winreg.CreateKeyEx(self.key, 'a')
            winreg.SetValueEx(key, '', 0, winreg.REG_BINARY, b'\x00binary\xff')
            key = winreg.CreateKeyEx(key, 'b')
            winreg.SetValueEx(key, '', 0, winreg.REG_BINARY, b'also\x00binary\xff')
            
            c = self.c
            c.init('a', b'')
            c.init('a.b', b'')
            c.read()
            
            self.assertEqual(c['a'], b'\x00binary\xff')
            self.assertEqual(c['a.b'], b'also\x00binary\xff')
        
        def test_binary_write(self):
            c = self.c
            c['a'] = b'\x00binary\xff'
            c.write()
            
            value = winreg.QueryValueEx(self.key, 'a')[0]
            self.assertEqual(value, b'\x00binary\xff')
        
        def test_unicode_read(self):
            key = winreg.CreateKeyEx(self.key, '\uff9c')
            winreg.SetValueEx(key, '', 0, winreg.REG_SZ, '\uff9c')
            
            c = self.c
            c.init('\uff9c', '')
            c.read()
            
            self.assertEqual(c['\uff9c'], '\uff9c')
        
        def test_unicode_write(self):
            c = self.c
            c['\uff9c'] = '\uff9c'
            c.write()
            
            value = winreg.QueryValueEx(self.key, '\uff9c')[0]
            self.assertEqual(value, '\uff9c')

if __name__ == '__main__':
    unittest.main()
