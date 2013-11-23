import io
import config

c = config.Config()

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
c.format = config.IniFormat()
c.sync(buf)
print(buf.getvalue())
print('len:', len(buf.getvalue()))

print('\nJsonFormat')
buf = io.StringIO()
c.format = config.JsonFormat()
c.sync(buf)
print(buf.getvalue())
print('len:', len(buf.getvalue()))

print('\nConfigFormat')
buf = io.StringIO()
c.format = config.ConfigFormat()
c.sync(buf)
print(buf.getvalue())
print('len:', len(buf.getvalue()))

print('\nPickleFormat')
buf = io.BytesIO()
c.format = config.PickleFormat()
c.sync(buf)
print(repr(buf.getvalue()))
print('len:', len(buf.getvalue()))
