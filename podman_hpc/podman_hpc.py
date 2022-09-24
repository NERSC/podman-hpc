#!/usr/bin/python3 -s

import argparse
import os
import sys
from copy import deepcopy
from .migrate2scratch import migrate_image, remove_image
from .migrate2scratch import read_json, get_img_info
import toml


class config:
    """
    Config class
    """

    def __init__(self, squash_dir=None):
        self.uid = os.getuid()
        self.bin_dir = os.path.dirname(__file__)
        try:
            self.user = os.getlogin()
        except Exception:
            self.user = os.environ["USER"]
        self.xdg_base = "/tmp/%d_hpc" % (self.uid)
        self.run_root = self.xdg_base
        self.graph_root = "%s/storage" % (self.xdg_base)
        squash_default = "%s/storage" % (os.environ["SCRATCH"])
        self.squash_dir = os.environ.get("SQUASH_DIR", squash_default)
        if squash_dir:
            self.squash_dir = squash_dir
        home_def = self.bin_dir.replace("/bin", "")
        self.podman_base = os.environ.get("PODMAN_HPC_HOME", home_def)
        self.podman_bin = which("podman")
        self.hooks = os.path.join(self.podman_base, 'hooks.d')
        self.mount_program = os.path.join(self.bin_dir, 'fuse-overlayfs-wrap')
        self.conmon_bin = os.path.join(self.bin_dir, 'conmon')
        self.runtime = 'crun'
        self.options = []

    def get_default_store_conf(self):
        return {'storage': {
                   'driver': 'overlay',
                   'graphroot': self.graph_root,
                   'runroot': self.run_root,
                   'options': {
                       'size': '',
                       'remap-uids': '',
                       'remap-gids': '',
                       'ignore_chown_errors': 'true',
                       'remap-user': '',
                       'remap-group': '',
                       'mount_program': self.mount_program,
                       'mountopt': '',
                       'overlay': {}
                    }
                  }
                }

    def get_default_containers_conf(self):
        return {'engine': {
                    'hooks_dir': [self.hooks],
                    'conmon_path': [self.conmon_bin],
                  },
                'containers': {
                    'seccomp_profile': 'unconfined',
                    'runtime': self.runtime
                  }
                }

    def get_config_home(self):
        return "%s/config" % (self.xdg_base)


def which(bin):
    for p in os.environ["PATH"].split(":"):
        fpath = os.path.join(p, bin)
        if os.path.exists(fpath):
            return fpath
    return None


def mpich(data):
    """
    MPICH handler
    """
    cmd = []
    lpath = "/opt/udiImage/modules/mpich:/opt/udiImage/modules/mpich/dep"
    env_add = ["SLURM_*",
               "PALS_*",
               "PMI_*",
               "LD_LIBRARY_PATH={}".format(lpath)
               ]
    if os.path.exists("/dev/xxxinfiniband"):
        env_add.append("ENABLE_MPICH=1")
    else:
        env_add.append("ENABLE_MPICH_SS=1")
    for en in env_add:
        cmd.append("-e")
        cmd.append(en)
    cmd.append("--ipc=host")
    cmd.append("--network=host")
    cmd.append("--privileged")
    cmd.append("--pid=host")
    return data, cmd


def gpu(data):
    """
    GPU handler
    """
    if not os.path.exists("/dev/nvidia0"):
        return data, []
    if "CUDA_VISIBLE_DEVICES" not in os.environ:
        sys.stderr.write("WARNING: CUDA_VISIBLE_DEVICES not set.\n")
        sys.stderr.write("         GPU Support may not function\n\n")
    cmd = ["-e", "NVIDIA_VISIBLE_DEVICES"]
    cmd.extend(["-e", "ENABLE_GPU=1"])
    return data, cmd


def _write_conf(fn, data, conf, overwrite=False):
    """
    Write out a conf file
    """
    cdir = "/tmp/containers-user-%d/containers" % (conf.uid)
    os.makedirs(cdir, exist_ok=True)
    os.makedirs("%s/containers" % (conf.get_config_home()), exist_ok=True)
    fp = os.path.join(conf.get_config_home(), "containers", fn)
    if not os.path.exists(fp) or overwrite:
        with open(fp, "w") as f:
            toml.dump(data, f)


def config_storage(conf, additional_stores=None):
    """
    Create a storage conf object
    """
    stor_conf = conf.get_default_store_conf()
    opt = stor_conf["storage"]["options"]
    if "additionalimagestores" not in stor_conf["storage"]["options"]:
        stor_conf["storage"]["options"]["additionalimagestores"] = []
    opt["additionalimagestores"].append(conf.squash_dir)
    if additional_stores:
        for loc in additional_stores.split(","):
            opt["additionalimagestores"].append(loc)

    return stor_conf


def config_containers(conf, args):
    """
    Create a container conf object
    """
    cont_conf = conf.get_default_containers_conf()
    cmds = []
    if args.gpu:
        _, cmd = gpu(cont_conf)
        conf.options.append("gpu")
        cmds.extend(cmd)
    if args.mpich:
        _, cmd = mpich(cont_conf)
        conf.options.append("mpi")
        cmds.extend(cmd)
    cont_conf["containers"]["seccomp_profile"] = "unconfined"
    return cont_conf, cmds


def conf_env(conf, hpc):
    """
    Generate the environment setup
    """

    new_env = deepcopy(os.environ)
    if hpc:
        new_env["XDG_CONFIG_HOME"] = conf.get_config_home()
        if "XDG_RUNTIME_DIR" in new_env:
            new_env.pop("XDG_RUNTIME_DIR")
    new_env["PATH"] = "%s/bin:%s" % (conf.podman_base, new_env["PATH"])
    return new_env


def check_image(conf, image):
    """
    Get image info from squash area
    """

    imgs = read_json(conf.squash_dir, "images")
    return get_img_info(image, imgs)


def get_params(args):
    """
    Try to extract the podman command and image name
    """

    comm = None
    image = None
    for arg in args:
        if arg.startswith("-"):
            continue
        if comm:
            image = arg
            break
        comm = arg
    return comm, image


def main():
    parser = argparse.ArgumentParser(prog='podman-hpc', add_help=False)
    parser.add_argument("--gpu", action="store_true",
                        help="Enable gpu support")
    parser.add_argument("--mpich", action="store_true",
                        help="Enable mpich support")
    parser.add_argument("--hpc", action="store_true",
                        help="Enable hpc support")
    parser.add_argument("--additional-stores", type=str,
                        help="Specify other storage locations")
    parser.add_argument("--squash-dir", type=str,
                        help="Specify alternate squash directory location")
    parser.add_argument("--update-conf", action="store_true",
                        help="Force update of storage conf")
    args, podman_args = parser.parse_known_args()
    comm, image = get_params(podman_args)
    conf = config(squash_dir=args.squash_dir)

    if len(podman_args) > 0 and podman_args[0].startswith("mig"):
        image = podman_args[1]
        migrate_image(image, conf.squash_dir)
        sys.exit()

    # Generate Configs
    stor_conf = config_storage(conf, additional_stores=args.additional_stores)
    cont_conf, cmds = config_containers(conf, args)
    overwrite = False
    if args.additional_stores or args.squash_dir or args.update_conf:
        overwrite = True
    _write_conf("storage.conf", stor_conf, conf, overwrite=overwrite)
    _write_conf("containers.conf", cont_conf, conf)

    # Prepare podman exec
    env = conf_env(conf, True)
    podman_args.insert(0, conf.podman_bin)
    ll_set = False
    for arg in podman_args:
        if arg.startswith("--log-level"):
            ll_set = True
    if not ll_set:
        cmds.extend(["--log-level", "fatal"])

    if comm == "run":
        start = podman_args.index("run") + 1
        for idx, item in enumerate(cmds):
            podman_args.insert(start + idx, item)
        os.execve(conf.podman_bin, podman_args, env)
        sys.exit()
    elif comm == "pull":
        # If pull, then pull and migrate
        pid = os.fork()
        if pid == 0:
            os.execve(conf.podman_bin, podman_args, os.environ)
        pid, status = os.wait()
        if status == 0:
            print("INFO: Migrating image to %s" % (conf.squash_dir))
            migrate_image(image, conf.squash_dir)
        else:
            sys.stderr.write("Pull failed\n")
    elif comm == "rmi":
        remove_image(image, conf.squash_dir)
    else:
        os.execve(conf.podman_bin, podman_args, env)


if __name__ == "__main__":
    main()
