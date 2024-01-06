#!/usr/bin/env python3
"""flagext - Named multi-thread Event flags

This extension provides a means for threads to synchronize with
each other.  It allows the script to create named "flags" that
script elements running in different threads (such as handlers)
can manipulate.  A flag may be raised or lowered, and threads
can wait for a flag to be raised.  Flags may also be checked for
state without waiting.

If multiple threads are waiting on a flag, they will all be released
when it's raised.

This is really a wrapper around a set of Threading.Event() objects.
The "flag" metaphore is easier to visualize, and the Extension handles
all of the fussy bits of managing a bunch of Event objects.

Make the functions available to a script by adding:

    loadExtension_('flagext')

to it.  Functions exported by this extension:

Methods:

        flag_add_()         :   Create a named flag (state == lowered)
        flag_del_()         :   Delete a named flag and release any waits
        flag_raise_()       :   Raise the flag and release any flag_wait_()s
        flag_lower_()       :   Reset the flag to lowered state
        flag_israised_()    :   Check the flag state
        flag_wait_()        :   Wait for a flag to be raised, or timeout
        flag_list_()        :   Return a list[] of flag names

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

import threading
import time

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

modready = True

__key__ = 'flagext'
__cname__ = 'FlagExt'

MODNAME = "flagext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class FlagExt():
    """This class manages commands to set and clear sync flags."""

    def __init__(self, api, options={}):
        """Constructs an instance of the FlagExt class.

        This instance will manage all named flags.  There will be only
        one of these instances at a time.

        Args:

            api     : an instance of ExtensionAPI connecting us to the engine

            options : a dict of option settings passed down to the extension

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        self.__flagnames = set()
        self.__flags = {}

        self.__locktimeout = 5
        self.__lock = threading.Lock()

    def register(self):
        """Make this extension's functions available to scripts

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * flag_add_()         :   Create a named flag (state == lowered)
                * flag_del_()         :   Delete a named flag and release any waits
                * flag_raise_()       :   Raise the flag and release any flag_wait_()s
                * flag_lower_()       :   Reset the flag to lowered state
                * flag_israised_()    :   Check the flag state
                * flag_wait_()        :   Wait for a flag to be raised, or timeout
                * flag_list_()        :   Return a list[] of flag names

            Args:

                None

            Returns:

                True        :   Commands are installed and the extension is ready to use.

                False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        self.__cmddict['flag_add_'] = self.flag_add_
        self.__cmddict['flag_del_'] = self.flag_del_
        self.__cmddict['flag_raise_'] = self.flag_raise_
        self.__cmddict['flag_lower_'] = self.flag_lower_
        self.__cmddict['flag_israised_'] = self.flag_israised_
        self.__cmddict['flag_wait_'] = self.flag_wait_
        self.__cmddict['flag_list_'] = self.flag_list_

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

        try:
            self.__lock.acquire(blocking=True, timeout=2)

            # for all active events
            for evn in self.__flags.keys():
                ev = self.__flags[evname]
                # release the threads
                ev.set()
                # remove the event object
                del self.__flags[evn]

            self.__flagnames.clear()
            self.__flags.clear()
            unlock__(self.__lock)
        except:
            unlock__(self.__lock)
        return True

# ----------------------------------------------------------------------
#
# Script API
#
# ----------------------------------------------------------------------

    # add a new, lowered flag
    def flag_add_(self, name):
        """Handles the flag_add_() function.

        Creates a new flag and adds it's name to the table.

            Args:

                name       :   The flag name to create. Must not be in use.

            Returns:

                True if the flag was created.

                False if an error occurred.

            Options:

                None

        """

        # check the format of the flag name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name, False)

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not add "'+name+'"', False)

            # check for duplicate flag names
            if name in self.__flagnames:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'Flag name already used:'+name, False)

            # create a new Event
            newevent = threading.Event()
            self.__flagnames.add(name)
            self.__flags[name] = newevent
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in flag_add_ '+'"'+name+'":'+str(e), False)
        return True

    # delete an existing flag
    def flag_del_(self, name):
        """Handles the flag_del_() function.

        Momentarily raises the flag (to release any flag_wait_()
        listeners), then deletes the flag from the table.

            Args:

                name    :   The name of the flag to delete.

            Returns:

                The return value. True for success, False otherwise.

        """

        # check the format of the flag name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name, False)

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not del "'+name+'"', False)

            if name not in self.__flagnames:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'Flag name not found:'+name, False)

            # get the event
            ev = self.__flags[name]
            # release any waiting threads
            ev.set()
            time.sleep(0.01)
            # delete the object
            del self.__flags[name]
            # and remove the name
            self.__flagnames.discard(name)
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in flag_del_ '+'"'+name+'":'+str(e), False)
        return True

    # raise a flag
    def flag_raise_(self, name, toggle=False):
        """Handles the flag_raise_() function.

        Raises the flag (releasing any flag_wait_() listeners).

            Args:

                name    :   The name of the flag to raise.

                toggle  :   If True, lower the flag after a tiny pause

            Returns:

                The return value. True for success, False otherwise.

        """

        # check the format of the flag name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name, False)

        try:
            if name not in self.__flagnames:
                return retError(self.__api, MODNAME, 'name not found:'+name, False)

            # get the event
            ev = self.__flags[name]
            # release any waiting threads
            ev.set()
            # if we're just toggling it,
            if toggle:
                # wait a tiny bit for the threads to wake
                time.sleep(0.01)
                # and clear it
                ev.clear()
            return True
        except:
            return False

    # lower a flag
    def flag_lower_(self, name):
        """Handles the flag_lower_() function.

        Lowers the flag, priming it for flag_wait_() listeners.

            Args:

                name    :   The name of the flag to lower.

            Returns:

                The return value. True for success, False otherwise.

        """

        # check the format of the flag name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name, False)

        try:
            if name not in self.__flagnames:
                return retError(self.__api, MODNAME, 'name not found:'+name, False)

            # get the event
            ev = self.__flags[name]
            # release any waiting threads
            ev.clear()
            return True
        except:
            return False

    # is the flag up?
    def flag_israised_(self, name):
        """Handles the flag_israised_() function.

        Checks the state of the flag without having to wait()

            Args:

                name    :   The name of the flag to check.

            Returns:

                The flag state. True if raised, False if lowered

        """

        # check the format of the flag name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name, False)

        try:
            if name not in self.__flagnames:
                return retError(self.__api, MODNAME, 'name not found:'+name, False)

            # get the event
            ev = self.__flags[name]
            # return it's status
            return ev.is_set()
        except:
            return False

    # returns True is the flag was raised
    # return False if the wait timed out
    def flag_wait_(self, name, timeout=1.0, **kwargs):
        """Handles the flag_wait_() function.

        Waits for a flag to be raised, or a timeout to expire.

            Args:

                name        :   The name of the flag to wait on.

                timeout     :   The time to wait in seconds

                **kwargs    :   A dict with supported options.

            Returns:

                The return value. True for success, False on error or timeout.

            Options:

                prelower    :   If True, lower the flag BEFORE waiting

                postlower   :   If True, lower the flag AFTER waiting

        """

        # check the format of the flag name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name, False)

        try:
            if name not in self.__flagnames:
                return retError(self.__api, MODNAME, 'name not found:'+name, False)

            # option to make sure it's lowered on entry
            prelower = kwargs.get('prelower', False)
            # option to make sure it's lowered on exit
            postlower = kwargs.get('postlower', False)

            # get the event
            ev = self.__flags[name]
            if prelower:
                ev.clear()

            # wait for the event to trigger, or timeout
            # ret == True if it didn't time out
            ret = ev.wait(timeout)

            # lower it if requested, and raised
            if ret and postlower:
                ev.clear()
            if not ret:
                return False
            return True
        except:
            pass
        return False

    # list current flags
    def flag_list_(self):
        """Handles the flag_list_() function.

        Returns a list with the names of all named flags.

            Args:

                None

            Returns:

                A list[] of flag names.  The list may be empty if
                there are no flags.

                None if there was an error.
        """

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not list flags', None)

            if len(self.__flagnames) == 0:
                unlock__(self.__lock)
                return []
            outlist = []
            for evn in self.__flags.keys():
                ev = self.__flags[evn]
                rec = (evn, ev.is_set())
                outlist.append(rec)

            unlock__(self.__lock)
            return outlist
        except:
            pass
        return None

# ----------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------
