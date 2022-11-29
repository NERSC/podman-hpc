# Podman-HPC

Podman-HPC (`podman-hpc`) is a wrapper script around the Pod Manager (`podman`) container engine,
which provides HPC configuration and infrastructure for the Podman ecosystem at NERSC.

## Prerequisites
1. `podman` should be installed separately, per the instructions at https://podman.io/

## Site Installation
It is recommended that `podman-hpc` is installed site-wide in a multi-user HPC center.
To build and deploy an RPM using this repo:
1. `git clone https://github.com/NERSC/podman-hpc`
1. `cd podman-hpc`
1. `./rpmsrcprep.sh`
1. `rpmbuild -ba podman-hpc.spec`
1. Deploy resulting RPM as usual.
1. Add/edit site modules as required in `/etc/podman_hpc/modules.d`

## Developer Installation
The `podman-hpc` package is bundled as a python package and may be installed
in an isolated python environment for development or testing.

1. `git clone https://github.com/NERSC/podman-hpc`
1. `cd podman-hpc`
1. `pip install .`
1. `python -m podman_hpc.configure_hooks`

