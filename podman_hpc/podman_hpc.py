#!/usr/bin/env python

import sys
import os
import math
import socket
import re
import time
import click
from . import click_passthrough as cpt
from .migrate2scratch import MigrateUtils
from .migrate2scratch import ImageStore
from .siteconfig import SiteConfig
from multiprocessing import Process
from subprocess import Popen, PIPE


__version__ = "1.1.1"


def _round_nearest(x, a):
    return round(x / a) * a


def _param_scale_log2(x, p):
    return _round_nearest(p*(1 + math.log2(x)), p)


def podman_devnull(cmd, conf):
    """
    Run a command and ignore the output.
    Returns the exit code
    """
    newcmd = [conf.podman_bin]
    newcmd.extend(conf.get_cmd_extensions(cmd[0], None))
    newcmd.extend(cmd)
    proc = Popen(newcmd, stdout=PIPE, stderr=PIPE)
    proc.communicate()
    return proc.returncode


def pmi_fd():
    """
    This method kicks in if PMI_FD is set.  If set,
    this will dup that file descriptor to fd 3,
    set PMI_FD to 3, and add a new cli arg to pass
    the file descriptor.

    Note: This is a bit of a one off and we should
    find a cleaner solution when there is time.
    """

    if "PMI_FD" not in os.environ:
        return []
    pmifd = int(os.environ['PMI_FD'])
    os.dup2(pmifd, 3)
    os.set_inheritable(3, True)
    os.environ['PMI_FD'] = "3"
    return ["--preserve-fds", "1"]


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


# parse the `podman --help` page so it can be added as a custom epilog to
# main command help
initenv = os.environ
if "XDG_RUNTIME_DIR" in os.environ:
    os.environ.pop("XDG_RUNTIME_DIR")
with os.popen("podman --help") as fid:
    try:
        text = re.sub(
            "^.+(?=(Available Commands))", "\b\n", fid.read(), flags=re.DOTALL
        )
        podman_epilog = re.sub(r"(\n\s*\n)(?=\S)", "\n\n\b\n", text)
    except Exception:
        podman_epilog = "For additional commands please see `podman --help`."
os.environ = initenv

# decorator so that subcommands can request to receive SiteConfig object
pass_siteconf = click.make_pass_decorator(SiteConfig, ensure=True)


# podman-hpc command #######################################################
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
@click.option("--log-level", type=str, default="fatal", hidden=True)
def podhpc(ctx, additional_stores, squash_dir, log_level):
    """Manage pods, containers and images ... on HPC!

    The podman-hpc utility is a wrapper script around the podman
    container engine. It provides additional subcommands for ease of
    use and configuration of podman in a multi-node, multi-user high
    performance computing environment.

    """
    if not ctx.invoked_subcommand:
        click.echo(ctx.get_help())
        ctx.exit()

    # set up site configuration object
    try:
        conf = SiteConfig(squash_dir=squash_dir, log_level=log_level)
    except Exception as ex:
        sys.stderr.write(f"Error: {ex}... Exiting\n")
        sys.exit(1)

    if not os.path.exists(conf.squash_dir):
        ImageStore(conf.squash_dir, read_only=False).init_storage()
    conf.read_site_modules()
    conf.config_env(hpc=True)

    # add appropriate flags to call_podman based on invoked subcommand
    # defcmd = ctx.command.default_command_fn
    invcmd = ctx.command.get_command(ctx, ctx.invoked_subcommand)
    for k, v in conf.sitemods.get(ctx.invoked_subcommand, {}).items():
        if 'cli_arg' not in v:
            continue
        invcmd = click.option(
            f"--{v['cli_arg']}",
            is_flag=True,
            hidden=v.get("hidden", False),
            help=v.get("help"),
        )(invcmd)

    # save the site config to a context object so it can be passed to
    # subcommands
    ctx.obj = conf


# podman-hpc infohpc subcommand ############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
def infohpc(siteconf):
    """Dump configuration information for podman_hpc."""
    print(f"Podman-HPC Version: {__version__}")
    siteconf.dump_config()
    sys.exit()


# podman-hpc migrate subcommand ############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
@click.argument("image", type=str)
def migrate(siteconf, image):
    """Migrate an image to squashed."""
    mu = MigrateUtils(conf=siteconf)
    mu.migrate_image(image)
    sys.exit()


# podman-hpc rmsqi subcommand ##############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
@click.argument("image", type=str)
def rmsqi(siteconf, image):
    """Removes a squashed image."""
    mu = MigrateUtils(conf=siteconf)
    mu.remove_image(image)

# podman-hpc images subcommand #############################################
@pass_siteconf
@click.pass_context
@click.argument("podman_args", nargs=-1, type=click.UNPROCESSED)
def images(ctx, siteconf, image, podman_args, **site_opts):
    """Displays images in both local and additionalimagestore."""
    cmd = [siteconf.podman_bin, "images"]
    cmd.extend(podman_args)
    cmd.extend(siteconf.get_cmd_extensions("images", site_opts))

# podman-hpc pull subcommand (modified) ####################################
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
def pull(ctx, siteconf, image, podman_args, **site_opts):
    """Pulls an image to a local repository and makes a squashed copy."""
    cmd = [siteconf.podman_bin, "pull"]
    cmd.extend(podman_args)
    cmd.extend(siteconf.get_cmd_extensions("pull", site_opts))
    cmd.append(image)
    proc = Popen(cmd)
    proc.communicate()
    if proc.returncode == 0:
        sys.stdout.write(f"INFO: Migrating image to {siteconf.squash_dir}\n")
        mu = MigrateUtils(conf=siteconf)
        mu.migrate_image(image)
    else:
        sys.stderr.write("Pull failed.\n")
        sys.exit(proc.returncode)

# podman-hpc shared-run subcommand #########################################
@podhpc.command(
    context_settings=dict(
        ignore_unknown_options=True,
    ),
    options_metavar="[options]",
)
@pass_siteconf
@click.argument(
    "run-args",
    nargs=-1,
    type=click.UNPROCESSED,
    metavar="IMAGE [COMMAND [ARG...]]",
)
def shared_run(conf, run_args, **site_opts):
    """Launch a single container and exec many threads in it

    This is the recommended way to launch a container from a parallel launcher
    such as Slurm `srun` or `mpirun`. One container will be started (per node),
    and all process tasks will then be launched into that container via `exec`
    subcommand.

    When all `exec` processes have concluded, the container will close and
    remove itself.

    For valid flag options, see help pages for `run` and `exec` subcommands:

    \b
      podman-hpc run --help
      podman-hpc exec --help
    """
    # click.echo(f"Launching a shared-run with args: {sys.argv}")
    _shared_run(conf, run_args, **site_opts)

def _shared_run(conf, run_args, **site_opts):
    """
    Internal function for the shared_run.  This is so we can
    also call it when the user does run but enabled a module
    that has shared_run set to True. 
    """

    localid = os.environ.get(conf.localid_var)
    ntasks_raw = os.environ.get(conf.tasks_per_node_var, "1")
    ntasks = int(re.search(conf.ntasks_pattern, ntasks_raw)[0])
    container_name = f"uid-{os.getuid()}-pid-{os.getppid()}"
    sock_name = f"/tmp/uid-{os.getuid()}-pid-{os.getppid()}"

    # construct run and exec commands from user options
    # We need to filter out any run args in the run_args
    cmd = [conf.podman_bin, "run", "--help"]
    valid_params = cpt.filterValidOptions(list(run_args), cmd)
    # Find the first occurence not in the valid list
    idx = 0
    for idx, item in enumerate(run_args):
        if item in valid_params:
            continue
        break
    image = run_args[idx]
    container_cmd = run_args[idx+1:]
    # TODO: maybe do some validation on the iamge and container_cmd

    options = sys.argv[
        sys.argv.index("shared-run") + 1: sys.argv.index(image)
    ]

    run_cmd = [conf.podman_bin, "run", "--rm", "-d", "--name", container_name]
    run_cmd.extend(
        cpt.filterValidOptions(options, [conf.podman_bin, "run", "--help"])
    )
    run_cmd.extend(conf.get_cmd_extensions("run", site_opts))
    run_cmd.append(image)
    run_cmd.extend(conf.shared_run_command)

    exec_cmd = [
        conf.podman_bin,
        "exec",
    ]
    exec_cmd.extend(conf.get_cmd_extensions("exec", site_opts))
    exec_cmd.extend(pmi_fd())
    exec_cmd.extend(conf.shared_run_exec_args)
    exec_cmd.extend(
        cpt.filterValidOptions(options, [conf.podman_bin, "exec", "--help"])
    )
    exec_cmd.extend([container_name] + list(container_cmd))
    # click.echo(f"run_cmd is: {run_cmd}")
    # click.echo(f"exec_cmd is: {exec_cmd}")

    # Start monitor and run threads
    monitor_thread = None
    run_thread = None
    proc = None
    if (localid is None or int(localid) == 0):
        monitor_thread = Process(target=monitor, args=(sock_name, ntasks,
                                                       container_name, conf))
        monitor_thread.start()
        run_thread = Process(target=shared_run_exec, args=(run_cmd, conf.env))
        run_thread.start()

    try:
        # wait for container to exist
        comm = ["container", "exists", container_name]
        start_time = time.time()
        wait_poll_interval = _param_scale_log2(ntasks, conf.wait_poll_interval)
        wait_timeout = _param_scale_log2(ntasks, conf.wait_timeout)
        while True:
            time.sleep(wait_poll_interval)
            if podman_devnull(comm, conf) == 0:
                break
            if time.time() - start_time > wait_timeout:
                msg = "Timeout waiting for shared-run start"
                raise OSError(msg)
            if run_thread and run_thread.exitcode:
                raise OSError("Failed to start container")
        comm = ["wait", "--condition", "running", container_name]
        podman_devnull(comm, conf)
        fds = [0, 1, 2]
        if 'PMI_FD' in os.environ:
            fds.append(int(os.environ['PMI_FD']))
            conf.env["PMI_FD"] = os.environ["PMI_FD"]
        proc = Popen(exec_cmd, env=conf.env, pass_fds=fds)
        proc.communicate()
        send_complete(sock_name, localid)
        # Close out threads
        if monitor_thread:
            monitor_thread.join()
        if run_thread:
            run_thread.join()
    except Exception as ex:
        sys.stderr.write(str(ex))
        if monitor_thread:
            sys.stderr.write("Killing monitor thread")
            monitor_thread.kill()
        if run_thread:
            run_thread.kill()
        if os.path.exists(sock_name):
            os.remove(sock_name)
    finally:
        exit_code = 1
        if proc:
            exit_code = proc.returncode
        sys.exit(exit_code)


# podman-hpc call_podman subcommand (default, hidden, passthrough) #########
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
    cmd.extend(pmi_fd())
    cmd.extend(podman_args)

    # if the help flag is called, we pass podman's STDOUT stream through a pipe
    # to a stream editor, to inject additional help page info
    if help:
        app_name = ctx.find_root().command_path
        passthrough_name = os.path.basename(cmd[0])

        formatter = ctx.make_formatter()
        ctx.command.format_options(ctx, formatter)
        app_options = ""
        if formatter.getvalue():
            app_options = (
                f"{app_name.capitalize()} {formatter.getvalue()}\n")

        cmd = [siteconf.podman_bin, ctx.info_name, "--help"]
        proc = Popen(cmd, env=siteconf.env, stdout=PIPE)
        out, _ = proc.communicate()
        option_line = f"{app_options}{passthrough_name.capitalize()}"
        option_line += " options follow:"
        newout = ""
        for line in out.decode().split("\n"):
            newline = line.replace(passthrough_name, app_name)
            newline = newline.replace("Options:", option_line)
            newout += f"{newline}\n"

        sys.stdout.write(newout)
    else:
        if siteconf.shared_run:
            for idx, arg in enumerate(sys.argv):
                if arg == "run":
                    sys.argv[idx] = "shared-run"
            _shared_run(siteconf, podman_args, **site_opts)
        else:
            if 'PMI_FD' in os.environ:
                siteconf.env["PMI_FD"] = os.environ["PMI_FD"]
            os.execve(cmd[0], cmd, siteconf.env)


def shared_run_exec(run_cmd, env):
    proc = Popen(run_cmd, stdout=PIPE, stderr=PIPE, env=env)
    out, err = proc.communicate()
    if proc.returncode != 0:
        sys.stderr.write(err.decode())


def monitor(sockfile, ntasks, container_name, conf):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        os.remove(sockfile)
    except OSError:
        pass
    s.bind(sockfile)
    ct = 0
    while True:
        s.listen()
        conn, addr = s.accept()
        ct += 1
        if ct == ntasks:
            break
    conn.close()
    os.remove(sockfile)
    # cleanup
    podman_devnull(["kill", container_name], conf)
    podman_devnull(["rm", container_name], conf)


def send_complete(sockfile, lid):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(sockfile)
        s.send(bytes(lid, 'utf-8'))
        s.close()
    except Exception as ex:
        sys.stderr.write(f"send_complete failed for {lid}\n{ex}\n")


def main():
    podhpc(prog_name="podman-hpc")


if __name__ == "__main__":
    main()
