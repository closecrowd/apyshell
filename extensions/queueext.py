#!/usr/bin/env python3
"""
    queueext - Named multi-thread queues

    This extension provides thread-safe queues for communicating between
    threads (and callback handlers).  It has all the queue management
    functions anyone should need.

     Make the functions available to a script by adding:

        loadExtension_('queueext')

    to it.  Functions exported by this extension:

            queue_open_()       : Create a named queue
            queue_close_()      : Flush and destroy an existing queue
            queue_put_()        : Put data on a qurur
            queue_get_()        : Get the next item from a queue
            queue_clear_()      : Clear all items from a queue
            queue_len_()        : Return the number of items in a queue
            queue_isempty_()    : Return True if the queue is empty
            queue_list_()       : Return a list[] of the current queue names


    version: 1.0
    last update: 2023-Nov-13
    License:  MIT
    Author:  Mark Anacker <closecrowd@pm.me>
    Copyright (c) 2023 by Mark Anacker
--------------------------------------------------------------------
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

    ''' This class provides thread-safe queues. '''

    def __init__(self, api, options={}):
        '''
        Parameters
        ----------
        api     : an instance of ExtensionAPI connecting us to the engine
        options : a dict of option settings passed down to the extension

        '''

        self.__api = api
        self.__options = options

        self.__cmddict = {}

        self.__queuenames = set()
        self.__queues = {}

        self.__locktimeout = 5
        self.__lock = threading.Lock()


    def register(self):
        ''' Make this extension's commands available to scripts

        Commands installed
        ------------------

            queue_open_()       : Create a named queue
            queue_close_()      : Flush and destroy an existing queue
            queue_put_()        : Put data on a qurur
            queue_get_()        : Get the next item from a queue
            queue_clear_()      : Clear all items from a queue
            queue_len_()        : Return the number of items in a queue
            queue_isempty_()    : Return True if the queue is empty
            queue_list_()       : Return a list[] of the current queue names

        Returns
        -------
        True            :   Commands are installed and the extension is
                            ready to use.
        False           :   Commands are NOT installed, and the extension
                            is inactive.
        '''

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

    # add a new queue
    def queue_open_(self, name, **kwargs):
        ''' Create a new queue and add it's name to the table '''

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
        ''' Remove a queue, clearing any data waiting in it '''
        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+name+'"', False)

            if name not in self.__queuenames:
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'Queue name not found:'+name)

            # get the event
            q = self.__queues[name]
            # empty the queue
            q.tqueue_clear_()
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
        ''' Add an item to the back of a queue '''
        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  False)
            self.__queues[name].tqueue_put_(value, **kwargs)
            return True
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error in queue_put_ '+'"'+name+'":'+str(e), False)
        return False

    def queue_get_(self, name, **kwargs):
        ''' Grab the item at the head of a queue '''
        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  None)

            ret = self.__queues[name].tqueue_get_(**kwargs)
            return ret
        except:
            return None

    def queue_clear_(self, name):
        ''' Clear all entries in a queue '''
        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  False)

            self.__queues[name].tqueue_clear_()
            return True
        except:
            return False

    def queue_len_(self, name):
        ''' Return the number of entries in a queue '''
        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name,  0)

            ret = self.__queues[name].tqueue_len_()
            return ret
        except:
            return 0

    def queue_isempty_(self, name):
        ''' Return True if the queue is empty '''
        try:
            if name not in self.__queuenames:
                return retError(self.__api, MODNAME, 'Queue name not found:'+name, False)

            return self.__queues[name].tqueue_isempty_()
        except:
            return False

    def queue_list_(self):
        ''' Return a list[] of queue names '''
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
    ''' This class implements the actual thread-safe queue.  There is
        one of these for every named queue in the table.
    '''

    def __init__(self, name, api,  qtype):

        self.__name = name      # save our name
        self.__api = api
        self.__qtype = qtype    # save the type (FIFO, LIFO)

        self.__closed = False

        if qtype == 'lifo':
            self.__queue = queue.LifoQueue()
        else:
            self.__queue = queue.Queue()

    def tqueue_close_(self):
        self.__closed = True

    def tqueue_put_(self, value, **kwargs):
        # get the queue object
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
                while count <= timeout and self.__closed == False:
                    try:
                        q.put(value,  block=True, timeout=1)
                        break
                    except:
                        if timeout > 0:
                            count += 1
            else:
                q.put(value, block=False)
        except Exception as e:
            print(str(e))
            return False
        return True


    def tqueue_get_(self, **kwargs):
        ret = None
        # get the queue object
        q = self.__queue

        try:
            block = True
            timeout = 0
            if kwargs:
                block = kwargs.get('block', True)
                timeout = kwargs.get('timeout', 0)

            # if it's a blocking get
            if block:
                count = 0
                while count <= timeout and self.__closed == False:
                    try:
                        ret = q.get(block=True, timeout=1)
                        break
                    except:
                        if timeout > 0:
                            count += 1
            else:
                # non-blocking
                ret = q.get(block=False)
        except:
            oass
        q.task_done()
        return ret


    def tqueue_clear_(self):
        try:
            clearq__(self.__queue)
            return True
        except:
            return False

    def tqueue_len_(self):
        try:

            ret = self.__queue.qsize()
            return ret
        except:
            return 0

    def tqueue_isempty_(self):
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
