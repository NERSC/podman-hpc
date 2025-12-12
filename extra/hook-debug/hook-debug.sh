#!/bin/bash
set -e

DEBUG_HOOK_DIR="${DEBUG_HOOK_DIR:-$(mktemp -d)}"
DEBUG_HOOK_TOOL="${DEBUG_HOOK_DIR}/hook_tool.sh"
DEBUG_HOOK_OUTPUT="${DEBUG_HOOK_DIR}/hook.dbg"

echo "Configuring debug hook dir at $DEBUG_HOOK_DIR"

mkdir -p $DEBUG_HOOK_DIR/hooks.d

cat <<EOF > $DEBUG_HOOK_TOOL
#!/bin/bash
exec hook_tool $@  >> $DEBUG_HOOK_OUTPUT 2>&1
EOF

chmod +x $DEBUG_HOOK_TOOL

cat <<EOF > $DEBUG_HOOK_DIR/hooks.d/02-hook_tool.json
{
    "version": "1.0.0",
    "hook": {
        "path": "$DEBUG_HOOK_TOOL",
        "args": ["hook_tool"]
    },
    "when": {
        "annotations": {
           "podman_hpc.hook_tool": "true"
        }
    },
    "stages": ["prestart"]
}
EOF

echo
echo "To use debug hook, set PODMANHPC_HOOKS_DIR=$DEBUG_HOOK_DIR/hooks.d"
echo
echo "Check log file at $DEBUG_HOOK_OUTPUT"
echo
