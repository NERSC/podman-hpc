#!/usr/bin/python3
import ctypes
import ctypes.util
import os
import sys
import errno
import subprocess
import json
import yaml
import stat
from glob import glob
from shutil import copyfile

_libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
_libc.mount.argtypes = (ctypes.c_char_p,
                        ctypes.c_char_p,
                        ctypes.c_char_p,
                        ctypes.c_ulong,
                        ctypes.c_char_p)
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


def mount(source, target, fs, options=''):
    ret = _libc.mount(source.encode(), target.encode(),
                      fs.encode(), 0, options.encode())
    if ret < 0:
        errno = ctypes.get_errno()
        msg = f"Error mounting {source} ({fs}) on {target} " + \
              f"with options '{options}': {os.strerror(errno)}"
        raise OSError(errno, msg)


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
    log(subprocess.check_output(["/bin/ls"]).decode('utf-8'))
    ret = "unknown"
    try:
        ret = subprocess.check_output(["/sbin/ldconfig"])
    except subprocess.CalledProcessError:
        log("ldconfig failed")
        log(ret)


def do_plugin(rp, mod):
    log(mod)
    log(rp)
    for f in mod['copy']:
        (src, tgt) = f.split(":")
        tgt2 = os.path.join(rp, tgt[1:])
        log("%s %s" % (src, tgt2))
        if os.path.exists(tgt2):
            os.remove(tgt2)
        tgt_dir = os.path.dirname(tgt2)
        if not os.path.exists(tgt_dir):
            os.makedirs(tgt_dir)
        copyfile(src, tgt2, follow_symlinks=False)
    for f in mod['bind']:
        (src, tgt) = f.split(":")
        if src.endswith('*'):
            for fp in glob(src):
                tgt2 = os.path.join(rp, fp[1:])
                bind_mount(fp, tgt2)
        else:
            tgt2 = os.path.join(rp, tgt[1:])
            bind_mount(src, tgt2)


def makedev(rp, tgt, major, minor, chardev=True):
    tgt2 = os.path.join(rp, tgt[1:])
    mode = 0o600
    if chardev:
        mode |= stat.S_IFCHR
    else:
        mode |= stat.S_IFBLK
    log("mknod %s %o" % (tgt2, mode))
    os.mknod(tgt2, mode, os.makedev(major, minor))


def main():
    global logger

    plug_conf_fn = sys.argv[1]

    plug_conf = yaml.load(open(plug_conf_fn), Loader=yaml.FullLoader)
    lf = os.environ.get("LOG_PLUGIN")
    if lf:
        logger = open(lf, "w")
    log(os.environ)
    inp = json.load(sys.stdin)
    log(json.dumps(inp, indent=2))
    pid = inp['pid']
    cf = json.load(open("config.json"))
    log(json.dumps(cf, indent=2))
    rp = cf["root"]["path"]

    setns(pid, "mnt")
    os.chroot("/")
    envs = {}
    for e in cf['process']['env']:
        k, v = e.split("=", maxsplit=1)
        envs[k] = v
    for m in plug_conf:
        if plug_conf[m]['annotation'] in inp['annotations']:
            log("Loading %s" % (m))
            do_plugin(rp, plug_conf[m])
        if plug_conf[m]['env'] in envs:
            log("Loading %s" % (m))
            do_plugin(rp, plug_conf[m])
#    tgt = "%s/%s" % (rp, "motd")
#    bind_mount("/etc/motd", tgt)
#    makedev(rp, "/dev/nvidia0", 195, 0)
    ret = os.chroot(rp)
    log(ret)

    ldconfig()


if __name__ == "__main__":
    main()
