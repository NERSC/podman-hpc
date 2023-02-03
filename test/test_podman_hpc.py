import podman_hpc.podman_hpc as phpc
import sys
import os
import pytest
import json


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
        for line in f.read().split("\n"):
            items = line.split(" ")
            if items[0] == "run":
                run = items
            elif "exec --root" in line:
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


def test_run_fail(monkeypatch, fix_paths, mock_podman, mock_exit):
    sys.argv = ["podman_hpc", "shared-run", "-it", "--rm",
                "-e", "FAILME=1", "ubuntu", "uptime"]
    monkeypatch.setenv("SLURM_LOCALID", "0")
    monkeypatch.setenv("SLURM_STEP_TASKS_PER_NODE", "1")
    monkeypatch.setenv("PODMANHPC_WAIT_TIMEOUT", "0.5")
    monkeypatch.setenv("MOCK_FAILURE", "1")
    phpc.main()
    run = None
    out = open(mock_podman).read()
    assert "run --rm" in out
    assert "exec --root" not in out
    fn = f"/tmp/uid-{os.getuid()}-pid-{os.getppid()}.txt"


def test_shared_run_auto(monkeypatch, fix_paths, mock_podman, mock_exit):
    sys.argv = ["podman_hpc", "run", "-it", "--rm", "--mpi",
                "--volume", "/a:/b", "ubuntu", "uptime"]
    monkeypatch.setenv("SLURM_LOCALID", "0")
    monkeypatch.setenv("SLURM_STEP_TASKS_PER_NODE", "1")
    test_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(test_dir, "..", "etc", "modules.d")
    monkeypatch.setenv("PODMANHPC_MODULES_DIR", modules_dir)
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
    assert "ubuntu" in run
    assert exec is not None
    assert exec[-1] == "uptime"
    assert "SLURM_*" in exec
    assert "PALS_*" in exec


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
    imagej = os.path.join(tmp_path, "overlay-images",
                          "images.json")
    d = json.load(open(imagej))
    id = "9c6f0724472873bb50a2ae67a9e7adcb57673a183cea8b06eb778dca859181b5"
    assert d[0]['id'] == id
    run = out.split("\n")[-2].split()
    assert "/mksq" in run
    assert "/sqout" in run
    sys.argv = ["podman_hpc", "--squash-dir", str(tmp_path),
                "rmsqi", "alpine"]
    phpc.main()
    d = json.load(open(imagej))
    assert len(d) == 0


def test_migrate(fix_paths, mock_podman, mock_exit, tmp_path):
    sys.argv = ["podman_hpc", "--squash-dir",
                str(tmp_path), "migrate", "ubuntu"]
    phpc.main()
    assert os.path.exists(os.path.join(tmp_path, "overlay"))
    # TODO: Add more checks


def test_modules(monkeypatch, fix_paths, mock_exit):
    sys.argv = ["podman_hpc", "run", "-it", "--rm", "--gpu",
                "ubuntu"]
    global args_passed
    args_passed = []

    def mock_execve(bin, args, path):
        global args_passed
        args_passed.append(args)
        return 0

    monkeypatch.setattr(os, "execve", mock_execve)
    test_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(test_dir, "..", "etc", "modules.d")
    monkeypatch.setenv("PODMANHPC_MODULES_DIR", modules_dir)
    phpc.main()
    assert "--gpu" not in args_passed[0]
    assert "ENABLE_GPU=1" in args_passed[0]
