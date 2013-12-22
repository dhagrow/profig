import config

print('--[Config()]--')
cfg = config.Config()
cfg['server.host'] = '8.8.8.8'
cfg['server.port'] = 8181

print('--[sync(app.cfg)]--')
print(cfg.asdict())
cfg.sync('app.cfg')
print(cfg.asdict())

print('--[app.cfg]--')
print(open('app.cfg').read())

# Initialization

print('--[Config(app.cfg, app2.cfg)]--')
cfg = config.Config('app.cfg', 'app2.cfg')

cfg.init('server.host', '127.0.0.1')
cfg.init('server.port', 8080, int)
cfg.init('server.ssl', False, bool)

print('--[sync()]--')
print(cfg.asdict())
cfg.sync()
print(cfg.asdict())

print('--[app.cfg]--')
print(open('app.cfg').read())
print('--[app2.cfg]--')
print()

print('--[Config(app.cfg, app2.cfg)]--')
cfg = config.Config('app.cfg', 'app2.cfg')
cfg['server.host'] = '1.1.1.1'
cfg['server.ssl'] = True

print('--[sync(app2.cfg)]--')
print(cfg.asdict())
cfg.sync('app2.cfg')
print(cfg.asdict())

print('--[app.cfg]--')
print(open('app.cfg').read())

print('--[app2.cfg]--')
print(open('app2.cfg').read())

print('--[sync]--')
print(cfg.asdict())
cfg.sync()
print(cfg.asdict())

cfg['server.host'] = '2.2.2.2'

print('--[sync]--')
print(cfg.asdict())
cfg.sync()
print(cfg.asdict())

print('--[app.cfg]--')
print(open('app.cfg').read())

print('--[app2.cfg]--')
print(open('app2.cfg').read())
