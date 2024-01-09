#!/usr/bin/env python3
"""extensionapi - The interface between extensions and the engine.

An instance of this class is passed to the extensions at load time
to give them an API back into the engine via the ExtensionMgr

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

from support import *

##############################################################################

MODNAME = "extensionapi:"
DEBUG = False
# DEBUG=True
def debug(*args):
    if DEBUG:
        print(MODNAME, str(args))

# ----------------------------------------------------------------------------
#
# API class
#
# ----------------------------------------------------------------------------

class ExtensionAPI:

    def __init__(self, eng, parent, internal=True):
        debug("ExtensionAPI")
        self.__engine = eng
        self.__parent = parent

#
# engine api - called by extensions
#

    # callback from extensions into the script
    def handleEvents(self, name, data):
        """Handle callback events.

        If an extension allows for handlers to receive events, each
        callback comes through here.  This function passes the name
        and data object through to the ExtensionMgr to run in the
        engine.

            Args:

                name    :   The name of the handler func().

                data    :   The object to pass as the **only** argument to the handler.

            Returns:

                 ret    :   A string with the return from the handler()

                None    :   Something failed

        """

        return self.__parent.handleEvents(name, data)


    # register the module's new funcs in the engine
    def registerCmds(self, mdict):
        """Make an extension's functions available to scripts

        Extensions call here through the api reference to install
        their commands into the engine.

            Args:

                mdict   :   A dict with the commands and function refs.

            Returns
                True        :   Commands are installed and the extension is
                                ready to use.

                False       :   Commands are NOT installed, and the extension
                                is inactive.

        """

        ret = True

        if len(mdict) < 1:
            return False
        try:
            # add them to the engine
            ret = self.__engine.addcmds(mdict)
        except:
            debug('*** failed to register cmds')
            return False
        return ret

    # remove a module's commands
    def unregisterCmds(self, mdict):
        """Remove an extension's commands from the engine.

        Extensions call here through the api reference to remove
        their commands from the engine.

            Args:

                mdict   :   A dict with the commands and function refs.

            Returns

                True        :   Commands have been removed.

                False       :   Something failed.

        """

        ret = True

        if len(mdict) < 1:
            return False
        try:
            # then remove them from the engine
            ret = self.__engine.delcmds(mdict)
        except:
            debug('*** failed to unregister cmds')
            return False
        return ret

    # regcmd
    def regcmd(self, name, func=None):
        ''' Add a new command callable by scripts '''
        return self.__engine.regcmd(name, func)

    #
    def list_Modules_(self):
        ''' Return a list of install_()-ed modules '''
        return self.__engine.list_Modules_()

    # loadScript_
    def loadScript_(self, filename, persist=False):
        ''' Load and execute a script file '''
        return self.__engine.loadScript_(filename, persist)

    # isDef_
    def isDef_(self, name):
        ''' Return True is the name is defined '''
        return self.__engine.isDef_(name)

    # getProcs_
    def listDefs_(self, exception_list=None):
        ''' Return a list of script def procs '''
        return self.__engine.listDefs_(exception_list)

    # getvar_
    def getvar_(self, vname, default=None):
        ''' Return the value of a script variable or a default '''
        return self.__engine.getvar_(vname, default)

    # setvar_
    def setvar_(self, vname, val):
        ''' Set a script variable '''
        return self.__engine.setvar_(vname, val)

    # extensions can set globals
    def setSysvar_(self, name, val):
        ''' Set a system variable '''
        return self.__engine.setSysvar_(name, val)

    # get global var
    def getSysvar_(self, name, default=None):
        ''' Return the value of a system variable or a default '''
        return self.__engine.getSysvar_(name, default)

    # handle error msgs from the extensions
    def logError(self, modname='', *args):
        errorMsg(modname, *args)
