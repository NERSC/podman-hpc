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
    conf.config_env(True)
    assert conf.env is not None


def test_conf_file(fix_paths, conf_file, monkeypatch):
    monkeypatch.setenv("FOO", "BAR")
    conf = config.SiteConfig(squash_dir="/tmp")
    uid = os.getuid()
    user = os.getlogin()
    assert conf.podman_bin == "/bin/sleep"
    assert conf.mount_program == "/bin/sleep"
    assert "-e SLURM_*" in conf.shared_run_exec_args
    assert "bogus" in conf.shared_run_command
    assert user in conf.graph_root
    assert user in conf.run_root
    assert f"--root /images/{user}/storage" in conf.default_args
    assert f"--runroot /tmp/{uid}/" in conf.default_args
    assert f"--test BAR" in conf.default_args


def test_conf_modules(fix_paths, monkeypatch):
    test_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(test_dir, "..", "etc", "modules.d")
    monkeypatch.setenv("PODMANHPC_MODULES_DIR", modules_dir)
    conf = config.SiteConfig(squash_dir="/tmp")
    assert len(conf.active_modules) > 0


def test_conf_prec(conf_file, fix_paths, monkeypatch):
    test_dir = os.path.dirname(__file__)
    modules_dir = os.path.join(test_dir, "..", "etc", "modules.d")
    monkeypatch.setenv("PODMANHPC_MODULES_DIR", modules_dir)
    conf = config.SiteConfig(squash_dir="/tmp")
    assert conf.modules_dir == modules_dir


#    def get_default_store_conf(self):
#    def get_default_containers_conf(self):
#    def get_config_home(self):
#    def config_storage(self, additional_stores=None):
#        sc = self.get_default_store_conf()
#        ais = sc["storage"]["options"].setdefault("additionalimagestores", [])
#    def config_containers(self):
#        cc = self.get_default_containers_conf()
#    def config_env(self, hpc):
#    def _write_conf(self, filename, data, overwrite=False):
#    def export_storage_conf(self, filename="storage.conf", overwrite=False):
#    def export_containers_conf(
#    def get_cmd_extensions(self, subcommand, args):
#    # to parse appropriately.  This would allow adding site-specific default
#    def read_site_modules(self):
