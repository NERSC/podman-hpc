import sys
import os
import shutil
import toml
import re
from yaml import load
from yaml import FullLoader
from copy import deepcopy
from glob import glob

_ENV_PREFIX = "PODMANHPC"
_MOD_ENV = f"{_ENV_PREFIX}_MODULES_DIR"
_HOOKS_ANNO = "podman_hpc.hook_tool"
_CONF_ENV = f"{_ENV_PREFIX}_CONFIG_FILE"


class SiteConfig:
    """
    Class to represent site specific configurations for Podman-HPC.

    Precedence order lowest to highest:
    - Built-in defaults
    - Config file
    - Environment variables
    """

    _default_conf_file = "/etc/podman_hpc/podman_hpc.yaml"
    _valid_params = ["podman_bin", "mount_program", "modules_dir",
                     "shared_run_exec_args", "shared_run_command",
                     "graph_root", "run_root",
                     "additional_stores", "hooks_dir",
                     "localid_var", "tasks_per_node_var", "ntasks_pattern",
                     "config_home", "mksquashfs_bin",
                     "wait_timeout", "wait_poll_interval",
                     "use_default_args",
                     ]
    _valid_templates = ["shared_run_args_template",
                        "graph_root_template",
                        "run_root_template",
                        "additional_stores_template",
                        "config_home_template"
                        ]
    _uid = os.getuid()
    _xdg_base = f"/tmp/{_uid}_hpc"
    config_home = f"{_xdg_base}/config"
    run_root = _xdg_base
    additional_stores = []
    hooks_dir = f"{sys.prefix}/share/containers/oci/hooks.d"
    graph_root = f"{_xdg_base}/storage"
    squash_dir = os.environ.get(
        "SQUASH_DIR", f'{os.environ.get("SCRATCH", "/tmp")}/storage'
    )
    modules_dir = "/etc/podman_hpc/modules.d"
    shared_run_exec_args = ["-e", "SLURM_*", "-e", "PALS_*", "-e", "PMI_*"]
    use_default_args = True
    shared_run_command = ["sleep", "infinity"]
    podman_bin = "podman"
    mount_program = "fuse-overlayfs-wrap"
    runtime = "runc"
    localid_var = "SLURM_LOCALID"
    tasks_per_node_var = "SLURM_STEP_TASKS_PER_NODE"
    ntasks_pattern = r'[0-9]+'
    mksquashfs_bin = "mksquashfs.static"
    wait_poll_interval = 0.2
    wait_timeout = 10
    shared_run = False
    source = dict()

    def __init__(self, squash_dir=None, log_level=None):

        # getlogin may fail on a compute node
        try:
            self.user = os.getlogin()
        except Exception:
            self.user = os.environ["USER"]
        # TODO: move these as a test at the end
        self.podman_bin = self.trywhich("podman")
        self.mount_program = self.trywhich("fuse-overlayfs-wrap")
        try:
            self.runtime = self.trywhich("crun")
        except OSError:
            self.runtime = self.trywhich("runc")
        # self.options = []
        if squash_dir:
            self.squash_dir = squash_dir
        self.conf_file_data = {}
        self._read_config_file()
        for param in self._valid_templates:
            self._check_and_set(param)
        for param in self._valid_params:
            self._check_and_set(param)

        self.read_site_modules()

        if isinstance(self.wait_poll_interval, str):
            self.wait_poll_interval = \
                float(self.wait_poll_interval)
        if isinstance(self.wait_timeout, str):
            self.wait_timeout = float(self.wait_timeout)

        if self.use_default_args is True:
            self.default_args = [
                    "--root", self.graph_root,
                    "--runroot", self.run_root,
                    "--storage-opt",
                    f"mount_program={self.mount_program}",
                    "--cgroup-manager", "cgroupfs",
                    ]
            self.default_run_args = [
                    "--storage-opt",
                    "ignore_chown_errors=true",                    
                    "--storage-opt",
                    f"additionalimagestore={self.additionalimagestore()}",
                    "--hooks-dir", self.hooks_dir,
                    "--env", f"{_MOD_ENV}={self.modules_dir}",
                    "--annotation", f"{_HOOKS_ANNO}=true",
                    "--security-opt", "seccomp=unconfined",
                    ]
            self.default_build_args = [
                    "--hooks-dir", self.hooks_dir,
                    "--env", f"{_MOD_ENV}={self.modules_dir}",
                    "--annotation", f"{_HOOKS_ANNO}=true",
                    ]
            self.default_pull_args = [
                    "--storage-opt",
                    "ignore_chown_errors=true",
                    ]
            self.default_images_args = [
                    "--storage-opt",
                    f"additionalimagestore={self.additionalimagestore()}",
                    ]
        else:
            self.default_args = []
            self.default_run_args = []
            self.default_build_args = []
            self.default_pull_args = []
            self.default_images_args = []
        
        self.log_level = log_level

    def dump_config(self):
        """
        Debug method to dump the configuration
        """

        for param in self._valid_params + ["active_modules"]:
            val = getattr(self, param)
            source = ""
            if param in self.source:
                source = f" ({self.source[param]})"
            # source = self.source.get(param, "unknown")
            if isinstance(val, list):
                print(f"{param} {source}: (list)")
                for item in val:
                    print(f" - {item}")
            else:
                print(f"{param}{source}: {val}")

    @staticmethod
    def trywhich(cmd, *args, **kwargs):
        """
        Use which and raise an error if it can't be found.
        """
        res = shutil.which(cmd, *args, **kwargs)
        if res is None:
            raise OSError(
                f"No {cmd} binary found in {kwargs.get('path','PATH')}"
            )
        return res

    def _check_and_set(self, attr: str, envname=None, parname=None):
        """
        Helper function to apply the right precedence
        """
        source = "default"
        if not parname:
            parname = attr
        if not envname:
            uppar = attr.upper()
            envname = f"{_ENV_PREFIX}_{uppar}"

        setval = False
        if envname in os.environ:
            setval = True
            newval = os.environ[envname]
            source = f"env: {envname}"
        elif parname in self.conf_file_data:
            setval = True
            newval = self.conf_file_data[parname]
            source = f"file: {parname}"
        if setval and attr.endswith("_template"):
            setattr(self, attr, newval)
            newval = self._apply_template(newval)
            attr = attr.replace("_template", "")

        if setval:
            # Expand to a list if the type should be a list
            # Assumes a common seperated string
            if isinstance(getattr(self, attr), list) and \
               isinstance(newval, str):
                newval = newval.split(',')
            setattr(self, attr, newval)
            self.source[attr] = source
        else:
            if attr not in self.source:
                self.source[attr] = source

    def _apply_template(self, templ):
        """
        Helper function to convert templates
        """
        def _templ(val):
            val = val.replace("{{ user }}", self.user)
            val = val.replace("{{ uid }}", str(self._uid))
            for pat in re.findall(r'{{ env\.[A-Za-z0-9]+ }}', val):
                envname = pat.replace("{{ env.", "").replace(" }}", "")
                val = val.replace(pat, os.environ[envname])
            return val

        if isinstance(templ, list):
            newlist = []
            for item in templ:
                newlist.append(_templ(item))
            return newlist
        elif isinstance(templ, str):
            return _templ(templ)
        else:
            raise ValueError("Can handle template type")

    def _read_config_file(self):
        """
        Read the global config file
        """
        config_file = os.environ.get(_CONF_ENV, self._default_conf_file)
        if not os.path.exists(config_file):
            return
        self.conf_file_data = load(open(config_file), Loader=FullLoader)
        for p in self.conf_file_data:
            if p not in self._valid_params and p not in self._valid_templates:
                raise ValueError(f"Unrecongnized Option: {p}")

    def get_default_store_conf(self):
        """
        Generate a default storage conf object
        """
        return {
            "storage": {
                "driver": "overlay",
                "graphroot": self.graph_root,
                "runroot": self.run_root,
                "options": {
                    "size": "",
                    "remap-uids": "",
                    "remap-gids": "",
                    "ignore_chown_errors": "true",
                    "remap-user": "",
                    "remap-group": "",
                    "mount_program": self.mount_program,
                    "mountopt": "",
                    "overlay": {},
                },
            }
        }

    def get_default_containers_conf(self):
        """
        Generate a default containers conf object
        """
        return {
            "engine": {
                "cgroup_manager": "cgroupfs",
            },
            "containers": {
                "seccomp_profile": "unconfined",
            },
        }

    def additionalimagestore(self):
        ais = [self.squash_dir]
        ais.extend(self.additional_stores)
        return ','.join(ais)

    def config_storage(self, additional_stores=None):
        """
        Create a storage conf object
        """
        sc = self.get_default_store_conf()
        ais = sc["storage"]["options"].setdefault("additionalimagestores", [])
        ais.append(self.squash_dir)
        if additional_stores:
            ais.extend(additional_stores.split(","))
        self.storage_conf = sc

    def config_containers(self):
        """
        Create a container conf object
        """
        cc = self.get_default_containers_conf()
        self.container_conf = cc

    def config_env(self, hpc):
        """
        Generate the environment setup

        TODO: Redo this
        """
        new_env = deepcopy(os.environ)
        if hpc:
            new_env["XDG_CONFIG_HOME"] = self.config_home
            new_env.pop("XDG_RUNTIME_DIR", None)
        self.env = new_env

    def _write_conf(self, filename, data, overwrite=False):
        """
        Write out a conf file
        """
        os.makedirs(
            f"/tmp/containers-user-{self._uid}/containers", exist_ok=True
        )
        os.makedirs(f"{self.config_home}/containers", exist_ok=True)
        fp = os.path.join(self.config_home, "containers", filename)
        if not os.path.exists(fp) or overwrite:
            with open(fp, "w") as f:
                toml.dump(data, f)

    def export_storage_conf(self, filename="storage.conf", overwrite=False):
        """
        Write out the storage.conf file
        """
        self._write_conf(filename, self.storage_conf, overwrite=overwrite)

    def export_containers_conf(
        self, filename="containers.conf", overwrite=False
    ):
        """
        Write out the containers.conf file
        """
        self._write_conf(filename, self.container_conf, overwrite=overwrite)

    def get_cmd_extensions(self, subcommand, args):
        """
        Generate the podman command-line parameters

        subcomand: run, images, etc
        """
        cmds = []
        cmds.extend(self.default_args)
        if subcommand == "run":
            cmds.extend(self.default_run_args)
        elif subcommand == "build":
            cmds.extend(self.default_build_args)
        elif subcommand == "pull":
            cmds.extend(self.default_pull_args)
        elif subcommand == "images":
            cmds.extend(self.default_images_args)
        else:
            pass
        for mod, mconf in self.sitemods.get(subcommand, {}).items():
            if 'cli_arg' not in mconf:
                continue
            cli_arg = mconf["cli_arg"].replace("-", "_")
            if args.get(cli_arg, False):
                cmds.extend(mconf.get("additional_args", []))
                cmds.extend(["-e", f"{mconf['env']}=1"])
                if mconf.get("shared_run"):
                    self.shared_run = True
        if self.log_level:
            cmds.extend(["--log-level", self.log_level])
        return cmds

    # TODO - This manually indicates that site modules apply to podman
    # subcommand `run`, however we should bake this into yamls themselves
    # and then edit podman_hpc.siteconfig.SiteConfig.read_site_modules()
    # to parse appropriately.  This would allow adding site-specific default
    # flags for any podman subcommand.
    def read_site_modules(self):
        mods = {}
        active_mods = []
        for modfile in glob(f"{self.modules_dir}/*.yaml"):
            mod = load(open(modfile), Loader=FullLoader)
            mods[mod["name"]] = mod
            active_mods.append(modfile)
        self.active_modules = active_mods
        self.sitemods = {"run": mods, "shared-run": mods}
