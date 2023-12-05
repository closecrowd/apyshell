#!/usr/bin/env python3
"""queueext - Named multi-thread queues.

This extension provides thread-safe queues for communicating between
threads (and callback handlers).  It has all the queue management
functions anyone should need.

Queues are referenced by name (set in the queue_open_() function), and
may be either a classic First-In-First-Out queue, or a Last-In-First-Out
stack.  These queues are an excellent way to pass data from an
event-driven handler function to a main processing loop.


Make the functions available to a script by adding:

    loadExtension_('queueext')

to it.  Functions exported by this extension:

Methods:
        queue_open_()       : Create a named queue
        queue_close_()      : Flush and destroy an existing queue
        queue_put_()        : Put data into a queue
        queue_get_()        : Get the next item from a queue
        queue_clear_()      : Clear all items from a queue
        queue_len_()        : Return the number of items in a queue
        queue_isempty_()    : Return True if the queue is empty
        queue_list_()       : Return a list[] of the current queue names

Credits:
    * version: 1.0.0
    * last update: 2023-Nov-13
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

modready = True

import queue
import threading

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'queueext'
__cname__ = 'QueueExt'

MODNAME = "queueext"
DEBUG=False
#DEBUG=True

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class QueueExt():
    """This class provides thread-safe queues."""

    def __init__(self, api, options={}):
        """Constructs an instance of the QueueExt class.

        This instance will manage all named queues.  There will be only
        one of these instances at a time.

        Args:
            api     : an instance of ExtensionAPI connecting us to the engine

            options : a dict of option settings passed down to the extension

        """

        self.__api = api
        self.__options = options

        self.__cmddict = {}

        self.__queuenames = set()
        self.__queues = {}

        self.__locktimeout = 5
        self.__lock = threading.Lock()


    def register(self):
        """Make this extension's functions available to scripts

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * queue_open_()       : Create a named queue
                * queue_close_()      : Flush and destroy an existing queue
                * queue_put_()        : Put data on a qurur
                * queue_get_()        : Get the next item from a queue
                * queue_clear_()      : Clear all items from a queue
                * queue_len_()        : Return the number of items in a queue
                * queue_isempty_()    : Return True if the queue is empty
                * queue_list_()       : Return a list[] of the current queue names

            Args:

                None

            Returns:

                True        :   Commands are installed and the extension is ready to use.

                False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        self.__cmddict['queue_open_'] = self.queue_open_
        self.__cmddict['queue_close_'] = self.queue_close_

        self.__cmddict['queue_put_'] = self.queue_put_
        self.__cmddict['queue_get_'] = self.queue_get_

        self.__cmddict['queue_clear_'] = self.queue_clear_

        self.__cmddict['queue_len_'] = self.queue_len_
        self.__cmddict['queue_isempty_'] = self.queue_isempty_

        self.__cmddict['queue_list_'] = self.queue_list_


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

        This gets called by the extension manager just before
        the extension is unloaded.

        """

        return True

#----------------------------------------------------------------------
#
# Script API
#
#----------------------------------------------------------------------

    # add a new queue
    def queue_open_(self, name, **kwargs):
        """Handles the queue_open_() function.

        Creates a new queue and add it's name to the table.

            Args:
                cname       :   The queue name to use. Must not be in use.

                **kwargs    :   Options to pass down to the Queue.

            Returns:
                True if the queue was created.

                False if an error occurred.

            Options:
                    type    :   'fifo' or 'lifo' - queue or stack

        """

        # check the format of the queue name
        if not checkFileName(name):
            return retError(self.__api, MODNAME, 'invalid name:'+name)

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not open "'+name+'"', False)

            # check for duplicate queue names
            if name in self.__queuenames:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'Queue name already used:'+name)

            # create a new Queue

            qtype = kwargs.get('type', 'fifo')
            q = ThreadQueue_(name,  self.__api,  qtype)

            self.__queuenames.add(name)
            self.__queues[name] = q

            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in queue_open_ '+'"'+name+'":'+str(e), False)
        return True

    def queue_close_(self, name):
        """Handles the queue_close_() function.

        Close an open queue and clear any data currently in it.

            Args:
                name    :   The name of the queue to close.

            Returns:
                The return value. True for success, False otherwise.

        """

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+name+'"', False)

            if name not in self.__queuenames:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'Queue name not found:'+name)

            # get the queue object
            q = self.__queues[name]
            # empty the queue
            q.tqueue_clear_()
            # and close it
            q.tqueue_close_()
            # delete the object
            del self.__queues[name]
            # and remove the name
            self.__queuenames.discard(name)
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in queue_close_ '+'"'+name+'":'+str(e), False)
        return True


    def queue_put_(self, name, value, **kwargs):
        """Handles the queue_put_() function.

        Adds an item to the queue.  Items are always added to the back
        of the queue.

        The put operation may be either blocking or non-blocking.  If the
        block option in kwargs is False, the item is simply sent to the
        queue.  If the queue is full, the item will be silently discarded.
        If block is True (default), the put operation will be retried at
        1-second intervals until either: the item is added to the queue,
        the timeout count is reached, or the queue is closed.  A timeout
        of 0 will retry until either success or close.

            Args:
                name    :   The name of the queue to add to.

                value   :   The data item to add to the queue

                **kwargs    :   Options to pass down to the Queue.

            Options:
                    block   :   If True, block until timeout if the queue is full.

                    timeout :   Seconds to wait when blocking. 0 means wait forever.

            Returns:
                The return value. True for success, False otherwise.

        """
        if not value:
            return False

        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  False)
            self.__queues[name].tqueue_put_(value, **kwargs)
            return True
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error in queue_put_ '+'"'+name+'":'+str(e), False)
        return False

    def queue_get_(self, name, **kwargs):
        """Handles the queue_get_() function.

        Gets an item from the queue.  A 'fifo' queue returns the item at the
        HEAD of the queue.  A 'lifo' type will return the item at the END of
        the queue.

        The get operation may be either blocking or non-blocking.  If the
        block option in kwargs is False, the operation will return
        immediately.  If the queue was empty, the return will be None.

        If block is True (default) and the queue is empty, the get operation
        will be retried at 1-second intervals until either: an item is added
        to the queue, the timeout count is reached, or the queue is closed.
        A timeout of 0 will retry until either success or close.

            Args:
                name    :   The name of the queue to get from.

                **kwargs    :   Options to pass down to the Queue.

            Options:
                    block   :   If True, block until timeout if the queue is empty.

                    timeout :   Seconds to wait when blocking. 0 means wait forever.

            Returns:
                The next value from the queue, or None.

        """

        # TODO: add an option to raise() an exception on timeout

        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  None)

            ret = self.__queues[name].tqueue_get_(**kwargs)
            return ret
        except:
            return None

    def queue_clear_(self, name):
        """Handles the queue_clear_() function.

        Removes all items in a queue.

            Args:
                name    :   The name of the queue to get from.

            Returns:
                The return value. True for success, False otherwise.

        """

        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  False)

            self.__queues[name].tqueue_clear_()
            return True
        except:
            return False

    def queue_len_(self, name):
        """Handles the queue_len_() function.

        Returns the number of entries in a queue.

            Args:
                name    :   The name of the queue to check.

            Returns:
                The number of items in the named queue.  Any error returns 0.

        """

        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  0)

            ret = self.__queues[name].tqueue_len_()
            return ret
        except:
            return 0

    def queue_isempty_(self, name):
        """Handles the queue_isempty_() function.

        Returns True if the queue is empty.

            Args:
                name    :   The name of the queue to check.

            Returns:
                True if the named queue is empty, or there was an error.

        """

        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name, True)

            return self.__queues[name].tqueue_isempty_()
        except:
            return True

    def queue_list_(self):
        """Handles the queue_list_() function.

        Returns a list with the names of all open queues.

            Args:
                None

            Returns:
                A list[] of open queues.  The list may be empty if
                there are no queues open.

                None if there was an error.
        """

        ret = None
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not list queues', None)

            ret = list(self.__queues.keys())
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'Error in queue_list_:'+str(e), None)

        return ret

#----------------------------------------------------------------------
#
# queue class
#
#----------------------------------------------------------------------

class ThreadQueue_():
    """This class implements the actual thread-safe queue.

    There is one of these for every named queue in the table.


    """

    # create a ThreadQueue_ object
    def __init__(self, name, api,  qtype):

        self.__name = name      # save our name
        self.__api = api        # engine api
        self.__qtype = qtype    # save the type (FIFO, LIFO)

        self.__closed = False

        if qtype == 'lifo':
            self.__queue = queue.LifoQueue()
        else:
            self.__queue = queue.Queue()

    # Mark the queue closed
    def tqueue_close_(self):
        # flag it as closed
        self.__closed = True
        # wake up any sleeping gets()
        q.put(None, block=False)

    # Add an item to the queue
    def tqueue_put_(self, value, **kwargs):

        if self.__closed or value == None:
            return False

        # put the queue object
        q = self.__queue

        try:
            block = True
            timeout = 0
            if kwargs:
                block = kwargs.get('block', True)
                timeout = kwargs.get('timeout', 0)

            # if it's a blocking put
            if block:
                count = 0
                if self.__closed:
                    return False
                # loop until we succeed, timeout, or are closed
                while count <= timeout and self.__closed == False:
                    try:
                        if self.__closed:
                            break
                        # we try for 1 second each time
                        q.put(value,  block=True, timeout=1)
                        # success
                        return True
                    except:
                        # if timeout is not 0, bump the counter
                        if timeout > 0:
                            count += 1
                # timout has expired
                return False
            else:
                # otherwise, just toss it in there and hope
                q.put(value, block=False)
        except Exception as e:
            # TODO: return err msg through the api
            print(str(e))
            return False
        return True

    # Get an item from the queue and return it
    def tqueue_get_(self, **kwargs):

        if self.__closed:
            return None

        ret = None
        # get the queue object
        q = self.__queue

        try:
            block = True
            timeout = 0     # 0 means loop forever
            if kwargs:
                block = kwargs.get('block', True)
                timeout = kwargs.get('timeout', 0)

            # if it's a blocking get
            if block:
                count = 0
                while count <= timeout and self.__closed == False:
                    try:
                        if self.__closed:
                            break
                        # note that this is actually a 1-second timeout
                        # this allows other activities in the engine to continue
                        ret = q.get(block=True, timeout=1)
                        break
                    except:
                        # if it's not an infinite loop
                        if timeout > 0:
                            count += 1
                # timeout expired
            else:
                # non-blocking
                ret = q.get(block=False)
        except:
            pass
        q.task_done()
        return ret

    # Remove all items from the queue
    def tqueue_clear_(self):

        if self.__closed:
            return False

        try:
            clearq__(self.__queue)
            return True
        except:
            return False

    # Return the number of items in the queue
    def tqueue_len_(self):
        if self.__closed:
            return 0

        try:
            ret = self.__queue.qsize()
            return ret
        except:
            return 0

    # Return the empty state
    def tqueue_isempty_(self):

        if self.__closed:
            return False

        try:
            return self.__queue.empty()
        except:
            return False





#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

# clear all entries from a queue
def clearq__(q):
    if q:
        try:
            while not q.empty():
                q.get(block=False)
            q.task_done()
        except:
            pass
