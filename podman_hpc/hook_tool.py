#!/usr/bin/python3
import ctypes
import ctypes.util
import os
import sys
import errno
import subprocess
import json
import yaml
import shutil
import re
from glob import glob, iglob

_MOD_ENV = "PODMANHPC_MODULES_DIR"

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
_libc.mount.argtypes = (
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_char_p,
    ctypes.c_ulong,
    ctypes.c_char_p,
)
logger = None


def log(msg):
    if logger:
        logger.write(f"{msg}\n")


def setns(pid, ns):
    """
    Attach to a namespace using the pid
    ns = ["mnt", "pid", "net", ...]
    """
    pth = f"/proc/{pid}/ns/{ns}"
    tgt = open(pth, "r")
    if _libc.setns(tgt.fileno(), 0) == -1:
        e = ctypes.get_errno()
        raise OSError(e, errno.errorcode[e])


def bind_mount(src, tgt):
    """
    bind mount a file into a namespace.
    """
    # Create mount point
    if os.path.isdir(src) and not os.path.exists(tgt):
        os.makedirs(tgt)
    elif not os.path.exists(tgt):
        open(tgt, "w").close()
    subprocess.check_output(["mount", "--rbind", src, tgt])


def copy(src, tgt, symlinks=True):
    if os.path.isdir(src):
        shutil.copytree(
            src,
            tgt,
            symlinks=symlinks,
            copy_function=shutil.copyfile,
            dirs_exist_ok=True,
        )
    else:
        shutil.copyfile(src, tgt, follow_symlinks=(not symlinks))


def ldconfig():
    if not os.path.exists("/sbin/ldconfig"):
        return
    ret = "unknown"
    try:
        ret = subprocess.check_output(["/sbin/ldconfig"])
    except subprocess.CalledProcessError:
        log(f"ldconfig failed: {ret}")


def resolve_src_and_dest(rule, root_path, modulesd=os.path.abspath("")):
    # extract source and destination patterns from the rule
    rs, rd = (rule + ":").split(":")[:2]

    # expand vars
    rs = os.path.expanduser(os.path.expandvars(rs))
    rd = os.path.expanduser(os.path.expandvars(rd))

    # ensure source pattern is absolute path
    if not os.path.isabs(rs):
        rs = os.path.join(modulesd, rs)
    rs = os.path.abspath(os.path.expanduser(os.path.expandvars(rs)))

    # error checks
    if not os.path.isabs(rd):
        log(
            f"Error: Destination in pattern must be an absolute path.\n\tdestination: {rd}"
        )
        return {}
    if "*" in rd:
        if rs.count("*") != 1:
            log(
                "Error: Using glob '*' in destination requires exactly one glob '*' in source."
                f"\n\tsource: {rs}\n\tdestination: {rd}"
            )
            return {}
        else:
            # this is used to capture the glob expansion later
            globstrip = "^{}|{}$".format(*rs.split("*"))

    # determine how to construct absolute path to destination object
    # if no destination rule is given, use the path from source rule
    if rd == "":
        dest = lambda src: os.path.join(root_path, src[1:])
    # if the destination rule reuses the glob pattern, trailing path separator
    # determines if it interpreted as a directory or obj name
    elif "*" in rd and rd[-1] == os.path.sep:
        dest = lambda src: os.path.join(
            root_path,
            rd.replace("*", re.sub(globstrip, "", src))[1:],
            os.path.basename(src),
        )
    elif "*" in rd and rd[-1] != os.path.sep:
        dest = lambda src: os.path.join(
            root_path, rd.replace("*", re.sub(globstrip, "", src))[1:]
        )
    # if we glob multiple sources, interpret destination as a directory, and append shortest unique path
    elif 1 < len(glob(rs)):
        common_prefix = os.path.commonpath(glob(rs))
        dest = lambda src: os.path.join(
            root_path, rd[1:], os.path.relpath(src, common_prefix)
        )
    # otherwise, trailing path separator determines whether destination is interpreted as a directory
    elif rd[-1] == os.path.sep:
        dest = lambda src: os.path.join(
            root_path, rd[1:], os.path.basename(src)
        )
    else:
        dest = lambda src: os.path.join(root_path, rd[1:])

    return {src: os.path.normpath(dest(src)) for src in iglob(rs)}


def do_plugin(rp, mod, modulesd):
    """
    set up to do copies and bind mounts
    handle wildcards appropriately
    """
    log(f"Module: {mod}")

    actions = {"copy": copy, "bind": bind_mount}

    for a in actions:
        for rule in mod.get(a) or []:
            log(f"\t{rule}")
            for src, tgt in resolve_src_and_dest(rule, rp, modulesd).items():
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                log(f"\t\t{a}: {src} to {tgt}")
                actions[a](src, tgt)


def read_confs(mdir):
    confs = {}
    for d in glob(f"{mdir}/*.yaml"):
        conf = yaml.load(open(d), Loader=yaml.FullLoader)
        confs[conf["name"]] = conf
    return confs


def main():
    global logger

    inp = json.load(sys.stdin)
    pid = inp["pid"]
    cf = json.load(open("config.json"))
    cf_env = {}
    # initialize with any values set in the hook env configuration
    cf_env.update(os.environ)
    for e in cf["process"]["env"]:
        k, v = e.split("=", maxsplit=1)
        cf_env[k] = v

    plug_conf_fn = cf_env.get(
        _MOD_ENV, f"{sys.prefix}/etc/podman_hpc/modules.d"
    )
    plug_conf = read_confs(plug_conf_fn)

    lf = cf_env.get("LOG_PLUGIN")
    if lf:
        logger = open(lf, "w")
    log("input")
    log(json.dumps(inp, indent=2))
    log("config.json")
    log(json.dumps(cf, indent=2))
    rp = cf["root"]["path"]

    setns(pid, "mnt")
    os.chroot("/")
    log(json.dumps(plug_conf, indent=2))
    for m in plug_conf:
        if plug_conf[m]["env"] in cf_env:
            log(f"Loading {m}")
            do_plugin(rp, plug_conf[m], plug_conf_fn)
    ret = os.chroot(rp)
    log(f"chroot return: {ret}")

    ldconfig()


if __name__ == "__main__":
    main()
