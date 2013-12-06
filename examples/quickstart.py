import config

cfg = config.Config()
cfg['server.host'] = '127.0.0.1'
cfg['server.port'] = 8080

cfg.sync('app.ini', config.IniFormat())
