# Podman-hpc

Future home of infrastructure developed to help
the Podman container ecosystem run at NERSC.

## conda env install
```
conda create -n podman-hpc python
source activate podman-hpc
git clone github.com/nersc/podman-hpc
pip install podman-hpc
python -m podman_hpc.configure_hooks
```
