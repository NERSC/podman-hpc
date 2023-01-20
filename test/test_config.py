import podman_hpc.siteconfig as config
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
def conf_file(monkeypatch):
    test_dir = os.path.dirname(__file__)
    test_conf = os.path.join(test_dir, "test_conf.yaml")
    monkeypatch.setenv(config._CONF_ENV, test_conf)
    monkeypatch.setenv("FOO", "BAR")


def test_conf_defaults(fix_paths):
    conf = config.SiteConfig(squash_dir="/tmp")
    uid = os.getuid()
    assert conf.run_root == f"/tmp/{uid}_hpc"
    assert conf._xdg_base == f"/tmp/{uid}_hpc"
    assert conf.config_home == f"/tmp/{uid}_hpc/config"
    assert conf.get_default_store_conf() is not None
    assert conf.get_default_containers_conf() is not None
    assert f"/tmp/{uid}_hpc/storage" in conf.default_args
    conf.config_env(True)
    assert conf.env is not None


def test_conf_file(fix_paths, conf_file, monkeypatch):
    conf = config.SiteConfig(squash_dir="/tmp")
    uid = os.getuid()
    user = os.getlogin()
    assert conf.podman_bin == "/bin/sleep"
    assert conf.mount_program == "/bin/sleep"
    assert "SLURM_*" in conf.shared_run_exec_args
    assert "bogus" in conf.shared_run_command
    assert user in conf.graph_root
    assert str(uid) in conf.run_root
    assert f"/imagedir/{user}/storage" == conf.graph_root
    assert f"/tmp/{uid}/run" == conf.run_root
    # This test environment variable substition and
    # environment variables precedence
    monkeypatch.setenv("FOO", "BAR")
    tmpl = "/tmp/{{ env.FOO }}"
    monkeypatch.setenv("PODMANHPC_RUN_ROOT_TEMPLATE", tmpl)
    conf = config.SiteConfig(squash_dir="/tmp")
    assert "/tmp/BAR" == conf.run_root
    assert f"/images/{user}/storage" in conf.default_args
    assert f"/tmp/{uid}/" in conf.default_args


def test_conf_modules(fix_paths, monkeypatch):
    test_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(test_dir, "..", "etc", "modules.d")
    monkeypatch.setenv("PODMANHPC_MODULES_DIR", modules_dir)
    conf = config.SiteConfig(squash_dir="/tmp", log_level="DEBUG")
    assert len(conf.active_modules) > 0
    args = conf.get_cmd_extensions("run", {"gpu": True})
    assert "ENABLE_GPU=1" in args


def test_conf_prec(conf_file, fix_paths, monkeypatch):
    test_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(test_dir, "..", "etc", "modules.d")
    monkeypatch.setenv("PODMANHPC_MODULES_DIR", modules_dir)
    conf = config.SiteConfig(squash_dir="/tmp")
    assert conf.modules_dir == modules_dir


def test_conf_funcs(fix_paths, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("PODMANHPC_CONFIG_HOME", str(tmp_path))
    conf = config.SiteConfig(squash_dir="/tmp")
    conf.config_containers()
    conf.config_storage(additional_stores="/a:/b")
    conf.export_containers_conf()
    conf.export_storage_conf()
    sc = os.path.join(tmp_path, "containers", "storage.conf")
    assert os.path.exists(sc)
    sc = os.path.join(tmp_path, "containers", "containers.conf")
    assert os.path.exists(sc)
    conf.dump_config()
    captured = capsys.readouterr()
    assert "SLURM_LOCALID" in captured.out


def test_typing(fix_paths, monkeypatch, tmp_path):
    monkeypatch.setenv("PODMANHPC_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("PODMANHPC_DEFAULT_ARGS", "a,b")
    monkeypatch.setenv("PODMANHPC_DEFAULT_RUN_ARGS_TEMPLATE",
                       "{{ uid }},{{ user }}")
    conf = config.SiteConfig(squash_dir="/tmp")
    assert isinstance(conf.default_args, list)
    assert conf.default_args == ["a", "b"]
    uid = os.getuid()
    user = os.getlogin()
    assert conf.default_run_args == [str(uid), user]
