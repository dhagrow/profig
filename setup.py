#!/usr/bin/env python

import sys
import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import config

setup(
    name='config',
    version=config.__version__,
    description='Configuration management.',
    long_description=config.__doc__,
    author=config.__author__,
    author_email='cymrow@gmail.com',
    url='http://config.dhagrow.org/',
    py_modules=['config'],
    license='MIT',
    platforms = 'any',
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Topic :: Software Development :: Libraries',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.2',
        'Programming Language :: Python :: 3.3',
        ],
    )
    