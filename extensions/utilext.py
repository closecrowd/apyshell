#!/usr/bin/env python3
"""
    utilext - utility functions

    This extension add a few useful functions callable by scripts.
    Some of these functions may be disabled by options passed in
    from apyshell.

    Make these functions available to a script by adding:

        loadExtension_('utilext')

    to it.  Functions exported by this extension:

        input_()        :   read characters from the terminal, return
                            as a string.
        system_()       :   execute a string in the user's default shell. *
        getenv_()       :   return the value of an environment variable. *

    * may be disabled by option settings

    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>
    Copyright (c) 2023 by Mark Anacker
--------------------------------------------------------------------
"""

modready = True

import os
import sys
import select

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'utilext'
__cname__ = 'UtilExt'

MODNAME="utilext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class UtilExt():

    ''' This class manages utility commands. '''

    def __init__(self, api, options={}):
        '''
        Parameters
        ----------
        api     : an instance of ExtensionAPI connecting us to the engine
        options : a dict of option settings passed down to the extension

            Defined options:    'allow_system' - install the system_()
                                command allowing the script to run
                                commands in the system shell.

                                'allow_getenv' - install the getenv_()
                                command to allow the script to read
                                environment variables.
        '''

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        self.systemflag = options.get('allow_system', False)
        self.envflag = options.get('allow_getenv', False)

    def register(self):
        ''' Make this extension's commands available to scripts

        Commands installed
        ------------------

        input_()        :   read characters from the terminal, return
                            as a string.
        system_()       :   execute a string in the user's default shell.
        getenv_()       :   return the value of an environment variable

        Returns
        -------
        True            :   Commands are installed and the extension is
                            ready to use.
        False           :   Commands are NOT installed, and the extension
                            is inactive.
        '''

        if not modready:
            return False

        self.__cmddict['input_'] = self.input_

        # optional commands
        if self.systemflag:
            self.__cmddict['system_'] = self.system_
        if self.envflag:
            self.__cmddict['getenv_'] = self.getenv_

        self.__api.registerCmds(self.__cmddict)

        return True

    def unregister(self):
        ''' Remove this extension's commands '''
        if not modready:
            return False

        # unregister the extensions script functions
        self.__api.unregisterCmds(self.__cmddict)

        return True

    def shutdown(self):
        ''' Perform a graceful shutdown '''
        return True

#----------------------------------------------------------------------
#
# Script API
#
#----------------------------------------------------------------------

    # timed input with defaults
    def input_(self, prompt=None, default=None, **kwargs):

        timeout = 0
        todef = None
        toraise = False
        if kwargs:
            timeout = kwargs.get('timeout', 0)      # timeout in seconds
            todef = kwargs.get('todef', None)       # default return if timed out
            toraise = kwargs.get('toraise', False)  # raise or return

        if prompt:
            sys.stdout.write(prompt)
            sys.stdout.flush()

        rlist, _, _ = select.select([sys.stdin], [],[], timeout)
        if rlist:
            # got data
            ret = sys.stdin.readline().rstrip('\n') # expect stdin to be line-buffered
            # if there's a timeout default
            if todef:
                # and the input happens to match it
                if ret == todef:
                    # filter it out
                    ret = ''
        else:
            # timed out
            if toraise:
                raise Exception('Timed out')
            else:
                ret = todef

        if not ret or len(ret) == 0:
            if default:
                ret = default

        return ret


    def system_(self, cmd):
        ''' run a shell command - possibly dangerous. (definitely dangerous) '''
        return os.system(cmd)


    def getenv_(self,  name):
        ''' Return an environment variable '''
        if not name:
            return None

        return os.environ.get(name,  None)

#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------
