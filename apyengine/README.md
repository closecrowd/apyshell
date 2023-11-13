# apyengine
	Version 1.0

ApyEngine is an interpreter for a Python-subset language, written in Python3.  It's easily embedded in a Python application, and provides a means to add safe scripting.  It great for education - teaching programming concepts in a secure environment.  Or giving the users of your application the ability to write their own scripts, without introducing security issues.

At it's heart is a fork and extension of <b>asteval</b>  by Matt Newville  [GitHub](https://github.com/newville/asteval), with many, many new features and abilities.  
        
Some of the major features:

-  Familiar - Python syntax, easy to learn.
- Embeddable - It's easy to run scripts from your application, and interact  with the script's environment.
- Extensible - Add-on modules provide extra features as needed.  And it's easy to  create your own modules.
- Powerful - Most of the core Python 3 functionality, with easy multi-threading support.
- Secure - The host application determines which modules and extensions are available to the scripts.  Scripts can not break out and compromise the host system.
        
There are some major differences from standard Python.  Scripts can not import Python modules, and can not define classes (as of Version 1).  Any Python function that would allow a script to affect the host system is blocked or re-defined.

Python elements that are **not** allowed include:

import, eval, exec, getattr, lambda, class, global, yield, Generators,  Decorators

among others.
         
The documentation in the GitHub project has more details [here](https://github.com/closecrowd/apyengine)

It currently runs on Linux, and tested with Python 3.5 to 3.9.  Ports to Android, Windows, and MacOS are underway.


### History

The seeds of this project started a few years ago.  I had written an Android application for cellular engineers that performed a variety of network tests, and logged the results.  It worked well, but adding new test functionality meant re-releasing the app, which became tiresome.

I wanted to give the RF engineers the ability to add new tests, and maybe create their own.  That meant a scripting language, easy to code in, and with support for their specific needs.  And it had to be safe, so a rogue or defective script could not compromise the test devices.

I could have created a new scripting language, but I picked Python for it's flexibility and vast training resources.  The .apy language ***is*** Python, just restricted.

The original prototype of the new app was written in Python 2,7, using Kivy as it's UI on Android.  It worked, but was pretty primitive compared to the current version.

The project ran it's source, and the app was retired.  I took the basic concepts, rewrote the entire codebase from scratch in Python 3, and began using it my own networks.  The engine is embedded in my apyshell framework, and has been running system management and Home Automation tasks for a few years now.

### Installation

The setup.py installer isn't fully tested yet.  So for right now, grab the .py files from this repo, and put them in an "apyengine" directory under your main application.

### Running

The simplest invocation of the engine would look something like this:

```python
import apyengine

# create the scripting engine
engine = apyengine.ApyEngine()

# load and run the primary script
engine.loadScript_("myscriptname")
```

This runs a script named "myscriptname.apy" in the current directory.    You can perform actions like setting variables before the script is run:

```python
# pass in the name of this machine
engine.setSysVar_('hostname',  platform.node())
```

See the documentation for the full list of API commands.

### Example

Here's a very simple example of the core syntax.  This doesn't use any of the add-on extensions or features.  In fact, it'll execute under regular Python as well:

```python
def primes_sieve(limit):

    limitn = limit + 1
    primes = list(range(2, limitn))

    for i in primes:
        factors = list(range(i, limitn, i))

        for f in factors[1:]:
            if f in primes:
                primes.remove(f)

    return primes


p = primes_sieve(20000)
print(p)
```

