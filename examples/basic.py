import io
import config

c = config.Config()
c.format = config.IniFormat()

c.init('config value', 3, float)
c.init('a.b.c', 3.4, int)
c['asdf'] = 234

c._dump()

buf = io.StringIO()
c.sync(buf)
print(buf.getvalue())

print(c.section('a.b'))
print(c)
