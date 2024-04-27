#!/usr/bin/python
import os
import sys
import json
import base64
import hashlib
from shutil import which
from subprocess import Popen, PIPE
import logging
import random
import string

DEBUG = os.environ.get("DEBUG_M2SQ", False)


def generate_link_name(length=26):
    characters = string.ascii_uppercase + string.digits
    random_string = ''.join(random.choice(characters) for _ in range(length))
    return random_string


def encode_name(name: str, data={}):
    if data and 'sha256' in data and 'sha256' in name:
        if name.startswith("manifest"):
            name = f"manifest-{data['sha256']}"
        else:
            name = data['sha256']
    if ":" not in name:
        return name
    return "=" + base64.b64encode(name.encode()).decode()


def shaify(data):
    json_data = json.dumps(data["data"])
    m = hashlib.sha256()
    m.update(json_data.encode())
    data["sha256"] = f"sha256:{m.hexdigest()}"
    data["json"] = json_data


class ImageStore:
    """
    Class to provide some basic functions for interacting with
    an image store.
    """

    images = []
    layers = []

    def __init__(self, base, read_only=True):
        """
        Inputs:
        base: base directory path of the image store
        """
        self.base = base
        self.images_dir = os.path.join(base, "overlay-images")
        self.images_json = os.path.join(self.images_dir, "images.json")
        self.layers_dir = os.path.join(base, "overlay-layers")
        self.layers_json = os.path.join(self.layers_dir, "layers.json")
        self.overlay_dir = os.path.join(base, "overlay")
        self.read_only = read_only
        if os.path.exists(self.images_json):
            self.images = json.load(open(self.images_json))
        if os.path.exists(self.layers_json):
            self.layers = json.load(open(self.layers_json))

    def refresh(self):
        """
        Currently just used in testing.
        """
        if os.path.exists(self.images_dir):
            self.images = json.load(open(self.images_json))
            self.layers = json.load(open(self.layers_json))

    def get_img_info(self, img_name):
        """
        Finds the image info by name.  This tries different variant
        including adding repositories and latest tag.

        Inputs:
        img_name: name to lookup. Can be a short form.
        """
        # Try exact match
        for img in self.images:
            if img["id"].startswith(img_name):
                logging.debug("Found by ID")
                return img, img["id"]
        if ":" not in img_name:
            img_name = f"{img_name}:latest"
        prefs = ["", "docker.io/", "docker.io/library/", "localhost/"]
        for pref in prefs:
            long_name = f"{pref}{img_name}"
            for img in self.images:
                for n in img.get("names", []):
                    if long_name == n:
                        return img, long_name
        return None, None

    # def get_manifest(self, imgid):
    #     """
    #     Retruns the contents of the manifest for the given image ID

    #     Inputs:
    #     imgid: image id
    #     """
    #     mf = os.path.join(self.images_dir, imgid, "manifest")
    #     return json.load(open(mf))

    def init_storage(self):
        """
        Initializes a directory as an image store.  This creates
        the minimum directories and JSON files.
        """
        if self.read_only:
            raise ValueError("Cannot init read-only stroage")

        if not os.path.exists(self.base):
            os.mkdir(self.base)
        for ext in ["", "/l", "-images", "-layers"]:
            pth = os.path.join(self.base, f"overlay{ext}")
            if not os.path.exists(pth):
                os.mkdir(pth)
        for typ in ["images", "layers"]:
            pth = f"{self.base}/overlay-{typ}/{typ}.lock"
            if not os.path.exists(pth):
                with open(pth, "w") as f:
                    f.write("")
            pth = f"{self.base}/overlay-{typ}/{typ}.json"
            if not os.path.exists(pth):
                with open(pth, "w") as f:
                    f.write("[]")

    def chk_image(self, id):
        """
        Checks if an ID is present in a image store. Returns True/False

        Inputs:
        id: Image ID
        """
        for img in self.images:
            if img["id"] == id:
                return True
        return False

    def del_rec(self, otype, id, key="id"):
        """
        Deletes a record from a JSON file

        Inputs:
        otype: object type (images/layers)
        id: object id
        key: key name for the ID
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        fn = os.path.join(self.base, f"overlay-{otype}", f"{otype}.json")
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
            logging.debug(f"Updated {fn}")

    def drop_tag(self, image, id):
        """
        Removes an image tag from an image by its ID.
        This leaves the repo but just drops the tag which
        is only allowed to be set for one image.

        Inputs:
        image: image tag name
        id: image ID
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        data = self.images
        for img in data:
            if img["id"] == id:
                nnames = []
                for name in img["names"]:
                    if name == image:
                        name = ":".join(image.split(":")[:-1])
                    nnames.append(name)
                img["names"] = nnames
        json.dump(data, open(self.images_json, "w"))
        self.images = data

    def add_recs(self, otype, recs):
        """
        Adds records to the JSON store.

        Inputs:
        otype: Object type (images/layers)
        recs: list of records to add.

        Note: No validation is done on the records other than checking
              for duplicate IDs.
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        fn = os.path.join(self.base, f"overlay-{otype}", f"{otype}.json")
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
            logging.debug(f"Updated {fn}")
            self.refresh()

    def get_squash_filename(self, link):
        return os.path.join(self.overlay_dir, "l", f"{link}.squash")

    def read_link_file(self, img_id):
        """
        Read the overlay link file
        """
        lf = os.path.join(self.overlay_dir, img_id, "link")
        return open(lf).read()

    def get_layer(self, layer_id):
        for layer in self.layers:
            if layer['id'] == layer_id:
                return layer

    def create_overlay(self, id):
        over_dir = os.path.join(self.overlay_dir, id)
        os.makedirs(over_dir, exist_ok=True)
        for dir_name in ["empty", "work", "merged"]:
            os.makedirs(os.path.join(over_dir, dir_name), exist_ok=True)
        link_name = generate_link_name()
        with open(os.path.join(over_dir, "link"), "w") as f:
            f.write(link_name)
        link_file = os.path.join(self.overlay_dir, "l", link_name)
        link_tgt = os.path.join("..", id, "diff")
        os.symlink(link_tgt, link_file)

    def read_image_data(self, id, file_list):
        image_dir = os.path.join(self.images_dir, id)
        img_data = {}
        for fname in file_list:
            if not fname.startswith("manifest") and \
               not fname.startswith("sha256"):
                continue
            full_name = os.path.join(image_dir, encode_name(fname))
            with open(full_name) as f:
                data = f.read()
            img_data[fname] = {"orig_name": fname,
                               "json": data,
                               "data": json.loads(data)}
        return img_data

    def write_image_data(self, id, img_data):
        image_dir = os.path.join(self.images_dir, id)
        os.makedirs(image_dir, exist_ok=True)
        for fname, data in img_data.items():
            full_name = os.path.join(image_dir, encode_name(fname, data=data))
            with open(full_name, "w") as f:
                f.write(data["json"])


class MigrateUtils:
    """
    Utility to migrate/copy images from one image store to another.
    """

    src = None
    dst = None
    images = None
    podman_bin = "podman"
    mksq_bin = "mksquashfs.static"
    mksq_options = ["-comp", "lz4", "-xattrs-exclude", "security.capability"]
    exclude_list = ["/sqout", "/mksq", "/proc", "/sys", "/dev"]
    _mksq_inside = "/mksq"

    def __init__(self, src=None, dst=None, conf=None):
        """
        Inputs:
        src: base directory of source image store
        dst: base directory of destination image store
        conf: a podman_hpc config object

        If src isn't provided, then default to user's default store.

        If dst isn't provided, then default to the values of the
        SQUASH_DIR environment variable.
        """
        self.src_dir = src
        self.dst_dir = dst
        self._lazy_init_called = False
        if conf:
            self.podman_bin = conf.podman_bin
            self.mksq_bin = conf.mksquashfs_bin
            if not self.src_dir:
                self.src_dir = conf.graph_root
            if not self.dst_dir:
                self.dst_dir = conf.squash_dir

    def _lazy_init(self):
        if not self._lazy_init_called:
            self.src_dir = self.src_dir or self._get_paths()
            self.src = ImageStore(self.src_dir)
            self.dst_dir = self.dst_dir or os.environ["SQUASH_DIR"]
            self.dst = ImageStore(self.dst_dir, read_only=False)
            self._lazy_init_called = True

    @staticmethod
    def _get_paths():
        """
        Helper function to lookup the default image store.
        """
        home = os.environ["HOME"]
        cf = f"{home}/.config/containers/storage.conf"
        with open(cf) as f:
            for line in f:
                if "#" in line:
                    continue
                if "graphroot" in line:
                    val = line.rstrip().split("=")[1]
                    p = val.replace(" ", "").replace('"', "")
        return p

    def _mksq(self, img_id, top_id):
        # Get the link name
        ln = self.dst.read_link_file(top_id)
        _mksqstatic = self.mksq_bin
        if not _mksqstatic.startswith("/"):
            _mksqstatic = which(_mksqstatic)
        tgt = self.dst.get_squash_filename(ln)
        if os.path.exists(tgt):
            logging.info("Squash file already generated")
            return True
        logging.info(f"Generating squash file {tgt}")
        # To make the squash file we will start up a container
        # with the tgt image and then run mksq in it.
        # This requires a statically linked mksquashfs
        com = [
            self.podman_bin, "run", "--rm",
            "--root", self.src.base,
            "-v", f"{_mksqstatic}:{self._mksq_inside}",
            "-v", f"{self.dst.base}/overlay/l/:/sqout",
            "--user", "0",
            "--entrypoint", self._mksq_inside,
            img_id,
            "/", f"/sqout/{ln}.squash",
        ]
        com.extend(self.mksq_options)
        # Exclude these
        for ex in self.exclude_list:
            com.extend(["-e", ex])
        proc = Popen(com, stdout=PIPE, stderr=PIPE, env=os.environ)
        out, err = proc.communicate()

        if proc.returncode != 0:
            logging.error("Squash Failed")
            logging.error(out.decode("utf-8"))
            logging.error(err.decode("utf-8"))
            return False

        logging.info("Created squash image")
        return True

    def migrate_image(self, image):
        self._lazy_init()
        logging.debug(f"Migrating {image}")
        self.dst.init_storage()
        self.src.refresh()
        self.dst.refresh()
        # Read in json data

        img_info, fullname = self.src.get_img_info(image)
        if not img_info:
            logging.error(f"Image {image} not found\n")
            return False

        img_id = img_info["id"]
        # Get the layers from the manifest
        top_id = img_info["layer"]
        layer = self.src.get_layer(top_id)
        layer.pop("parent", None)
        # make sure the src squash file exist
        logging.debug(f"Reading link: {top_id}")

        if self.dst.chk_image(img_id):
            logging.info("Previously migrated")
            return True

        # Check if previously tagged image exist
        dimg = None
        if fullname:
            dimg, _ = self.dst.get_img_info(fullname)
        if dimg and dimg["id"] != img_info["id"]:
            logging.info("Replace previous version")
            self.dst.drop_tag(fullname, dimg["id"])

        # Copy image info
        file_list = img_info["big-data-names"]
        image_data = self.src.read_image_data(img_id, file_list)

        # Fix Manifest
        manifest = image_data["manifest"]["data"]
        manifest["layers"] = []

        # Fix config
        config = image_data[manifest["config"]["digest"]]
        for hist in config["data"]["history"]:
            hist["empty_layer"] = True
        config["data"]["rootfs"]["diff_ids"] = []
        shaify(config)
        manifest["config"]["digest"] = config['sha256']
        shaify(image_data["manifest"])
        # print(json.dumps(config_data, indent=2))

        self.dst.write_image_data(img_id, image_data)

        # Copy layers
        self.dst.add_recs("layers", [layer])

        # Overlay
        self.dst.create_overlay(top_id)

        # Generate squash
        logging.debug(f"squashing {img_id}")
        resp = self._mksq(img_id, top_id)
        if not resp:
            return False

        # Add img to images.json
        # Save this for the end so things are all ready
        self.dst.add_recs("images", [img_info])
        return True

    def remove_image(self, image):
        self._lazy_init()
        logging.debug(f"Removing {image}")
        self.dst.refresh()
        img_info, _ = self.dst.get_img_info(image)
        if not img_info:
            logging.error(f"Image {image} not found\n")
            return False
        img_id = img_info["id"]
        top_id = img_info["layer"]

        ln = self.dst.read_link_file(top_id)
        sqf = self.dst.get_squash_filename(ln)
        if os.path.exists(sqf):
            os.unlink(sqf)
        self.dst.del_rec("images", img_id)
        return True


def usage():
    """
    print usage info
    """
    print("Usage: m2scr [mig|rmi|init] <image name> [<dest>]")
    print("Set SQUASH_DIR to define the default destination")


if __name__ == "__main__":  # pragma: no cover
    mu = MigrateUtils()
    dst = os.environ.get("SQUASH_DIR")
    if len(sys.argv) < 2:
        usage()
    elif sys.argv[1] == "rmi":
        sys.argv.pop(0)
        image = sys.argv[1]
        if not dst:
            dst = sys.argv[2]
        mu.remove_image(image)
        sys.exit()
    elif sys.argv[1] == "init":
        if not dst:
            dst = sys.argv[2]
        mu.dst.init_storage(dst)
    elif sys.argv[1].startswith("mig"):
        image = sys.argv[2]
        if not dst:
            dst = sys.argv[3]
        mu = MigrateUtils(dst=dst)
        mu.migrate_image(image)
    else:
        usage()
