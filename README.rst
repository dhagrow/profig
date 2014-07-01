*profig* is a configuration library for Python.

.. image:: https://travis-ci.org/dhagrow/profig.svg?branch=master
    :target: https://travis-ci.org/dhagrow/profig

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
* Section nesting.
* Dict-like access.
* Extensible input/output formats.
* Built-in support for INI files and the Windows registry.
* Preserves ordering and comments of INI files.
* Supports Python 2.7+ and 3.2+.

Installation
------------

*profig* installs using *easy_install* or *pip*::
    
    $ pip install profig

Example
-------

Basic usage is cake. Let's assume our config file looks like this::
    
    [server]
    host = 192.168.1.1
    port = 9090

First, we specify the defaults and types to expect::
    
    >>> cfg = profig.Config('server.cfg')
    >>> cfg.init('server.host', 'localhost')
    >>> cfg.init('server.port', 8080)

Then, we sync our current state with the state of the config file::

    >>> cfg.sync()

As expected, we can access the values directly without any extra effort, either
directly::

    >>> cfg['server.host']
    '192.168.1.1'

Or by section::
    
    >>> server_cfg = cfg.section('server')
    >>> server_cfg['port']
    9090

Resources
----------

* Documentation_
* PyPI_
* Repository_

.. _Documentation: http://profig.rtfd.org/
.. _PyPI: https://pypi.python.org/pypi/profig
.. _Repository: https://bitbucket.org/dhagrow/profig
