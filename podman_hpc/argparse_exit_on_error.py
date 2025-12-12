"""Compatibility wrapper for argparse exit-on-error behavior.

Python 3.9's argparse does not support the `exit_on_error` keyword. This module
provides a drop-in replacement that can be imported in place of `argparse` when
running on older Python versions. It exposes an `ArgumentParser` subclass that
respects the `exit_on_error` flag and suppresses `error()` behavior when
requested.
"""

from argparse import *  # noqa: F401,F403 - re-export argparse API for consumers
from argparse import ArgumentParser as _ArgumentParser


class ArgumentParser(_ArgumentParser):
    """ArgumentParser that can opt-out of exiting on parse errors.

    When constructed with `exit_on_error=False`, the parser will not call the
    default `error()` behavior (which prints a message and exits the program).
    This enables callers to handle parse errors programmatically using
    `parse_known_args` or by catching exceptions.
    """

    def __init__(self, *args, exit_on_error=True, **kwargs):
        """Initialize the parser.

        Parameters
        - exit_on_error: if False, suppress `error()` calls to avoid exiting.
        """
        self._exit_on_error = bool(exit_on_error)
        super().__init__(*args, **kwargs)

    def error(self, *args, **kwargs):
        """Override error to respect `exit_on_error` flag."""
        if self._exit_on_error:
            super().error(*args, **kwargs)
