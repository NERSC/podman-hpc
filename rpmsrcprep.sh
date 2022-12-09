#!/bin/bash

SOURCES=$(rpmbuild --eval="%{_sourcedir}")

# source dir is first arg, or defaults to current working directory
DIRECTORY=${1:-`pwd`}
BASENAME=$(basename $DIRECTORY)

# try to detect a .spec file in source dir
cd $DIRECTORY
shopt -s nullglob
NAMEDSPECS=(*$BASENAME.spec)
ALLSPECS=(*.spec)
: "${SPEC:=${NAMEDSPECS[0]}}"
: "${SPEC:=${ALLSPECS[0]}}"
shopt -u nullglob

# extract name, version, source archive from .spec file
NAME=$(rpmspec -q --qf "%{name}" $SPEC 2>/dev/null)
VERSION=$(rpmspec -q --qf "%{version}" $SPEC 2>/dev/null)
ARCHIVE=$(rpmspec --srpm -q --qf "%{source}" $SPEC 2>/dev/null)

# write the archive
mkdir -p $SOURCES
cd ..
tar \
  --exclude-vcs --exclude-vcs-ignore \
  --transform "s/${BASENAME}/${NAME}-${VERSION}/" \
  -cvaf $SOURCES/$ARCHIVE ${BASENAME}
