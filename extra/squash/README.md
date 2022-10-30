# Building a static mksquashfs

This directory contains a Dockerfile that
can be used to generate a static mksquashfs.
This utility is required during the migration.
It needs to be statically compiled so that the
binary can work on any architectually compatible
image.

## Instructions

This requires podman to be installed and logged into
Docker Hub.

```
podman login docker.io
make rpm
```

