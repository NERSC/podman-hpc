import sys
import os
import shutil
import toml
import yaml
from copy import deepcopy
from glob import glob

_MOD_ENV = "PODMANHPC_MODULES_DIR"
_HOOKS_ENV = "PODMANHPC_HOOKS_DIR"
_HOOKS_ANNO = "podman_hpc.hook_tool"


class SiteConfig:
    """
    Class to represent site specific configurations for Podman-HPC.
    """

    def __init__(self, squash_dir=None, log_level=None):
        self.uid = os.getuid()
        try:
            self.user = os.getlogin()
        except Exception:
            self.user = os.environ["USER"]
        self.xdg_base = f"/tmp/{self.uid}_hpc"
        self.run_root = self.xdg_base
        self.graph_root = f"{self.xdg_base}/storage"
        self.squash_dir = squash_dir or os.environ.get(
            "SQUASH_DIR", f'{os.environ["SCRATCH"]}/storage'
        )
        self.modules_dir = os.environ.get(
            _MOD_ENV, "/etc/podman_hpc/modules.d"
        )
        self.podman_bin = self.trywhich("podman")
        self.mount_program = self.trywhich("fuse-overlayfs-wrap")
        self.conmon_bin = self.trywhich("conmon")
        try:
            self.runtime = self.trywhich("crun")
        except OSError:
            self.runtime = self.trywhich("runc")
        self.options = []
        self.log_level = log_level

    @staticmethod
    def trywhich(cmd, *args, **kwargs):
        res = shutil.which(cmd, *args, **kwargs)
        if res is None:
            raise OSError(
                f"No {cmd} binary found in {kwargs.get('path','PATH')}"
            )
        return res

    def get_default_store_conf(self):
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
        return {
            "engine": {
                "cgroup_manager": "cgroupfs",
            },
            "containers": {
                "seccomp_profile": "unconfined",
            },
        }

    def get_config_home(self):
        return f"{self.xdg_base}/config"

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
        """
        new_env = deepcopy(os.environ)
        if hpc:
            new_env["XDG_CONFIG_HOME"] = self.get_config_home()
            new_env.pop("XDG_RUNTIME_DIR", None)
        self.env = new_env

    def _write_conf(self, filename, data, overwrite=False):
        """
        Write out a conf file
        """
        os.makedirs(
            f"/tmp/containers-user-{self.uid}/containers", exist_ok=True
        )
        os.makedirs(f"{self.get_config_home()}/containers", exist_ok=True)
        fp = os.path.join(self.get_config_home(), "containers", filename)
        if not os.path.exists(fp) or overwrite:
            with open(fp, "w") as f:
                toml.dump(data, f)

    def export_storage_conf(self, filename="storage.conf", overwrite=False):
        self._write_conf(filename, self.storage_conf, overwrite=overwrite)

    def export_containers_conf(
        self, filename="containers.conf", overwrite=False
    ):
        self._write_conf(filename, self.container_conf, overwrite=overwrite)

    def get_cmd_extensions(self, subcommand, args):
        cmds = []
        if subcommand == "run":
            cmds.extend(
                [
                    "--hooks-dir",
                    os.environ.get(
                        _HOOKS_ENV,
                        f"{sys.prefix}/share/containers/oci/hooks.d",
                    ),
                    "-e",
                    f"{_MOD_ENV}={self.modules_dir}",
                    "--annotation",
                    f"{_HOOKS_ANNO}=true",
                ]
            )
        for mod, mconf in self.sitemods.get(subcommand, {}).items():
            cli_arg = mconf["cli_arg"].replace("-", "_")
            if args.get(cli_arg, False):
                cmds.extend(mconf.get("additional_args", []))
                cmds.extend(["-e", f"{mconf['env']}=1"])
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
        for modfile in glob(f"{self.modules_dir}/*.yaml"):
            mod = yaml.load(open(modfile), Loader=yaml.FullLoader)
            mods[mod["name"]] = mod
        self.sitemods = {"run": mods, "shared-run": mods}
