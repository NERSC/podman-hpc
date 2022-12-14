#!/usr/bin/env python

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
    """ Filter invalid arguments from an argument list 
    for a given podman subcommand based on its --help text. """
    # extract valid flags from subcommand help text, and populate an arg parser
    opt_regex = re.compile("^\s*(?:(-\w), )?(--\w[\w\-]+)(?:\s(\w+))?")
    p = argparse.ArgumentParser(exit_on_error=False)
    with os.popen(' '.join([podman_bin,subcommand,'--help'])) as f:
        for line in f:
            opt = opt_regex.match(line)
            if opt:
                action = 'store' if opt.groups()[2] else 'store_true'
                flags = [flag for flag in opt.groups()[:-1] if flag]
                p.add_argument(*flags,action=action)
    # remove unknown args from the podman_args
    subcmd_args = podman_args.copy()
    unknowns = p.parse_known_args(subcmd_args)[1]
    uk_safe={} # indices of valid args that string== unknowns
    while unknowns:
        ukd={} # candidate indices of where to remove unknowns
        for uk in set(unknowns):
            ukd[uk]=[idx for idx,arg in enumerate(subcmd_args) if (arg==uk and idx not in uk_safe.get(uk,[]))]
        uk=unknowns.pop(0) 
        # find and remove an invalid occurence of uk
        while True:
            args_tmp = subcmd_args.copy()
            args_tmp.pop(ukd[uk][0])
            try:
                if p.parse_known_args(args_tmp)[1]==unknowns:
                    subcmd_args.pop(ukd[uk][0])
                    break
            except argparse.ArgumentError:
                pass
            uk_safe.setdefault(uk,[]).append(ukd[uk].pop(0))
    return [podman_bin,subcommand]+subcmd_args


def shared_run_args(podman_args,image,container_name='hpc'):
    """ Construct argument list for `podman run` and `podman exec`
    by filtering flags passed to `podman shared-run` """
    print("calling shared_run_args with podman_args:")
    print(f"\t{podman_args}")
    
    # generate valid subcommands from the given podman_args
    prun =filter_podman_subcommand(podman_args[0],'run',podman_args)
    pexec=filter_podman_subcommand(podman_args[0],'exec',podman_args)

    prun[2:2] = ['--rm','-d','-v','/global/homes/d/dfulton/repos/podman-hpc/bin/exec-wait:/bin/exec-wait','--name',container_name]
    prun.extend([image,'/bin/exec-wait'])
    pexec[2:2] = ['-e','"PALS_*"','-e','"PMI_*"','-e','"SLURM_*"','--log-level','fatal']
    pexec.extend([container_name])
    pexec.extend(podman_args[podman_args.index(image)+1:])

    print(f"podman run command:\n\t{prun}")
    print(f"podman exec command:\n\t{pexec}")

    return prun, pexec

def shared_run_launch(localid,run_cmd,env):
    """ helper to break out of an if block """
    if localid and localid!=0:
        return
    pid = os.fork()
    if pid==0:
        os.execve(run_cmd[0],run_cmd,env)
    return pid

def main():
    parser = argparse.ArgumentParser(prog='podman-hpc', add_help=False)
    parser.add_argument("--additional-stores", type=str,
                        help="Specify other storage locations")
    parser.add_argument("--squash-dir", type=str,
                        help="Specify alternate squash directory location")
    parser.add_argument("--update-conf", action="store_true",
                        help="Force update of storage conf")
    confs = read_confs()
    add_args(parser, confs)
    args, podman_args = parser.parse_known_args()
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
        localid_var = os.environ.get("PODMAN_HPC_LOCALID_VAR","SLURM_LOCALID")
        localid = os.environ.get(localid_var)

        container_name = f"uid-{os.getuid()}-pid-{os.getppid()}"
        run_cmd, exec_cmd = shared_run_args(podman_args,image,container_name)

        shared_run_launch(localid,run_cmd,os.environ)

        # wait for the named container to start (maybe convert this to python instead of bash)
        os.system(f'while [ $(podman --log-level fatal ps -a | grep {container_name} | grep -c Up) -eq 0 ] ; do sleep 0.2')
        os.execve(exec_cmd[0], exec_cmd, os.environ)

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
            mu.migrate_image(image)
        else:
            sys.stderr.write("Pull failed\n")
    elif comm == "rmi":
        mu.remove_image(image)
    else:
        os.execve(conf.podman_bin, podman_args, env)


if __name__ == "__main__":
    main()