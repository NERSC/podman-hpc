# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.1] - 2024-12-05

This is a patch release that primarily implements bugfixes and other minor updates.

- Fix for missing layers that causes a migrated image to not show up on all nodes.
- Fix for duplicate tagging on migrated images.
- Fix for timeouts with shared run
- Adds convience modules for volume mounts

## [1.1.0] - 2023-11-12

This is a minor release. It adds initial support for OpenMPI4/PMI2 and OpenMPI5/PMIx.

- Adds ability to pass through file descriptors needed for PMI2 (#95)

## [1.0.4] - 2023-10-02

This is a patch release that fixes a bug.

- Fixes bug where squashed images in the additionalimagestore were not displayed by the `podman-hpc images` command (#87)

## [1.0.3] - 2023-09-01

This is a patch release that fixes several bugs.

- Fixes issue using userns keep-id for squashed images (#83)
- Fixes inconsistencies in pull, build, and run settings (#81, #80, #76). Makes it possible for users to override default settings and provide their own.

## [1.0.2] - 2023-06-15

This is a patch release that fixes several additional bugs.

- Fixes issue that causes unclean exit from leftover mounts, contributed by Pat Tovo at HPE (#54)
- Fixes issue that causes problems with keepid during image squash (#69)
- Fixes issue that prevents images from building on compute nodes (#66)
- podman-hpc pull now returns nonzero exit if something fails (#57)
- Fix issue caused by squashing different images with same name and tag (#53)

## [1.0.1] - 2023-03-17

This is a patch release that fixes several bugs that have been found in early testing.

### Bugfixes

- Fixed an issue when the squash storage area wasn't yet initialized
- Don't use squash storage during builds (#42)
- Use rbind for bind mounts (#40)
- Enabled ignore_chown_errors (#30)

### Features

- Support recursive copy in modules (#40)


## [0.9.0] - 2023-02-03

Initial test release
