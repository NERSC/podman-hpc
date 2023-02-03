#!/bin/sh -l

# build python packages
DIST=dist
python3 -m build --outdir $DIST

# build SRPM and RPM
RPMBUILD_TOPDIR=$(rpmbuild --eval="%{_topdir}")
cp $DIST/*.tar.gz $RPMBUILD_TOPDIR/SOURCES/
rpmbuild -ba podman-hpc.spec

echo python_dist=$DIST >> $GITHUB_OUTPUT
echo rpmbuild_topdir=$RPMBUILD_TOPDIR >> $GITHUB_OUTPUT
echo srpm_dir=$RPMBUILD_TOPDIR/SRPMS >> $GITHUB_OUTPUT
echo rpm_dir=$RPMBUILD_TOPDIR/RPMS >> $GITHUB_OUTPUT
