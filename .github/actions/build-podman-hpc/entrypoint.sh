#!/bin/sh -l

# build python packages
DIST=dist
pip3 install .
python3 -m build --outdir $DIST

# build SRPM and RPM
OLD_VER=$(grep Version: podman-hpc.spec|sed 's/.* //')
VER=$(grep __version__.= podman_hpc/podman_hpc.py|sed 's/.*=..//'|sed 's/.$//')
sed -i "s/${OLD_VER}/${VER}/" podman-hpc.spec

RPMBUILD_TOPDIR=$(rpmbuild --eval="%{_topdir}")
cp $DIST/*.tar.gz $RPMBUILD_TOPDIR/SOURCES/
rpmbuild -ba podman-hpc.spec
mv $RPMBUILD_TOPDIR/SRPMS ./
mv $RPMBUILD_TOPDIR/RPMS ./


echo python_dist=$DIST >> $GITHUB_OUTPUT
echo srpm_dir=SRPMS >> $GITHUB_OUTPUT
echo rpm_dir=RPMS >> $GITHUB_OUTPUT
