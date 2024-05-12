# Podman-HPC

Podman-HPC (`podman-hpc`) is a wrapper script around the Pod Manager (`podman`) container engine,
which provides HPC configuration and infrastructure for the Podman ecosystem at NERSC.

## Configuration

The wrapper can be configured through a configuration file and environment variables.
The order of precedence from lowest to highest is:

1. built-in defaults
1. configuration file template (if a template is allowed)
1. environment variable template (if a template is allowed)
1. configuration file
1. enviornment variables

The enviornment variable override is the configuration parameter in upper case prefixed
with PODMANHPC_ (e.g. podman_bin becomes PODMANHPC_PODMAN_BIN).

The list of configurable values is:
* podman_bin: (str) path to the podman binary (default: podman)
* mount_program: (str) path the mount_program wrapper (default: fuse-overlayfs-wrap)
* modules_dir: (str) directory of podman-hpc modules
* shared_run_exec_args: (str) additional arguments passed to the exec command when using shared_run mode (default: None)
* shared_run_command: (list) command to run in the shared_run container (default: sleep infinity)
* graph_root: (str) directory for the graph root (default: /tmp/{uid}_hpc/storage)
* run_root: (str) directory for the run root (default: /tmp/{uid}_hpc)
* use_default_args: (bool) default True. User can set to False to turn off all defaults, and must provide all settings themselves.
* additional_stores: (list) additional storage areas
* hooks_dir: (str) directory for hooks. Note: this should have the podman_hpc hooks tool configured.
* config_home: (str) directory where the generated configuration files will be written and XDG_CONFIG_HOME will be set.
* localid_var: (str) environment variable to determine the local node rank (default: `SLURM_LOCALID`)
* tasks_per_node_var: (str) environment variable to determine the tasks per node (default: `SLURM_STEP_TASKS_PER_NDOE`)
* ntasks_pattern: (str) regular expression pattern to filter the tasks per node (default: `[0-9]+`)
* wait_timeout: (str) timeout in seconds to wait for a shared-run container to start (default: 10)
* wait_poll_interval: (str) interval in seconds to poll for a shared-run container to start (default: 0.2)

### Templating

Some parameters can be set using a template.  The template is set by the parameter with `_template` appended to the parameter to
be templated (e.g. graph_root_template would be used to generate the value for the graph_root parameter).

The template replaces strings with `{{ variable }}` with the approriate value. The following variables are supported.
* uid: replaced with the user id of the calling user
* user: replaced with the user name of the calling user
* env.VARIABLE: replaced with the value of the environment `VARIABLE`.  For example, env.HOME would be replaced with the value of `HOME`.

## Prerequisites
1. `podman` should be installed separately, per the instructions at https://podman.io/
2. User namespaces and, ideally, subuid/gid support should be enabled for the users.  This typically requires some local customization for managing this configuration.

## Site Installation
It is recommended that `podman-hpc` is installed site-wide in a multi-user HPC center.
To build and deploy an RPM using this repo:
1. `git clone https://github.com/NERSC/podman-hpc`
1. `cd podman-hpc`
1. `./rpmsrcprep.sh`
1. `rpmbuild -ba podman-hpc.spec`
1. Deploy resulting RPM as usual.
1. (Optional) Add/edit site modules as required in `/etc/podman_hpc/modules.d`

## Developer Installation
The `podman-hpc` package is bundled as a python package and may be installed
in an isolated python environment for development or testing.

1. `git clone https://github.com/NERSC/podman-hpc`
1. `cd podman-hpc`
1. `pip install .`
1. `python -m podman_hpc.configure_hooks`
1. (Optional) Add/edit site modules as required in `<podman-hpc python sys.prefix>/etc/podman_hpc/modules.d`

