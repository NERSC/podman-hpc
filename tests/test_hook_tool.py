import podman_hpc.hook_tool as ht
import sys
import io
import os
import json
import ctypes
import tempfile
import time
import pytest


_libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)


def test_conf(monkeypatch):
    tdir = os.path.dirname(__file__)
    conf = os.path.join(tdir, "test.yaml")
    tempd = tempfile.TemporaryDirectory(dir="/tmp")
    rdir = os.path.join(tempd.name, "root")
    os.mkdir(rdir)
    os.mkdir(os.path.join(rdir, "etc"))
    env = [ "ENABLE_MODULE1=1" ]
    cconf = {
             "root": {
                      "path": rdir
                     },
             "process": { "env": env}
            }
    with open(os.path.join(tempd.name, "config.json"), "w") as f:
         json.dump(cconf, f)
    pid = os.fork()
    if pid == 0:
        uidmapfile = '/proc/self/uid_map'
        uidmap = "0 %d 1" % os.getuid()
        resp = _libc.unshare(0x00020000|0x10000000|0x20000000)
        print("Writing uidmap = '%s' to '%s'" % (uidmap, uidmapfile))
        with open(uidmapfile,'w') as file:
            file.write(uidmap)
        time.sleep(5)
        os._exit(0)
    time.sleep(1)
#    uidmapfile = '/proc/self/uid_map'
#    uidmap = "0 %d 1" % os.getuid()
    ht.setns(pid, "user")
#    print("Writing uidmap = '%s' to '%s'" % (uidmap, uidmapfile))
#    with open(uidmapfile,'w') as file_:
#        file_.write(uidmap)

    hconf = {
            'pid': pid,
            'annotations': {}
           }
    sys.stdin = io.StringIO(json.dumps(hconf))
    here = os.getcwd()
    sys.argv = [sys.argv[0], conf]
    os.chdir(tempd.name)

    def mock_chroot(dir):
        return 0

    monkeypatch.setattr(os, "chroot", mock_chroot)
    monkeypatch.setenv("LOG_PLUGIN", "/tmp/log.out")
    ht.main()
    os.chdir(here)
    motd = os.path.join(rdir, "a/motd")
    assert os.path.exists(motd)
    null = os.path.join(rdir, "null")
    assert os.path.exists(null)
    hosts = os.path.join(rdir, "etc/hosts")
    assert os.path.exists(hosts)
    null2 = os.path.join(rdir, "null2")
    assert not os.path.exists(null2)
    os.wait()
    ret = _libc.umount2(null, 2)
    print(ret)
