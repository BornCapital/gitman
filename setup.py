#!/usr/bin/env python

from distutils.core import setup

import os
import sys
import unittest


setup_dir = os.path.dirname(sys.argv[0])
if setup_dir:
  os.chdir(setup_dir)

def run_test(mod):
  if os.system('python tests/%s.py' % mod):
    raise RuntimeError('Test Failed: ' + mod)

tests = ['acl_ut']

tests_failed = False
for test in tests:
  try:
    run_test(test)
  except Exception as e:
    tests_failed = True
print '\n*******************************\n\n'

if not tests_failed:
  bindir = os.path.join(sys.prefix, 'bin')

  setup(name='gitman',
        version='0.9',
        description='Gitman',
        packages=['Gitman'],
        py_modules=['ansi',],
        data_files=[(bindir, ['gitman'])])

