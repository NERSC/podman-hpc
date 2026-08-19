#!/usr/bin/python
import os
import sys
import json
from shutil import rmtree
from shutil import copytree, copy, which
from subprocess import Popen, PIPE
from tempfile import TemporaryDirectory
import logging

DEBUG = os.environ.get("DEBUG_M2SQ", False)


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

        long_names = [img_name]
        first_part = img_name.split("/", 1)[0]
        has_registry = "/" in img_name and (
            "." in first_part or ":" in first_part
            or first_part == "localhost"
        )

        if not has_registry:
            long_names.extend([
                f"docker.io/{img_name}",
                f"docker.io/library/{img_name}",
                f"localhost/{img_name}",
            ])
        elif img_name.startswith("docker.io/"):
            remainder = img_name[len("docker.io/"):]
            if "/" not in remainder:
                long_names.append(f"docker.io/library/{remainder}")
        elif img_name.startswith("docker.io/library/"):
            remainder = img_name[len("docker.io/library/"):]
            if "/" not in remainder:
                long_names.append(f"docker.io/{remainder}")

        for long_name in long_names:
            for img in self.images:
                for n in img.get("names", []):
                    if long_name == n:
                        return img, long_name
        return None, None

    def get_manifest(self, imgid):
        """
        Retruns the contents of the manifest for the given image ID

        Inputs:
        imgid: image id
        """
        mf = os.path.join(self.images_dir, imgid, "manifest")
        return json.load(open(mf))

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

    def _write_json(self, fn, data):
        """
        Atomically replace a store metadata file.

        Build the replacement under the destination store so the final
        os.replace() is a same-filesystem rename.  Readers therefore see
        either the old complete JSON document or the new complete document,
        never a partially written file.
        """
        mode = None
        if os.path.exists(fn):
            mode = os.stat(fn).st_mode & 0o7777

        with TemporaryDirectory(
            prefix=".podman-hpc-metadata-", dir=os.path.dirname(fn)
        ) as staging_dir:
            staged_fn = os.path.join(staging_dir, os.path.basename(fn))
            with open(staged_fn, "w") as f:
                json.dump(data, f)
            if mode is not None:
                os.chmod(staged_fn, mode)
            os.replace(staged_fn, fn)

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
            self._write_json(fn, out)
            logging.debug(f"Updated {fn}")

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

        data = self.images
 
        for img in data:
            for tag in tags:
                if tag in img['names']:
                    img['names'].remove(tag)
        self._write_json(self.images_json, data)
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
            self._write_json(fn, data)
            logging.debug(f"Updated {fn}")
            self.refresh()

    @staticmethod
    def _merge_unique(existing, new):
        merged = []
        for item in existing + new:
            if item not in merged:
                merged.append(item)
        return merged

    def upsert_image(self, img_info):
        """
        Add or update an image record in images.json.

        For an existing image ID, merge tag metadata so alternate names for the
        same content remain visible in the destination store.  Remove active
        tags from other image IDs in the same update so tag reassignment is
        published atomically with the new image record.
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        data = json.load(open(self.images_json))
        existing_idx = None
        existing_row = None
        image_names = set(img_info.get("names", []))
        changed = False
        for idx, row in enumerate(data):
            if row["id"] == img_info["id"]:
                existing_idx = idx
                existing_row = row
                continue

            names = row.get("names", [])
            updated_names = [
                name for name in names if name not in image_names
            ]
            if updated_names != names:
                updated = dict(row)
                updated["names"] = updated_names
                data[idx] = updated
                changed = True

        if existing_row is None:
            data.append(img_info)
            changed = True
        else:
            updated = dict(existing_row)
            updated.update(img_info)
            updated["names"] = self._merge_unique(
                existing_row.get("names", []), img_info.get("names", [])
            )
            updated["names-history"] = self._merge_unique(
                existing_row.get("names-history", []),
                img_info.get("names-history", []) + img_info.get("names", []),
            )
            if updated != existing_row:
                data[existing_idx] = updated
                changed = True

        if changed:
            self._write_json(self.images_json, data)
            logging.debug(f"Updated {self.images_json}")
            self.refresh()

    def remove_image_tag(self, img_id, tag):
        """
        Remove a tag from an image record.

        Returns the updated record, or None when the image record no longer
        has any tag history and should be fully deleted.
        """
        if self.read_only:
            raise ValueError("Cannot init read-only storage")

        data = json.load(open(self.images_json))
        existing_idx = None
        existing_row = None
        for idx, row in enumerate(data):
            if row["id"] == img_id:
                existing_idx = idx
                existing_row = row
                break

        if existing_row is None:
            return None

        updated = dict(existing_row)
        changed = False
        if tag in updated.get("names", []):
            updated["names"] = [
                name for name in updated["names"] if name != tag
            ]
            changed = True
        if tag in updated.get("names-history", []):
            updated["names-history"] = [
                name for name in updated["names-history"]
                if name != tag
            ]
            changed = True

        if not updated.get("names-history", []):
            del data[existing_idx]
            updated = None
            changed = True
        else:
            data[existing_idx] = updated

        if changed:
            self._write_json(self.images_json, data)
            logging.debug(f"Updated {self.images_json}")
            self.refresh()

        return updated

    def get_squash_filename(self, link):
        return os.path.join(self.overlay_dir, "l", f"{link}.squash")

    def read_link_file(self, img_id):
        """
        Read the overlay link file
        """
        lf = os.path.join(self.overlay_dir, img_id, "link")
        return open(lf).read()


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

    def _get_img_layers(self, store, top_layer):
        """
        This finds all the required layers for an image
        including layers coming from dependent images.

        Inputs:
        imgid: Image ID
        """

        def _add_parent(layer, layer_map, layers=None, layer_ids=None):
            """
            Recrusive function to walk up parent graph.

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
        all_layers = merge_recs([self.src.layers, self.dst.layers], "id")
        for layer in all_layers:
            layer_map[layer["id"]] = layer
        layer = layer_map[top_layer]
        layers = _add_parent(layer, layer_map)
        return layers

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
            id = layer["id"]
            sbpath = os.path.join(self.src.overlay_dir, id)
            dbpath = os.path.join(self.dst.overlay_dir, id)
            if os.path.exists(sbpath) and not os.path.exists(dbpath):
                os.mkdir(dbpath)
            for p in ["empty", "merged", "work", "diff"]:
                spath = os.path.join(sbpath, p)
                dpath = os.path.join(dbpath, p)
                if os.path.exists(spath) and not os.path.exists(dpath):
                    os.mkdir(dpath)
            # the link
            src = os.path.join(sbpath, "link")
            dst = os.path.join(dbpath, "link")
            if not os.path.exists(dst):
                logging.debug(f"Copy {src} to{dst}")
                copy(src, dst)

            # Create symlink file
            link = self.dst.read_link_file(id)
            lname = os.path.join(self.dst.overlay_dir, "l", link)
            tgt = os.path.join("..", id, "diff")
            if not os.path.exists(lname):
                os.symlink(tgt, lname)
            # Finally the squash file
            # Since there typically isn't a squash file, this is more
            # for future cases
            src = self.src.get_squash_filename(link)
            dst = self.dst.get_squash_filename(link)
            if os.path.exists(src) and not os.path.exists(dst):
                logging.debug(f"Copy {src} to {dst}")
                copy(src, dst)

    def _get_squash_link(self, top_id):
        """
        Return the link name used for a migrated image's squash file.

        Prefer an existing destination link so retrying an incomplete
        migration repairs the existing overlay entry.  New migrations use
        the source store's link, which is copied to the destination after the
        squash file has been created successfully.
        """
        dst_link = os.path.join(self.dst.overlay_dir, top_id, "link")
        if os.path.exists(dst_link):
            return self.dst.read_link_file(top_id)
        return self.src.read_link_file(top_id)

    def _mksq(self, img_id, top_id, reuse_existing=True):
        # Get the link name
        ln = self._get_squash_link(top_id)
        _mksqstatic = self.mksq_bin
        if not _mksqstatic.startswith("/"):
            _mksqstatic = which(_mksqstatic)
        tgt = self.dst.get_squash_filename(ln)
        if os.path.exists(tgt) and reuse_existing:
            logging.info("Squash file already generated")
            return True
        if os.path.exists(tgt):
            logging.warning(
                "Regenerating squash file without a committed image record"
            )
        logging.info(f"Generating squash file {tgt}")

        # Generate outside the active overlay store.  If podman-hpc is
        # interrupted, the incomplete file is not visible as an image layer.
        # The completed squash is atomically published before any destination
        # overlay directories or layer records are copied.
        with TemporaryDirectory(
            prefix=".podman-hpc-migrate-", dir=self.dst.base
        ) as staging_dir:
            staged_tgt = os.path.join(staging_dir, f"{ln}.squash")

            # To make the squash file we will start up a container with the
            # target image and then run mksq in it.  This requires a statically
            # linked mksquashfs.
            com = [
                self.podman_bin, "run", "--rm",
                "--root", self.src.base,
                "-v", f"{_mksqstatic}:{self._mksq_inside}",
                "-v", f"{staging_dir}:/sqout",
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

            if not os.path.exists(staged_tgt):
                logging.error(
                    "Squash command succeeded but did not create "
                    f"{staged_tgt}"
                )
                return False

            try:
                os.replace(staged_tgt, tgt)
            except OSError as ex:
                logging.error(f"Failed to publish squash file: {ex}")
                return False

        logging.info("Created squash image")
        return True

    def _delete_migrated_image_data(self, img_id, top_id):
        # The squashed payload is stored in the top layer for migrated images.
        ln = self.dst.read_link_file(top_id)
        sqf = self.dst.get_squash_filename(ln)
        if os.path.exists(sqf):
            logging.info("Removing squash file")
            os.unlink(sqf)

        link_path = os.path.join(self.dst.overlay_dir, "l", ln)
        if os.path.lexists(link_path):
            os.unlink(link_path)

        overlay_path = os.path.join(self.dst.overlay_dir, top_id)
        if os.path.exists(overlay_path):
            rmtree(overlay_path)

        layer_blob = os.path.join(self.dst.layers_dir, f"{top_id}.tar-split.gz")
        if os.path.exists(layer_blob):
            os.unlink(layer_blob)

        self.dst.del_rec("layers", top_id)
        logging.info("Removing image record")
        self.dst.del_rec("images", img_id)

    def migrate_image(self, image):
        self._lazy_init()
        logging.debug(f"Migrating {image}")
        self.dst.init_storage()
        self.src.refresh()
        self.dst.refresh()
        # Read in json data

        img_info, _ = self.src.get_img_info(image)
        if not img_info:
            logging.error(f"Image {image} not found\n")
            return False

        img_id = img_info["id"]
        top_id = img_info["layer"]
        # Get the layers from the manifest
        rld = self._get_img_layers(self.src, top_id)

        # make sure the src squash file exist
        logging.debug(f"Reading link: {top_id}")

        image_committed = self.dst.chk_image(img_id)
        if image_committed:
            ln = self._get_squash_link(top_id)
            sqf = self.dst.get_squash_filename(ln)
            if os.path.exists(sqf):
                logging.info("Previously migrated")
                self.dst.upsert_image(img_info)
                return True
            logging.warning(
                "Image metadata exists without a squash file; "
                "repairing incomplete migration"
            )

        # Generate and publish the squash before exposing destination overlay
        # directories or layer metadata.  A failed or interrupted migration
        # therefore cannot shadow the same layer in another image store.
        logging.debug(f"squashing {img_id}")
        resp = self._mksq(
            img_id, top_id, reuse_existing=image_committed
        )
        if not resp:
            return False

        # Copy image info
        self._copy_image_info(img_id)

        # Build the destination overlay before publishing layer records.
        self._copy_overlay(img_id, rld)

        # Copy layer blobs, then atomically publish layers.json.
        self._copy_required_layers(rld)

        # Add img to images.json
        # Save this for the end so things are all ready
        self.dst.upsert_image(img_info)
        return True

    def remove_image(self, image):
        self._lazy_init()
        logging.debug(f"Removing {image}")
        self.dst.refresh()
        img_info, fullname = self.dst.get_img_info(image)
        if not img_info:
            logging.error(f"Image {image} not found\n")
            return False
        img_id = img_info["id"]
        top_id = img_info["layer"]
        if fullname == img_id:
            self._delete_migrated_image_data(img_id, top_id)
            return True

        tag = fullname or image

        updated = self.dst.remove_image_tag(img_id, tag)
        if updated is None:
            self._delete_migrated_image_data(img_id, top_id)
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
