#!/bin/sh -l

# build python packages
DIST=dist
python3 -m build --outdir $DIST

# build SRPM and RPM
RPMBUILD_TOPDIR=$(rpmbuild --eval="%{_topdir}")
cp $DIST/*.tar.gz $RPMBUILD_TOPDIR/SOURCES/
rpmbuild -ba podman-hpc.spec
mv $RPMBUILD_TOPDIR/SRPMS ./
mv $RPMBUILD_TOPDIR/RPMS ./


echo python_dist=$DIST >> $GITHUB_OUTPUT
echo srpm_dir=SRPMS >> $GITHUB_OUTPUT
echo rpm_dir=RPMS >> $GITHUB_OUTPUT
