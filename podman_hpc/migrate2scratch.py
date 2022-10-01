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


def merge_recs(recs_list, key):
    """
    Generic method to merge a list of records
    """
    res = []
    done = {}
    for recs in recs_list:
        for r in recs:
            id = r[key]
            if id not in done:
                res.append(r)
                done[id] = r
    return res


class MigrateUtils():
    src = None
    dst = None
    images = None
    all_layers = None

    def __init__(self, src=None, dst=None):
        if src:
            self.src = src
        else:
            self.src = self._get_paths()
        if dst:
            self.dst = dst
        else:
            self.dst = os.environ["SQUASH_DIR"]

    def _get_paths(self):
        cf = "%s/.config/containers/storage.conf" % (os.environ["HOME"])
        with open(cf) as f:
            for line in f:
                if "#" in line:
                    continue
                if "graphroot" in line:
                    val = line.rstrip().split("=")[1]
                    p = val.replace(" ", "").replace("\"", "")
        return p

    def init_cache(self):
        self.images = self.read_json_file(self.src, "images")
        slayers = self.read_json_file(self.src, "layers")
        self.dimages = self.read_json_file(self.dst, "images")
        dlayers = self.read_json_file(self.dst, "layers")
        self.all_layers = merge_recs([slayers, dlayers], "id")

    def _get_img_info(self, img_name, images):
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

    def init_storage(self):
        if not os.path.exists(self.dst):
            os.mkdir(self.dst)
        for e in ["", "/l", "-images", "-layers"]:
            p = os.path.join(self.dst, "overlay%s" % (e))
            if not os.path.exists(p):
                os.mkdir(p)
        for t in ["images", "layers"]:
            p = "%s/overlay-%s/%s.lock" % (self.dst, t, t)
            if not os.path.exists(p):
                with open(p, "w") as f:
                    f.write("")
        for t in ["images", "layers"]:
            p = "%s/overlay-%s/%s.json" % (self.dst, t, t)
            if not os.path.exists(p):
                with open(p, "w") as f:
                    f.write("[]")

    def read_json_file(self, base, otype):
        fn = os.path.join(base, "overlay-%s/%s.json" % (otype, otype))
        data = json.load(open(fn))
        return data

    def chk_dst_image(self, id):
        images = self.read_json_file(self.dst, "images")
        for img in images:
            if img['id'] == id:
                return True
        return False

    def get_img_layers(self, imgid):

        def _add_parent(layer, layers, by_id, layer_ids):
            if 'parent' in layer and layer['parent'] not in layer_ids:
                parent = by_id[layer['parent']]
                layers.append(parent)
                layer_ids = parent['id']
                _add_parent(parent, layers, by_id, layer_ids)

        by_digest = {}
        by_id = {}
        for layer in self.all_layers:
            if "compressed-diff-digest" in layer:
                by_digest[layer["compressed-diff-digest"]] = layer
            if "diff-digest" in layer:
                by_digest[layer["diff-digest"]] = layer
            by_id[layer["id"]] = layer
        mf = os.path.join(self.src, "overlay-images", imgid, "manifest")
        md = json.load(open(mf))
        layers = []
        layer_ids = {}
        for layer in md['layers']:
            ld = by_digest[layer['digest']]
            layer_ids[ld['id']] = layer
            _add_parent(ld, layers, by_id, layer_ids)
            layers.append(ld)

        return layers

    def del_rec(self, otype, id, key="id"):
        fn = os.path.join(self.dst, "overlay-%s/%s.json" % (otype, otype))
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

    def drop_tag(self, image, id):
        if self.dimages:
            data = self.dimages
        else:
            data = self.read_json_file(self.dst, "images")
        for img in data:
            if img['id'] == id:
                nnames = []
                for name in img['names']:
                    if name == image:
                        name = ":".join(image.split(":")[:-1])
                    nnames.append(name)
                img['names'] = nnames
        fn = os.path.join(self.dst, "overlay-images/images.json")
        json.dump(data, open(fn, "w"))
        self.dimages = data


    def add_recs(self, base, otype, recs):
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


    def copy_image_info(self, img_id):
        srcd = os.path.join(self.src, "overlay-images", img_id)
        dstd = os.path.join(self.dst, "overlay-images", img_id)
        # Copy image directory
        if not os.path.exists(dstd):
            copytree(srcd, dstd)


    def copy_required_layers(self, req_layers):
        for layer in req_layers:
            lid = layer["id"]
            fn = "%s.tar-split.gz" % (lid)
            srcd = os.path.join(self.src, "overlay-layers", fn)
            dstd = os.path.join(self.dst, "overlay-layers", fn)
            if not os.path.exists(dstd):
                _debug("Copy %s to %s" % (srcd, dstd))
                copy(srcd, dstd)
        self.add_recs(self.dst, "layers", req_layers)


    def copy_overlay(self, img_id, layers):
        for layer in layers:
            id = layer["id"]
            spath = os.path.join(self.src, "overlay", id)
            dpath = os.path.join(self.dst, "overlay", id)
            if os.path.exists(spath) and not os.path.exists(dpath):
                os.mkdir(dpath)
            for p in ["empty", "merged", "work", "diff"]:
                spath = os.path.join(self.src, "overlay", id, p)
                dpath = os.path.join(self.dst, "overlay", id, p)
                if os.path.exists(spath) and not os.path.exists(dpath):
                    os.mkdir(dpath)
            # the link
            src = os.path.join(self.src, "overlay", id, "link")
            dst = os.path.join(self.dst, "overlay", id, "link")
            if not os.path.exists(dst):
                _debug("Copy %s to %s" % (src, dst))
                copy(src, dst)

            # Create symlink file
            link = self.read_link_file(self.dst, id)
            lname = os.path.join(self.dst, "overlay", "l", link)
            tgt = os.path.join("..", id, "diff")
            _debug("tgt=%s link=%s" % (tgt, lname))
            if not os.path.exists(lname):
                os.symlink(tgt, lname)
            # Finally the squash file
            # Since there typically isn't a squash file, this is more
            # for future cases
            src = os.path.join(self.src, "overlay", "l", "%s.squash" % (link))
            dst = os.path.join(self.dst, "overlay", "l", "%s.squash" % (link))
            if os.path.exists(src) and not os.path.exists(dst):
                _debug("Copy %s to %s" % (src, dst))
                copy(src, dst)


    def mksq(self, img_id, ln):
        # Get the link name
        bin_dir = os.path.dirname(__file__)
        _mksqstatic = os.path.join(bin_dir, "mksquashfs.static")
        tgt = os.path.join(self.dst, "overlay/l", "%s.squash" % (ln))
        print(tgt)
        if os.path.exists(tgt):
            print("INFO: Squash file already generated")
            print(tgt)
            return True
        print("INFO: Generating squash file")
        # To make the squash file we will start up a container
        # with the tgt image and then run mksq in it.
        com = [
            "podman", "run", "--rm",
            "-v", "%s:/mksq" % (_mksqstatic),
            "-v", "%s/overlay/l/:/sqout" % (self.dst),
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


    def read_link_file(self, base, img_id):
        """
        Read the overlay link file
        """
        lf = os.path.join(base, "overlay", img_id, "link")
        _debug("lf=%s" % (lf))
        return open(lf).read()


    def migrate_image(self, image):
        self.init_storage()
        # Read in json data
        self.init_cache()

        _debug(self.dst)
        img_info = self._get_img_info(image, self.images)
        if not img_info:
            sys.stderr.write("Image %s not found\n" % (image))
            return

        img_id = img_info['id']
        # Get the layers from the manifest
        rld = self.get_img_layers(img_id)

        # make sure the src squash file exist
        top_id = rld[-1]['id']
        _debug("Reading link: %s" % (top_id))

        if self.chk_dst_image(img_id):
            print("INFO: Previously migrated")
        # Check if previously tagged image exist
        dimg = self._get_img_info(image, self.dimages)
        if dimg and dimg['id'] != img_info['id']:
            print("INFO: Replace previous version")
            print(dimg['id'])
            self.drop_tag(image, dimg['id'])

        # Copy image info
        self.copy_image_info(img_id)

        # Copy layers
        self.copy_required_layers(rld)

        # Overlay
        self.copy_overlay(img_id, rld)

        # Generate squash
        ln = self.read_link_file(self.dst, top_id)
        _debug("squashing %s: %s" % (img_id, ln))
        self.mksq(img_id, ln)

        # Add img to images.json
        # Save this for the end so things are all ready
        self.add_recs(self.dst, "images", [img_info])


    def remove_image(self, image):
        images = self.read_json_file(self.dst, "images")
        layers = self.read_json_file(self.dst, "layers")
        img_info = self._get_img_info(image, images)
        if not img_info:
            sys.stderr.write("Image %s not found\n" % (image))
            return
        img_id = img_info['id']
        # Get the layers from the manifest
        rld = self.get_img_layers(img_id)

        # make sure the src squash file exist
        top_id = rld[-1]['id']
        ln = self.read_link_file(self.dst, top_id)
        sqf = os.path.join(self.dst, "overlay/l", "%s.squash" % (ln))
        if os.path.exists(sqf):
            os.unlink(sqf)
        self.del_rec("images", img_id)


def usage():
    print("Usage: m2scr [mig|rmi|init] <image name> [<dest>]")
    print("Set SQUASH_DIR to define the default destination")


if __name__ == "__main__": # pragma: no cover
    mu = MigrateUtils()
    dst = os.environ.get("SQUASH_DIR")
    if len(sys.argv) < 2:
        usage()
    elif sys.argv[1] == "rmi":
        sys.argv.pop(0)
        image = sys.argv[1]
        if not dst:
            dst = sys.argv[2]
        mu.remove_image(image, dst)
        sys.exit()
    elif sys.argv[1] == "init":
        if not dst:
            dst = sys.argv[2]
        mu.init_storage(dst)
    elif sys.argv[1].startswith("mig"):
        image = sys.argv[2]
        if not dst:
            dst = sys.argv[3]
        mu.migrate_image(image, dst)
    else:
        usage()
