#!/usr/bin/python
import os
import sys
import json
from shutil import copytree, copy
from subprocess import Popen, PIPE

DEBUG = os.environ.get("DEBUG_M2SQ", False)


def _debug(text):
    if DEBUG:
        print(text)


def _jprint(obj):
    print(json.dumps(obj, indent=2))


def get_paths():
    cf = "%s/.config/containers/storage.conf" % (os.environ["HOME"])
    with open(cf) as f:
        for line in f:
            if "#" in line:
                continue
            if "graphroot" in line:
                val = line.rstrip().split("=")[1]
                p = val.replace(" ", "").replace("\"", "")
    return p


def get_img_info(img_name, images):
    # Try exact match
    for img in images:
        if img["id"].startswith(img_name):
            return img
    if ":" not in img_name:
        img_name = '%s:latest' % (img_name)
    prefs = ["", "docker.io/", "docker.io/library/", "localhost/"]
    for pref in prefs:
        long_name = "%s%s" % (pref, img_name)
        for img in images:
            for n in img["names"]:
                if long_name == n:
                    return img
    return None


def init_storage(base):
    if not os.path.exists(base):
        os.mkdir(base)
    for e in ["", "/l", "-images", "-layers"]:
        p = os.path.join(base, "overlay%s" % (e))
        if not os.path.exists(p):
            os.mkdir(p)
    for t in ["images", "layers"]:
        p = "%s/overlay-%s/%s.lock" % (base, t, t)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write("")
    for t in ["images", "layers"]:
        p = "%s/overlay-%s/%s.json" % (base, t, t)
        if not os.path.exists(p):
            with open(p, "w") as f:
                f.write("[]")


def read_json(base, otype):
    fn = os.path.join(base, "overlay-%s/%s.json" % (otype, otype))
    data = json.load(open(fn))
    return data


def chk_image(dst, id):
    images = read_json(dst, "images")
    for img in images:
        if img['id'] == id:
            return True
    return False


def lock(base, ltype, id):
    # TODO: lf = os.path.join(base, "overlay-%s/%s.lock" % (ltype, ltype))
    pass


def _add_parent(layer, layers, by_id, layer_ids):
    if 'parent' in layer and layer['parent'] not in layer_ids:
        parent = by_id[layer['parent']]
        layers.append(parent)
        layer_ids = parent['id']
        _add_parent(parent, layers, by_id, layer_ids)


def list_img_layers(base, imgid, all_layers):
    by_digest = {}
    by_id = {}
    for layer in all_layers:
        if "compressed-diff-digest" in layer:
            by_digest[layer["compressed-diff-digest"]] = layer
        if "diff-digest" in layer:
            by_digest[layer["diff-digest"]] = layer
        by_id[layer["id"]] = layer
    mf = os.path.join(base, "overlay-images", imgid, "manifest")
    md = json.load(open(mf))
    layers = []
    layer_ids = {}
    for layer in md['layers']:
        ld = by_digest[layer['digest']]
        layer_ids[ld['id']] = layer
        _add_parent(ld, layers, by_id, layer_ids)
        layers.append(ld)

    return layers


def del_rec(base, otype, id, key="id"):
    fn = os.path.join(base, "overlay-%s/%s.json" % (otype, otype))
    data = json.load(open(fn))
    changed = False
    out = []
    for rec in data:
        if rec[key] == id:
            changed = True
            continue
        out.append(rec)
    if changed:
        json.dump(out, open(fn, "w"))
        _debug("Updated %s" % (fn))


def drop_tag(base, image, id):
    data = read_json(base, "images")
    for img in data:
        if img['id'] == id:
            nnames = []
            for name in img['names']:
                if name == image:
                    name = ":".join(image.split(":")[:-1])
                nnames.append(name)
            img['names'] = nnames
    fn = os.path.join(base, "overlay-images/images.json")
    json.dump(data, open(fn, "w"))


def add_recs(base, otype, recs):
    fn = os.path.join(base, "overlay-%s/%s.json" % (otype, otype))
    data = json.load(open(fn))
    by_id = {}
    for row in data:
        by_id[row["id"]] = row

    changed = False
    for rec in recs:
        if rec["id"] not in by_id:
            data.append(rec)
            changed = True
    if changed:
        json.dump(data, open(fn, "w"))
        _debug("Updated %s" % (fn))


def copy_image_info(src, dst, img_id):
    srcd = os.path.join(src, "overlay-images", img_id)
    dstd = os.path.join(dst, "overlay-images", img_id)
    # Copy image directory
    if not os.path.exists(dstd):
        copytree(srcd, dstd)


def copy_required_layers(srcd, dstd, req_layers):
    for layer in req_layers:
        lid = layer["id"]
        fn = "%s.tar-split.gz" % (lid)
        src = os.path.join(srcd, "overlay-layers", fn)
        dst = os.path.join(dstd, "overlay-layers", fn)
        if not os.path.exists(dst):
            _debug("Copy %s to %s" % (src, dst))
            copy(src, dst)
    add_recs(dstd, "layers", req_layers)


def copy_overlay(srcd, dstd, img_id, layers):
    for layer in layers:
        id = layer["id"]
        opath = os.path.join(srcd, "overlay", id)
        dpath = os.path.join(dstd, "overlay", id)
        if os.path.exists(opath) and not os.path.exists(dpath):
            os.mkdir(dpath)
        for p in ["empty", "merged", "work", "diff"]:
            opath = os.path.join(srcd, "overlay", id, p)
            dpath = os.path.join(dstd, "overlay", id, p)
            if os.path.exists(opath) and not os.path.exists(dpath):
                os.mkdir(dpath)
        # the link
        src = os.path.join(srcd, "overlay", id, "link")
        dst = os.path.join(dstd, "overlay", id, "link")
        if not os.path.exists(dst):
            _debug("Copy %s to %s" % (src, dst))
            copy(src, dst)

        # Create symlink file
        link = read_link_file(dstd, id)
        lname = os.path.join(dstd, "overlay", "l", link)
        tgt = os.path.join("..", id, "diff")
        _debug("tgt=%s link=%s" % (tgt, lname))
        if not os.path.exists(lname):
            os.symlink(tgt, lname)
        # Finally the squash file
        # Since there typically isn't a squash file, this is more
        # for future cases
        src = os.path.join(srcd, "overlay", "l", "%s.squash" % (link))
        dst = os.path.join(dstd, "overlay", "l", "%s.squash" % (link))
        if os.path.exists(src) and not os.path.exists(dst):
            _debug("Copy %s to %s" % (src, dst))
            copy(src, dst)


def mksq(base, dst, img_id, ln):
    # Get the link name
    bin_dir = os.path.dirname(__file__)
    _mksqstatic = os.path.join(bin_dir, "mksquashfs.static")
    tgt = os.path.join(dst, "overlay/l", "%s.squash" % (ln))
    if os.path.exists(tgt):
        print("INFO: Squash file already generated")
        return True
    print("INFO: Generating squash file")
    # To make the squash file we will start up a container
    # with the tgt image and then run mksq in it.
    com = [
           "podman", "run", "--rm",
           "-v", "%s:/mksq" % (_mksqstatic),
           "-v", "%s/overlay/l/:/sqout" % (dst),
           "--entrypoint", "/mksq",
           img_id,
           "/", "/sqout/%s.squash" % (ln), "-comp", "lz4"
          ]
    # Exclude these
    for ex in ["/sqout", "/mksq", "/proc", "/sys"]:
        com.extend(["-e", ex])
    proc = Popen(com, stdout=PIPE, stderr=PIPE, env=os.environ)
    out, err = proc.communicate()

    if proc.returncode != 0:
        print(out.decode('utf-8'))
        print(err.decode('utf-8'))
        return False

    print("Created squash image")
    return True


def merge_recs(recs_list, key):
    res = []
    done = {}
    for recs in recs_list:
        for r in recs:
            id = r[key]
            if id not in done:
                res.append(r)
                done[id] = r
    return res


def read_link_file(base, img_id):
    """
    Read the overlay link file
    """
    lf = os.path.join(base, "overlay", img_id, "link")
    _debug("lf=%s" % (lf))
    return open(lf).read()


def migrate_image(image, dst):
    init_storage(dst)
    src = get_paths()
    # Read in json data
    images = read_json(src, "images")
    layers = read_json(src, "layers")
    dimages = read_json(dst, "images")
    olayers = read_json(dst, "layers")
    all_layers = merge_recs([layers, olayers], "id")

    _debug(dst)
    img_info = get_img_info(image, images)
    if not img_info:
        sys.stderr.write("Image %s not found\n" % (image))
        return

    img_id = img_info['id']
    # Get the layers from the manifest
    rld = list_img_layers(src, img_id, all_layers)

    # make sure the src squash file exist
    top_id = rld[-1]['id']
    _debug("Reading link: %s" % (top_id))

    if chk_image(dst, img_id):
        print("INFO: Previously migrated")
    # Check if previously tagged image exist
    dimg = get_img_info(image, dimages)
    if dimg and dimg['id'] != img_info['id']:
        print("INFO: Replace previous version")
        drop_tag(dst, image, dimg['id'])

    # Copy image info
    copy_image_info(src, dst, img_id)

    # Copy layers
    copy_required_layers(src, dst, rld)

    # Overlay
    copy_overlay(src, dst, img_id, rld)

    # Generate squash
    ln = read_link_file(dst, top_id)
    _debug("squashing %s: %s" % (img_id, ln))
    mksq(src, dst, img_id, ln)

    # Add img to images.json
    # Save this for the end so things are all ready
    add_recs(dst, "images", [img_info])


def remove_image(image, dst):
    images = read_json(dst, "images")
    layers = read_json(dst, "layers")
    img_info = get_img_info(image, images)
    if not img_info:
        sys.stderr.write("Image %s not found\n" % (image))
        return
    img_id = img_info['id']
    # Get the layers from the manifest
    rld = list_img_layers(dst, img_id, layers)

    # make sure the src squash file exist
    top_id = rld[-1]['id']
    ln = read_link_file(dst, top_id)
    sqf = os.path.join(dst, "overlay/l", "%s.squash" % (ln))
    if os.path.exists(sqf):
        os.unlink(sqf)
    del_rec(dst, "images", img_id)


def usage():
    print("Usage: %s [mig|rmi|init] <image name> [<dest>]")
    print("Set SQUASH_DIR to define the default destination")


if __name__ == "__main__":
    dst = os.environ.get("SQUASH_DIR")
    if len(sys.argv) < 2:
        usage()
    elif sys.argv[1] == "rmi":
        sys.argv.pop(0)
        image = sys.argv[1]
        if not dst:
            dst = sys.argv[2]
        remove_image(image, dst)
        sys.exit()
    elif sys.argv[1] == "init":
        if not dst:
            dst = sys.argv[2]
        init_storage(dst)
    elif sys.argv[1].startswith("mig"):
        image = sys.argv[2]
        if not dst:
            dst = sys.argv[3]
        migrate_image(image, dst)
    else:
        usage()
