#!/usr/bin/env python3
"""httpext - HTTP(S) client extension

This extension provides HTTP(s) client functions to the scripts.
It can perform GET and PUT requests, using one of two external
modules (requests or http.client).  If you are using the requests
mode (1), you can also issue any HTTP request type.

Make these functions available to a script by adding:

    loadExtension_('httpext')

to it.  Functions exported by this extension:

Methods:

    http_modes_()       :   Return a list of available client modes
    http_get_()         :   Do a GET to a URL
    http_put_()         :   Do a PUT to a URL
    http_requests_()    :   Calls requests() directly (if available)

Credits:
    * version: 1.0.0
    * last update: 2023-Dec-12
    * License:  MIT
    * Author:  Mark Anacker <closecrowd@pm.me>
    * Copyright (c) 2023 by Mark Anacker

"""

modready = True
modelist = []   # modes available (1==requests, 2==http.client)

# this section determines which client module we can use:
# requests and/or http.client.

# first, try to use the requests module
try:
    import requests
    hasrequests = True
    modelist.append(1)
except Exception as ex:
    print('import failed:', ex,'mode 1 unavailable')
    hasrequests = False

# now try http.client
try:
    import http.client
    import ssl
    hasclient = True
    modelist.append(2)
except Exception as ex:
    print('import failed:', ex,'mode 2 unavailable')
    hasclient = False

# we have neither, so nothing will be installed
if hasrequests == False and hasclient == False:
    print('no network support for http')
    modready = False
else:
    # if we have some http support, add urllib
    try:
        from urllib.parse import urlparse
    except Exception as ex:
        print('import failed:', ex)
        modready = False

from ctypes import *

from support import *
from extensionapi import *

##############################################################################

#
# Globals
#

__key__ = 'httpext'
__cname__ = 'HttpExt'

MODNAME="httpext"
DEBUG=False
#DEBUG=True

schemes = {'http', 'https'} # we only support these schemes

# the default header to send if none was passed in
DEFHEADER = {"Content-type": "text/plain; charset=UTF-8",
             "Accept": "text/plain", "Connection": "close" }

# error return status codes and messages
ERRORS = {  999 : 'Client mode unavailable: ',
            998 : 'http_get_() invalid scheme: ',
            997 : 'no data',
            996 : 'http_get_() exception: ',
            995 : 'http_put_() invalid scheme: ',
            994 : 'http_put_() exception: ',
            993 : 'http_request_() exception: ',
            992 : 'Client request exception: ',
         }

##############################################################################

def debug(*args):
    if DEBUG:
        print(MODNAME,str(args))

# ----------------------------------------------------------------------------
#
# Extension class
#
# ----------------------------------------------------------------------------

class HttpExt():
    """This class provides an HTTP/HTTPS client."""

    def __init__(self, api, options={}):
        """

        This instance contains the HTTP client functions.  Some flags are set
        based on the results of the imports above.

            Args:

                api     : an instance of ExtensionAPI connecting us to the engine.

                options : a dict of option settings passed down to the extension.

            Returns:

                Nothing.

        """

        self.__api = api
        self.__options = options
        self.__cmddict = {}
        self.__clientmode = 0
        # we default to the requests module unless...
        if hasrequests:
            self.__clientmode = 1
        # we only have http.client
        elif hasclient:
            self.__clientmode = 2


    def register(self):
        """Make this extension's functions available to scripts.

        This method installs our script API methods as functions in the
        engine symbol table, making them available to scripts.

        This is called by the ExtensionMgr during loading.

        Note:
            Functions installed:
                * http_modes_()     :   Returns the list of available modes
                * http_get_()       :   Performs a GET to a URL
                * http_put_()       :   Performs a PUT to a URL
                * http_request_()   :   Calls requests() directly (if available)

            Args:

                None

            Returns

                True        :   Commands are installed and the extension is ready to use.

                False       :   Commands are NOT installed, and the extension is inactive.

        """

        if not modready:
            return retError(self.__api, MODNAME, 'No HTTP support available', False)

        self.__cmddict['http_modes_'] = self.http_clientModes_
        self.__cmddict['http_get_'] = self.http_get_
        self.__cmddict['http_put_'] = self.http_put_

        # this function is only installed if the requests module is
        # available
        if hasrequests:
            self.__cmddict['http_request_'] = self.http_request_

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

    # return the list of available client modes, and the current mode
    def http_clientModes_(self):
        """Returns the list of available modes.

        Returns a tuple consisting of the list[] of available client modes,
        and the default mode selected by the extension.  There are currently
        two client modes: 1 uses the requests module, and 2 uses the http.client
        module.  This extension tries to use mode 1, but will use mode 2 if
        the requests module fails to import.

        Each request may override the default and choose which mode it wants,
        if that mode is available.

            Args:

                None

            Returns:

                A tuple: (modelist, default)

            Example:

                ([1,2], 1)

        """
        return((modelist, self.__clientmode))

    # HTTP(s) GET
    def http_get_(self, url, **kwargs):
        """Performs a GET from a URL.

        Sends an HTTP or HTTPS GET to the specified URL, using one of the
        client modes.  The mode is either the default set in __init__()
        above, or specified by the 'client=' option.

            Args:

                url         :   The URL to send the GET to.

                **kwargs    :   A dict with supported options.

            Returns:

                If simple is True, return just the data from the body
                of the response.  In the case of an error, an empty
                string will be returned.

                If simple is False, return a tuple with the HTTP status
                code, the contents of the response, and a dict with detailed
                response data.  The entries in this dict will vary depending
                on the client mode.

            Options:

                client      :   The client mode (1 or 2) to use.

                headers     :   A dict of HTTP headers to use.

                simple      :   Returns only the retrieved text.

                timeout     :   Request timeout in seconds.

                cert        :   TLS certificate - either a String with just the client cert, or a tuple with the cert and keyfile (cert, keyfile).

                verify      :   Verify the server hostname.

            Other options are passed to the requests or http.client modules.

        """

        # add a default header if onw wasn't specified
        if 'headers' not in  kwargs:
            kwargs['headers'] = DEFHEADER

        # check for simple output mode
        simple = kwargs.pop('simple', False)

        # caller wants to select the client mode
        clientmode = int( kwargs.pop('client', self.__clientmode)  )

        # they chose poorly...
        if clientmode not in modelist:
            if simple:
                return('')
            else:
                # 'Client mode unavailable:'
                return(999, ERRORS[999]+str(clientmode), None)


        try:
            # parse the URL
            u = urlparse(url)
            debug('GET from:', u.netloc,  u.scheme)

            # check for an allowed scheme
            if u.scheme not in schemes:
                if simple:
                    return('')
                else:
                    # 'http_get_() invalid scheme:'
                    return(998, ERRORS[998]+u.scheme, None)

            if clientmode == 1:
                # GET via the request_ function below
                (sc, emsg, r) = self.http_request_('GET', url, **kwargs)
            elif clientmode == 2:
                # GET via the http.client module
                (sc, emsg, r) = _httpclientreq('GET', url, **kwargs)
                if emsg:
                    emsg = emsg.decode('utf-8')
            if emsg != None:
                if simple:
                    # return just the message
                    return(emsg)
                else:
                    return(sc, emsg, r)
            else:
                if simple:
                    return('')
                else:
                    # 'no data'
                    return(997, ERRORS[997], None)
        except Exception as ex:
            if simple:
                return('')
            else:
                # 'http_get_() exception:'
                return(996, ERRORS[996]+str(ex), None)


    # HTTP(s) PUT
    def http_put_(self, url, **kwargs):
        """Performs a PUT to a URL.

        Sends an HTTP or HTTPS PUT to the specified URL, using one of the
        client modes.  The mode is either the default set in __init__()
        above, or specified by the 'client=' option.

        The data to send in the body of the PUT is set by the 'data='
        option.

            Args:

                url         :   The URL to send the GET to.

                **kwargs    :   A dict with supported options.

            Returns:

                Returns a tuple with the HTTP status code, the contents
                of the response, and a dict with detailed response data.
                The entries in this dict will vary depending on the client mode.

            Options:

                client      :   The client mode (1 or 2) to use.

                data        :   The data to send to the server

                headers     :   A dict of HTTP headers to use.

                timeout     :   Request timeout in seconds.

                cert        :   TLS certificate - either a String with just the client cert, or a tuple with the cert and keyfile (cert, keyfile).

                verify      :   Verify the server hostname.

            Other options are passed to the requests or http.client modules.

        """

        r = None

        if 'headers' not in  kwargs:
            kwargs['headers'] = DEFHEADER

        # caller wants to select the client mode
        clientmode = int( kwargs.pop('client', self.__clientmode)  )

        # they chose poorly...
        if clientmode not in modelist:
            # 'Client mode unavailable:'
            return(999, ERRORS[999]+str(clientmode), None)

        try:
            # parse the URL
            u = urlparse(url)

            # check for an allowed scheme
            if u.scheme not in schemes:
                # 'http_put_() invalid scheme:'
                return(995, ERRORS[995]+u.scheme, None)

            if clientmode == 1:
                (sc, emsg, r) = self.http_request_('PUT', url, **kwargs)
            elif clientmode == 2:
                (sc, emsg, r) = _httpclientreq('PUT', url, **kwargs)
            return(sc, emsg, r)
        except Exception as ex:
            pass

        # 'http_put_() exception:'
        return(994, ERRORS[994]+str(ex), None)


    # mode 1 only - requests module
    def http_request_(self, method, url, **kwargs):
        """Sends a request to a URL.

        This is a thin wrapper over the requests method of the
        requests module.  As such, it's only available if the requests
        import succeeded.

            Args:

                method      :   The method to use (String). Must be: GET, OPTIONS, HEAD, POST, PUT, PATCH, or DELETE.

                url         :   The URL to use (String).

                **kwargs    :   A dict with supported options.

            Returns:

                Returns a tuple with the HTTP status code, the contents
                of the response, and a dict with detailed response data.

            Options:

                Options are passed to the requests module.
                See: https://requests.readthedocs.io/en/latest/

        """

        try:
            if kwargs:
                r = requests.request(method, url, **kwargs)
            else:
                r = requests.request(method, url)
            return(r.status_code, r.text, vars(r))

        except Exception as ex:
            pass

        # 'http_request_() exception:'
        return(993, ERRORS[993]+str(ex), None)

#----------------------------------------------------------------------
#
# Support functions
#
#----------------------------------------------------------------------

# mode 2 - http.client requester
def _httpclientreq(method, url, **kwargs):

    u = urlparse(url)

    # get the connection timeout - default = 4.0 seconds
    timeout = float( kwargs.pop('timeout', 4.0) )

    try:
        if u.scheme == 'https':
            checkflag = kwargs.pop('verify', False)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS)
            context.check_hostname = checkflag
            context.verify_mode = ssl.CERT_OPTIONAL
            context.load_default_certs()

            if 'cert' in kwargs:
                carg = kwargs['cert']
                if carg is String:
                    (certfile, keyfile) = (carg, None)
                else:
                    (certfile, keyfile) = carg
                context.load_cert_chain(certfile, keyfile)
            conn = http.client.HTTPSConnection(u.netloc, context=context, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(u.netloc, timeout=timeout)

        bod = None
        if method == 'PUT':
            bod = kwargs.get('data', None)
        conn.request(method, u.path, body=bod)

    except Exception as ex:
        # 'Client request exception:'
        return(992, ERRORS[992]+str(ex), None)

    try:
        r = conn.getresponse()
        emsg = r.read()
        conn.close()
        d = _httpresptodict(r)
        return(r.status, emsg, d)
    except Exception as ex:
        # 'Client request exception:'
        return(992, ERRORS[992]+str(ex), None)


# Convert http.client.HTTPResponse to dict
def _httpresptodict(r):
    if r == None:
        return {}
    d = vars(r)
    if 'msg' in d.keys():
        d['msg'] = str(r.msg)
    if 'headers' in d.keys():
        d['headers'] = str(r.headers)
    return d

