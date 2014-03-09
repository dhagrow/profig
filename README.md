fig
===

*fig* is a configuration management library for Python.

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
* Built-in support for INI, JSON, and Pickle.
* Easily extensible input/output formats.

Example
-------

Basic usage is cake::
    
    >>> cfg = fig.Config('server.cfg')
    >>> cfg.init('server.host', 'localhost')
    >>> cfg.init('server.port', 8080)
    >>> cfg.sync()
    >>> cfg['server.host']
    '192.168.1.1'
    >>> cfg.section('server')['port']
    9090
