#!/usr/bin/env python

from distutils.core import setup

import os
import sys
import unittest


setup_dir = os.path.dirname(sys.argv[0])
if setup_dir:
  os.chdir(setup_dir)

bindir = os.path.join(sys.prefix, 'bin')
sharedir = os.path.join(sys.prefix, 'share', 'gitman')

with open('VERSION') as f:
    version = f.readline().rstrip()

setup(name='gitman',
    version=version,
    description='Gitman',
    packages=['Gitman'],
    py_modules=['ansi',],
    data_files=[(bindir, ['gitman']), (sharedir, ['COPYING'])])

