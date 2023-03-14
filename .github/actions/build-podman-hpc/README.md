# Build Podman-HPC docker action

This is actually a pretty generic action that builds a python package, and then
an RPM from the sdist, but in this case it is being used to build Podman-HPC.

It exports some paths which can be used for uploading release assets in a 
subsequent workflow step.

## Inputs

No input variables.  All the magic is in the entrypoint script.

## Outputs

## `python_dist`

The path to python sdist and wheel.

## `srpm_dir`

Output directory for SRPM.

## `rpm_dir`

Output directory for RPM.

## Example usage

uses: ./.github/actions/build-podman-hpc

