#!/usr/bin/python3
import ctypes
import ctypes.util
import os
import sys
import errno
import subprocess
import json
import yaml
from glob import glob
from shutil import copyfile

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
        logger.write("%s\n" % (msg))


def setns(pid, ns):
    """
    Attach to a namespace using the pid
    ns = ["mnt", "pid", "net", ...]
    """
    pth = "/proc/%s/ns/%s" % (pid, ns)
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
    log(f"Module: {mod}")
    for f in mod["copy"]:
        (src, tgt) = f.split(":")
        src = resolve_src(src, modulesd)
        tgt2 = os.path.join(rp, tgt[1:])
        log(f"copying: {src} to {tgt2}")
        if os.path.exists(tgt2):
            os.remove(tgt2)
        tgt_dir = os.path.dirname(tgt2)
        if not os.path.exists(tgt_dir):
            os.makedirs(tgt_dir)
        copyfile(src, tgt2, follow_symlinks=False)
    for f in mod["bind"]:
        (src, tgt) = f.split(":")
        src = resolve_src(src, modulesd)
        if src.endswith("*"):
            for fp in glob(src):
                tgt2 = os.path.join(rp, fp[1:])
                log(f"mounting: {fp} to {tgt2}")
                bind_mount(fp, tgt2)
        else:
            tgt2 = os.path.join(rp, tgt[1:])
            log(f"mounting: {src} to {tgt2}")
            bind_mount(src, tgt2)


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
            log("Loading %s" % (m))
            do_plugin(rp, plug_conf[m], plug_conf_fn)
    ret = os.chroot(rp)
    log(f"chroot return: {ret}")

    ldconfig()


if __name__ == "__main__":
    main()
