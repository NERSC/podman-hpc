#!/bin/sh -l

# build python packages
DIST=dist
python3 -m build --outdir $DIST

# build SRPM and RPM
BUILDRPM_ROOT=/usr/src/packages
cp $DIST/*.tar.gz $(rpmbuild --eval="%{_sourcedir}")/
rpmbuild -ba podman-hpc.spec

echo python_dist=$DIST >> $GITHUB_OUTPUT
echo rpm_dir=$BUILDRPM_ROOT/RPMS >> $GITHUB_OUTPUT
echo srpm_dir=$BUILDRPM_ROOT/SRPMS >> $GITHUB_OUTPUT
