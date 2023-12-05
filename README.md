# apyshell
		Version 1.0

ApyShell is a host for the embedded interpreter apyengine.  It sets up the environment for the engine, specifying directory paths and available features.  It also manages the extension modules, loading and unloading them as needed by the scripts.

You can use this program from the command line to run .apy scripts in a safe(r) environment.  You can also embed apyshell in your own application, to add powerful scripting capabilities.

What's it good for? Anywhere you want to use the full power of Python scripts, yet tightly limit what the scripts can do.  Uses include:

- Games: Embed a full-featured scripting language in your game, and add custom extensions to make it easy control the game.  This project was initially conceived as a tool-scripting language.

- Educational: Students can learn coding in a simplified version of Python, but still create complex applications.  And without being able to damage the host system (accidentally or otherwise).  They can only use the Python functionality that you allow, even if regular Python modules are installed.

- Rapid tool development:  I use apyshell scripts running as daemons to do many monitoring and control functions in my networks.  With the right extensions available, it's pretty easy to do things like IOT control.

- Functional prototyping: With custom extensions simulating various subsystems, a functional prototype can be put together and re-arranged quickly.  You can work out the structure and flow of your appplication *before* it's set in stone, and costly to alter.


It's pretty easy to hook together extensions talking to various systems and protocols, with far less glue logic than bare Python.  It's similar to the way that a document template processor combines a small amount of text with a large boilerplate.  An .apy script may be very few lines, yet have the same funcionality as pages and pages of raw Python.  Most of the complexity is hidden in the loadable extensions.

Apyshell is like school spring break - lots of fun, and no classes!


This code is currently being developed on Linux, and tested on Python 3.5.4 to 3.11.6.  Ports to Windows, Android, and MacOS are in progress.

The code is fully functional, and the documentation is in process.  Expect updates.  Suggestions are always welcome at:  **closecrowd@pm.me**

### Installation

Before you install apyshell, you’ll need to download and install “**apyengine**”.  Clone that project from [GitHub](https://github.com/closecrowd/apyengine) into a local directory. Change to the directory, and run “pip install .” to install the engine core. 

Next, clone the **apyshell** project from [GitHub](https://github.com/closecrowd/apyshell) into a local directory.  Make any changes that you need to apyshell.py – particularly the default directory paths and extension options.  Then copy the entire directory tree to your desired location.  I use “/opt/apyshell” by default, but you may change the paths.

The default directories for scripts and extension files in apyshell.py are: 

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
    -o, --extensionopts A list of options key:value pairs to pass to extensions
    -p, --pidfile       A file with the shell's current PID
    -g, --global        All script variables are global
    -v, --verbose       Debug output

So to run a script named 'demo.apy' from the distribution directory, you would enter:

    ./apyshell.py demo -b ./scripts -e ./extensions

Apyshell will exit when the the script reaches it's end, or it gets a SIGINT or SIGTERM from the O/S.  A ^c will cleanly shutdown the system and end the script.

If you have the scripts and extensions directories under the default '/opt/apyshell/' location, then you don't need any options.  just:

    /opt/apyshell/apyshell.py demo

### Modules

Sometimes, you need some functionality that doesn't fit well into the Extension format.  Apyshell scripts can call for certain selected Pythons modules to be installed directly into the engine.  These modules add new commands directly into the symbol table.

Modules currently available are:

- numpy
- time
- json
- base64

Your script installs a module by using the "install_()" command.  For instance, to make Python's time module available:

	install_('time')

and your script will now have access to the time functions.  Once a module is installed, is stays available until apyshell exits.  There is no "unstall_()".

One thing to note: The functions are from Python, but the names have been changed slightly to fit into apyengine's scheme.  For instance, **asctime() ** is changed to **asctime_()**.  Functionality is unchanged - only the names.

A full list of module function names will be in the Apyshell Programming Manual.

### Extensions

Extensions provide advanced features to your scripts, while keeping things safe and simple.  The selection of extensions available to scripts is controlled by the **extensiondir**  option.  

Extensions are added with the "loadExtension_()" command.   For example:

	r = loadExtension_('mqttext')

If **r** is True, the extension is loaded and it's functions are available to the scripts.  Unlike Modules, there is a corresponding "unloadExtension_()" command to remove the extension.

There are many extensions in development.  They'll be added to the GitHub repo as quickly as their documentation and sample scripts can be updated.

Currently available are:

- mqttext - A full-featured MQTT client

- redisext - A Redis cache client

- sqliteext - Manage Sqlite3 databases

- queueext - A utility extension providing thread-safe queues (FIFO and LIFO)

- fileext - Simple path-restricted text file operations

- utilext - A utility extension with several useful functions


There are many more completed or in development.  They will be published to the GitHub repo as soon as their documentation is finished.

