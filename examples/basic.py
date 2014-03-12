import io
import fig

c = fig.Config()

c.init('config value', 3, float)
c.init('a.b.c', 3.4, int)
c['asdf'] = 234

print('Root')
print(c)

print('\nSection')
print(c.section('a.b'))

print('\nDump')
c._dump()

print('\nIniFormat')
buf = io.StringIO()
c.set_format('ini')
c.sync(buf)
print(buf.getvalue())
print('len:', len(buf.getvalue()))

print('\nFigFormat')
buf = io.StringIO()
c.set_format('fig')
c.sync(buf)
print(buf.getvalue())
print('len:', len(buf.getvalue()))
