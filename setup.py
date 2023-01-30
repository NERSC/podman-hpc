#!/usr/bin/env python
import subprocess
from setuptools import setup
from setuptools.command.build_py import build_py


class BuildMakeCommand (build_py):
    def run(self):
        super(build_py, self).run()
        subprocess.run(['make', 'setuptools-build_py'], check=True)


if __name__ == "__main__":
    setup(cmdclass={'build_py': BuildMakeCommand})
