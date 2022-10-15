import podman_hpc.podman_hpc as phpc
import sys
import os


def test_conf():
    conf = phpc.config()
    home = conf.get_config_home()
    assert home is not None


def test_sconf():
    conf = phpc.config()
    sconf = conf.get_default_store_conf()
    assert 'storage' in sconf
    assert 'options' in sconf['storage']
    assert 'mount_program' in sconf['storage']['options']


def test_cconf():
    conf = phpc.config()
    sconf = conf.get_default_containers_conf()
    assert 'engine' in sconf
    assert 'containers' in sconf


def test_main(monkeypatch):
    sys.argv = ["podman_hpc", "--help"]
    global args_passed

    def mock_exit():
        return 0

    def mock_execve(bin, args, path):
        global args_passed
        args_passed = args
        return 0

    monkeypatch.setattr(sys, "exit", mock_exit)
    monkeypatch.setattr(os, "execve", mock_execve)
    phpc.main()
    assert "--help" in args_passed

    sys.argv = ["podman_hpc", "run", "-it", "alpine"]
    monkeypatch.setattr(os, "execve", mock_execve)
    phpc.main()
    assert "run" in args_passed
