profig
======

*profig* is a configuration library for Python.

Motivation
----------

Why another configuration library? The simple answer is that none of the
available options gave me everything I wanted, with an API that I enjoyed using.
This library is as close to my ideal as I have been able to come. It tries
to provide some (but not too much) powerful functionality, without sacrificing
simplicity.

Features
--------

* Automatic value conversion.
* Simple section nesting.
* Dict-like access.
* Easily extensible input/output formats.
* Preserves ordering and comments of config files.

Installation
------------

*profig* installs easily using *easy_install* or *pip*::
    
    $ pip install profig

Example
-------

Basic usage is cake. Assuming our config file looks like this::
    
    [server]
    host = 192.168.1.1
    port = 9090

First we specify the defaults and types to expect::
    
    >>> cfg = profig.Config('server.cfg')
    >>> cfg.init('server.host', 'localhost')
    >>> cfg.init('server.port', 8080)

Then we sync our current state with the state of the config file::

    >>> cfg.sync()

Then we can access the values directly without any extra effort, either
directly::

    >>> cfg['server.host']
    '192.168.1.1'

Or by section::
    
    >>> server_cfg = cfg.section('server')
    >>> server_cfg['port']
    9090

Resources
---------

* PyPI_
* Repository_
* Documentation_

.. _PyPI: https://pypi.python.org/pypi/profig
.. _Repository: https://bitbucket.org/dhagrow/profig
.. _Documentation: http://profig.rtfd.org/

