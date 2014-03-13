fig
===

*fig* is a configuration library for Python.

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

*fig* installs easily using *easy_install* or *pip*::
    
    $ pip install figpy

NOTE: The package exists as figpy_ on PyPI due to a naming conflict. The
installed package name is *fig*.

Example
-------

Basic usage is cake::
    
    >>> import fig
    >>> cfg = fig.Config('server.cfg')
    >>> cfg.init('server.host', 'localhost')
    >>> cfg.init('server.port', 8080)
    >>> cfg.sync()
    >>> cfg['server.host']
    '192.168.1.1'
    >>> cfg.section('server')['port']
    9090

Resources
---------

* PyPI_
* Repository_
* Documentation_

.. _figpy: https://pypi.python.org/pypi/figpy
.. _PyPI: https://pypi.python.org/pypi/figpy
.. _Repository: https://bitbucket.org/dhagrow/fig
.. _Documentation: http://fig.rtfd.org/
