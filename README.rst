profig
===

*profig* is a configuration library for Python.

Motivation
----------

Why another configuration library? The simple answer is that none of the
available options gave me everything I wanted, with an API that I enjoyed using.
This library is as close to my ideal as I have been able to come. It tries
to provide some (but not too much) powerful functionality, without sacrificing
ease-of-use.

Features
--------

* Automatic value conversion.
* Simple section nesting.
* Dict-like access.
* Easily extensible input/output formats.

Installation
------------

*profig* installs easily using *easy_install* or *pip*::
    
    $ pip install figpy

NOTE: The package exists as figpy_ on PyPI due to a naming conflict. The
installed package name is *profig*.

Example
-------

Basic usage is cake. Assuming our config file looks like this (INI formatting
is also supported)::
    
    server.host: 192.168.1.1
    server.port: 9090

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

.. _figpy: https://pypi.python.org/pypi/figpy
.. _PyPI: https://pypi.python.org/pypi/figpy
.. _Repository: https://bitbucket.org/dhagrow/profig
.. _Documentation: http://profig.rtfd.org/
