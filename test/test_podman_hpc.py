import podman_hpc.podman_hpc as phpc
import sys
import os
import pytest


@pytest.fixture
def fix_paths(monkeypatch):
    test_dir = os.path.dirname(__file__)
    mock_dir = os.path.join(test_dir, "mock_bin")
    bin_dir = os.path.join(test_dir, "..", "bin")
    monkeypatch.setenv("PATH", mock_dir, prepend=os.pathsep)
    monkeypatch.setenv("PATH", bin_dir, prepend=os.pathsep)


def test_main(monkeypatch, fix_paths):
    sys.argv = ["podman_hpc", "run", "--help"]
    global args_passed
    args_passed = []

    def mock_exit(exit_code):
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
    phpc.main()
    assert "run" in args_passed
