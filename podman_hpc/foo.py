import os
import re
import sys
import click

@click.command(context_settings=dict(ignore_unknown_options=True,))
@click.pass_context
@click.argument('raw_args',nargs=-1, type=click.UNPROCESSED)
def shared_run(ctx,raw_args):
    siteconf = type('siteconf',(),{})
    siteconf.podman_bin = "/global/common/shared/das/podman/bin/podman"
    #print(ctx.__dict__)
    #print('yada is ',yada)
    print('shared-run received args  :',raw_args)
    
    @click.command(context_settings=dict(ignore_unknown_options=True,allow_extra_args=True))
    def exec_filter(**kwargs):
        print('\tin exec_filter...')
        print('\tkwargs are   :',kwargs)
        #print('\tunknowns are : ',unknowns)

    opt_regex = re.compile("^\s*(?:(-\w), )?(--\w[\w\-]+)(?:\s(\w+))?")
    with os.popen(' '.join([siteconf.podman_bin,'exec','--help'])) as f:
        for line in f:
            opt = opt_regex.match(line)
            if opt:
                #action = 'store' if opt.groups()[2] else 'store_true'
                flags = [flag for flag in opt.groups()[:-1] if flag]
                exec_filter = click.option(*flags,is_flag=(not opt.groups()[2]))(exec_filter)
                #p.add_argument(*flags,action=action)
                
    exec_ctx = exec_filter.make_context('exec',list(raw_args),ctx)
    #print(exec_ctx.__dict__,'\n')
    print('\tparams are   :',exec_ctx.params)
    print('\tunknowns     :',exec_ctx.args)
    print('')
    
    
    #exec_filter.invoke(exec_ctx)
        
    #barctx = bar.make_context('bar',list(raw_args),ctx)
    #print(barctx.__dict__,'\n')
    #bar.invoke(barctx)
    #print('*raw_args(foo) : ',*raw_args)
    #print('*raw_args(foo) : ',*list(raw_args))
    #ctx.params.pop('raw_args')
    #ctx.params.pop('yada')
    #ctx.forward(bar)
    #ctx.invoke(bar,list(raw_args))
    #a = bar(raw_args)
    #print('a is\n',a)
    #print("aaaaaaaaaaaaaaaaaaaaaaaaa")
    
@click.command(context_settings=dict(ignore_unknown_options=True,))
@click.pass_context
@click.option('--watev',is_flag=True)
@click.argument('unknown_args',nargs=-1, type=click.UNPROCESSED)
def bar(ctx,watev,unknown_args=None):
    print('entering bar')
    #print(sys.argv[:])
    print(ctx.__dict__)
    #print(ctx.command.__dict__)
    #print('raw_args     : ',raw_args)
    print('watev        : ',watev)
    print('unknown_args : ',unknown_args)
    #ctx.invoke(baz,*ctx.params,raw_args=ctx.parent.params["raw_args"])
    return ctx.params
    
    return filter_wrap(cmd)

if __name__ == "__main__":
    shared_run(prog_name='foobar')
    #print(click.Command.invoke(filter_abc,sys.argv[1:]))

    
