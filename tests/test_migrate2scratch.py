from podman_hpc.migrate2scratch import MigrateUtils
import os
import json


def test_getpaths():
    mu = MigrateUtils(dst = "/tmp/d")
    assert mu.src is not None


def test_init_storage():
    base = "/tmp/x"
    mu = MigrateUtils(dst=base)
    mu.init_storage()
    idir = os.path.join(base, "overlay-images")
    assert os.path.exists(idir)
    mu.read_json_file(base, "images")


def test_bad_image_name():
    base = "/tmp/x"
    tdir = os.path.dirname(__file__)
    sdir = os.path.join(tdir, "storage")
    mu = MigrateUtils(src=sdir, dst=base)
    mu.migrate_image("balpine")


def test_migrate_remove():
    base = "/tmp/x"
    img = "docker.io/library/alpine:latest"
    tdir = os.path.dirname(__file__)
    sdir = os.path.join(tdir, "storage")
    bimg = json.load(open(os.path.join(tdir, "bogus_image.json")))
    mu = MigrateUtils(src=sdir, dst=base)
    mu.init_storage()
    imgf = os.path.join(base, "overlay-images/images.json")
    with open(imgf, "w") as f:
        json.dump([bimg], f)
    mu.migrate_image(img)

    # Remigrate to test check logic
    mu.migrate_image(img)

    # Remigrate to test check logic
    mu.migrate_image("9c6f0724472873bb50a2ae67a9e7adcb57673a183cea8b06eb778dca859181b5")

    # Test removing the image
    mu.remove_image(img)
#def get_img_info(img_name, images):
#def read_json(base, otype):
#def chk_image(dst, id):
#def lock(base, ltype, id):
#def _add_parent(layer, layers, by_id, layer_ids):
#def list_img_layers(base, imgid, all_layers):
#def del_rec(base, otype, id, key="id"):
#def drop_tag(base, image, id):
#def add_recs(base, otype, recs):
#def copy_image_info(src, dst, img_id):
#def copy_required_layers(srcd, dstd, req_layers):
#def copy_overlay(srcd, dstd, img_id, layers):
#def mksq(base, dst, img_id, ln):
#def merge_recs(recs_list, key):
#def read_link_file(base, img_id):
#def migrate_image(image, dst):
#def remove_image(image, dst):

