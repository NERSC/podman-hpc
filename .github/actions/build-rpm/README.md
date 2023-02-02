# Build RPM docker action

This action builds an RPM from the repo and outputs a path and name
which can be used by future workflow steps.

## Inputs

## `who-to-greet`

**Required** The name of the person to greet. Default `"World"`.

## Outputs

## `source_rpm_path`

The path to the Source RPM file.

## `source_rpm_name`

The name of the Source RPM.

## Example usage

uses: ./.github/actions/build-rpm
with:
  who-to-greet: 'Mona the Octocat'
