#!/usr/bin/env python3
"""tlistext - Thread-safe List.

This extension provides thread-safe, named Lists.  Different threads are
free to add and remove items from the lists, without corrupting the data.

Each named tlist has it's own lock, so they are relatively independent
once created.

See also the companion tdict extension.

Make these functions available to a script by adding:

    loadExtension_('tlistext')

to it.  Functions exported by this extension:

Methods:

    tlist_open_()       :   create a named list
    tlist_close_()      :   delete an existing list

    tlist_append_()     :   add data to the end of a list
    tlist_extend_()     :   add a list to the end of a list
    tlist_insert_()     :   insert data into a list

    tlist_remove_()     :   remove data from a list
    tlist_get_()        :   retrieve data from a list
    tlist_pop_()        :   get data from a list, then remove it

    tlist_clear_()      :   remove all data from a list

    tlist_index_()      :   find a value in a list
    tlist_count_()      :   count occurrences of a value in a list
    tlist_len_()        :   return the number of items in a list

    tlist_reverse_()    :   reverse the order of item in a list
    tlist_copy_()       :   return a copy of the list as a Python list

Credits:
    * version: 1.0.0
    * last update: 2024-Jan-08
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

import threading
from ctypes import *

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

modready = True

__key__ = 'tlistext'
__cname__ = 'TListExt'

MODNAME = "tlistext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class TListExt():
    """This class provides a thread-safe list."""

    def __init__(self, api, options={}):
        """Constructs an instance of the TListExt class.

        This instance will manage all thread-safe lists.
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
            self.__locktimeout = int(options.get('tlist_timeo', 20))
        else:
            self.__locktimeout = 20

        self.__lists = {}       # list objects
        self.__lock = threading.Lock()


    def register(self):
        """ Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * tlist_open_()     : create a named list
                * tlist_close_()    : delete an existing list

                * tlist_append_()   : add data to the end of a list
                * tlist_extend_()   : add a list to the end of a list
                * tlist_insert_()   : insert data into a list

                * tlist_remove_()   : remove data from a list
                * tlist_get_()      : retrieve data from a list
                * tlist_pop_()      : get data from a list, then remove it

                * tlist_clear_()    : remove all data from a list

                * tlist_index_()    : find a item in a list
                * tlist_count_()    : count occurrences of a item in a list
                * tlist_len_()      : return the number of items in a list

                * tlist_reverse_()  : reverse the order of item in a list
                * tlist_copy_()     : return a copy of the list as a Python list

        Args:

            None

        Returns:

            True        :   Commands are installed and the extension is ready to use.

            False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        self.__cmddict['tlist_open_'] = self.tlist_open_
        self.__cmddict['tlist_close_'] = self.tlist_close_

        self.__cmddict['tlist_append_'] = self.tlist_append_
        self.__cmddict['tlist_extend_'] = self.tlist_extend_
        self.__cmddict['tlist_insert_'] = self.tlist_insert_

        self.__cmddict['tlist_remove_'] = self.tlist_remove_
        self.__cmddict['tlist_get_'] = self.tlist_get_
        self.__cmddict['tlist_pop_'] = self.tlist_pop_

        self.__cmddict['tlist_clear_'] = self.tlist_clear_

        self.__cmddict['tlist_index_'] = self.tlist_index_
        self.__cmddict['tlist_count_'] = self.tlist_count_
        self.__cmddict['tlist_len_'] = self.tlist_len_

#        self.__cmddict['tlist_sort_'] = self.tlist_sort_
        self.__cmddict['tlist_reverse_'] = self.tlist_reverse_
        self.__cmddict['tlist_copy_'] = self.tlist_copy_

        self.__cmddict['tlist_wait_'] = self.tlist_wait_

        self.__cmddict['tlist_list_'] = self.tlist_list_

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
            for lname in self.__lists.keys():
                self.__lists[lname].close_()

            self.__lists.clear()
            unlock__(self.__lock)
        except:
            unlock__(self.__lock)
        return True


# ----------------------------------------------------------------------
#
# Script API
#
# ----------------------------------------------------------------------

    def tlist_open_(self, lname, ilist=None):
        """Handles the tlist_open_() function.

        Creates a new tlist object attached to the given name.

            Args:

                lname   :   The name of the list to create.

                ilist   :   A Python list to init the tlist with (optional)

            Returns:

                True for success, False otherwise.

        """

        # check the format of the list name
        if not checkFileName(lname):
            return retError(self.__api, MODNAME, 'invalid name:'+lname, False)

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not open "'+lname+'"', False)

        if lname in self.__lists.keys():
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'TList name already used:'+lname, False)
        try:
            # make sure the optional init is a list
            if type(ilist) is not list:
                ilist = None

            b = ThreadList_(lname, self.__api, self.__locktimeout, ilist)
            self.__lists[lname] = b
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'TList error :'+str(e), False)
        return True


    def tlist_close_(self, lname):
        """Handles the tdict_close_() function.

        Clears out the data from an existing tlist, then removes it.

            Args:

                lname   :   The name of the list to remove.

            Returns:

                True for success, False otherwise.

        """
        # check the format of the list name
        if not checkFileName(lname):
            return retError(self.__api, MODNAME, 'invalid name:'+lname, False)

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not close "'+lname+'"', False)

        if lname not in self.__lists.keys():
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'TList name not found:'+lname, False)

        try:
            ret = self.__lists[lname].close_()
            del self.__lists[lname]
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'TList error :'+str(e), False)

        return ret

###

    # perform one of the commands defined below.  This saves a lot of
    # redundant code.  Note that this function is NOT exported to the
    # scripts.
    def __tlist_cmd(self, cmd, lname, item=None, index=None, endindex=None, errret=None):

        # check the format of the list name
        if not checkFileName(lname):
            return retError(self.__api, MODNAME, 'invalid name:'+lname, errret)

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not '+cmd+' "'+lname+'"', errret)

            if lname not in self.__lists.keys():
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'Tlist name not found:'+lname, errret)

            ret = self.__lists[lname].cmd_(cmd, item, index, endindex, errret)
            unlock__(self.__lock)
            return ret
        except:
            pass

        # return the passed-in default
        return errret

###

    def tlist_append_(self, lname, item):
        """Handles the tlist_append_() function.

        Adds an item at the end of the existing list.  If item is a
        list, then the existing list will be lenghtened by 1.  See
        tlist_extend_() for an alternative.

            Args:

                lname   :   The name of the list to add to.

                item    :   The item to add.

            Returns:

                True for success, False otherwise.

        """

        return self.__tlist_cmd('append', lname, item, None, None, False)

    def tlist_extend_(self, lname, nlist):
        """Handles the tlist_extend_() function.

        This function merges a new list into an existing one, making
        the existing list longer by the number of items in nlist.

            Args:

                lname   :   The name of the list to extend.

                nlist   :   The new list to add at the end.

            Returns:

                True for success, False otherwise.

        """

        return self.__tlist_cmd('extend', lname, nlist, None, None, False)

    def tlist_insert_(self, lname, item, index):
        """Handles the tlist_insert_() function.

        This function sticks the item into the list at index (starting
        from 0). The index value determines where it will be inserted.

        If index is 0, put it at the head of the list.
        If index >0, put it that many places from the head of the list.
        If index is None, append it to the end of the list.
        If index <0, put it that many places from the END of the list.

            Args:

                lname   :   The name of the list to insert into.

                item    :   The item to add to the list.

                index   :   The 0-based index to insert at.

            Returns:

                True for success, False otherwise.

        """
        return self.__tlist_cmd('insert', lname, item, index, None, False)

    def tlist_remove_(self, lname, value):
        """Handles the tlist_remove_() function.

        Remove the item matching 'value' from the list, if it's
        found in the list.

            Args:

                lname   :   The name of the list to scan.

                value   :   The item to look for and remove.

            Returns:

                True for success, False otherwise.

        """

        return self.__tlist_cmd('remove', lname, value, None, None, False)

    def tlist_get_(self, lname, index=None, endindex=None, step=None):
        """Handles the tlist_get_() function.

        Return a subset of the list starting at index for endindex characters
        as a plain Python list.  Negative indices are supported, as well as
        a step increment > 1.

            Args:

                lname       :   The name of the list to extract from.

                index       :   Starting index.

                endindex    :   Number of items to return starting at index.

                step        :   Index increment (defaults to 1)

            Returns:

                A Python list with the selected subset of the list, or None if error.

        """

        return self.__tlist_cmd('get', lname, index, endindex, step, None)

    def tlist_pop_(self, lname, index=None):
        """Handles the tlist_pop_() function.

        Return the item at the head of the list, or at the specified index
        (if valid). Removes the item from the list.

        If index is 0, get it from the head of the list.
        If index >0, get it from that many places from the head of the list.
        If index is None, get it from the end of the list.
        If index <0, get it from that many places from the END of the list.

            Args:

                lname   :   The name of the list to insert into.

                item    :   The item to add to the list.

                index   :   The 0-based index to insert at.

            Returns:

                The item at the specified index, or None for error.

        """

        return self.__tlist_cmd('pop', lname, index, None, None, None)

    def tlist_clear_(self, lname):
        """Handles the tlist_clear_() function.

        Removes all of the items in the list.

            Args:

                lname   :   The name of the list to clear.

            Returns:

                True for success, False otherwise.

        """

        return self.__tlist_cmd('clear', lname, None, None, None, False)

    def tlist_index_(self, lname, value, index=None, endindex=None):
        """Handles the index_() function.

        Returns zero-based index in the list of the first item whose value
        is equal to 'value'. The index arguments, if present,  restrict the
        search to a subset of the list.

            Args:

                lname       :   The name of the list to check.

                value       :   The item to look for.

                index       :   Starting index.

                endindex    :   Number of items to search starting at index.

            Returns:

                The index where 'item' appears in the list.  The return index
                is relative to the entire list, not 'idex'.

        """

        return self.__tlist_cmd('index', lname, value, index, endindex, None)

    def tlist_count_(self, lname, value):
        """Handles the tlist_count_() function.

        Return the count of items matching 'value'.

            Args:

                lname   :   The name of the list to check.

                value   :   The item to look for.

            Returns:

                The number of times 'item' appears in the list.

        """

        return self.__tlist_cmd('count', lname, value, None, None, 0)

    def tlist_len_(self, lname):
        """Handles the tlist_len_() function.

        Returns the number of items in the list.

            Args:

                lname   :   The name of the list to count.

            Returns:

                The number of items currently in the list.

        """

        return self.__tlist_cmd('len', lname, None, None, None, 0)

    def tlist_reverse_(self, lname):
        """Handles the tlist_reverse_() function.

        Reverses the order of the items in the list.

            Args:

                lname   :   The name of the list to reverse.

            Returns:

                True for success, False otherwise.

        """
        return self.__tlist_cmd('reverse', lname, None, None, None, False)

    def tlist_copy_(self, lname):
        """Handles the tlist_copy_() function.

        Returns a copy of the contents of this tlist as a plain
        Python list.

        """
        return self.__tlist_cmd('copy', lname, None, None, None, None)


    # wait for data to be added to the list
    def tlist_wait_(self, lname, timeout=10):
        """Handles the tlist_wait_() function.

        Waits for an item to be added to the list, or when the timeout
        (in seconds) expires.  If there are items in the list when this
        function is called, it returns True immediately.

            Args:

                lname   :   The name of the list to insert into.

                timeout :   The item to add to the list.

            Returns:

                True if there are items in the list, False otherwise.

        """

        # check the format of the list name
        if not checkFileName(lname):
            return retError(self.__api, MODNAME, 'invalid name:'+lname, False)

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not acquire "'+lname+'"', False)

        if lname not in self.__lists.keys():
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Tlist name not found:'+lname, False)

        # get the entry to the object
        func = self.__lists[lname].cmd_
        unlock__(self.__lock)

        # this has to be outside the lock to prevent deadlocks
        try:
            ret = func('wait', timeout)
            return ret
        except:
            return False

    def tlist_list_(self):
        """Handles the tlist_list_() function.

        Returns a list with the names of all current tlists.

            Args:

                None

            Returns:

                A list[] of active tlists.  The list may be empty if there are none.

                None if there was an error.

        """

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not list tlists', False)

        ret = list(self.__lists.keys())
        unlock__(self.__lock)
        return ret


# ----------------------------------------------------------------------
#
# data classes
#
# ----------------------------------------------------------------------

class ThreadList_():

    def __init__(self, name, api, timeout=20, ilist=None):

        self.__name = name
        self.__api = api

        self.locktimeout = timeout

        self.__storage = []
        self.__lock = threading.Lock()
        self.__event = threading.Event()
        if ilist is not None:
            self.__storage.extend(ilist)


    def close_(self):
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+self.__name+'"', False)
            self.__storage.clear()
            # trigger any hanging wait() threads
            self.__event.set()
            self.__event.clear()
            unlock__(self.__lock)
            return True
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error closing TList '+'"'+self.__name+'":'+str(e), False)
        return False

    # command processor
    def cmd_(self, cmd, value=None, index=None, endindex=None, errret=True):
        """Internal tlist command dispatcher.

        This method performs the actual list operations.  Not every
        command uses all of the arguments.


        """

        ret = errret

        # wait must be outside of the lock
        if cmd == 'wait':
            if len(self.__storage) > 0:
                return True
            try:
                self.__event.clear()
                return self.__event.wait(float(value))
            except:
                return False

        # lock the list and process commands
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.locktimeout):
                return retError(self.__api, MODNAME, 'Could not '+cmd+' "'+value+'" to '+self.__name, False)

            if cmd == 'append':
                if value is not None:
                    self.__storage.append(value)
                    self.__event.set()
                else:
                    ret = False
            elif cmd == 'extend':
                if value is not None:
                    self.__storage.extend(value)
                    self.__event.set()
                else:
                    ret = False
            elif cmd == 'insert':
                if value is not None:
                    # None says to append it at the end
                    if index is None:
                        ind = len(self.__storage)
                    else:
                        ind = int(index)
                    if ind < 0:
                        ind = len(self.__storage) - abs(ind)
                    self.__storage.insert(ind,  value)
                    self.__event.set()
                    ret = True
                else:
                    ret = False
            elif cmd == 'remove':
                if value is not None:
                    if value in self.__storage:
                        self.__storage.remove(value)
                    if len(self.__storage) == 0:
                        self.__event.clear()
                else:
                    ret = False
            elif cmd == 'get':
                if value is None:
                    value = 0
                if index is None:
                    index = len(self.__storage)
                if endindex is None:
                    endindex = 1
                ret = self.__storage[int(value):int(index):int(endindex)]
            elif cmd == 'pop':
                if value is None:
                    # return the LAST item
                    ret = self.__storage.pop()
                else:
                    ind = int(value)
                    llen = len(self.__storage)
                    # if nothing in the list, or index is too big
                    if llen == 0 or ind >= llen:
                        ret = None
                    else:
                        if ind < 0:
                            ind = len(self.__storage) - abs(ind) - 1
                        ret = self.__storage.pop(ind)
                if len(self.__storage) == 0:
                    self.__event.clear()
            elif cmd == 'clear':
                self.__storage.clear()
                self.__event.clear()
            elif cmd == 'index':
                try:
                    if endindex is not None:
                        ret = self.__storage.index(value,  index,  endindex)
                    elif index is not None:
                        ret = self.__storage.index(value,  index)
                    else:
                        ret = self.__storage.index(value)
                except:
                    ret = -1
            elif cmd == 'count':
                if value is not None:
                    ret = self.__storage.count(value)
                else:
                    ret = -1
            elif cmd == 'len':
                ret = len(self.__storage)
            elif cmd == 'reverse':
                ret = self.__storage.reverse()
            elif cmd == 'copy':
                ret = self.__storage.copy()

            unlock__(self.__lock)
            return ret
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'TList error :'+str(e), False)
        return ret

# ----------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------
