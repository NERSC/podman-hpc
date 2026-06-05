#!/usr/bin/env python
import subprocess
from setuptools import setup
from setuptools.command.build_py import build_py
from setuptools.command.sdist import sdist
from packaging.version import Version
try:
    from importlib.metadata import version
except ModuleNotFoundError:
    from importlib_metadata import version

_monkeypatch_pep625 = (Version(version("setuptools")) < Version("69.3.0"))

if _monkeypatch_pep625:
    from types import MethodType
    from packaging.utils import canonicalize_name, canonicalize_version
    def _get_fullname_canonicalized(self):
        return "{}-{}".format(
            canonicalize_name(self.get_name()).replace('-','_'),
            canonicalize_version(self.get_version()),
        )

class build_py_with_make_epilogue(build_py):
    def run(self):
        super(build_py, self).run()
        subprocess.run(['make', 'setuptools-build_py'], check=True)

class sdist_pep625(sdist):
    def make_distribution(self):
        if _monkeypatch_pep625:
            self.distribution.get_fullname = MethodType(_get_fullname_canonicalized, self.distribution)
        super(sdist, self).make_distribution()

if __name__ == "__main__":
    setup(cmdclass={'build_py': build_py_with_make_epilogue, 'sdist': sdist_pep625})
