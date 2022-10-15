# Building a static mksquashfs

This directory contains a Dockerfile that
can be used to generate a static mksquashfs.
This utility is required during the migration.
It needs to be statically compiled so that the
binary can work on any architectually compatible
image.

## Instructions


```
docker build -t mksq .
podman run -it --rm -v /tmp:/d  mksq cp /usr/local/bin/mksquashfs /d/mksquashfs.static
```

