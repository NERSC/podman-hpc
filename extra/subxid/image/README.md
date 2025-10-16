# subxid-service

## Building
```
podman build --pull -t subxid:latest .
```

## Testing
You can run the container with:
```
mkdir output
podman run -it --rm -v $(realpath output):/subxid-html subxid:latest
```
... and a file named `subxid` should be generated in the directory output once per minute.
An `index.html` file will also be copied to this directory, which can be mounted with a
vanilla nginx container to host the file.

For debugging purposes, you can run the container with a shell:
```
podman run -it --rm --entrypoint /bin/sh subxid:latest
```

## PreBuilt Images
```
podman pull nersc/subxid
```

## Using the Image
You can use this image in conjunction with a vanilla webserver image such as `nginx:stable-alpine`. 
Using shared storage, simply volume mount the same directory at `$SUBXID_OUT` directory (default `/subxid-html`) 
in this container and at `/usr/share/nginx/html` in the nginx container.

You can control the path to the output directory in this image by setting the `$SUBXID_OUT` environment variable.

## LDAP Structure

The service expects the user to have a field in the LDAP record of the form:

```
description: 1001:2065536:65536
```

