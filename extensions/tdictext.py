#!/usr/bin/env python3
"""tdictext - Thread-safe Dict

This extension provides thread-safe, named dictionaries (key,value).
Python's built-in dict objects are *mostly* atomic (and therefore
thread-safe), but not *always*.  And not every operation is guaranteed
to be safe.  Scripts in apyshell may make extensive use of threads, so
an assured safe dict is needed.

Each named tdict has it's own lock, so they are relatively independant
once created.

See also the companion tlist extension.

Make these functions available to a script by adding:

    loadExtension_('tdictext')

to it.  Functions exported by this extension:

Methods:

    tdict_open_()       :   create a named dict
    tdict_close_()      :   delete an existing dict
    tdict_put_()        :   add an item to the named dict
    tdict_update_()     :   add a dict to the named dict
    tdict_get_()        :   get an item by key
    tdict_pop_()        :   get an item by key, then remove it
    tdict_del_()        :   remove an item from the dict by key
    tdict_clear_()      :   remove all items from the dict
    tdict_keys_()       :   return a list[] of keys
    tdict_items_()      :   return a list[] of items
    tdict_len_()        :   return the number of items in the dict
    tdict_copy_()       :   return a shallow copy of the dict
    tdict_list_()       :   return a list[] of tdicts

Credits:
    * version: 1.0.0
    * last update: 2023-Dec-05
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

modready = True

import threading

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'tdictext'
__cname__ = 'TDictExt'

MODNAME = "tdictext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class TDictExt():
    """This class provides a thread-safe key-value store."""

    def __init__(self, api, options={}):
        """Constructs an instance of the TDictExt class.

        This instance will manage all thread-safe dictionaries.
        There will be only one of these instances at a time.

            Args:

                api     : an instance of ExtensionAPI connecting us to the engine.

                options : a dict of option settings passed down to the extension.

            Returns:

                Nothing.

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        # lock accquire timeout
        if options:
            self.__locktimeout = int(options.get('tdict_timeo', 20))
        else:
            self.__locktimeout = 20

        self.__dicts = {}       # dict objects
        self.__lock = threading.Lock()


    def register(self):
        """Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:

                * tdict_open_()       : create a named dict
                * tdict_close_()      : delete an existing dict
                * tdict_put_()        : add an item to the named dict
                * tdict_update_()     : add a dict to the named dict
                * tdict_get_()        : get an item by key
                * tdict_pop_()        : get an item by key, then remove it
                * tdict_del_()        : remove an item from the dict by key
                * tdict_clear_()      : remove all items from the dict
                * tdict_keys_()       : return a list[] of keys
                * tdict_items_()      : return a list[] of items
                * tdict_len_()        : return the number of items in the dict
                * tdict_copy_()       : return a shallow copy of the dict
                * tdict_list_()       : return a list[] of tdicts

        Args:
            None

        Returns
            True        :   Commands are installed and the extension is
                            ready to use.

            False       :   Commands are NOT installed, and the extension
                            is inactive.

        """

        if not modready:
            return False

        self.__cmddict['tdict_open_'] = self.tdict_open_
        self.__cmddict['tdict_close_'] = self.tdict_close_

        self.__cmddict['tdict_put_'] = self.tdict_put_
        self.__cmddict['tdict_update_'] = self.tdict_update_

        self.__cmddict['tdict_get_'] = self.tdict_get_
        self.__cmddict['tdict_pop_'] = self.tdict_pop_
        self.__cmddict['tdict_del_'] = self.tdict_del_

        self.__cmddict['tdict_clear_'] = self.tdict_clear_

        self.__cmddict['tdict_keys_'] = self.tdict_keys_
        self.__cmddict['tdict_items_'] = self.tdict_items_
        self.__cmddict['tdict_len_'] = self.tdict_len_

        self.__cmddict['tdict_copy_'] = self.tdict_copy_

        self.__cmddict['tdict_list_'] = self.tdict_list_

        # register the extensions script functions
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

        Clear then close all of the active dictionaries.  This gets called
        by the extension manager just before the extension is unloaded.

        """

        try:
            self.__lock.acquire(blocking=True, timeout=2)

            for dname in self.__dicts.keys():
                self.__dicts[dname].close_()

            self.__dicts.clear()
            unlock__(self.__lock)
        except:
            unlock__(self.__lock)
        return True



#----------------------------------------------------------------------
#
# Script API
#
#----------------------------------------------------------------------

    # open a dict with thread-locking
    def tdict_open_(self, cname):
        """Handles the tdict_open_() function.

        Creates a new tdict object attached to the given name.

            Args:
                cname   :   The name of the dict to create.

            Returns:
                True for success, False otherwise.

        """

        # try to acquire the lock on the table of TDicts.
        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not open "'+cname+'"', False)

        if cname in self.__dicts.keys():
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'tdict name already used:'+cname, False)
        try:
            b = ThreadDict_(cname, self.__api,  self.__locktimeout)
            self.__dicts[cname] = b
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'tdict error :'+str(e), False)
        return True

    # close an open tdict
    def tdict_close_(self, cname):
        """Handles the tdict_close_() function.

        Clears out the data from an existing tdict, then removes it.

            Args:
                cname   :   The name of the dict to remove.

            Returns:
                True for success, False otherwise.

        """

        # try to acquire the lock on the table of TDicts.
        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not close "'+cname+'"', False)

        if cname not in self.__dicts.keys():
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'tdict name not found:'+cname, False)

        try:
            ret = self.__dicts[cname].close_()
            del self.__dicts[cname]
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'tdict error :'+str(e), False)

        return ret

    # perform one of the commands defined below.  This saves a lot of
    # redundant code.  Note that this function is NOT exported to the
    # scripts.
    def tdict_cmd(self, cmd, cname, key=None, value=None):
        """Internal command dispatcher.

        Performs the operation specified by the "cmd" argument on the
        dict object associated with "cname", and returns the result.

            Args:
                cmd     :   The operation to perform

                cname   :   The name of the dict to use.

                key     :   A key string (if needed)

                value   :   A value argument (if needed)

            Returns:
                Depends on the operation.  See the functions below
                for the specific returns.

        """

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not '+cmd+' "'+cname+'"', False)

            if cname not in self.__dicts.keys():
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'tdict name not found:'+cname, False)

            ret = self.__dicts[cname].cmd_(cmd, key, value)
            unlock__(self.__lock)
            return ret
        except:
            pass
        return None

    # put a single value in the dict
    def tdict_put_(self, cname, key, value):
        """Handles the tdict_put_() function.

        Adds a new value indexed by the key to the dict, or replaces
        an existing value with the new one.

            Args:
                cname   :   The name of the dict to use.

                key     :   A key string.

                value   :   A value argument to add or replace.

            Returns:
                True for success, False otherwise.

        """

        return self.tdict_cmd('put', cname, key, value)

    def tdict_update_(self, cname,  value):
        """Handles the tdict_update_() function.

        Merges the entire contents of an existing dict object into
        the named tdict.

            Args:
                cname   :   The name of the dict to use.

                value   :   The dict object to merge in.

            Returns:
                True for success, False otherwise.

        """

        return self.tdict_cmd('update', cname, None, value)

    def tdict_get_(self, cname, key, value=None):
        """Handles the tdict_get_() function.

        Retrieves an item indexed by the key from the dict, or
        returns a default value if the key isn't found.

            Args:
                cname   :   The name of the dict to use.

                key     :   A key string to look for.

                value   :   A default to return if key isn't in the dict.

            Returns:
                The retrieved item, or the supplied value.

        """

        return self.tdict_cmd('get', cname, key, value)

    def tdict_pop_(self, cname, key, value):
        """Handles the tdict_pop_() function.

        Retrieves an item indexed by the key from the dict, or
        returns a default value if the key isn't found.  Removes
        the item from the dict if the key was found.

            Args:
                cname   :   The name of the dict to use.

                key     :   A key string to look for.

                value   :   A default to return if key isn't in the dict.

            Returns:
                The retrieved item, or the supplied value.

        """

        return self.tdict_cmd('pop', cname, key, value)

    def tdict_del_(self, cname, key):
        """Handles the tdict_del_() function.

        Removes an item indexed by the key from the dict.

            Args:
                cname   :   The name of the dict to use.

                key     :   A key string to remove.

            Returns:
                True for success, False otherwise.

        """

        return self.tdict_cmd('del', cname, key)

    def tdict_clear_(self, cname):
        """Handles the tdict_clear_() function.

        Removes all items from the named dict.

            Args:
                cname   :   The name of the dict to use.

            Returns:
                True for success, False otherwise.

        """

        return self.tdict_cmd('clear', cname)

    def tdict_keys_(self, cname):
        """Handles the tdict_keys_() function.

        Returns a list with the keys in the named dict.

            Args:
                None

            Returns:
                A list[] of keys in the dict.  The list may be empty
                if there are none.

                None if there was an error.
        """

        return self.tdict_cmd('keys', cname)

    def tdict_items_(self, cname):
        return self.tdict_cmd('items', cname)

    def tdict_len_(self, cname):
        return self.tdict_cmd('len', cname)

    def tdict_copy_(self, cname):
        return self.tdict_cmd('copy', cname)

    # list all current dicts
    def tdict_list_(self):
        """Handles the tdict_list_() function.

        Returns a list with the names of all current dictionaries.

            Args:
                None

            Returns:
                A list[] of active dictionaries.  The list may be empty if
                there are none.

                None if there was an error.
        """

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not list tdicts', False)

        ret = list(self.__dicts.keys())
        unlock__(self.__lock)
        return ret

#----------------------------------------------------------------------
#
# data classes
#
#----------------------------------------------------------------------

class ThreadDict_():

    def __init__(self, name, api,  timeout=20):

        self.__name = name
        self.__api = api

        self.locktimeout = timeout

        self.__storage = {}
        self.__lock = threading.Lock()


    def close_(self):
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+self.__name+'"', False)
            self.__storage.clear()
            unlock__(self.__lock)
            return True
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error closing tdict '+'"'+self.__name+'":'+str(e), False)
        return False


    def cmd_(self, cmd, key=None, value=None):
        ret = True
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.locktimeout):
                return retError(self.__api, MODNAME, 'Could not '+cmd+' "'+value+'" to '+self.__name, False)

            if cmd == 'put':
                self.__storage[key] = value
            elif cmd == 'update':
                self.__storage.update(value)
            elif cmd == 'get':
                ret = self.__storage.get(key, value)
            elif cmd == 'pop':
                ret = self.__storage.pop(key, value)
            elif cmd == 'del':
                if key in self.__storage:
                    del self.__storage[key]
            elif cmd == 'clear':
                self.__storage.clear()
            elif cmd == 'keys':
                ret = list(self.__storage.keys())
            elif cmd == 'items':
                ret = list(self.__storage.items())
            elif cmd == 'len':
                ret = len(self.__storage)
            elif cmd == 'copy':
                ret = self.__storage.copy()

            unlock__(self.__lock)
            return ret
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'TList error in '+cmd+':'+str(e), False)
        return ret



#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

