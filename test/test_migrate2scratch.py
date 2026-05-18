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


def test_migrate_remove(src, tmp_path, mocker):
    img = "docker.io/library/alpine:latest"
    hash = "9c6f0724472873bb50a2ae67a9e7adcb57673a183cea8b06eb778dca859181b5"
    tdir = os.path.dirname(__file__)
    bimg = json.load(open(os.path.join(tdir, "bogus_image.json")))

    # Mock Popen
    popen = mocker.patch("podman_hpc.migrate2scratch.Popen")
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

    # Now a successful one
    popen.return_value = mockproc()
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


def test_migrate_existing_image_adds_new_tag(src, tmp_path, mocker):
    img_latest = "docker.io/library/ubuntu:jammy"
    img_edge = "docker.io/library/ubuntu:22.04"
    src_copy = tmp_path / "src"
    dst = tmp_path / "dst"
    copytree(src, src_copy)

    src_images = src_copy / "overlay-images" / "images.json"
    data = json.load(open(src_images))
    data[0]["names"].append(img_edge)
    data[0]["names-history"].append(img_edge)
    json.dump(data, open(src_images, "w"))

    popen = mocker.patch("podman_hpc.migrate2scratch.Popen")
    popen.return_value = mockproc()

    mu = MigrateUtils(src=str(src_copy), dst=str(dst))
    assert mu.migrate_image(img_latest)
    assert get_count(mu.dst.images_json, img_latest) == 1
    assert get_count(mu.dst.images_json, img_edge) == 1

    assert mu.migrate_image(img_edge)
    assert get_count(mu.dst.images_json, img_latest) == 1
    assert get_count(mu.dst.images_json, img_edge) == 1


def test_remove_image_only_drops_requested_tag_until_history_empty(
    src, tmp_path, mocker
):
    img_latest = "docker.io/library/ubuntu:jammy"
    img_edge = "docker.io/library/ubuntu:22.04"
    src_copy = tmp_path / "src"
    dst = tmp_path / "dst"
    copytree(src, src_copy)

    src_images = src_copy / "overlay-images" / "images.json"
    data = json.load(open(src_images))
    data[0]["names"].append(img_edge)
    data[0]["names-history"].append(img_edge)
    json.dump(data, open(src_images, "w"))

    popen = mocker.patch("podman_hpc.migrate2scratch.Popen")
    popen.return_value = mockproc()

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
