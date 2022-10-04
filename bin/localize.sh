#!/bin/bash

TGT=/tmp/$(id -u)_hpc/podman

if [ $(echo $0|grep -c localize) -eq 0 ] ; then
	ME=/global/common/shared/das/podman/bin/localize.sh
else
	ME=$0
fi

localize () {
	echo "Syncing $(hostname)"
	ORIG=/global/common/shared/das/podman/
	BDIR=$(dirname $ME|sed 's/.bin//')
	echo $BDIR
	mkdir -p $TGT
	rsync -az \
             --exclude __pycache__ \
             --exclude attic \
             --exclude conf/ \
             $BDIR/ $TGT/

	for f in $(grep -lr $ORIG $TGT) ; do
	    sed -i "s|$ORIG|$TGT/|" $f
	done
}

if [ -z $SLURM_NODEID ] ; then
	localize
        echo "Set PATH PATH=${TGT}/bin:\$PATH"
        PATH=${TGT}/bin:$PATH
elif [ ! -z $SLURM_CPU_BIND ] ; then
	localize
else
	echo "Doing srun"
	srun -N $SLURM_NNODES -n $SLURM_NNODES $0
        echo "Set PATH PATH=${TGT}/bin:\$PATH"
        PATH=${TGT}/bin:$PATH
fi
