#!/usr/bin/env python
import os
import sys
import re
import click
from . import click_passthrough as cpt
from .migrate2scratch import MigrateUtils
from .siteconfig import SiteConfig
        

# function to specify help message formatting to mimic the podman help page.
# follows the style of click.Command.format_help()
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

            
# parse the `podman --help` page so it can be added as a custom epilog to main command help
with os.popen('podman --help') as fid:
    try:
        text = re.sub("^.+(?=(Available Commands))","\b\n",fid.read(),flags=re.DOTALL)
        podman_epilog = re.sub("(\n\s*\n)(?=\S)","\n\n\b\n",text)
    except:
        podman_epilog = "For additional commands please see `podman --help`."
            
            
# decorator so that subcommands can request to receive SiteConfig object
pass_siteconf = click.make_pass_decorator(SiteConfig, ensure=True)


### podman-hpc command #######################################################
@click.group(cls=cpt.PassthroughGroup,custom_format=podman_format,epilog=podman_epilog,options_metavar="[options]",passthrough='podman',invoke_without_command=True,)
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
    overwrite = additional_stores or squash_dir or update_conf
    if not (overwrite or ctx.invoked_subcommand):
        click.echo(ctx.get_help())
        ctx.exit()

    # set up site configuration object
    conf = SiteConfig(squash_dir=squash_dir,log_level=log_level)
    conf.read_site_modules()
    # migrate was here, is that important?
    conf.config_storage(additional_stores)
    conf.config_containers()
    conf.config_env(hpc=True)

    # optionally, save the storage conf
    conf.export_storage_conf(overwrite=overwrite)
    
    # add appropriate flags to call_podman based on invoked subcommand
    defcmd = ctx.command.default_command_fn
    for k,v in conf.sitemods.get(ctx.invoked_subcommand,{}).items():
        defcmd = click.option(f"--{v['cli_arg']}",
                                   is_flag=True,
                                   hidden=v.get('hidden',False),
                                   help=v.get("help"))(defcmd)
            
    # save the site config to a context object so it can be passed to subcommands
    ctx.obj = conf

    
### podman-hpc migrate subcommand ############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
@click.argument('image',type=str)
def migrate(siteconf,image):
    """Migrate an image to squashed."""
    mu = MigrateUtils(dst=siteconf.squash_dir)
    mu.migrate_image(image)
    sys.exit()

    
### podman-hpc rmsqi subcommand ##############################################
@podhpc.command(options_metavar="[options]")
@pass_siteconf
@click.argument('image',type=str)
def rmsqi(siteconf,image):
    """Removes a squashed image. """
    mu = MigrateUtils(dst=siteconf.squash_dir)
    mu.remove_image(image)

        
### podman-hpc pull subcommand (modified) ####################################
@podhpc.command(context_settings=dict(ignore_unknown_options=True,),options_metavar="[options]")
@pass_siteconf
@click.pass_context
@click.argument('podman_args', nargs=-1, type=click.UNPROCESSED)
@click.argument('image')
def pull(ctx,siteconf,image,podman_args):
    """ Pulls an image to a local repository and makes a squashed copy. """
    pid = os.fork()
    if pid == 0:
        cmd = [siteconf.podman_bin, 'pull']
        cmd.extend(podman_args)
        cmd.append(image)
        os.execve(cmd[0], cmd, os.environ)
    pid, status = os.wait()
    if status == 0:
        click.echo(f"INFO: Migrating image to {siteconf.squash_dir}")
        ctx.invoke(migrate,image=image)
    else:
        sys.stderr.write("Pull failed.\n")

    
### podman-hpc shared-run subcommand #########################################
@podhpc.command(context_settings=dict(ignore_unknown_options=True,),options_metavar="[options]")
@click.argument('image')
@click.argument('shared_run_args', nargs=-1, type=click.UNPROCESSED, metavar="[COMMAND [ARG...]]")
def shared_run(image,shared_run_args=None):
    """ Launch a single container and exec many threads in it
    
    This is the recommended way to launch a container from a parallel launcher 
    such as Slurm `srun` or `mpirun`. One container will be started (per node), and all
    process tasks will then be launched into that container via `exec` subcommand.  
    When all `exec` processes have concluded, the container will close and remove itself.
    
    For valid flag options, see help pages for `run` and `exec` subcommands:    
    
    \b
      podman-hpc run --help
      podman-hpc exec --help
    """
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
    if localid and int(localid)!=0:
        return
    pid = os.fork()
    if pid==0:
        os.execve(run_cmd[0],run_cmd,env)
    return pid


### podman-hpc call_podman subcommand (default, hidden, passthrough) #########
@podhpc.default_command(context_settings=dict(ignore_unknown_options=True,help_option_names=[]),hidden=True)
@pass_siteconf
@click.pass_context
@click.option('--help',is_flag=True,hidden=True)
@click.argument('podman_args', nargs=-1, type=click.UNPROCESSED)
def call_podman(ctx,siteconf,help,podman_args,**site_opts):
    cmd = [siteconf.podman_bin, ctx.info_name]
    cmd.extend(siteconf.get_cmd_extensions(ctx.info_name,site_opts))
    cmd.extend(podman_args)

    # if the help flag is called, we pass podman's STDOUT stream through a pipe
    # to a stream editor, to inject additional help page info
    if help:
        cmd.insert(2,'--help')
        app_name = ctx.find_root().command_path
        passthrough_name = os.path.basename(cmd[0])
        
        formatter = ctx.make_formatter()
        ctx.command.format_options(ctx,formatter)
        app_options=''
        if formatter.getvalue():
            app_options = f"{app_name.capitalize()} {formatter.getvalue()}\n".replace('\n','\\n')
        
        cmd_sed = ['/usr/bin/sed',
                   '-e', f's/{passthrough_name}/{app_name}/',
                   '-e', f's/Options:/{app_options}{passthrough_name.capitalize()} &/'
                  ]
        
        STDIN = 0
        STDOUT = 1
        p_read, p_write = os.pipe()
        if os.fork():
            os.close(p_write)
            os.dup2(p_read, STDIN)
            os.execv(cmd_sed[0],cmd_sed)
            os._exit(os.EX_OSERR)
        else:
            os.close(p_read)
            os.dup2(p_write, STDOUT)
            
    os.execve(cmd[0],cmd,siteconf.env)

def main():
    podhpc(prog_name='podman-hpc')

if __name__ == "__main__":
    main()
