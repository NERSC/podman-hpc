#!/bin/sh -l

PACKAGE=python.package

echo "Hello $1" > $PACKAGE

echo wheel_path=$(pwd)/$PACKAGE >> $GITHUB_OUTPUT
echo wheel_name=$PACKAGE >> $GITHUB_OUTPUT
