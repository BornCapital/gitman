#!/bin/bash

set -e

release=1

if [ $# -eq 0 ]; then
  echo "Usage: $0 [release-number]"
  exit 1
elif [ $# -ge 1 ]; then
  release=$1
fi

rm -rf dist
export PYTHONPATH=`pwd`:$PYTHONPATH
./setup.py clean bdist_rpm --release=${release}

