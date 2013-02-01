#!/usr/bin/env python

from distutils.core import setup

import os
import sys

setup_dir = os.path.dirname(sys.argv[0])
if setup_dir:
  os.chdir(setup_dir)

bindir = os.path.join(sys.prefix, 'bin')

setup(name='gitman',
      version='0.9',
      description='Gitman',
      packages=['Gitman'],
      py_modules=['ansi',],
      data_files=[(bindir, ['gitman'])])

