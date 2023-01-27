from podman_hpc.migrate2scratch import MigrateUtils
import os
import json
import pytest
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

    # Test removing the image
    resp = mu.remove_image(img)
    assert resp
    assert get_count(mu.dst.images_json, img) == 0
