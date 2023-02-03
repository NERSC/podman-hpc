#!/bin/sh -l

PACKAGE=python.package

set -x

echo "Hello $1" > $PACKAGE
ls

echo wheel_path=$(pwd)/$PACKAGE >> $GITHUB_OUTPUT
echo wheel_name=$PACKAGE >> $GITHUB_OUTPUT
