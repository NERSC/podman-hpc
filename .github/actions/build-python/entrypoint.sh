#!/bin/sh -l

DIST=dist

python3 -m build --outdir $DIST

echo python_dist=$DIST >> $GITHUB_OUTPUT

