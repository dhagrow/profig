#!/usr/bin/env python

import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import profig

BASE_DIR = os.path.dirname(__file__)
README_PATH = os.path.join(BASE_DIR, 'README.rst')
DESCRIPTION = open(README_PATH).read()

setup(
    name='profig',
    version=profig.__version__,
    description='A configuration library.',
    long_description=DESCRIPTION,
    author=profig.__author__,
    author_email='cymrow@gmail.com',
    url='https://github.com/dhagrow/profig',
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
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        ],
    )
