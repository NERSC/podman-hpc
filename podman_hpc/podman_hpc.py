#!/usr/bin/env python

import sys
import os
import socket
import re
import time
import click
from . import click_passthrough as cpt
from .migrate2scratch import MigrateUtils
from .siteconfig import SiteConfig


try:
    from os import waitstatus_to_exitcode
except ImportError:

    def waitstatus_to_exitcode(status):
        return (
            os.WEXITSTATUS(status)
            if os.WIFEXITED(status)
            else -1 * os.WTERMSIG(status)
        )


# function to specify help message formatting to mimic the podman help page.
# follows the style of click.Command.format_help()
# this will be inherited by subcommands created with @podhpc.command()
def podman_format(self, ctx, formatter):
    self.format_short_help(ctx, formatter)
    self.format_description(ctx, formatter)
    formatter.write_paragraph()
    self.format_usage(ctx, formatter)
    self.format_options(ctx, formatter)
    if self.epilog:
        with formatter.section("Podman help page follows"):
            self.format_epilog(ctx, formatter)


# parse the `podman --help` page so it can be added as a custom epilog to main command help
initenv = os.environ
if "XDG_RUNTIME_DIR" in os.environ:
    os.environ.pop("XDG_RUNTIME_DIR")
with os.popen("podman --help") as fid:
    try:
        text = re.sub(
            "^.+(?=(Available Commands))", "\b\n", fid.read(), flags=re.DOTALL
        )
        podman_epilog = re.sub("(\n\s*\n)(?=\S)", "\n\n\b\n", text)
    except:
        podman_epilog = "For additional commands please see `podman --help`."
os.environ = initenv

# decorator so that subcommands can request to receive SiteConfig object
pass_siteconf = click.make_pass_decorator(SiteConfig, ensure=True)


### podman-hpc command #######################################################
@click.group(
    cls=cpt.PassthroughGroup,
    custom_format=podman_format,
    epilog=podman_epilog,
    options_metavar="[options]",
    passthrough="podman",
    invoke_without_command=True,
)
@click.pass_context
@click.option(
    "--additional-stores", type=str, help="Specify other storage locations"
)
@click.option(
    "--squash-dir",
    type=str,
    help="Specify alternate squash directory location",
)
@click.option(
    "--update-conf",
    is_flag=True,
    show_default=True,
    default=False,
    help="Force update of storage conf",
)
@click.option("--log-level", type=str, default="fatal", hidden=True)
def podhpc(ctx, additional_stores, squash_dir, update_conf, log_level):
    """Manage pods, containers and images ... on HPC!

    The podman-hpc utility is a wrapper script around the podman
    container engine. It provides additional subcommands for ease of
    use and configuration of podman in a multi-node, multi-user high
    performance computing environment.

    """
    overwrite = additional_stores or squash_dir or update_conf
    if not (overwrite or ctx.invoked_subcommand):
        click.echo(ctx.get_help())
        ctx.exit()

    # set up site configuration object
    conf = SiteConfig(squash_dir=squash_dir, log_level=log_level)
    conf.read_site_modules()
    # migrate was here, is that important?
    conf.config_storage(additional_stores)
    conf.config_containers()
    conf.config_env(hpc=True)

    # optionally, save the storage conf
    conf.export_storage_conf(overwrite=overwrite)
    conf.export_containers_conf(overwrite=overwrite)

    # add appropriate flags to call_podman based on invoked subcommand
    # defcmd = ctx.command.default_command_fn
    invcmd = ctx.command.get_command(ctx, ctx.invoked_subcommand)
    for k, v in conf.sitemods.get(ctx.invoked_subcommand, {}).items():
        invcmd = click.option(
            f"--{v['cli_arg']}",
            is_flag=True,
            hidden=v.get("hidden", False),
            help=v.get("help"),
        )(invcmd)

    # save the site config to a context object so it can be passed to subcommands
    ctx.obj = conf


### podman-hpc migrate subcommand ############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
@click.argument("image", type=str)
def migrate(siteconf, image):
    """Migrate an image to squashed."""
    mu = MigrateUtils(dst=siteconf.squash_dir)
    mu.migrate_image(image)
    sys.exit()


### podman-hpc rmsqi subcommand ##############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
@click.argument("image", type=str)
def rmsqi(siteconf, image):
    """Removes a squashed image."""
    mu = MigrateUtils(dst=siteconf.squash_dir)
    mu.remove_image(image)


### podman-hpc pull subcommand (modified) ####################################
@podhpc.command(
    context_settings=dict(
        ignore_unknown_options=True,
    ),
    options_metavar="[options]",
)
@pass_siteconf
@click.pass_context
@click.argument("podman_args", nargs=-1, type=click.UNPROCESSED)
@click.argument("image")
def pull(ctx, siteconf, image, podman_args):
    """Pulls an image to a local repository and makes a squashed copy."""
    pid = os.fork()
    if pid == 0:
        cmd = [siteconf.podman_bin, "pull"]
        cmd.extend(podman_args)
        cmd.append(image)
        os.execve(cmd[0], cmd, os.environ)
    pid, status = os.wait()
    if status == 0:
        click.echo(f"INFO: Migrating image to {siteconf.squash_dir}")
        ctx.invoke(migrate, image=image)
    else:
        sys.stderr.write("Pull failed.\n")


### podman-hpc shared-run subcommand #########################################
@podhpc.command(
    context_settings=dict(
        ignore_unknown_options=True,
    ),
    options_metavar="[options]",
)
@pass_siteconf
@click.argument("image")
@click.argument(
    "container-cmd",
    nargs=-1,
    type=click.UNPROCESSED,
    metavar="[COMMAND [ARG...]]",
)
def shared_run(conf, image, container_cmd, **site_opts):
    """Launch a single container and exec many threads in it

    This is the recommended way to launch a container from a parallel launcher
    such as Slurm `srun` or `mpirun`. One container will be started (per node), and all
    process tasks will then be launched into that container via `exec` subcommand.
    When all `exec` processes have concluded, the container will close and remove itself.

    For valid flag options, see help pages for `run` and `exec` subcommands:

    \b
      podman-hpc run --help
      podman-hpc exec --help
    """
    # click.echo(f"Launching a shared-run with args: {sys.argv}")

    localid_var = os.environ.get("PODMANHPC_LOCALID_VAR", "SLURM_LOCALID")
    ntasks_var = os.environ.get("PODMANHPC_TASKS_PER_NODE_VAR", "SLURM_STEP_TASKS_PER_NODE")

    localid = os.environ.get(localid_var)
    ntasks = int(os.environ.get(ntasks_var, "1").split('(')[0])
    container_name = f"uid-{os.getuid()}-pid-{os.getppid()}"
    sock_name = f"/tmp/uid-{os.getuid()}-pid-{os.getppid()}"

    # construct run and exec commands from user options
    options = sys.argv[
        sys.argv.index("shared-run") + 1 : sys.argv.index(image)
    ]

    run_cmd = [conf.podman_bin, "run", "--rm", "-d", "--name", container_name]
    run_cmd.extend(
        cpt.filterValidOptions(options, [conf.podman_bin, "run", "--help"])
    )
    run_cmd.extend(conf.get_cmd_extensions("run", site_opts))
    run_cmd.extend([image, "sleep", "infinity"])

    exec_cmd = [
        conf.podman_bin,
        "exec",
        "-e",
        'PALS_*',
        "-e",
        'PMI_*',
        "-e",
        'SLURM_*',
    ]
    exec_cmd.extend(
        cpt.filterValidOptions(options, [conf.podman_bin, "exec", "--help"])
    )
    exec_cmd.extend([container_name] + list(container_cmd))

    # click.echo(f"run_cmd is: {run_cmd}")
    # click.echo(f"exec_cmd is: {exec_cmd}")

    # Start monitor thread
    if (localid is None or int(localid) == 0) and os.fork():
        monitor(sock_name, ntasks, container_name, conf)

    # start container with `podman run ...`
    if (localid is None or int(localid) == 0) and os.fork():
        devnull = os.open('/dev/null', os.O_WRONLY)
        os.dup2(devnull, 1)
        os.execve(run_cmd[0], run_cmd, conf.env)
    # wait for container to exist
    while waitstatus_to_exitcode(
        os.system(
            f"{conf.podman_bin} --log-level fatal container exists {container_name}"
        )
    ):
        time.sleep(0.2)
    # wait for container to be "running"
    os.system(
        f"{conf.podman_bin} wait --log-level fatal --condition running {container_name} >/dev/null 2>&1"
    )
    # launch cmd in container with `podman exec ...`
    pid = os.fork()
    if pid == 0:
        os.execve(exec_cmd[0], exec_cmd, conf.env)
    else:
        os.waitpid(pid, 0)
        send_complete(sock_name, localid)


### podman-hpc call_podman subcommand (default, hidden, passthrough) #########
@podhpc.default_command(
    context_settings=dict(ignore_unknown_options=True, help_option_names=[]),
    hidden=True,
)
@pass_siteconf
@click.pass_context
@click.option("--help", is_flag=True, hidden=True)
@click.argument("podman_args", nargs=-1, type=click.UNPROCESSED)
def call_podman(ctx, siteconf, help, podman_args, **site_opts):
    cmd = [siteconf.podman_bin, ctx.info_name]
    cmd.extend(siteconf.get_cmd_extensions(ctx.info_name, site_opts))
    cmd.extend(podman_args)

    # click.echo("will call:")
    # click.echo(cmd)

    # if the help flag is called, we pass podman's STDOUT stream through a pipe
    # to a stream editor, to inject additional help page info
    if help:
        cmd.insert(2, "--help")
        app_name = ctx.find_root().command_path
        passthrough_name = os.path.basename(cmd[0])

        formatter = ctx.make_formatter()
        ctx.command.format_options(ctx, formatter)
        app_options = ""
        if formatter.getvalue():
            app_options = (
                f"{app_name.capitalize()} {formatter.getvalue()}\n".replace(
                    "\n", "\\n"
                )
            )

        cmd_sed = [
            "/usr/bin/sed",
            "-e",
            f"s/{passthrough_name}/{app_name}/",
            "-e",
            f"s/Options:/{app_options}{passthrough_name.capitalize()} &/",
        ]

        STDIN = 0
        STDOUT = 1
        p_read, p_write = os.pipe()
        if os.fork():
            os.close(p_write)
            os.dup2(p_read, STDIN)
            os.execv(cmd_sed[0], cmd_sed)
            os._exit(os.EX_OSERR)
        else:
            os.close(p_read)
            os.dup2(p_write, STDOUT)

    os.execve(cmd[0], cmd, siteconf.env)


def monitor(sockfile, ntasks, container_name, conf):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.remove(sockfile)
    except OSError:
        pass
    s.bind(sockfile)
    ct = 0
    while True:
        s.listen(1)
        conn, addr = s.accept()
        data = conn.recv(1024)
        ct += 1
        if ct == ntasks:
            break
    conn.close()
    os.remove(sockfile)
    # cleanup
    log = "--log-level fatal"
    os.system(
            f"{conf.podman_bin} {log} kill {container_name} > /dev/null 2>&1"
        )
    os.system(
            f"{conf.podman_bin} {log} rm {container_name} > /dev/null 2>&1"
        )
    sys.exit()


def send_complete(sockfile, lid):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(sockfile)
    s.send(bytes(lid, 'utf-8'))
    s.close()


def main():
    podhpc(prog_name="podman-hpc")


if __name__ == "__main__":
    main()
