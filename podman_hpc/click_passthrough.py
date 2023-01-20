import os
import re
import click
import warnings
import inspect
import typing as t
import functools

try:
    from argparse import ArgumentParser as _

    _ = _(exit_on_error=True)
    import argparse
except TypeError:
    from . import argparse_exit_on_error as argparse


class DefaultCommandGroup(click.Group):
    def __init__(self, *args, hide_default=False, **attrs):
        super().__init__(*args, **attrs)
        self.default_command_fn = None
        self.hide_default = hide_default

    def set_default_command(self, cmd, name=None):
        if not self.default_command_fn:
            name = name or cmd.name
            if name is None:
                raise TypeError("Command has no name.")
            self.default_command_fn = cmd
        else:
            warnings.warn(
                f"{self.name}.default_command_fn is already set: " +
                f"{self.default_command_fn}",
                UserWarning,
                stacklevel=2,
            )

    def add_command(self, cmd, name=None, default=False):
        super().add_command(cmd, name)
        if default:
            self.set_default_command(cmd)

    def default_command(self, *args, **kwargs):
        from click.decorators import command

        if self.command_class and kwargs.get("cls") is None:
            kwargs["cls"] = self.command_class

        func: t.Optional[t.Callable] = None

        if args and callable(args[0]):
            assert (
                len(args) == 1 and not kwargs
            ), "Use 'command(**kwargs)(callable)' to provide arguments."
            (func,) = args
            args = ()

        def decorator(f: t.Callable[..., t.Any]) -> click.Command:
            cmd: click.Command = command(*args, **kwargs)(f)
            self.set_default_command(cmd)
            self.add_command(cmd)
            return cmd

        if func is not None:
            return decorator(func)

        return decorator

    def get_command(
        self, ctx: click.Context, cmd_name: str
    ) -> t.Optional[click.Command]:
        return self.commands.get(cmd_name, self.default_command_fn)

    def list_commands(self, ctx: click.Context) -> t.List[str]:
        if self.default_command_fn and self.hide_default:
            return [
                cmd
                for cmd in sorted(self.commands)
                if not (
                    cmd == self.default_command_fn.name and self.hide_default
                )
            ]
        else:
            return sorted(self.commands)


def customize_help(cls):
    """Decorator to add custom help formatting on _click classes.

    This decorator can be placed before class declarations for classes
    inheriting from click.Command.

    The class __init__ method is modified to take an additional keyword
    parameter, `custom_format`.  The value should be a function which
    accepts three parameters (self, ctx, formatter), following the
    convention and syntax of click.Command.format_help().  The decorator
    additionally adds other convenience methods to extract description
    and example text from the docstring.

    If no custom formatting function is provided when the decorated
    class is instantiated, it may be provided later by setting the
    custom_format attribute on the instantiated object.

    If no custom_format is set when the instance attempts to display
    the help message, then the object will attempt to inherit a format
    from parents in it's click calling context, until either (1) a
    custom_format is found, (2) an undecorated parent is encountered
    while ascending the context tree, or (3) the root of the calling
    context is reached.  If no custom formatting function is present
    or inherited, then the decorated class will revert to standard
    click help formatting.

    """
    # wrappers to modify, otherwise just replace
    def mod__init__(cls_init):
        @functools.wraps(cls_init)
        def wrapper(self, *args, custom_format=None, **kwargs):
            self.custom_format = custom_format
            return cls_init(self, *args, **kwargs)

        return wrapper

    def get_custom_format(self, ctx):
        if self.custom_format is not None:
            return self.custom_format
        elif ctx.parent is not None:
            return getattr(
                ctx.parent.command, "get_custom_format", lambda x: None
            )(ctx.parent)
        else:
            return None

    def format_short_help(self, ctx, formatter):
        if getattr(self, "short_help", None) is None:
            self.short_help = self.help.splitlines()[0] if self.help else None
        if getattr(self, "short_help", None):
            formatter.write_text(self.short_help)

    def format_description(self, ctx, formatter):
        if getattr(self, "description", None) is None:
            self.description = (
                inspect.cleandoc(re.sub("^.+", "", self.help))
                if self.help
                else None
            )
        if getattr(self, "description", None):
            with formatter.section("Description"):
                formatter.write_text(self.description)

    def mod_format_help(cls_format_help):
        @functools.wraps(cls_format_help)
        def wrapper(self, ctx, formatter):
            custom_format_help = self.get_custom_format(ctx)
            if custom_format_help is not None:
                custom_format_help(self, ctx, formatter)
            else:
                cls_format_help(self, ctx, formatter)

        return wrapper

    cls.__init__ = mod__init__(cls.__init__)
    cls.get_custom_format = get_custom_format
    cls.format_short_help = format_short_help
    cls.format_description = format_description
    cls.format_help = mod_format_help(cls.format_help)
    return cls


@customize_help
class TemplateHelpCommand(click.Command):
    pass


@customize_help
class PassthroughGroup(DefaultCommandGroup):
    def __init__(self, *args, passthrough=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.command_class = TemplateHelpCommand
        if passthrough is not None:
            self.init_passthrough(passthrough)

    def init_passthrough(self, passthrough_bin):
        """Generate a default command for this group,
        which calls the specified passthrough bin."""
        pass


def parametersFromPassthrough(cmd, passthrough):
    pass


def filterValidOptions(options, subcmd, option_regex=None):
    """Filter invalid arguments from an argument list
    for a given subcommand based on its --help text."""
    if not option_regex:
        option_regex = re.compile(r"^\s*(?:(-\w), )?(--\w[\w\-]+)(?:\s(\w+))?")

    # create a dummy parser and populate it with valid option flags
    p = argparse.ArgumentParser(exit_on_error=False, add_help=False)
    with os.popen(" ".join(subcmd)) as f:
        for line in f:
            opt = option_regex.match(line)
            if opt:
                action = "store" if opt.groups()[2] else "store_true"
                flags = [flag for flag in opt.groups()[:-1] if flag]
                p.add_argument(*flags, action=action)

    # remove unknown options from the given options
    valid_options = options.copy()
    unknowns = p.parse_known_args(valid_options)[1]
    # some args may match unknowns but actually be valid because they
    # provide a value for a valid flag, store these "safe" indices here
    uk_safe_index = {}
    # iterate until we've accounted for all the unknown options
    while unknowns:
        ukd = {}  # candidate indices of where to remove unknowns
        for uk in set(unknowns):
            ukd[uk] = [
                idx
                for idx, opt in enumerate(valid_options)
                if (opt == uk and idx not in uk_safe_index.get(uk, []))
            ]
        uk = unknowns.pop(0)
        # find and remove an invalid occurence of uk
        while True:
            valid_options_tmp = valid_options.copy()
            valid_options_tmp.pop(ukd[uk][0])
            try:
                if p.parse_known_args(valid_options_tmp)[1] == unknowns:
                    valid_options.pop(ukd[uk][0])
                    break
            except argparse.ArgumentError:
                pass
            uk_safe_index.setdefault(uk, []).append(ukd[uk].pop(0))
    return valid_options
