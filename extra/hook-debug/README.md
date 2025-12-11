# Hook Debug

This directory contains a script to help troubleshoot hook tool issues.

## Example usage

```console
> ./hook-debug.sh
Configuring debug hook dir at /tmp/tmp.IonqaOURw3

To use debug hook, set PODMANHPC_HOOKS_DIR=/tmp/tmp.IonqaOURw3/hooks.d
Check log file at /tmp/tmp.IonqaOURw3/hook.dbg

> PODMANHPC_HOOKS_DIR=/tmp/tmp.IonqaOURw3/hooks.d podman-hpc run --userns=keep-id --device nvidia.com/gpu=all --rm ubuntu nvidia-smi -L
Error: OCI runtime error: crun: error executing hook `/tmp/tmp.IonqaOURw3/hook_tool.sh` (exit code: 1)

> cat /tmp/tmp.IonqaOURw3/hook.dbg
Traceback (most recent call last):
  File "/usr/bin/hook_tool", line 11, in <module>
    load_entry_point('podman-hpc==1.1.4', 'console_scripts', 'hook_tool')()
  File "/usr/lib/python3.6/site-packages/podman_hpc/hook_tool.py", line 173, in main
    cf = json.load(open("config.json"))
FileNotFoundError: [Errno 2] No such file or directory: 'config.json'
```

Additional commands could be added to the generated hook tool wrapper script
at `$DEBUG_HOOK_DIR/hook_tool.sh` to inspect the environment.

