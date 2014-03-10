#!/usr/bin/env python

import sys
import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import fig

setup(
    name='figpy',
    version=fig.__version__,
    description='A configuration management library.',
    long_description=open('README.rst').read(),
    author=fig.__author__,
    author_email='cymrow@gmail.com',
    url='https://bitbucket.org/dhagrow/fig/',
    py_modules=['fig'],
    license='MIT',
    platforms = 'any',
    keywords=['config', 'configuration', 'options', 'settings'],
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
    