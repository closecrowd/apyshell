#!/usr/bin/env python3
"""apyshell - Python Embedded apy script runnner

This module creates a framework for running lightweight scripts
under the apyengine interpreter.  It demonstrates embedding and
controlling the engine, and extending the funcionality available
to scripts.

It can be run either stand-alone, or itself embedded into an application.

Credits:
    * version: 1.0.0
    * last update: 2023-Nov-21
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

import os
import sys
import getopt
import signal
import platform

from support import *
import apyengine
from extensionmgr import *

##############################################################################

#
# Globals
#

VERSION = "1.0.0"

# default directory paths
basedir = '/opt/apyshell/scripts'           # script base directory
extensiondir = '/opt/apyshell/extensions'   # extension base dir

# options passed to various extensions.  Modify to suit your environment.
extension_opts = {  'allow_redis_cmds': True,  # allow raw commands in redisext
                    'allow_system': True,      # allow system_() call in utilext
                    'allow_getenv': True,      # allow getenv_() call in utilext
                    'file_root': '/opt/apyshell/files',  # fileext is rooted here
                    'read_only': False,                  # fileext can write files
                    'list_files': True,                  # fileext can return a dir list
                    'sql_root': '/opt/apyshell/files',   # sqliteext files go here
                    'sql_ext': 'db'                      # sqliteext file extension
                 }

validpidfile = False

# ----------------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------------

def usage():
    """Help message.
    """

    print("""
    apyshell.py script [ options ]

    script              The script file to execute (required). The .apy is optional

    -h, --help          This message
    -a, --args          Optional argument string to pass to the script
    -i, --initscript    A script to execute before the specified script
    -b, --basedir       Base directory for scripts (use , for multiple paths)
    -e, --extensiondir  Base directory for extensions (use , for multiple paths)
    -o, --extensionopts A list of options key:value pairs to pass to extensions
    -p, --pidfile       Write a file with the shell's current PID
    -g, --global        All script variables are global
    -v, --verbose       Debug output

""")

# save our current PID if we can
# note: this doesn't do any checking of the file path.
# take care if running under root
def savepid(pfile):
    """Save our current PID if we can.

    Note:
        this doesn't do any checking of the file path. Take care if
        running under root.

    """

    global validpidfile

    mypid = os.getpid()
    try:
        file = open(pfile, "w")
        file.write(str(mypid))
        file.close()
        validpidfile = True
        return True
    except:
        pass
    return False

# remove pidfile
def cleanpid(pfile):
    """Remove our pidfile if it was created.

    Note:
        this doesn't do any checking of the file path. Take care if
        running under root.

    """

    global validpidfile

    # was it previously created?
    if validpidfile:
        try:
            os.remove(pfile)
        except:
            pass

    validpidfile = False

# add the key:value pairs into the extension_opts
# dict.  This can add new options, or over-ride the
# pre-set ones.  The pairs are separated by ,
# ex.: "allow_getenv:True,file_root:/opt/apyshell/files"
#
def processOptions(eopts):
    """Process extension options arguments.

    This function takes the argument to the '-o' or '--extensionopts'
    argument and breaks it down to key:value pairs added to the
    extension_opts dict.  This dict is passed to each extension when
    it is loaded with "loadExtension_()".

    This can be used to add new options that are not pre-set in this
    module, or to over-ride the pre-set ones.

    """

    if not eopts or len(eopts) < 3:
        return False

    # if a list, split at the commas
    if ',' in eopts:
        olist = eopts.split(',')
    else:
        # if single, make it a list anyways
        olist = list()
        olist.append(eopts)

    # for each pair in the list
    for kp in olist:
        # sanity check on the input
        if ':' not in kp:
            continue
        # split the pair
        (key, val) = kp.split(':')
        # convert string to boolean
        if val in ['False', 'True']:
            val = bool(val)
        # store the value in the dict
        extension_opts[key] = val

    return True

# run a script
#
# If you are embedding this module, this is the main entry point
#
def apyshell(script, basedir=basedir, extensiondir=extensiondir,
                extension_opts=None, args=None, initscript=None, globals=False ):
    """Execute a script file under apyengine.

    This is the main entry point.

        Args:
            script  :   The .apy script to execute.
        Returns:
            The return value. True for success, False otherwise.


    """

    if not script:
        return 99

    # handler for shutdown signals
    def sighand(signum, frame):
        ''' Intercepts ^c from the keyboard and does an orderly shutdown'''

        if engine:
            # termination signals come here
            if signum == signal.SIGTERM or signum == signal.SIGINT:
                # stop the current script
                engine.abortrun()
                return

            # USR1/USR2 come here.  If there is a script function named
            # "usrsignal", it will be called with the numeric signal
            # as the argument
            if engine.isDef_('usrsignal'):
                engine.eval_('usrsignal('+str(signum)+')')


    # create the scripting engine
    engine = apyengine.ApyEngine(basedir, global_funcs=globals, writer=sys.stdout, err_writer=sys.stderr)

    # grab ^c and sigint so we can shut down cleanly
    signal.signal(signal.SIGTERM, sighand)
    signal.signal(signal.SIGINT, sighand)
    signal.signal(signal.SIGUSR1, sighand)
    signal.signal(signal.SIGUSR2, sighand)

    # create the extension manager
    emgr = ExtensionMgr(engine, extensiondir, extension_opts)
    # register it's commands
    emgr.register()

    # pass any args to the scripts
    if args:
        engine.setSysVar_('args', args)

    # pass in the name of this machine
    engine.setSysVar_('hostname',  platform.node())

    # load the optional init script (if any)
    if initscript:
        engine.loadScript_(initscript)

    # load and run the primary script
    engine.loadScript_(script)

    # retrieve the exit code if any
    rv = engine.getSysVar_('exitcode_', 0)

    # shut everything down
    emgr.shutdown()

    return rv

# ----------------------------------------------------------------------------
#
# main
#
# ----------------------------------------------------------------------------

if __name__ == "__main__":

    if sys.argv[1][0] == '-':
        offset = 1
    else:
        offset = 2

    try:
        opts, args = getopt.getopt(sys.argv[offset:], "h?vgi:b:e:o:a:p:",
            ["help", "verbose", "globals", "initscript=", "basedir=", "extensiondir=", "extensionopt=", "args=", "pidfile="])
    except:
        print('Invalid option - use -h for help')
        sys.exit(1)

    verbose = False
    globals = False     # treat all symbols as globals
    initscript = None   # a script to run *before* the specified one
    scargs = None       # args to pass to the script
    eopts = None        # extension opts overrides
    pidfile = None      # a pidfile name if needed
    for o, a in opts:

        if o == "-v":
            verbose = True
        elif o in ("-g",  'globals'):
            globals = True
        elif o in ("-h", "-?", "--help"):
            usage()
            sys.exit()
        elif o in ("-i", "--initscript"):
            initscript = a
        elif o in ("-b", "--basedir"):
            basedir = a
        elif o in ("-e", "--extensiondir"):
            extensiondir = a
        elif o in ("-o", "--extensionopt"):
            eopts = a
        elif o in ("-a", "--args"):
            scargs = a
        elif o in ("-p", "--pidfile"):
            pidfile = a
        else:
            assert False, "unhandled option - use -h for help"

    if verbose:
        enableDebug(True)

    if len(sys.argv) < 2:
        print('** No script specified - use -h for help')
        sys.exit(1)

    if eopts:
        processOptions(eopts)

    debugMsg('apyshell', 'basedir=', basedir, 'extdir=', extensiondir)

    # get the script name
    script = sys.argv[1]

    # save our PID to the file if requested
    if pidfile:
        if not savepid(pidfile):
            # warn of failure, but it's not fatal
            print('** Failed to create pidfile:', pidfile)

    # if this is a list of paths, make is a real list
    if ',' in basedir:
        basepath = basedir.split(',')
    else:
        basepath = [basedir]

    # and do the same for the extensions
    if ',' in extensiondir:
        extensionpath = extensiondir.split(',')
    else:
        extensionpath = [extensiondir]

    # run the script
    rv = apyshell(script, basepath, extensionpath, extension_opts, scargs, initscript, globals)

    # remove the pidfile (if any)
    if pidfile:
        cleanpid(pidfile)

    # and exit, sending the code with it
    sys.exit(rv)
