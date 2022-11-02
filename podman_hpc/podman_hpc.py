#!/usr/bin/python3 -s

import argparse
import os
import sys
import re
import warnings
from copy import deepcopy
from .migrate2scratch import MigrateUtils
import toml
from shutil import which
from glob import glob
import yaml


_MOD_ENV = "PODMAN_MODULES_DIR"


class config:
    """
    Config class
    """

    def __init__(self, squash_dir=None):
        self.uid = os.getuid()
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
        self.podman_bin = which("podman")
        if self.podman_bin is None:
            warnings.warn("No podman binary found in path! Please install podman.", stacklevel=2)
            self.podman_bin="podman"
        self.mount_program = which('fuse-overlayfs-wrap')
        self.conmon_bin = which('conmon')
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
                    'conmon_path': [self.conmon_bin],
                  },
                'containers': {
                    'seccomp_profile': 'unconfined',
                    'runtime': self.runtime
                  }
                }

    def get_config_home(self):
        return "%s/config" % (self.xdg_base)


# def mpich(data):
#     """
#     MPICH handler
#     """
#     cmd = []
#     lpath = "/opt/udiImage/modules/mpich:/opt/udiImage/modules/mpich/dep"
#     env_add = ["SLURM_*",
#                "PALS_*",
#                "PMI_*",
#                "LD_LIBRARY_PATH={}".format(lpath)
#                ]
#     if os.path.exists("/dev/xxxinfiniband"):
#         env_add.append("ENABLE_MPICH=1")
#     else:
#         env_add.append("ENABLE_MPICH_SS=1")
#     for en in env_add:
#         cmd.append("-e")
#         cmd.append(en)
#     cmd.append("--ipc=host")
#     cmd.append("--network=host")
#     cmd.append("--privileged")
#     cmd.append("--pid=host")
#     return data, cmd


# def gpu(data):
#     """
#     GPU handler
#     """
#     if not os.path.exists("/dev/nvidia0"):
#         return data, []
#     if "CUDA_VISIBLE_DEVICES" not in os.environ:
#         sys.stderr.write("WARNING: CUDA_VISIBLE_DEVICES not set.\n")
#         sys.stderr.write("         GPU Support may not function\n\n")
#     cmd = ["-e", "NVIDIA_VISIBLE_DEVICES"]
#     cmd.extend(["-e", "ENABLE_GPU=1"])
#     return data, cmd


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


def config_containers(conf, args, confs):
    """
    Create a container conf object
    """
    cont_conf = conf.get_default_containers_conf()
    cmds = []
    for mod, mconf in confs.items():
        cli_arg = mconf['cli_arg']
        if vars(args).get(cli_arg):
            cmds.extend(mconf.get("additional_args", []))
            cmds.extend(["-e", "%s=1" % (mconf['env'])])

    # if args.gpu:
    #     _, cmd = gpu(cont_conf)
    #     conf.options.append("gpu")
    #     cmds.extend(cmd)
    # if args.mpi:
    #     _, cmd = mpich(cont_conf)
    #     conf.options.append("mpi")
    #     cmds.extend(cmd)
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
    return new_env


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
    print(f"comm is: {comm}")
    print(f"image is: {image}")
    return comm, image


def read_confs():

    mdir = os.environ.get(_MOD_ENV, "/etc/podman_hpc/modules.d")
    confs = {}
    for d in glob(f"{mdir}/*.yaml"):
        conf = yaml.load(open(d), Loader=yaml.FullLoader)
        confs[conf['name']] = conf
    return confs


def add_args(parser, confs):
    for k, v in confs.items():
        parser.add_argument("--%s" % (v["cli_arg"]), action="store_true",
                            help=v.get("help"))


def filter_podman_subcommand(podman_bin, subcommand, podman_args):
    argflag = re.compile("^\s*(?:(-\w), )?(--\w[\w\-]+)")
    with os.popen(' '.join([podman_bin,subcommand,'--help'])) as helpstream:
        valid_flags = [flag for line in helpstream if argflag.match(line) for flag in argflag.match(line).groups() if flag]

    arg = re.compile("(?<!\S)(?:-\w|--\w[\w\-]+)(?:\s+(?:[^-\'\"\s]\S+|\"[^\"]*\"|\'[^\']*\'))?")
    return ' '.join([podman_bin,subcommand]+[a for a in arg.findall(' '.join(podman_args)) if a.split()[0] in valid_flags]).split()


def shared_run_args(podman_args,image,container_name='hpc'):
    print("calling shared_run_args with podman_args:")
    print(f"\t{podman_args}")
    
    # generate valid subcommands from the given podman_args
    prun =filter_podman_subcommand(podman_args[0],'run',podman_args)
    pexec=filter_podman_subcommand(podman_args[0],'exec',podman_args)

    prun[2:2] = ['--rm','-d','--name',container_name]
    prun.extend([image,'/path/to/exec-wait.o'])
    pexec[2:2] = ['-e','"PALS_*"','-e','"PMI_*"','-e','"SLURM_*"','--log-level','fatal']
    pexec.extend([container_name])

    print(f"podman run command:\n\t{prun}")
    print(f"podman exec command:\n\t{pexec}")

    return prun, pexec


def main(cmd_str=None):
    parser = argparse.ArgumentParser(prog='podman-hpc', add_help=False)
    parser.add_argument("--additional-stores", type=str,
                        help="Specify other storage locations")
    parser.add_argument("--squash-dir", type=str,
                        help="Specify alternate squash directory location")
    parser.add_argument("--update-conf", action="store_true",
                        help="Force update of storage conf")
    confs = read_confs()
    add_args(parser, confs)
    args, podman_args = parser.parse_known_args(cmd_str.split() if cmd_str else None)
    print(f"known args (podman-hpc) are: {args}")
    print(f"unknown args (podman) are  : {podman_args}")
    if "--help" in podman_args:
        parser.print_help()
    comm, image = get_params(podman_args)
    conf = config(squash_dir=args.squash_dir)
    mu = MigrateUtils(dst=conf.squash_dir)

    if len(podman_args) > 0 and podman_args[0].startswith("mig"):
        image = podman_args[1]
        mu.migrate_image(image, conf.squash_dir)
        sys.exit()

    # Generate Configs
    stor_conf = config_storage(conf, additional_stores=args.additional_stores)
    cont_conf, cmds = config_containers(conf, args, confs)

    overwrite = False
    if args.additional_stores or args.squash_dir or args.update_conf:
        overwrite = True
    _write_conf("storage.conf", stor_conf, conf, overwrite=overwrite)

    # Prepare podman exec
    env = conf_env(conf, True)
    podman_args.insert(0, conf.podman_bin)
    ll_set = False

    for arg in podman_args:
        if arg.startswith("--log-level"):
            ll_set = True
    if not ll_set:
        cmds.extend(["--log-level", "fatal"])

    if comm == "shared-run":
        localid = os.environ["SLURM_LOCALID"]
        container_name = f"uid-{os.getuid()}-pid-{os.getppid()}"
        run_cmd, exec_cmd = shared_run_args(podman_args,image,container_name)

        if localid == 0: # or race for it
            pid = os.fork()
            if pid == 0:
                os.execve(run_cmd[0],run_cmd,os.environ)
        # wait for the named container to start (maybe convert this to python instead of bash)
        os.system(f'while [ $(podman --log-level fatal ps -a | grep {container_name} | grep -c Up) -eq 0 ] ; do sleep 0.2')
        os.execve(exec_cmd[0], exec_cmd, os.environ)

    if comm == "run":
        start = podman_args.index("run") + 1
        for idx, item in enumerate(cmds):
            podman_args.insert(start + idx, item)
        #os.execve(conf.podman_bin, podman_args, env)
        sys.exit()
    elif comm == "pull":
        # If pull, then pull and migrate
        pid = os.fork()
        if pid == 0:
            pass #os.execve(conf.podman_bin, podman_args, os.environ)
        pid, status = os.wait()
        if status == 0:
            print("INFO: Migrating image to %s" % (conf.squash_dir))
            #mu.migrate_image(image)
        else:
            sys.stderr.write("Pull failed\n")
    elif comm == "rmi":
        pass #mu.remove_image(image)
    else:
        pass #os.execve(conf.podman_bin, podman_args, env)


if __name__ == "__main__":
    main()
