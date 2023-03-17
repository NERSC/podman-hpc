# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.1] - 2023-03-17

This is a minor release that fixes several bugs that have been found in early testing.

### Bugfixes

- Fixed an issue when the squash storage area wasn't yet initialized
- Don't use squash storage during builds (#42)
- Use rbind for bind mounts (#40)
- Enabled ignore_chown_errors (#30)

### Features

- Support recursive copy in modules (#40)


## [0.9.0] - 2023-02-03

Initial test release
