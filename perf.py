from __future__ import print_function

import timeit
import profig

setup = """\
import string
import profig
c = profig.Config()
c.use_cache = {}
c.init('a', list(string.ascii_letters for i in range(100)))
"""

def main():
    n = 10000
    
    print('convert: cache')
    t = timeit.timeit("c['a']", setup.format(True), number=n)
    print('  t = {:.4f}s'.format(t))
    
    print('convert: no cache')
    t = timeit.timeit("c['a']", setup.format(False), number=n)
    print('  t = {:.4f}s'.format(t))

if __name__ == '__main__':
    main()
