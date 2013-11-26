#! /usr/bin/env python
#coding: utf-8

"""
COPYRIGHT (c) 2009-2013

LICENSE
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import os
import sys
import platform
import optparse
import re
import unittest
import doctest
import time
import multiprocessing
import fnmatch
import functools

ON_PYTHON3 = sys.version_info[0] == 3
ON_WINDOWS = platform.system() == "Windows"


####
## Core
####

class Pytddmon:
    """The core class, all functionality is combined into this class"""

    def __init__(
            self,
            file_finder,
            monitor,
            project_name="<pytddmon>"
    ):
        self.file_finder = file_finder
        self.project_name = project_name
        self.monitor = monitor
        self.change_detected = False

        self.total_tests_run = 0
        self.total_tests_passed = 0
        self.last_test_run_time = -1
        self.log = ""
        self.status_message = 'n/a'

        self.run_tests()

    def run_tests(self):
        """Runs all tests and updates state variables with results."""

        file_paths = self.file_finder()

        # We need to run the tests in a separate process, since
        # Python caches loaded modules, and unittest/doctest
        # imports modules to run them.
        # However, we do not want to assume users' unit tests
        # are thread-safe, so we only run one test module at a
        # time, using processes = 1.
        start = time.time()
        if file_paths:
            pool = multiprocessing.Pool(processes=1)
            results = pool.map(run_tests_in_file, file_paths)
            pool.close()
            pool.join()
        else:
            results = []
        self.last_test_run_time = time.time() - start

        now = time.strftime("%H:%M:%S", time.localtime())
        self.log = ""
        self.log += "Monitoring folder %s.\n" % self.project_name
        self.log += "Found <TOTALTESTS> tests in %i files.\n" % len(results)
        self.log += "Last change detected at %s.\n" % now
        self.log += "Test run took %.2f seconds.\n" % self.last_test_run_time
        self.log += "\n"
        self.total_tests_passed = 0
        self.total_tests_run = 0
        module_logs = []  # Summary for each module with errors first
        for packed in results:
            (module, green, total, logtext) = packed
            self.total_tests_passed += green
            self.total_tests_run += total
            module_log = "\nLog from " + module + ":\n" + logtext
            if not isinstance(total, int) or total - green > 0:
                module_logs.insert(0, module_log)
            else:
                module_logs.append(module_log)
        self.log += ''.join(module_logs)
        self.log = self.log.replace('<TOTALTESTS>',
                                    str(int(self.total_tests_run.real)))
        self.status_message = now

    def get_and_set_change_detected(self):
        self.change_detected = self.monitor.look_for_changes()
        return self.change_detected

    def main(self):
        """This is the main loop body"""
        self.change_detected = self.monitor.look_for_changes()
        if self.change_detected:
            self.run_tests()

    def get_log(self):
        """Access the log string created during test run"""
        return self.log

    def get_status_message(self):
        """Return message in status bar"""
        return self.status_message


class Monitor:
    """Looks for file changes when prompted to"""

    def __init__(self, file_finder, get_file_size, get_file_modtime):
        self.file_finder = file_finder
        self.get_file_size = get_file_size
        self.get_file_modtime = get_file_modtime
        self.snapshot = self.get_snapshot()

    def get_snapshot(self):
        snapshot = {}
        for found_file in self.file_finder():
            file_size = self.get_file_size(found_file)
            file_modtime = self.get_file_modtime(found_file)
            snapshot[found_file] = (file_size, file_modtime)
        return snapshot

    def look_for_changes(self):
        new_snapshot = self.get_snapshot()
        change_detected = new_snapshot != self.snapshot
        self.snapshot = new_snapshot
        return change_detected


####
## Finding files
####

class FileFinder:
    """Returns all files matching given regular expression from root downwards"""

    def __init__(self, root, regexp):
        self.root = os.path.abspath(root)
        self.regexp = regexp

    def __call__(self):
        return self.find_files()

    def find_files(self):
        """recursively finds files matching regexp"""
        file_paths = set()
        for path, _folder, filenames in os.walk(self.root):
            for filename in filenames:
                if self.re_complete_match(filename):
                    file_paths.add(
                        os.path.abspath(os.path.join(path, filename))
                    )
        return file_paths

    def re_complete_match(self, string_to_match):
        """full string regexp check"""
        return bool(re.match(self.regexp + "$", string_to_match))


wildcard_to_regex = fnmatch.translate


####
## Finding & running tests
####

def log_exceptions(func):
    """Decorator that forwards the error message from an exception to the log
    slot of the return value, and also returns a complex number to signal that
    the result is an error."""
    wraps = functools.wraps

    @wraps(func)
    def wrapper(*a, **k):
        """Docstring"""
        try:
            return func(*a, **k)
        except:
            import traceback

            return 'Exception(%s)' % a[0], 0, 1j, traceback.format_exc()

    return wrapper


@log_exceptions
def run_tests_in_file(file_path):
    module = file_name_to_module("", file_path)
    return run_module(module)


def run_module(module):
    suite = find_tests_in_module(module)
    (green, total, log) = run_suite(suite)
    return module, green, total, log


def file_name_to_module(base_path, file_name):
    r"""Converts file_names of files in packages to import friendly dot
    separated paths.

    Examples:
    >>> print(file_name_to_module("","pytddmon.pyw"))
    pytddmon
    >>> print(file_name_to_module("","pytddmon.py"))
    pytddmon
    >>> print(file_name_to_module("","tests/pytddmon.py"))
    tests.pytddmon
    >>> print(file_name_to_module("","./tests/pytddmon.py"))
    tests.pytddmon
    >>> print(file_name_to_module("",".\\tests\\pytddmon.py"))
    tests.pytddmon
    >>> print(
    ...     file_name_to_module(
    ...         "/User/pytddmon\\ geek/pytddmon/",
    ...         "/User/pytddmon\\ geek/pytddmon/tests/pytddmon.py"
    ...     )
    ... )
    tests.pytddmon
    """
    symbol_stripped = os.path.relpath(file_name, base_path)
    for symbol in r"/\.":
        symbol_stripped = symbol_stripped.replace(symbol, " ")
    words = symbol_stripped.split()
    # remove .py/.pyw
    module_words = words[:-1]
    module_name = '.'.join(module_words)
    return module_name


def find_tests_in_module(module):
    suite = unittest.TestSuite()
    suite.addTests(find_unittests_in_module(module))
    suite.addTests(find_doctests_in_module(module))
    return suite


def find_unittests_in_module(module):
    test_loader = unittest.TestLoader()
    return test_loader.loadTestsFromName(module)


def find_doctests_in_module(module):
    try:
        return doctest.DocTestSuite(module, optionflags=doctest.ELLIPSIS)
    except ValueError:
        return unittest.TestSuite()


def run_suite(suite):
    def StringIO():
        if ON_PYTHON3:
            import io as StringIO
        else:
            import StringIO
        return StringIO.StringIO()

    err_log = StringIO()
    text_test_runner = unittest.TextTestRunner(stream=err_log, verbosity=1)
    result = text_test_runner.run(suite)
    green = result.testsRun - len(result.failures) - len(result.errors)
    total = result.testsRun
    log = err_log.getvalue() if green < total else "All %i tests passed\n" % green
    return green, total, log


####
## GUI
####

def import_tkinter():
    """imports tkinter from python 3.x or python 2.x"""
    if not ON_PYTHON3:
        import Tkinter as tkinter
    else:
        import tkinter
    return tkinter


def import_tkFont():
    """imports tkFont from python 3.x or python 2.x"""
    if not ON_PYTHON3:
        import tkFont
    else:
        from tkinter import font as tkFont
    return tkFont


class TKGUIButton(object):
    """Encapsulate the button(label)"""

    def __init__(self, tkinter, tkFont, toplevel, display_log_callback):
        self.font = tkFont.Font(name="Helvetica", size=28)
        self.label = tkinter.Label(
            toplevel,
            text="loading...",
            relief='raised',
            font=self.font,
            justify=tkinter.CENTER,
            anchor=tkinter.CENTER
        )
        self.bind_click(display_log_callback)
        self.pack()

    def bind_click(self, display_log_callback):
        """Binds the left mouse button click event to trigger the log_windows
        display method"""
        self.label.bind(
            '<Button-1>',
            display_log_callback
        )

    def pack(self):
        """packs the label"""
        self.label.pack(
            expand=1,
            fill='both'
        )

    def update(self, text, color):
        """updates the color and displayed text."""
        self.label.configure(
            bg=color,
            activebackground=color,
            text=text
        )


class TkGUI(object):
    """Connect pytddmon engine to Tkinter GUI toolkit"""

    def __init__(self, pytddmon, tkinter, tkFont):
        self.pytddmon = pytddmon
        self.tkinter = tkinter
        self.tkFont = tkFont
        self.color_picker = ColorPicker()
        self.root = None
        self.building_root()
        self.title_font = None
        self.building_fonts()
        self.frame = None
        self.building_frame()
        self.button = TKGUIButton(
            tkinter,
            tkFont,
            self.frame,
            self.display_log_message
        )
        self.status_bar = None
        self.building_status_bar()
        self.frame.grid()
        self.message_window = None
        self.text = None

        if ON_WINDOWS:
            buttons_width = 25
        else:
            buttons_width = 75
        self.root.minsize(
            width=self.title_font.measure(
                self.pytddmon.project_name
            ) + buttons_width,
            height=0
        )
        self.frame.pack(expand=1, fill="both")
        self.create_text_window()
        self.update_text_window()

    def building_root(self):
        """take hold of the tk root object as self.root"""
        self.root = self.tkinter.Tk()
        self.root.wm_attributes("-topmost", 1)
        if ON_WINDOWS:
            self.root.attributes("-toolwindow", 1)
            print("Minimize me!")

    def building_fonts(self):
        """building fonts"""
        self.title_font = self.tkFont.nametofont("TkCaptionFont")

    def building_frame(self):
        """Creates a frame and assigns it to self.frame"""
        # Calculate the width of the tilte + buttons
        self.frame = self.tkinter.Frame(
            self.root
        )
        # Sets the title of the gui
        self.frame.master.title(self.pytddmon.project_name)
        # Forces the window to not be resizeable
        self.frame.master.resizable(False, False)
        self.frame.pack(expand=1, fill="both")

    def building_status_bar(self):
        """Add status bar and assign it to self.status_bar"""
        self.status_bar = self.tkinter.Label(
            self.frame,
            text="n/a"
        )
        self.status_bar.pack(expand=1, fill="both")

    def _update_and_get_color(self):
        """Calculate the current color and trigger pulse"""
        self.color_picker.set_result(
            self.pytddmon.total_tests_passed,
            self.pytddmon.total_tests_run,
        )
        light, color = self.color_picker.pick()
        rgb = self.color_picker.translate_color(light, color)
        self.color_picker.pulse()
        return rgb

    def _get_text(self):
        """Calculates the text to show the user(passed/total or Error!)"""
        if self.pytddmon.total_tests_run.imag != 0:
            text = "?ERROR"
        else:
            text = "%r/%r" % (
                self.pytddmon.total_tests_passed,
                self.pytddmon.total_tests_run
            )
        return text

    def update(self):
        """updates the tk gui"""
        rgb = self._update_and_get_color()
        text = self._get_text()
        self.button.update(text, rgb)
        self.root.configure(bg=rgb)
        self.update_status(self.pytddmon.get_status_message())

        if self.pytddmon.change_detected:
            self.update_text_window()

    def update_status(self, message):
        self.status_bar.configure(
            text=message
        )
        self.status_bar.update_idletasks()

    def get_text_message(self):
        """returns the log message from pytddmon"""
        message = self.pytddmon.get_log()
        return message

    def create_text_window(self):
        """creates new window and text widget"""
        win = self.tkinter.Toplevel()
        if ON_WINDOWS:
            win.attributes("-toolwindow", 1)
        win.title('Details')
        self.message_window = win
        self.text = self.tkinter.Text(win)
        self.message_window.withdraw()

    def update_text_window(self):
        """inserts/replaces the log message in the text widget"""
        text = self.text
        text['state'] = self.tkinter.NORMAL
        text.delete(1.0, self.tkinter.END)
        text.insert(self.tkinter.INSERT, self.get_text_message())
        text['state'] = self.tkinter.DISABLED
        text.pack(expand=1, fill='both')
        text.focus_set()

    def display_log_message(self, _arg):
        """displays/close the log message from pytddmon in a window"""
        if self.message_window.state() == 'normal':
            self.message_window.state('iconic')
        else:
            self.message_window.state('normal')

    def loop(self):
        """the main loop"""
        if self.pytddmon.get_and_set_change_detected():
            self.update_status('Testing...')
            self.pytddmon.run_tests()
        self.update()
        self.frame.after(750, self.loop)

    def run(self):
        """starts the main loop and goes into sleep"""
        self.loop()
        self.root.mainloop()


class ColorPicker:
    """
    ColorPicker decides the background color the pytddmon window,
    based on the number of green tests, and the total number of
    tests. Also, there is a "pulse" (light color, dark color),
    to increase the feeling of continuous testing.
    """
    color_table = {
        (True, 'green'): '0f0',
        (False, 'green'): '0c0',
        (True, 'red'): 'f00',
        (False, 'red'): 'c00',
        (True, 'orange'): 'fc0',
        (False, 'orange'): 'ca0',
        (True, 'gray'): '999',
        (False, 'gray'): '555'
    }

    def __init__(self):
        self.color = 'green'
        self.light = True

    def pick(self):
        """returns the tuple (light, color) with the types(bool ,str)"""
        return self.light, self.color

    def pulse(self):
        """updates the light state"""
        self.light = not self.light

    def reset_pulse(self):
        """resets the light state"""
        self.light = True

    def set_result(self, green, total):
        """calculates what color should be used and may reset the lightness"""
        old_color = self.color
        self.color = 'green'
        if green.imag or total.imag:
            self.color = "orange"
        elif green == total - 1:
            self.color = 'red'
        elif green < total - 1:
            self.color = 'gray'
        if self.color != old_color:
            self.reset_pulse()

    @classmethod
    def translate_color(cls, light, color):
        """helper method to create a rgb string"""
        return "#" + cls.color_table[(light, color)]


def parse_commandline():
    """
    returns (files, test_mode) created from the command line arguments
    passed to pytddmon.
    """
    parser = optparse.OptionParser()
    parser.add_option(
        "--log-and-exit",
        action="store_true",
        default=False,
        help='Run all tests, write the results to "pytddmon.log" and exit.')
    parser.add_option(
        "--log-path",
        help='Instead of writing to "pytddmon.log" in --log-and-exit, write to LOG_PATH instead.')
    parser.add_option(
        "--stdout",
        action='store_true',
        default=False,
        help='Instead of writing to "pytddmon.log" in --log-and-exit, output to stdout instead.')
    (options, args) = parser.parse_args()
    return args, options.log_and_exit, options.log_path, options.stdout


def build_monitor(file_finder):
    os.stat_float_times(False)

    def get_file_size(file_path):
        stat = os.stat(file_path)
        return stat.st_size

    def get_file_modtime(file_path):
        stat = os.stat(file_path)
        return stat.st_mtime

    return Monitor(file_finder, get_file_size, get_file_modtime)


def run():
    """
    The main function: basic initialization and program start
    """
    cwd = os.getcwd()

    # Include current work directory in Python path
    sys.path[:0] = [cwd]

    # Command line argument handling
    (static_file_set, test_mode, test_output, stdout) = parse_commandline()

    # What files to monitor?
    if not static_file_set:
        regex = wildcard_to_regex("*.py")
    else:
        regex = '|'.join(static_file_set)
    file_finder = FileFinder(cwd, regex)

    # The change detector: Monitor
    monitor = build_monitor(file_finder)

    # Python engine ready to be setup
    pytddmon = Pytddmon(
        file_finder,
        monitor,
        project_name=os.path.basename(cwd)
    )

    # Start the engine!
    if not test_mode:
        TkGUI(pytddmon, import_tkinter(), import_tkFont()).run()
    else:
        pytddmon.main()
        result = "green=%r\ntotal=%r\n" % (
            pytddmon.total_tests_passed,
            pytddmon.total_tests_run)

        if stdout:
            outputfile = sys.stdout
        else:
            outputfile = open(test_output or 'pytddmon.log', 'w')
        with outputfile as log_file:
            log_file.write(result)


if __name__ == '__main__':
    run()
