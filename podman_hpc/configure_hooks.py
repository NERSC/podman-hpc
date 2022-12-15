#!/usr/bin/env python3
import sys
import os
import pathlib
import argparse
from inspect import cleandoc


hook_text = cleandoc(
    f"""
    {{
        "version": "1.0.0",
        "hook": {{
            "path": "{os.path.join(sys.prefix,'bin','hook_tool')}",
            "args": ["hook_tool"]
        }},
        "when": {{
            "annotations": {{
               "podman_hpc.hook_tool": "true"
            }}
        }},
        "stages": ["prestart"]
    }}

    """
)


def write_hook(hooksd, hook, filemode):
    hook_path = os.path.join(hooksd, hook)
    os.makedirs(hooksd, exist_ok=True)
    try:
        with open(hook_path, filemode) as fid:
            fid.write(hook_text)
        print(f"Successfully wrote hook configuration at {hook_path}")
    except FileExistsError:
        print(f"Hook is already configured at {hook_path}. No changes made.")


def main():
    p = argparse.ArgumentParser(
        prog="configure_hooks",
        description="Write a hooks.json and install to hooksd for podman-hpc.",
    )
    p.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Force overwrite of existing hook file.",
    )
    p.add_argument(
        "--hooksd",
        type=pathlib.Path,
        default=os.path.join(
            sys.prefix, "share", "containers", "oci", "hooks.d"
        ),
        help="Path to write hook file.",
    )

    ns = p.parse_args()
    hook = "02-hook_tool.json"
    filemode = "w" if ns.force else "x"

    write_hook(ns.hooksd, hook, filemode)


if __name__ == "__main__":
    main()
