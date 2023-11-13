# apyshell
		Version 1.0

ApyShell is a host for the embedded interpreter apyengine.  It sets up the environment for the engine, specifying directory paths and available features.  It also manages the extension modules, loading and unloading them as needed by the scripts.

You can use this program from the command line to run .apy scripts in a safe(r) environment.  You can also embed apyshell in your own application, to add powerful scripting capabilities.

What's it good for? Anywhere you want to use the full power of Python scripts, yet tightly limit what the scripts can do.  Uses include:

- Games: Embed a full-featured scripting language in your game, and add custom extensions to make it easy control the game.  This project was initially conceived as a tool-scripting language.

- Educational: Students can learn coding in a simplified version of Python, but still create complex applications.  And without being able to damage the host system (accidentally or otherwise).  They can only use the Python functionality that you allow, even if regular Python modules are installed.

- Rapid tool development:  I use apyshell scripts running as daemons to do many monitoring and control functions in my networks.  With the right extensions available, it's pretty easy to do things like IOT control.

It's pretty easy to hook together extensions talking to various systems and protocols, with far less glue logic than bare Python.  It's similar to the way that a document template processor combines a small amount of text with a large boilerplate.  An .apy script may be very few lines, yet have the same funcionality as pages and pages of raw Python.  Most of the complexity is hidden in the loadable extensions.


This code is currently being developed on Linux, and tested on Python 3.5.4 to 3.11.6.  Ports to Windows, Android, and MacOS are in progress.

The code is fully functional, and the documentation is in process.  Expect updates.  Suggestions are always welcome at:  closecrowd@pm.me

### Installation

Until the setup.py installer is finished, just grab the files from GitHub into a local directory.  

The default directories for scripts and extension files are set in apyshell.py:

~~~python
# default directory paths
basedir = '/opt/apyshell/scripts'           # script base directory
extensiondir = '/opt/apyshell/extensions'   # entension base dir
~~~

You can override these when launching the program.

These paths are a key piece of the security mechanism.  Scripts may only be run from the basedir (or subdirs below it), and only extensions present in the extensiondir directory are available to the scripts.  You can control which extensions your scripts can use by controlling the contents of this directory.

### Running scripts

You can see a list of the command-line arguments like this:

    ./apyshell.py -h

    apyshell.py script [ options ]

    script              The script file to execute (required). The .apy is optional

    -h, --help          This message
    -a, --args          Optional agrument string to pass to the script
    -i, --initscript    A script to execute before the specified script
    -b, --basedir       Base directory for scripts (use , for multiple paths)
    -e, --extensiondir  Base directory for extensions (use , for multiple paths)
    -p, --pidfile       A file with the shell's current PID
    -g, --global        All script variables are global
    -v, --verbose       Debug output

So to run a script named 'demo.apy' from the distribution directory, you would enter:

    ./apyshell.py demo -b ./scripts -e ./extensions

Apyshell will exit when the the script reaches it's end, or it gets a SIGINT or SIGTERM from the O/S.  A ^c will cleanly shutdown the system and end the script.

If you have the scripts and extensions directories under the default '/opt/apyshell/' location, then you don't need any options.  just:

    ./apyshell.py demo

