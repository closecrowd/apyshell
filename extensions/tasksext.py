#!/usr/bin/env python3
"""tasksext - Thread-safe task runner.

This extension manages script functions running in multiple
threads.

Make the functions available to a script by adding:

    loadExtension_('tasksext')

to it.  Functions exported by this extension:

Methods:

        tasks_open_()       : create a named task
        tasks_close_()      : delete an existing task
        tasks_start_()      : Starts a task running in a thread
        tasks_stop_()       : Stop a running task
        tasks_status_()     : Return state of a task
        tasks_list_()       : Return list[] of tasks

Credits:
    * version: 1.0.1
    * last update: 2024-Jan-08
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023,2024 by Mark Anacker

"""

import threading

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

modready = True

__key__ = 'tasksext'
__cname__ = 'TasksExt'

MODNAME = "tasksext"

##############################################################################

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class TasksExt():
    """This class provides scheduled tasks."""

    def __init__(self, api, options={}):
        """Constructs an instance of the TasksExt class.

        This instance will manage all thread tasks.  There will be only
        one of these instances at a time.

        Args:

            api     : an instance of ExtensionAPI connecting us to the engine

            options : a dict of option settings passed down to the extension

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}

        # lock accquire timeout
        if options:
            self.__locktimeout = int(options.get('tasks_timeo', 10))
        else:
            self.__locktimeout = 20

        self.__tasks = {}       # task objects
        self.__lock = threading.Lock()


    def register(self):
        """Make this extension's commands available to scripts


        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * tasks_open_()       : create a named task
                * tasks_close_()      : delete an existing task
                * tasks_start_()      : Starts a task running in a thread
                * tasks_stop_()       : Stop a running task
                * tasks_status_()     : Return state of a task
                * tasks_list_()       : Return list[] of tasks

            Args:

                None

            Returns:

                True        :   Commands are installed and the extension is ready to use.

                False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return False

        self.__cmddict['tasks_open_'] = self.tasks_open_
        self.__cmddict['tasks_close_'] = self.tasks_close_

        self.__cmddict['tasks_start_'] = self.tasks_start_
        self.__cmddict['tasks_stop_'] = self.tasks_stop_
        self.__cmddict['tasks_pause_'] = self.tasks_pause_

        self.__cmddict['tasks_status_'] = self.tasks_status_
        self.__cmddict['tasks_list_'] = self.tasks_list_

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

        try:
            self.__lock.acquire(blocking=True, timeout=2)

            for tname in self.__tasks.keys():
                self.__tasks[tname].stop_()
                self.__tasks[tname].close_()

            self.__tasks.clear()
            unlock__(self.__lock)
        except:
            unlock__(self.__lock)
        return True

# ----------------------------------------------------------------------
#
# Script API
#
# ----------------------------------------------------------------------

    # set up a task thread. delay of 0 makes it a 1-shot
    def tasks_open_(self, tname, handler, data=None, delay=1.0):
        """Handles the tasks_open_() function..

        Creates a new task thread and adds it's name to the table.  The
        task does not start running until tasks_start_() is called.

            Args:

                tname       :   The name to assign to this task.

                handler     :   The name of the script function to run.

                data        :   A parameter to pass to the handler.

                delay       :   The delay between calls to handler. Pass 0 to call it once only. Value is in seconds.

            Returns:

                True if the task was created.

                False if an error occurred.

        """

        # check the format of the task name
        if not checkFileName(tname):
            return retError(self.__api, MODNAME, 'invalid name:'+tname, False)

        # and the handler name
        if not checkFileName(handler):
            return retError(self.__api, MODNAME, 'invalid handler name:'+handler, False)

        try:

            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not open "'+tname+'"', False)

            if tname in self.__tasks.keys():
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'task name already used:'+tname, False)

            b = ThreadTask_(tname, self.__api, handler, data, delay)
            self.__tasks[tname] = b
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'task error :'+str(e), False)
        return True


    def tasks_close_(self, tname):
        """Handles the tasks_close_() function..

        Stops an existing task (if running), and releases it's resources.

            Args:

                tname       :   The name of the task to close.

            Returns:

                True if the task was closed.

                False if an error occurred.

        """

        # check the format of the task name
        if not checkFileName(tname):
            return retError(self.__api, MODNAME, 'invalid name:'+tname, False)

        try:

            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not close "'+tname+'"', False)

            if tname not in self.__tasks.keys():
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'task name not found:'+tname, False)

            ret = self.__tasks[tname].close_()
            self.__tasks[tname].join(2.0)
            del self.__tasks[tname]
            unlock__(self.__lock)
        except Exception as e:
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'task error :'+str(e), False)

        return ret

    # internal function called by tasks_start_,tasks_stop[_,tasks_pause_
    # not exposed to the scripts. This method cuts down the repetitive
    # code in the following methods.
    def tasks_cmd(self, cmd, tname, flag=None):

        # check the format of the task name
        if not checkFileName(tname):
            return retError(self.__api, MODNAME, 'invalid name:'+tname, False)

        try:
            if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
                return retError(self.__api, MODNAME, 'Could not '+cmd+' "'+tname+'"', False)

            if tname not in self.__tasks.keys():
                unlock__(self.__lock)
                return retError(self.__api, MODNAME, 'task name not found:'+tname, False)

            unlock__(self.__lock)

            ret = False

            # command dispatcher
            if cmd == 'start':
                ret = self.__tasks[tname].start()
            elif cmd == 'stop':
                ret = self.__tasks[tname].stop_()
            elif cmd == 'pause':
                ret = self.__tasks[tname].pause_(flag)

            return ret
        except Exception as e:
            print('cmd failed:', str(e))
            unlock__(self.__lock)
        return False

    def tasks_start_(self, tname):
        """Handles the tasks_start_() function..

        Begins calling the handler specified in tasks_open_().  If the delay
        value was 0, the handler will be called only once.  If > 0, the handler
        will be called repeatedly with 'delay' seconds between iterations.

            Args:

                tname       :   The name of the task to start.

            Returns:

                True if the task was started.

                False if an error occurred.

        """

        return self.tasks_cmd('start', tname)

    def tasks_stop_(self, tname):
        """Handles the tasks_stop_() function.

        Stops a running task. Do not reuse this task after stopping it.

            Args:

                tname       :   The name of the task to stop.

            Returns:

                True if the task was stopped.

                False if an error occurred.

        """

        return self.tasks_cmd('stop', tname)

    def tasks_pause_(self, tname, flag):
        """Handles the tasks_pause_() function.

        Pauses or resumes a running task.  Resuming a paused task causes
        it to execute immediately, then start a new delay period.

            Args:

                tname       :   The name of the task to pause/resume.

                flag        :   if True, pause the task.  If False, resume it.

            Returns:

                True if the task was paused/resumed.

                False if an error occurred.

        """

        return self.tasks_cmd('pause', tname, flag)

    # return task status
    def tasks_status_(self, tname):
        """Handles the tasks_status_() function.

        Returns True if the specified task is running.

            Args:

                tname       :   The name of the task to check.

            Returns:

                True if the task is running.

                False if the task is stopped, or an error occurred.

        """

        # check the format of the task name
        if not checkFileName(tname):
            return retError(self.__api, MODNAME, 'invalid name:'+tname, False)

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not get status of "'+tname+'"', False)

        if tname not in self.__tasks.keys():
            unlock__(self.__lock)
            return retError(self.__api, MODNAME, 'task name not found:'+tname, False)

        ret = self.__tasks[tname].is_alive()
        unlock__(self.__lock)
        return ret

    def tasks_list_(self):
        """Handles the tasks_list_() function.

        Returns a list with the names of all open tasks.

            Args:

                None

            Returns:

                A list[] of open tasks.  The list may be empty if
                there are no tasks open.

                None if there was an error.

        """

        if not self.__lock.acquire(blocking=True, timeout=self.__locktimeout):
            return retError(self.__api, MODNAME, 'Could not list tasks', False)

        ret = list(self.__tasks.keys())
        unlock__(self.__lock)
        return ret

# ----------------------------------------------------------------------
#
# data classes
#
# ----------------------------------------------------------------------

class ThreadTask_(threading.Thread):

    def __init__(self, name, api, handler, data=None, delay=1):
        threading.Thread.__init__(self)

        self.__name = name
        self.__api = api
        self.__handler = handler
        self.__data = data
        self.__delay = int(abs(delay))
        self.__delay = abs(delay)

        self.__quitFlag = threading.Event()
        self.__stop = False
        self.__paused = False
        self.__running = False
        if self.__data is None:
            self.__data = name

    def close_(self):
        try:
            self.__stop = True
            self.__quitFlag.set()
            return True
        except Exception as e:
            return retError(self.__api, MODNAME, 'Error closing task '+'"'+self.__name+'":'+str(e), False)
        return False

    def stop_(self):
        self.__stop = True
        self.__quitFlag.set()
        return True

    def pause_(self, flag):
        if flag is True:
            self.__paused = True
            self.__quitFlag.set()
        else:
            self.__paused = False
            self.__quitFlag.set()

    def is_running_(self):
        return self.__running

    def run(self):
        # init flags
        self.__stop = False
        self.__quitFlag.clear()
        self.__running = True

        # 0 - execute once then exit
        if self.__delay == 0:
            self.__callHandler()
            self.__stop = True
        else:
            # while active:
            while self.__stop is False:
                # clear the flag
                self.__quitFlag.clear()
                # if not paused, call the handler
                if self.__paused is False:
                    self.__callHandler()

                # ** delay handler **

                # > 0 - time delay in seconds, then keep looping
                if self.__stop:
                    break
                # wait for the flag or timeout
                ret = self.__quitFlag.wait(self.__delay)
                # stop was signalled
                if ret and self.__stop:
                    break

        self.__running = False

    # call the defined handler
    def __callHandler(self):
        # pass the data to the handler
        if type(self.__data) is str:
            # if it's a string, quote it
            self.__api.handleEvents(self.__handler, '"'+self.__data+'"' )
        else:
            # otherwise, pass the object in directly
            self.__api.handleEvents(self.__handler, self.__data )

# ----------------------------------------------------------------------
#
# Support functions
#
# ----------------------------------------------------------------------
