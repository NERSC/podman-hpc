#!/usr/bin/env python
import os
import sys
import re
import click
from . import click_passthrough as cpt
from .migrate2scratch import MigrateUtils
from .siteconfig import SiteConfig
        
        
# decorator so that subcommands receive SiteConfig object as first arg
pass_siteconf = click.make_pass_decorator(SiteConfig, ensure=True)


### podman-hpc command #######################################################
@click.group(cls=cpt.PassthroughGroup,passthrough='podman')
@click.pass_context
@click.option("--additional-stores", type=str,
                    help="Specify other storage locations")
@click.option("--squash-dir", type=str,
                    help="Specify alternate squash directory location")
@click.option("--update-conf", is_flag=True, show_default=True, default=False,
                    help="Force update of storage conf")
@click.option("--log-level", type=str, default="fatal", hidden=True)
def podhpc(ctx,additional_stores,squash_dir,update_conf,log_level):
    """Manage pods, containers and images ... on HPC!
    
    The podman-hpc utility is a wrapper script around the podman
    container engine. It provides additional subcommands for ease of
    use and configuration of podman in a multi-node, multi-user high 
    performance computing environment.
        
    """
    # set up site configuration object
    conf = SiteConfig(squash_dir=squash_dir,log_level=log_level)
    conf.read_site_modules()
    # migrate was here, is that important?
    conf.config_storage(additional_stores)
    conf.config_containers()
    conf.config_env(hpc=True)

    # optionally, save the storage conf
    overwrite = additional_stores or squash_dir or update_conf
    conf.export_storage_conf(overwrite=overwrite)
    
    # dynamically add option flags to 'run' subcommand
    scmd = ctx.command.commands.get('run',None)
    if scmd:
        for k,v in conf.sitemods.items():
            scmd = click.option(f"--{v['cli_arg']}", 
                                is_flag=True, 
                                help=v.get("help"))(scmd)
            
    # save the site config to a context object so it can be passed to subcommands
    ctx.obj = conf

# parse the `podman --help` page and add it as a custom epilog to main command help
with os.popen('podman --help') as fid:
    try:
        text = re.sub("^.+(?=(Available Commands))","\b\n",fid.read(),flags=re.DOTALL)
        podhpc.epilog = re.sub("(\n\s*\n)(?=\S)","\n\n\b\n",text)
    except:
        podhpc.epilog = "For additional commands please see `podman --help`."

# function in the style of click.Command.format_help() to mimic podman help page.
# this will be inherited by subcommands created with @podhpc.command()
def podman_format(self, ctx, formatter):
    self.format_short_help(ctx,formatter)
    self.format_description(ctx,formatter)
    formatter.write_paragraph()
    self.format_usage(ctx, formatter)
    self.format_options(ctx, formatter)
    if self.epilog:
        with formatter.section("Podman help page follows"):
            self.format_epilog(ctx,formatter)

podhpc.custom_format=podman_format


### podman-hpc migrate subcommand ############################################
@podhpc.command()
@pass_siteconf
@click.argument('image',type=str)
def migrate(siteconf,image):
    """Migrate an image to squashed."""
    mu = MigrateUtils(dst=siteconf.squash_dir)
    mu.migrate_image(image, siteconf.squash_dir)
    sys.exit()

    
### podman-hpc rmsqi subcommand ##############################################
@podhpc.command()
@click.argument('image',type=str)
def rmsqi(image):
    """Removes a squashed image. """
    mu.remove_image(image)

    
### podman-hpc run subcommand (modified) #####################################
@podhpc.command(context_settings=dict(ignore_unknown_options=True,))
@pass_siteconf
@click.argument('run_args', nargs=-1, type=click.UNPROCESSED)
def run(siteconf,run_args=None,**site_opts):
    """ This is a description of podman-hpc run. """
    cmd = [siteconf.podman_bin, 'run']
    cmd.extend(siteconf.get_cmd_extensions(site_opts))
    cmd.extend(run_args)
    #print(f"os.execve(\n\t{cmd[0]},\n\t{cmd},\n\tsiteconf.env\n)")
    os.execve(cmd[0],cmd,siteconf.env)
    sys.exit()

        
### podman-hpc pull subcommand (modified) ####################################
@podhpc.command()
def pull(podman_bin,podman_args):
    """ Pulls an image to a local repository and makes a squashed copy. """
    pid = os.fork()
    if pid == 0:
        #conf.podman_bin or podman_bin?
        os.execve(podman_bin, podman_args, os.environ)
    pid, status = os.wait()
    if status == 0:
        click.echo(f"INFO: Migrating image to {confc.squash_dir}")
        mu.migrate_image(image)
    else:
        sys.stderr.write("Pull failed\n")

    
### podman-hpc shared-run subcommand #########################################
@podhpc.command(context_settings=dict(ignore_unknown_options=True,))
@click.argument('shared_run_args', nargs=-1, type=click.UNPROCESSED)
def shared_run(shared_run_args=None):
    """ This is a description of podman-hpc shared-run."""
    click.echo(f"Launching a shared-run with args: {shared_run_args}")

    localid_var = os.environ.get("PODMAN_HPC_LOCALID_VAR","SLURM_LOCALID")
    localid = os.environ.get(localid_var)

    container_name = f"uid-{os.getuid()}-pid-{os.getppid()}"
    #run_cmd, exec_cmd = shared_run_args(podman_args,image,container_name)
    run_cmd = ['podman','run','--help']
    exec_cmd = ['podman','exec','--help']
    
    shared_run_launch(localid,run_cmd,os.environ)

    # wait for the named container to start (maybe convert this to python instead of bash)
    os.system(f'while [ $(podman --log-level fatal ps -a | grep {container_name} | grep -c Up) -eq 0 ] ; do sleep 0.2')
    os.execve(exec_cmd[0], exec_cmd, os.environ)

def shared_run_launch(localid,run_cmd,env):
    """ helper to break out of an if block """
    if localid and localid!=0:
        return
    pid = os.fork()
    if pid==0:
        os.execve(run_cmd[0],run_cmd,env)
    return pid

    
### podman-hpc call_podman subcommand (default, hidden, passthrough) #########
@podhpc.default_command(context_settings=dict(ignore_unknown_options=True,help_option_names=[]),hidden=True)
@pass_siteconf
@click.pass_context
@click.argument('podman_args', nargs=-1, type=click.UNPROCESSED)
def call_podman(ctx,siteconf,podman_args):
    cmd = [siteconf.podman_bin]    
    try:
        cmd.append(ctx.parent.invoked_subcommand)
    except:
        pass
    cmd.extend(podman_args)
    #print(f"os.execve(\n\t{cmd[0]},\n\t{cmd},\n\tsiteconf.env\n)")
    os.execve(cmd[0],cmd,siteconf.env)
    
def main():
    podhpc()

if __name__ == "__main__":
    main()
