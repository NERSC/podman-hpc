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


@pytest.fixture
def mock_exit(monkeypatch):
    def mock_exit_func(*args):
        return 0
    monkeypatch.setattr(sys, "exit", mock_exit_func)


@pytest.fixture
def mock_podman(monkeypatch, tmp_path):
    test_dir = os.path.dirname(__file__)
    mock_pod = os.path.join(test_dir, "mock_bin", "mock_podman")
    monkeypatch.setenv("PODMANHPC_PODMAN_BIN", mock_pod)
    mock_out = os.path.join(tmp_path, "mock.out")
    monkeypatch.setenv("MOCK_OUT", mock_out)
    return mock_out


def test_help(monkeypatch, fix_paths, capsys, mock_exit):
    sys.argv = ["podman_hpc", "--help"]
    phpc.main()
    captured = capsys.readouterr()
    assert "podman-hpc" in captured.out
    assert "Podman help page follows" in captured.out


def test_run_help(monkeypatch, fix_paths, capsys, mock_exit):
    sys.argv = ["podman_hpc", "run", "--help"]
    phpc.main()
    captured = capsys.readouterr()
    assert "podman-hpc" in captured.out
    assert "Podman options" in captured.out


def test_run(monkeypatch, fix_paths, mock_exit):
    sys.argv = ["podman_hpc", "run", "-it", "--rm", "ubuntu"]
    uid = os.getuid()
    global args_passed
    args_passed = []

    def mock_execve(bin, args, path):
        global args_passed
        args_passed.append(args)
        return 0

    monkeypatch.setattr(os, "execve", mock_execve)
    phpc.main()
    # TODO: Add more checks
    last = args_passed[-1]
    assert "run" in last
    assert f"/tmp/{uid}_hpc/storage" in last
    assert f"/tmp/{uid}_hpc" in last
    assert "cgroupfs" in last
    assert "--hooks-dir" in last
    assert "PODMANHPC_MODULES_DIR=/etc/podman_hpc/modules.d" in last
    assert "fatal" in last
    assert "podman_hpc.hook_tool=true"
    assert sys.argv[2:] == last[-3:]
    assert "seccomp=unconfined"


def test_shared_run(monkeypatch, fix_paths, mock_podman, mock_exit):
    sys.argv = ["podman_hpc", "shared-run", "-it", "--rm",
                "--volume", "/a:/b", "ubuntu", "uptime"]
    monkeypatch.setenv("SLURM_LOCALID", "0")
    monkeypatch.setenv("SLURM_STEP_TASKS_PER_NODE", "1")
    phpc.main()
    run = None
    with open(mock_podman) as f:
        for line in f:
            items = line.split()
            if items[0] == "run":
                run = items
            elif items[0] == "exec":
                exec = items
    uid = os.getuid()
    assert run is not None
    assert "--root" in run
    assert f"/tmp/{uid}_hpc/storage" in run
    assert "--name" in run
    assert "ubuntu" in run
    assert exec is not None
    assert exec[-1] == "uptime"
    assert "SLURM_*" in exec
    assert "PALS_*" in exec
    assert "--volume" not in exec
    assert "--rm" not in exec


def test_pull(monkeypatch, fix_paths, mock_podman, mock_exit,
              tmp_path, capsys):
    sys.argv = ["podman_hpc", "--squash-dir", str(tmp_path),
                "pull", "alpine"]
    tdir = os.path.dirname(__file__)
    src = os.path.join(tdir, "storage")
    monkeypatch.setenv("PODMANHPC_GRAPH_ROOT", src)
    phpc.main()
    captured = capsys.readouterr()
    assert "Migrating" in captured.out
    assert str(tmp_path) in captured.out
    out = open(mock_podman).read()
    assert "pull " in out
    assert src in out
    assert captured.err == ""


def test_migrate(fix_paths, mock_podman, mock_exit, tmp_path):
    sys.argv = ["podman_hpc", "--squash-dir",
                str(tmp_path), "migrate", "ubuntu"]
    phpc.main()
    assert os.path.exists(os.path.join(tmp_path, "overlay"))
    # TODO: Add more checks
