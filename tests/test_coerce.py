import unittest

import config

class TestCoercer(unittest.TestCase):
    def test_default(self):
        c = config.Coercer()
        
        values = [
            (1, '1', type(1)),
            ('s', 's', type('s')),
            (b's', '73', type(b's')),
            ]
        
        for v, s, t in values:
            self.assertEqual(s, c.adapt(v))
            self.assertEqual(s, c.adapt(v, t))
            self.assertEqual(v, c.convert(s, t))

if __name__ == '__main__':
    unittest.main()
