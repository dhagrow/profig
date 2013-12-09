import config

cfg = config.Config()
cfg['server.host'] = '8.8.8.8'
cfg['server.port'] = 8181

cfg.sync('app.cfg')

# Initialization

cfg = config.Config('app.cfg')

cfg.init('server.host', '127.0.0.1')
cfg.init('server.port', 8080, int)

cfg.sync()

print(cfg.asdict())
