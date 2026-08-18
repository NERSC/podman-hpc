from podman_hpc.migrate2scratch import MigrateUtils
import os
import json
import pytest
from shutil import copytree
from tempfile import TemporaryDirectory


def get_count(fn, img):
    images = json.load(open(fn))
    ct = 0
    for i in images:
        for n in i['names']:
            if n == img:
                ct += 1
    return ct


class mockproc():
    returncode = 0

    def __init__(self, rcode=None):
        if rcode:
            self.returncode = rcode

    def communicate(self):
        return b"blah", b"blah"


class mockpopen():
    def __init__(self):
        self.return_value = mockproc()
        self.side_effect = None
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        if self.side_effect:
            return self.side_effect(*args, **kwargs)
        return self.return_value

    def assert_called(self):
        assert self.call_count > 0


def successful_squash(cmd, *args, **kwargs):
    """Mock Popen and create the squash output requested by _mksq."""
    sqout = None
    for idx, arg in enumerate(cmd[:-1]):
        if arg == "-v" and cmd[idx + 1].endswith(":/sqout"):
            sqout = cmd[idx + 1].rsplit(":", 1)[0]
            break
    output = next(arg for arg in cmd if arg.startswith("/sqout/"))
    open(os.path.join(sqout, os.path.basename(output)), "w").close()
    return mockproc()


@pytest.fixture
def src():
    tdir = os.path.dirname(__file__)
    return os.path.join(tdir, "storage")


@pytest.fixture
def dst():
    tempd = TemporaryDirectory(dir="/tmp")
    return tempd.name


def test_init_storage(src):
    with TemporaryDirectory() as dst:
        mu = MigrateUtils(src=src, dst=dst)
        mu._lazy_init()
        mu.dst.init_storage()
        idir = os.path.join(dst, "overlay-images")
        assert os.path.exists(idir)


def test_store_metadata_is_replaced_atomically(src, tmp_path, monkeypatch):
    mu = MigrateUtils(src=src, dst=str(tmp_path))
    mu._lazy_init()
    mu.dst.init_storage()
    replacements = []
    real_replace = os.replace

    def record_replace(staged, target):
        replacements.append((staged, target))
        assert os.path.commonpath([staged, str(tmp_path)]) == str(tmp_path)
        real_replace(staged, target)

    monkeypatch.setattr("podman_hpc.migrate2scratch.os.replace", record_replace)
    mu.dst.add_recs("layers", [{"id": "new-layer"}])

    assert replacements[-1][1] == mu.dst.layers_json
    assert json.load(open(mu.dst.layers_json)) == [{"id": "new-layer"}]


def test_bad_image_name(src):
    with TemporaryDirectory() as dst:
        mu = MigrateUtils(src=src, dst=dst)
        mu.migrate_image("balpine")


def test_get_img_info_fully_qualified_dockerhub_name(src):
    mu = MigrateUtils(src=src, dst="/tmp/unused")
    mu._lazy_init()

    img, fullname = mu.src.get_img_info("docker.io/alpine:latest")
    assert img is not None
    assert fullname == "docker.io/library/alpine:latest"


def test_migrate_remove(src, tmp_path, monkeypatch):
    img = "docker.io/library/alpine:latest"
    hash = "9c6f0724472873bb50a2ae67a9e7adcb57673a183cea8b06eb778dca859181b5"
    tdir = os.path.dirname(__file__)
    bimg = json.load(open(os.path.join(tdir, "bogus_image.json")))

    # Mock Popen
    popen = mockpopen()
    monkeypatch.setattr("podman_hpc.migrate2scratch.Popen", popen)
    mu = MigrateUtils(src=src, dst=tmp_path)
    mu._lazy_init()
    mu.dst.init_storage()
    imgf = os.path.join(tmp_path, "overlay-images/images.json")
    with open(imgf, "w") as f:
        json.dump([bimg], f)
    mu.dst.refresh()

    # Mock squash failing
    popen.return_value = mockproc(rcode=1)
    resp = mu.migrate_image(img)
    assert resp is False
    src_img, _ = mu.src.get_img_info(img)
    top_layer = src_img["layer"]
    top_link = mu.src.read_link_file(top_layer)
    assert json.load(open(mu.dst.layers_json)) == []
    assert not os.path.exists(os.path.join(mu.dst.overlay_dir, top_layer))
    assert not os.path.exists(mu.dst.get_squash_filename(top_link))
    assert not os.path.exists(
        os.path.join(mu.dst.images_dir, src_img["id"])
    )

    # Now a successful one
    popen.side_effect = successful_squash
    resp = mu.migrate_image(img)
    assert resp
    assert get_count(mu.dst.images_json, img) == 1
    popen.assert_called()

    # Remigrate to test check logic
    resp = mu.migrate_image(img)
    assert resp
    assert get_count(mu.dst.images_json, img) == 1

    # Remigrate with hash
    resp = mu.migrate_image(hash)
    assert resp
    assert get_count(mu.dst.images_json, img) == 1

    migrated = json.load(open(mu.dst.images_json))[0]
    layer = migrated["layer"]
    link = mu.dst.read_link_file(layer)
    sqf = mu.dst.get_squash_filename(link)
    open(sqf, "w").close()

    # Test removing the image
    resp = mu.remove_image(img)
    assert resp
    assert get_count(mu.dst.images_json, img) == 0
    assert not os.path.exists(sqf)
    assert not os.path.exists(os.path.join(tmp_path, "overlay", layer))

    assert mu.migrate_image(img)
    migrated = json.load(open(mu.dst.images_json))[0]
    layer = migrated["layer"]
    link = mu.dst.read_link_file(layer)
    sqf = mu.dst.get_squash_filename(link)
    open(sqf, "w").close()

    resp = mu.remove_image(hash)
    assert resp
    assert get_count(mu.dst.images_json, img) == 0
    assert not os.path.exists(sqf)
    assert not os.path.exists(os.path.join(tmp_path, "overlay", layer))


def test_migrate_existing_image_adds_new_tag(src, tmp_path, monkeypatch):
    img_latest = "docker.io/library/ubuntu:jammy"
    img_edge = "docker.io/library/ubuntu:22.04"
    src_copy = tmp_path / "src"
    dst = tmp_path / "dst"
    copytree(src, src_copy)

    src_images = src_copy / "overlay-images" / "images.json"
    data = json.load(open(src_images))
    data[0]["names"] = [img_latest, img_edge]
    data[0]["names-history"] = [img_latest, img_edge]
    json.dump(data, open(src_images, "w"))

    popen = mockpopen()
    monkeypatch.setattr("podman_hpc.migrate2scratch.Popen", popen)
    popen.side_effect = successful_squash

    mu = MigrateUtils(src=str(src_copy), dst=str(dst))
    assert mu.migrate_image(img_latest)
    assert get_count(mu.dst.images_json, img_latest) == 1
    assert get_count(mu.dst.images_json, img_edge) == 1

    assert mu.migrate_image(img_edge)
    assert get_count(mu.dst.images_json, img_latest) == 1
    assert get_count(mu.dst.images_json, img_edge) == 1


def test_remove_image_only_drops_requested_tag_until_history_empty(
    src, tmp_path, monkeypatch
):
    img_latest = "docker.io/library/ubuntu:jammy"
    img_edge = "docker.io/library/ubuntu:22.04"
    src_copy = tmp_path / "src"
    dst = tmp_path / "dst"
    copytree(src, src_copy)

    src_images = src_copy / "overlay-images" / "images.json"
    data = json.load(open(src_images))
    data[0]["names"] = [img_latest, img_edge]
    data[0]["names-history"] = [img_latest, img_edge]
    json.dump(data, open(src_images, "w"))

    popen = mockpopen()
    monkeypatch.setattr("podman_hpc.migrate2scratch.Popen", popen)
    popen.side_effect = successful_squash

    mu = MigrateUtils(src=str(src_copy), dst=str(dst))
    assert mu.migrate_image(img_latest)

    migrated = json.load(open(mu.dst.images_json))[0]
    layer = migrated["layer"]
    link = mu.dst.read_link_file(layer)
    sqf = mu.dst.get_squash_filename(link)
    open(sqf, "w").close()

    assert mu.remove_image(img_edge)
    remaining = json.load(open(mu.dst.images_json))[0]
    assert remaining["names"] == [img_latest]
    assert remaining["names-history"] == [img_latest]
    assert os.path.exists(sqf)

    assert mu.remove_image(img_latest)
    assert json.load(open(mu.dst.images_json)) == []
    assert not os.path.exists(sqf)


def test_migrate_repairs_incomplete_destination(src, tmp_path, monkeypatch):
    img = "docker.io/library/alpine:latest"
    dst = tmp_path / "dst"
    popen = mockpopen()
    popen.side_effect = successful_squash
    monkeypatch.setattr("podman_hpc.migrate2scratch.Popen", popen)

    mu = MigrateUtils(src=src, dst=str(dst))
    mu._lazy_init()
    mu.dst.init_storage()
    mu.src.refresh()
    mu.dst.refresh()

    img_info, _ = mu.src.get_img_info(img)
    top_layer = img_info["layer"]
    layers = mu._get_img_layers(mu.src, top_layer)

    # Reproduce the destination state left by the old migration order.
    mu._copy_image_info(img_info["id"])
    mu._copy_required_layers(layers)
    mu._copy_overlay(img_info["id"], layers)
    link = mu.dst.read_link_file(top_layer)
    squash = mu.dst.get_squash_filename(link)
    assert not os.path.exists(squash)
    assert json.load(open(mu.dst.images_json)) == []

    assert mu.migrate_image(img)
    assert os.path.exists(squash)
    assert get_count(mu.dst.images_json, img) == 1
