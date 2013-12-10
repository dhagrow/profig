import config

cfg = config.Config()
cfg['server.host'] = '8.8.8.8'
cfg['server.port'] = 8181

cfg.sync('app.cfg')

# Initialization

cfg = config.Config(['app.cfg', 'app2.cfg'])
cfg.flags['write_unset_values'] = False

cfg.init('server.host', '127.0.0.1')
cfg.init('server.port', 8080, int)
cfg.init('server.ssl', False, bool)

cfg.sync()
print(cfg.asdict())

c = config.Config()
c['server.host'] = '1.1.1.1'
c['server.ssl'] = True
c.sync('app2.cfg')

cfg.sync()
print(cfg.asdict())
