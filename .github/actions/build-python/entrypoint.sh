#/bin/sh -l

# echo the entrypoint as it runs
set -x

DIST=dist

python3 -m build --outdir $DIST

echo python_dist=$DIST >> $GITHUB_OUTPUT
