#!/usr/bin/python3
"""
OCI hook tool for Podman-HPC.

This module provides utilities used by the OCI hook to:
- Enter a target process namespace
- Copy or bind-mount files and directories into the container root
- Load module configurations and apply rules
"""
import ctypes
import ctypes.util
import os
import sys
import subprocess
import json
import shutil
import re
from glob import glob, iglob
from typing import Dict, Callable, Iterable

_MOD_ENV = "PODMANHPC_MODULES_DIR"

_libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
# Ensure ctypes call signature for setns is specified for safer FFI calls
try:
    _libc.setns.argtypes = (ctypes.c_int, ctypes.c_int)
except AttributeError:
    # Some libc stubs may not expose setns; we will fail later on use
    pass
logger = None


def log(msg: str) -> None:
    """
    Write a line to the configured log stream if present.
    """
    if logger:
        logger.write(f"{msg}\n")
        try:
            logger.flush()
        except Exception:
            pass


def setns(pid: int, ns: str) -> None:
    """
    Attach to a namespace of a target process ID.

    Parameters
    - pid: Process ID whose namespace to join.
    - ns: Name of the namespace, e.g. "mnt", "pid", "net", ...

    Raises
    - OSError: if attaching to the namespace fails.
    """
    namespace_path = f"/proc/{pid}/ns/{ns}"
    if not os.path.exists(namespace_path):
        raise FileNotFoundError(f"Namespace path does not exist: {namespace_path}")
    with open(namespace_path, "r") as ns_file:
        if _libc.setns(ns_file.fileno(), 0) == -1:
            e = ctypes.get_errno()
            raise OSError(e, os.strerror(e))


def bind_mount(src: str, tgt: str) -> None:
    """
    Bind-mount a file or directory into the current namespace.
    """
    # Basic validations
    if not os.path.exists(src):
        log(f"bind_mount: source does not exist: {src}")
        return
    # Create mount point
    if os.path.isdir(src) and not os.path.exists(tgt):
        os.makedirs(tgt)
    elif not os.path.exists(tgt):
        try:
            open(tgt, "w").close()
        except OSError as exc:
            log(f"bind_mount: failed to create target {tgt}: {exc}")
            return
    try:
        subprocess.check_call(["mount", "--rbind", src, tgt])
    except subprocess.CalledProcessError as exc:
        log(f"bind_mount: mount failed for {src} -> {tgt}: {exc}")


def copy(src: str, tgt: str, symlinks: bool = True) -> None:
    """
    Copy a file or directory to target path.

    Parameters
    - src: Source path
    - tgt: Target path
    - symlinks: Preserve symbolic links when copying directories
    """
    if not os.path.exists(src):
        log(f"copy: source does not exist: {src}")
        return
    if os.path.isdir(src):
        try:
            shutil.copytree(
                src,
                tgt,
                symlinks=symlinks,
                copy_function=shutil.copyfile,
                dirs_exist_ok=True,
            )
        except OSError as exc:
            log(f"copy: directory copy failed {src} -> {tgt}: {exc}")
    else:
        try:
            shutil.copyfile(src, tgt, follow_symlinks=(not symlinks))
        except OSError as exc:
            log(f"copy: file copy failed {src} -> {tgt}: {exc}")


def ldconfig() -> None:
    """
    Run ldconfig if present to refresh the dynamic linker cache.
    """
    ld = shutil.which("ldconfig")
    if not ld:
        return
    try:
        subprocess.check_call([ld])
    except subprocess.CalledProcessError as exc:
        log(f"ldconfig failed: {exc}")


def resolve_src_and_dest(rule: str, root_path: str, modulesd: str = os.path.abspath("")) -> Dict[str, str]:
    """
    Resolve a copy/bind rule into a mapping of absolute source -> absolute target.

    The rule format is "SRC[:DST]". Globs in SRC are expanded. If DST contains
    a "*" then the corresponding matched part of SRC is substituted.

    Parameters
    - rule: A rule string "SRC[:DST]"
    - root_path: The target container root path prefix
    - modulesd: Base directory to resolve relative sources

    Returns
    - Dict of {source_path: target_path}
    """
    # extract source and destination patterns from the rule
    source_pattern, dest_pattern = (rule + ":").split(":")[:2]

    # expand vars
    source_pattern = os.path.expanduser(os.path.expandvars(source_pattern))
    dest_pattern = os.path.expanduser(os.path.expandvars(dest_pattern))

    # ensure source pattern is absolute path
    if not os.path.isabs(source_pattern):
        source_pattern = os.path.join(modulesd, source_pattern)
    source_pattern = os.path.abspath(
        os.path.expanduser(os.path.expandvars(source_pattern))
    )

    # error checks
    if dest_pattern and not os.path.isabs(dest_pattern):
        log(
            "Error: Destination in pattern must be an absolute path."
            f"\n\tdestination: {dest_pattern}"
        )
        return {}
    if "*" in dest_pattern:
        if source_pattern.count("*") != 1:
            log(
                "Error: Using glob '*' in destination requires exactly one glob '*' in source."
                f"\n\tsource: {source_pattern}\n\tdestination: {dest_pattern}"
            )
            return {}
        else:
            # this is used to capture the glob expansion later
            left, right = source_pattern.split("*")
            left_esc, right_esc = re.escape(left), re.escape(right)
            glob_strip_pattern = f"^{left_esc}|{right_esc}$"

    # determine how to construct absolute path to destination object
    # if no destination rule is given, use the path from source rule
    if dest_pattern == "":
        def dest(src: str) -> str:
            return os.path.join(root_path, src[1:])
    # if the destination rule reuses the glob pattern, trailing path separator
    # determines if it interpreted as a directory or obj name
    elif "*" in dest_pattern and dest_pattern[-1] == os.path.sep:
        def dest(src: str) -> str:
            return os.path.join(
                root_path,
                dest_pattern.replace("*", re.sub(glob_strip_pattern, "", src))[1:],
                os.path.basename(src),
            )
    elif "*" in dest_pattern and dest_pattern[-1] != os.path.sep:
        def dest(src: str) -> str:
            return os.path.join(
                root_path,
                dest_pattern.replace("*", re.sub(glob_strip_pattern, "", src))[1:]
            )
    # if we glob multiple sources, interpret destination as a directory, and append shortest unique path
    else:
        matches = glob(source_pattern)
        if 1 < len(matches):
            common_prefix = os.path.commonpath(matches)
            def dest(src: str) -> str:
                return os.path.join(
                    root_path, dest_pattern[1:], os.path.relpath(src, common_prefix)
                )
        # otherwise, trailing path separator determines whether destination is interpreted as a directory
        elif dest_pattern and dest_pattern[-1] == os.path.sep:
            def dest(src: str) -> str:
                return os.path.join(
                    root_path, dest_pattern[1:], os.path.basename(src)
                )
        else:
            def dest(src: str) -> str:
                return os.path.join(root_path, dest_pattern[1:])

    return {src: os.path.normpath(dest(src)) for src in iglob(source_pattern)}


def do_plugin(rp: str, mod: dict, modulesd: str) -> None:
    """
    Execute plugin rules for a single module configuration.

    Parameters
    - rp: Root path of the container filesystem
    - mod: Module configuration dict
    - modulesd: Path to modules.d configuration directory
    """
    log(f"Module: {mod}")

    actions: Dict[str, Callable[..., None]] = {"copy": copy, "bind": bind_mount}

    for action_name in actions:
        rules: Iterable[str] = mod.get(action_name) or []
        for rule in rules:
            log(f"\t{rule}")
            for src, tgt in resolve_src_and_dest(rule, rp, modulesd).items():
                os.makedirs(os.path.dirname(tgt), exist_ok=True)
                log(f"\t\t{action_name}: {src} to {tgt}")
                actions[action_name](src, tgt)


def read_confs(mdir: str) -> Dict[str, dict]:
    """
    Read all YAML configuration files in the given directory.

    Parameters
    - mdir: Directory containing one or more *.yaml files

    Returns
    - Dict keyed by module name containing config dictionaries
    """
    try:
        import yaml  # type: ignore
    except Exception as exc:
        log(f"YAML support not available: {exc}")
        return {}
    confs: Dict[str, dict] = {}
    for d in glob(f"{mdir}/*.yaml"):
        try:
            with open(d, "r") as fid:
                conf = yaml.safe_load(fid)
            if not isinstance(conf, dict) or "name" not in conf:
                log(f"Skipping invalid config (missing name): {d}")
                continue
            confs[conf["name"]] = conf
        except Exception as exc:
            log(f"Failed to load config {d}: {exc}")
    return confs


def main() -> int:
    global logger
    logger_opened = False
    try:
        try:
            hook_input = json.load(sys.stdin)
        except Exception as exc:
            print(f"Failed to parse hook stdin JSON: {exc}", file=sys.stderr)
            return 1
        pid = hook_input.get("pid")
        if not isinstance(pid, int):
            print("Invalid or missing 'pid' in hook input", file=sys.stderr)
            return 1
        if not os.path.exists("config.json"):
            print("Missing required config.json", file=sys.stderr)
            return 1
        try:
            with open("config.json", "r") as fid:
                config = json.load(fid)
        except Exception as exc:
            print(f"Failed to read config.json: {exc}", file=sys.stderr)
            return 1
        # initialize with environment values and those defined in hook config
        hook_env = {}
        hook_env.update(os.environ)
        for e in config.get("process", {}).get("env", []):
            # tolerate malformed entries without crashing
            if "=" in e:
                k, v = e.split("=", maxsplit=1)
                hook_env[k] = v

        modules_dir = hook_env.get(_MOD_ENV, f"{sys.prefix}/etc/podman_hpc/modules.d")
        plug_conf = read_confs(modules_dir) if os.path.isdir(modules_dir) else {}

        log_path = hook_env.get("LOG_PLUGIN")
        if log_path:
            try:
                # Replace existing logger if any
                logger = open(log_path, "w")
                logger_opened = True
            except OSError as exc:
                print(f"Failed to open LOG_PLUGIN file {log_path}: {exc}", file=sys.stderr)
        log("input")
        log(json.dumps(hook_input, indent=2))
        log("config.json")
        log(json.dumps(config, indent=2))
        root_path = config.get("root", {}).get("path")
        if not root_path:
            print("Missing root.path in config.json", file=sys.stderr)
            return 1

        # We require root privileges for namespace and chroot operations
        if os.geteuid() != 0:
            print("hook_tool must run as root (euid 0).", file=sys.stderr)
            return 1

        try:
            setns(pid, "mnt")
        except Exception as exc:
            print(f"Failed to setns to mnt for pid {pid}: {exc}", file=sys.stderr)
            return 1
        try:
            os.chroot("/")
        except Exception as exc:
            print(f"Failed to chroot('/'): {exc}", file=sys.stderr)
            return 1
        log(json.dumps(plug_conf, indent=2))
        for module_name, module_conf in plug_conf.items():
            env_key = module_conf.get("env")
            if env_key and env_key in hook_env:
                log(f"Loading {module_name}")
                do_plugin(root_path, module_conf, modules_dir)
        try:
            ret = os.chroot(root_path)
            log(f"chroot return: {ret}")
        except Exception as exc:
            print(f"Failed to chroot('{root_path}'): {exc}", file=sys.stderr)
            return 1

        ldconfig()
        return 0
    finally:
        if logger_opened and logger:
            try:
                logger.close()
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
