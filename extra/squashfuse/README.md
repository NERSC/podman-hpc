# Squashfuse

Squashfuse is required for podman-hpc. Some distributions (e.g. SLES) do not currently have an RPM for this. Here are instructions for building it.

Get the source from here: https://github.com/vasi/squashfuse

Modify this example spec file. Note this was modified from a spec file from Kyle Fazzari.

## Basic Steps

1. Retrieve the a release from https://github.com/vasi/squashfuse/releases
1. Modify the spec to match the release version
1. Use `rpmbuild -ba squashfuse.spec` to build the RPM
