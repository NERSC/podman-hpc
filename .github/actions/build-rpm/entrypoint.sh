#!/bin/sh -l

SRPM=podman-hpc.srpm

echo "Hello $1. I am SRPM!" > $SRPM

echo source_rpm_path=$(pwd)/$SRPM >> $GITHUB_OUTPUT
echo source_rpm_name=$SRPM >> $GITHUB_OUTPUT
