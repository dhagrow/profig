import config

c = config.Config()
c['server.host'] = '127.0.0.1'
c['server.port'] = 8080

c.sync('app.ini', config.IniFormat())
