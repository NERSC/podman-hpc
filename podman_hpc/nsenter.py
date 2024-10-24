from subprocess import Popen, PIPE
import json
import os
import time


"""
This provides a method to use nsenter to spawn the
mpi tasks.
"""


ns2flag = {
         'cgroup': '-C',
         'ipc': '-i',
         'mnt': '-m',
         'net': '-n',
         'pid': '-p',
         'time': '-T',
         'user': '-U',
         'uts': '-u',
        }


def get_env(pid, conf):
    """
    Construct the environment for the exec command
    """
    # Gather the environment from the run command
    with open(f"/proc/{pid}/environ") as f:
        data = f.read().split('\x00')[0:-1]
    new_env = dict()
    for e in data:
        k, v = e.split("=", maxsplit=1)
        new_env[k] = v
    next = False

    # Find any environments that should be
    # passed
    for arg in conf.shared_run_exec_args:
        # Find environment flags
        if arg == "-e":
            next = True
            continue
        if not next:
            continue
        next = False
        if arg.endswith('*'):
            patt = arg[0:-1]
            for env in os.environ:
                if env.startswith(patt):
                    new_env[env] = os.environ[env]
        elif '=' in arg:
            k, v = arg.split("=", maxsplit=1)
            new_env[k] = v
        else:
            new_env[arg] = os.environ[k]
    return new_env


def nsenter(conf, timer, args):
    """
    Run a command and ignore the output.
    Returns the exit code
    """

    cmd = ["lsns", "-J"]
    shared_run_command = " ".join(conf.shared_run_command)
    pid = None

    while not pid:
        timer.check()
        proc = Popen(cmd, stdout=PIPE, stderr=PIPE)
        out, err = proc.communicate()
        data = None
        try:
            data = json.loads(out.decode())
        except json.JSONDecodeError:
            time.sleep(conf.wait_poll_interval)
            continue
        for proc in data['namespaces']:
            if proc['command'] == shared_run_command:
                pid = proc['pid']
        if not pid:
            time.sleep(conf.wait_poll_interval)
            continue
        cmd = ["/usr/bin/nsenter",
               '-t', str(pid), '-U',
               "--preserve-credentials"
               ]
        for ns in data['namespaces']:
            if ns['pid'] == pid:
                cmd.append(ns2flag[ns['type']])

    cmd.extend(args)
    new_env = get_env(pid, conf)
    proc = Popen(cmd, env=new_env)
    proc.communicate()
    return proc.returncode
