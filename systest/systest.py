#! /usr/bin/env python
#coding: utf-8
import os
import subprocess
from optparse import OptionParser

def get_log_as_dictionary(path):
    f = open(path, 'r')
    rows = f.readlines()
    f.close()
    return get_dictionary(rows)

def get_output_as_dictionary(output):
    rows = output.split('\n')
    return get_dictionary(rows)

def get_dictionary(rows):
    dict = {}
    for row in rows:
        (name, splitter, value) = row.partition('=')
        dict[name] = value.strip()
    return dict

def get_log(testdir, logname):
    fullpath = os.path.join(testdir, logname)
    return get_log_as_dictionary(fullpath)

def pretty_please(testdir):
    testdir = testdir.replace('\\', '/')
    testdir = testdir.split('/')[-1]
    testdir = testdir.replace('_', ' ')
    testdir = testdir.title()
    return testdir

def compare(testdir, what, gotdict, expdict):
    got = gotdict[what]
    exp = expdict[what]
    pretty = pretty_please(testdir)
    if got != exp:
        print(pretty + ": expected " + exp + " " + what + " test(s), got " + got)

def compare_logs(testdir, got, exp):
    compare(testdir, 'green', got, exp)
    compare(testdir, 'total', got, exp)

def compare_logs_in_dir(testdir, output=None):
    if output:
        gotinfo = get_output_as_dictionary(output)
    else:
        gotinfo = get_log(testdir, "pytddmon.log")
    expinfo = get_log(testdir, "expected.log")
    compare_logs(testdir, gotinfo, expinfo)

def get_args(path):
    argspath = os.path.join(path, "args.txt")
    if not os.path.exists(argspath):
        return []
    f = open(argspath, "r")
    content = f.read().strip()
    f.close()
    return content.split()

def run_all():
    output = None
    clean_test = parse_commandline()
    cwd = os.getcwd()
    pytddmon_path = os.path.join(cwd, "../src/pytddmon.py")
    names = os.listdir(cwd)
    for name in names:
        path = os.path.join(cwd, name)
        if os.path.isdir(path):
            os.chdir(path)
            cmdline = ['python', pytddmon_path, "--log-and-exit"]
            if clean_test:
                cmdline.append('--stdout')
            args = get_args(path)
            cmdline.extend(args)
            try:
                output = subprocess.check_output(cmdline)
            except:
                print(" .. in test: " + path + "\n")
            if not clean_test:
                output = None
            compare_logs_in_dir(path, output)

    os.chdir(cwd)

def touch(fname, times=None):
    with file(fname, 'a'):
        os.utime(fname, times)

def parse_commandline():
    parser = OptionParser()
    parser.add_option('-c', '--clean-tests',
                      action='store_true',
                      default=False,
                      help='Do not write any output files')
    (options, args) = parser.parse_args()
    return options.clean_tests

if __name__ == "__main__":
    run_all()
