import podman_hpc.hook_tool as ht
import sys
import io
import os
import json
import ctypes
import time


_libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)


def test_conf(monkeypatch, tmp_path):
    tdir = os.path.dirname(__file__)
    # conf = os.path.join(tdir, "test.yaml")
    conf = os.path.join(tdir, "modules.d")
    log_file = os.path.join(tmp_path, "log.out")
    rdir = os.path.join(tmp_path, "root")
    os.mkdir(rdir)
    os.mkdir(os.path.join(rdir, "etc"))
    env = ["ENABLE_MODULE1=1",
           f"LOG_PLUGIN={log_file}",
           f"{ht._MOD_ENV}={conf}",
           ]
    cconf = {
        "root": {
            "path": rdir
            },
        "process": {"env": env}
    }
    with open(os.path.join(tmp_path, "config.json"), "w") as f:
        json.dump(cconf, f)
    pid = os.fork()
    if pid == 0:
        uidmapfile = '/proc/self/uid_map'
        uidmap = "0 %d 1" % os.getuid()
        _libc.unshare(0x00020000 | 0x10000000 | 0x20000000)
        print("Writing uidmap = '%s' to '%s'" % (uidmap, uidmapfile))
        with open(uidmapfile, 'w') as file:
            file.write(uidmap)
        time.sleep(4)
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
    sys.argv = [sys.argv[0]]
    os.chdir(tmp_path)

    def mock_chroot(dir):
        return 0

    monkeypatch.setattr(os, "chroot", mock_chroot)
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
    _libc.umount2(null, 2)
    assert os.path.exists(log_file)
    # print(ret)
