#!/usr/bin/env python

import sys
import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import profig

setup(
    name='profig',
    version=profig.__version__,
    description='A configuration library.',
    long_description=open('README.rst').read(),
    author=profig.__author__,
    author_email='cymrow@gmail.com',
    url='https://bitbucket.org/dhagrow/profig/',
    py_modules=['profig'],
    license=profig.__license__,
    platforms='any',
    keywords=['config', 'configuration', 'options', 'settings'],
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Software Development :: Libraries',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        ],
    )
