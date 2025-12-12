#!/usr/bin/python
"""Utilities for migrating Podman images into a squashed image store."""
import os
import sys
import json
from shutil import copytree, copy, which
from subprocess import Popen, PIPE
import logging

DEBUG = os.environ.get("DEBUG_M2SQ", False)


def merge_records_preserve_first(record_lists, key_name):
    """Merge a list of records preserving the first occurrence by key."""
    merged_records = []
    seen_keys = {}
    for records in record_lists:
        for record in records:
            record_key = record[key_name]
            if record_key not in seen_keys:
                merged_records.append(record)
                seen_keys[record_key] = record
    return merged_records


def merge_recs(recs_list, key):  # Backward compatibility wrapper
    return merge_records_preserve_first(recs_list, key)


class ImageStore:
    """
    Provide basic functions for interacting with an image store.

    The directory structure is expected to resemble Podman's overlay store
    layout including overlay, overlay-images, and overlay-layers.
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
            with open(self.images_json, encoding="utf-8") as fp:
                self.images = json.load(fp)
        if os.path.exists(self.layers_json):
            with open(self.layers_json, encoding="utf-8") as fp:
                self.layers = json.load(fp)

    def refresh(self):
        """
        Currently just used in testing.
        """
        if os.path.exists(self.images_dir):
            with open(self.images_json, encoding="utf-8") as fp:
                self.images = json.load(fp)
            with open(self.layers_json, encoding="utf-8") as fp:
                self.layers = json.load(fp)

    def get_image_info(self, image_name):
        """
        Find image info by name. Tries different variants including repos and tag.

        Inputs:
        image_name: name to lookup. Can be a short form.
        """
        # Try exact match
        for image in self.images:
            if image["id"].startswith(image_name):
                logging.debug("Found by ID")
                return image, image["id"]
        if ":" not in image_name:
            image_name = f"{image_name}:latest"
        prefixes = ["", "docker.io/", "docker.io/library/", "localhost/"]
        for pref in prefixes:
            long_name = f"{pref}{image_name}"
            for image in self.images:
                for n in image.get("names", []):
                    if long_name == n:
                        return image, long_name
        return None, None

    # Backward compatibility wrapper
    def get_img_info(self, img_name):
        return self.get_image_info(img_name)

    def get_manifest(self, image_id):
        """
        Return the contents of the manifest for the given image ID.

        Inputs:
        image_id: image id
        """
        manifest_path = os.path.join(self.images_dir, image_id, "manifest")
        with open(manifest_path, encoding="utf-8") as fp:
            return json.load(fp)

    def init_storage(self):
        """
        Initializes a directory as an image store.  This creates
        the minimum directories and JSON files.
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        if not os.path.exists(self.base):
            os.mkdir(self.base)
        for ext in ["", "/l", "-images", "-layers"]:
            pth = os.path.join(self.base, f"overlay{ext}")
            if not os.path.exists(pth):
                os.mkdir(pth)
        for typ in ["images", "layers"]:
            pth = f"{self.base}/overlay-{typ}/{typ}.lock"
            if not os.path.exists(pth):
                with open(pth, "w", encoding="utf-8") as f:
                    f.write("")
            pth = f"{self.base}/overlay-{typ}/{typ}.json"
            if not os.path.exists(pth):
                with open(pth, "w", encoding="utf-8") as f:
                    f.write("[]")

    def image_exists(self, image_id):
        """
        Checks if an ID is present in a image store. Returns True/False

        Inputs:
        image_id: Image ID
        """
        for img in self.images:
            if img["id"] == image_id:
                return True
        return False

    # Backward compatibility wrapper
    def chk_image(self, id):
        return self.image_exists(id)

    def delete_record(self, object_type, object_id, key_name="id"):
        """
        Deletes a record from a JSON file

        Inputs:
        object_type: object type (images/layers)
        object_id: object id
        key_name: key name for the ID
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        json_path = os.path.join(self.base, f"overlay-{object_type}", f"{object_type}.json")
        with open(json_path, encoding="utf-8") as fp:
            records = json.load(fp)
        changed = False
        out = []
        for rec in records:
            if rec[key_name] == object_id:
                changed = True
                continue
            out.append(rec)
        if changed:
            with open(json_path, "w", encoding="utf-8") as fp:
                json.dump(out, fp)
            logging.debug(f"Updated {json_path}")

    # Backward compatibility wrapper
    def del_rec(self, otype, id, key="id"):
        return self.delete_record(otype, id, key)

    def drop_tag(self, tags):
        """
        Removes an image tag from an image by its ID.
        This leaves the repo but just drops the tag which
        is only allowed to be set for one image.

        Inputs:
        tags: list of tags
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        images_data = self.images
 
        for img in images_data:
            for tag in tags:
                if tag in img['names']:
                    img['names'].remove(tag)
        with open(self.images_json, "w", encoding="utf-8") as fp:
            json.dump(images_data, fp)
        self.images = images_data

    def add_records(self, object_type, records):
        """
        Adds records to the JSON store.

        Inputs:
        object_type: Object type (images/layers)
        records: list of records to add.

        Note: No validation is done on the records other than checking
              for duplicate IDs.
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        json_path = os.path.join(self.base, f"overlay-{object_type}", f"{object_type}.json")
        with open(json_path, encoding="utf-8") as fp:
            data = json.load(fp)
        by_id = {}
        for row in data:
            by_id[row["id"]] = row

        changed = False
        for rec in records:
            if rec["id"] not in by_id:
                data.append(rec)
                changed = True
        if changed:
            with open(json_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp)
            logging.debug(f"Updated {json_path}")
            self.refresh()

    # Backward compatibility wrapper
    def add_recs(self, otype, recs):
        return self.add_records(otype, recs)

    def get_squash_filename(self, link):
        return os.path.join(self.overlay_dir, "l", f"{link}.squash")

    def read_link_file(self, img_id):
        """
        Read the overlay link file
        """
        link_path = os.path.join(self.overlay_dir, img_id, "link")
        with open(link_path, encoding="utf-8") as fp:
            return fp.read()


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
        Helper function to lookup the default image store path from config.
        """
        home = os.environ["HOME"]
        conf_path = f"{home}/.config/containers/storage.conf"
        store_path = None
        try:
            with open(conf_path, encoding="utf-8") as fp:
                for line in fp:
                    if "#" in line:
                        continue
                    if "graphroot" in line:
                        val = line.rstrip().split("=")[1]
                        store_path = val.replace(" ", "").replace('"', "")
        except FileNotFoundError:
            pass
        # Fall back to a sensible default if not found
        return store_path or f"/tmp/{os.getuid()}_hpc/storage"

    def _get_image_layers(self, top_layer):
        """
        This finds all the required layers for an image
        including layers coming from dependent images.

        Inputs:
        imgid: Image ID
        """

        def _add_parent(layer, layer_map, layers=None, layer_ids=None):
            """
            Recursive function to walk up parent graph.

            Inputs:
            layer: layer to walk
            layer_map: dictionary of layers by ID
            layers: list of layers that are being accumulated.
            layer_ids: accumulated dictionary of layers by ID
            """
            if not layer_ids:
                layer_ids = set()
            if not layers:
                layers = []
            logging.debug(f"Adding layer {layer['id']}")
            layers.append(layer)
            layer_ids.add(layer["id"])
            if "parent" in layer and layer["parent"] not in layer_ids:
                parent = layer_map[layer["parent"]]
                _add_parent(parent, layer_map, layers, layer_ids)
            return layers


        layer_map = {}
        all_layers = merge_records_preserve_first([self.src.layers, self.dst.layers], "id")
        for layer in all_layers:
            layer_map[layer["id"]] = layer
        layer = layer_map[top_layer]
        layers = _add_parent(layer, layer_map)
        return layers

    # Backward compatibility wrapper
    def _get_img_layers(self, store, top_layer):
        return self._get_image_layers(top_layer)

    def _copy_image_info(self, img_id):
        srcd = os.path.join(self.src.images_dir, img_id)
        dstd = os.path.join(self.dst.images_dir, img_id)
        # Copy image directory
        if not os.path.exists(dstd):
            copytree(srcd, dstd)

    def _copy_required_layers(self, req_layers):
        for layer in req_layers:
            layer_id = layer["id"]
            fn = f"{layer_id}.tar-split.gz"
            srcd = os.path.join(self.src.layers_dir, fn)
            dstd = os.path.join(self.dst.layers_dir, fn)
            if not os.path.exists(dstd):
                logging.debug(f"Copy {srcd} to {dstd}")
                copy(srcd, dstd)
        self.dst.add_recs("layers", req_layers)

    def _copy_overlay(self, img_id, layers):
        for layer in layers:
            layer_id = layer["id"]
            src_layer_dir = os.path.join(self.src.overlay_dir, layer_id)
            dst_layer_dir = os.path.join(self.dst.overlay_dir, layer_id)
            if os.path.exists(src_layer_dir) and not os.path.exists(dst_layer_dir):
                os.mkdir(dst_layer_dir)
            for p in ["empty", "merged", "work", "diff"]:
                src_path = os.path.join(src_layer_dir, p)
                dst_path = os.path.join(dst_layer_dir, p)
                if os.path.exists(src_path) and not os.path.exists(dst_path):
                    os.mkdir(dst_path)
            # the link
            src_link_path = os.path.join(src_layer_dir, "link")
            dst_link_path = os.path.join(dst_layer_dir, "link")
            if not os.path.exists(dst_link_path):
                logging.debug(f"Copy {src_link_path} to{dst_link_path}")
                copy(src_link_path, dst_link_path)

            # Create symlink file
            link = self.dst.read_link_file(layer_id)
            lname = os.path.join(self.dst.overlay_dir, "l", link)
            tgt = os.path.join("..", layer_id, "diff")
            if not os.path.exists(lname):
                try:
                    os.symlink(tgt, lname)
                except FileExistsError:
                    pass
                except OSError as ex:
                    logging.warning(f"Failed to create symlink {lname}: {ex}")
            # Finally the squash file
            # Since there typically isn't a squash file, this is more
            # for future cases
            src = self.src.get_squash_filename(link)
            dst = self.dst.get_squash_filename(link)
            if os.path.exists(src) and not os.path.exists(dst):
                logging.debug(f"Copy {src} to {dst}")
                copy(src, dst)

    def _generate_squashfs(self, img_id, top_id):
        # Get the link name
        link_name = self.dst.read_link_file(top_id)
        mksquashfs_path = self.mksq_bin
        if not mksquashfs_path.startswith("/"):
            mksquashfs_path = which(mksquashfs_path)
        target_path = self.dst.get_squash_filename(link_name)
        if os.path.exists(target_path):
            logging.info("Squash file already generated")
            return True
        logging.info(f"Generating squash file {target_path}")
        # To make the squash file we will start up a container
        # with the tgt image and then run mksq in it.
        # This requires a statically linked mksquashfs
        cmd = [
            self.podman_bin, "run", "--rm",
            "--root", self.src.base,
            "-v", f"{mksquashfs_path}:{self._mksq_inside}",
            "-v", f"{self.dst.base}/overlay/l/:/sqout",
            "--user", "0",
            "--entrypoint", self._mksq_inside,
            img_id,
            "/", f"/sqout/{link_name}.squash",
        ]
        cmd.extend(self.mksq_options)
        # Exclude these
        for ex in self.exclude_list:
            cmd.extend(["-e", ex])
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE, env=os.environ)
        out, err = proc.communicate()

        if proc.returncode != 0:
            logging.error("Squash Failed")
            logging.error(out.decode("utf-8"))
            logging.error(err.decode("utf-8"))
            return False

        logging.info("Created squash image")
        return True

    # Backward compatibility wrapper
    def _mksq(self, img_id, top_id):
        return self._generate_squashfs(img_id, top_id)

    def migrate_image(self, image):
        self._lazy_init()
        logging.debug(f"Migrating {image}")
        self.dst.init_storage()
        self.src.refresh()
        self.dst.refresh()
        # Read in json data

        img_info, fullname = self.src.get_image_info(image)
        if not img_info:
            logging.error(f"Image {image} not found\n")
            return False

        img_id = img_info["id"]
        top_id = img_info["layer"]
        # Get the layers from the manifest
        required_layers = self._get_image_layers(top_id)

        # make sure the src squash file exist
        logging.debug(f"Reading link: {top_id}")

        if self.dst.image_exists(img_id):
            logging.info("Previously migrated")
            return True

        # Check if previously tagged image exist
        if fullname:
            self.dst.get_image_info(fullname)
        self.dst.drop_tag(img_info["names"])

        # Copy image info
        self._copy_image_info(img_id)

        # Copy layers
        self._copy_required_layers(required_layers)

        # Overlay
        self._copy_overlay(img_id, required_layers)

        # Generate squash
        logging.debug(f"squashing {img_id}")
        resp = self._generate_squashfs(img_id, top_id)
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
        img_info, _ = self.dst.get_image_info(image)
        if not img_info:
            logging.error(f"Image {image} not found\n")
            return False
        img_id = img_info["id"]
        top_id = img_info["layer"]
        # Get the layers from the manifest
        _ = self._get_image_layers(top_id)

        # make sure the src squash file exist
        link_name = self.dst.read_link_file(top_id)
        squash_file_path = self.dst.get_squash_filename(link_name)
        if os.path.exists(squash_file_path):
            logging.info("Removing squash file")
            os.unlink(squash_file_path)
        logging.info("Removing image record")
        self.dst.delete_record("images", img_id)
        return True


def usage():
    """
    print usage info
    """
    print("Usage: m2scr [mig|rmi|init] <image name> [<dest>]")
    print("Set SQUASH_DIR to define the default destination")


if __name__ == "__main__":  # pragma: no cover
    mu = MigrateUtils()
    logging.basicConfig(level=logging.INFO)
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
        mu.migrate_image(image)
    else:
        usage()
