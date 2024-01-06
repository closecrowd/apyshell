#!/usr/bin/env python3
"""utilext - utility functions.

This extension adds a few useful functions callable by scripts.
Some of these functions may be disabled by options passed in
from apyshell.

Make these functions available to a script by adding:

    loadExtension_('utilext')

to it.  Functions exported by this extension:

Methods:
    input_()        :   read characters from the terminal, return
                        as a string.
    system_()       :   execute a string in the user's default shell. *
    getenv_()       :   return the value of an environment variable. *

* may be disabled by option settings

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

import os
import sys
import select

# from support import *
# from extensionapi import *

##############################################################################

#
# Globals
#

modready = True

__key__ = 'utilext'
__cname__ = 'UtilExt'

MODNAME = "utilext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class UtilExt():
    """This class provides utility commands. """

    def __init__(self, api, options={}):
        """Constructs an instance of the UtilExt class.

        This instance supplies some useful functions.

        Args:
            api     : an instance of ExtensionAPI connecting us to the engine.

            options : a dict of option settings passed down to the extension.

        Returns:
            None

        Options:
                    'allow_system' : install the system_() command allowing
                        the script to run commands in the system shell.

                    'allow_getenv' : install the getenv_() command to allow
                        the script to read environment variables.

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        self.systemflag = options.get('allow_system', False)
        self.envflag = options.get('allow_getenv', False)

    def register(self):
        """Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * input_()        :   read characters from the terminal, return as a string.
                * system_()       :   execute a string in the user's default shell.
                * getenv_()       :   return the value of an environment variable.

        Args:
            None

        Returns
            True        :   Commands are installed and the extension is ready to use.

            False       :   Commands are NOT installed, and the extension is inactive.

        """

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
        """Remove this extension's functions from the engine. """

        if not modready:
            return False

        # unregister the extensions script functions
        self.__api.unregisterCmds(self.__cmddict)

        return True

    def shutdown(self):
        """Perform a graceful shutdown.

        This gets called by the extension manager just before
        the extension is unloaded.

        """
        return True

# ----------------------------------------------------------------------
#
# Script API
#
# ----------------------------------------------------------------------

    # timed input with defaults
    def input_(self, prompt=None, default=None, **kwargs):
        """Get console input.

        This function will (optionally) print a prompt on the console,
        then wait for (and return) whatever the user types in.  A default
        value may be set to be returned if nothing was entered.  A
        timeout can also be set, either returning a default value or
        raising an exception if the timeout expires without a console entry.

        The timeout default value may be different from the input default.

            Args:

                prompt  :   The prompt to display on the console

                default :   A value to return if there is no input

                **kwargs    :   Various options:

                                Options:
                                    * timeout :   input timeout in seconds.

                                    * todef   :   default value to return if the timeout expires.

                                    * toraise :   If True, raise an Exception when the timeout expires.

            Returns:
                A string with the input (minus the trailing newline), or
                a sepcified default value.

            Raises:
                Exception('Timed out')

        """

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

        rlist, _, _ = select.select([sys.stdin], [], [], timeout)
        if rlist:
            # got data
            ret = sys.stdin.readline().rstrip('\n')  # expect stdin to be line-buffered
            # if there's a timeout default
            if todef:
                # and the input happens to match it
                if ret == todef:
                    # filter it out
                    ret = ''
        else:
            # timed out
            if toraise:
                # raise an exception
                raise Exception('Timed out')
            else:
                # or return the TO default
                ret = todef

        # return a default value
        if not ret or len(ret) == 0:
            if default:
                ret = default

        return ret


    def system_(self, cmd):
        """Run a shell command - possibly dangerous. (definitely dangerous!).

        This function simply runs whatever string is passed to it in the
        host environment.  Useful for debugging or ad-hoc scripting, it
        has to be deliberately enabled by the host application.

            Args:

                cmd :   A command to run.

            Returns:

                The output of the command.

        """

        return os.system(cmd)


    def getenv_(self, name):
        """Return an environment variable.

        This function returns the value of an item in the host application's
        environment.  Since this might be unsafe, it has to be specifically
        enabled by the host application.

            Args:

                name    :   The environment variable to return

            Returns:

                The contents of the env variable, or None if it isn't valid.


        """
        if not name:
            return None

        return os.environ.get(name, None)

# ----------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------
