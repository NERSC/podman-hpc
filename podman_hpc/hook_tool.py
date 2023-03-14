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
from glob import glob

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
    subprocess.check_output(["mount", "--bind", src, tgt])


def ldconfig():
    if not os.path.exists("/sbin/ldconfig"):
        return
    ret = "unknown"
    try:
        ret = subprocess.check_output(["/sbin/ldconfig"])
    except subprocess.CalledProcessError:
        log(f"ldconfig failed: {ret}")


def resolve_src(src, modulesd=os.path.abspath("")):
    if not os.path.isabs(src):
        src = os.path.join(modulesd, src)
    return os.path.abspath(os.path.expandvars(src))


def do_plugin(rp, mod, modulesd):
    """
    set up to do copies and bind mounts
    handle wildcards appropriately
    """
    log(f"Module: {mod}")

    # handle the copy case
    for f in mod["copy"]:
        (src, tgt) = f.split(":")
        src = resolve_src(src, modulesd)
        if '*' in src:
            for fp in glob(src):
                # fp is the full path + filename
                # we also need just the filename, fn
                fn = os.path.basename(fp)
                # let's prepare the target paste path in the container
                paste_path = os.path.join(rp, tgt[1:], fn)
                paste_dir = os.path.dirname(paste_path)
                if not os.path.exists(paste_dir):
                    os.makedirs(paste_dir)
                log(f"Copying: {fp} to {paste_path}")
                # in copyfile src and dst are full paths
                shutil.copyfile(fp, paste_path, follow_symlinks=False)
        else:
            paste_path = os.path.join(rp, tgt[1:])
            paste_dir = os.path.dirname(paste_path)
            if not os.path.exists(paste_dir):
                os.makedirs(paste_dir)
            log(f"Copying {src} to {paste_path}")
            shutil.copyfile(src, paste_path, follow_symlinks=False)

    # handle the bind case
    for f in mod["bind"]:
        (src, tgt) = f.split(":")
        src = resolve_src(src, modulesd)
        if '*' in src:
            for fp in glob(src):
                bind_path = os.path.join(rp, fp[1:])
                log(f"mounting: {fp} to {bind_path}")
                bind_mount(fp, bind_path)
        else:
            bind_path = os.path.join(rp, tgt[1:])
            log(f"mounting: {src} to {bind_path}")
            bind_mount(src, bind_path)


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
