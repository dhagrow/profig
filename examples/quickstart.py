import config

print('Sync')
print('====')

print('--[Config()]--')
cfg = config.Config()
cfg['server.host'] = '8.8.8.8'
cfg['server.port'] = 8181
print(cfg.as_dict())

print('--[sync(app.cfg)]--')
cfg.sync('app.cfg')
print(cfg.as_dict())

print('>>app.cfg<<')
print(open('app.cfg').read())

# Unitialized sync

print()
print('Uninitialized Sync')
print('==================')

open('app.cfg', 'w+').write("""\
server.host: 127.0.0.1
server.port: 8080
""")

cfg.sync('app.cfg')
print(cfg.as_dict())

# Initialization

print()
print('Initialization')
print('==============\n')

print('--[Config(app.cfg, app2.cfg)]--')
cfg = config.Config('app.cfg', 'app2.cfg')

cfg.init('server.host', '127.0.0.1')
cfg.init('server.port', 8080, int)
cfg.init('server.ssl', False, bool)

print('--[sync()]--')
print(cfg.as_dict())
cfg.sync()
print(cfg.as_dict())

print('>>app.cfg<<')
print(open('app.cfg').read())
print('>>app2.cfg<<')
print()

print('--[Config(app.cfg, app2.cfg)]--')
cfg = config.Config('app.cfg', 'app2.cfg')
cfg['server.host'] = '1.1.1.1'
cfg['server.ssl'] = True

print('--[sync(app2.cfg)]--')
print(cfg.as_dict())
cfg.sync('app2.cfg')
print(cfg.as_dict())

print('>>app.cfg<<')
print(open('app.cfg').read())

print('>>app2.cfg<<')
print(open('app2.cfg').read())

print('--[sync]--')
print(cfg.as_dict())
cfg.sync()
print(cfg.as_dict())

cfg['server.host'] = '2.2.2.2'

print('--[sync]--')
print(cfg.as_dict())
cfg.sync()
print(cfg.as_dict())

print('>>app.cfg<<')
print(open('app.cfg').read())

print('>>app2.cfg<<')
print(open('app2.cfg').read())
