# Build Python docker action

This action builds a python wheel from the repo and outputs a path and name
which can be used by future workflow steps.

## Inputs

## `who-to-greet`

**Required** The name of the person to greet. Default `"World"`.

## Outputs

## `wheel_path`

The path to the python wheel.

## `wheel_name`

The name of the python wheel.

## Example usage

uses: ./.github/actions/build-python
with:
  who-to-greet: 'Mona the Octocat'
