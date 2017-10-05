# coding: utf8
from __future__ import unicode_literals

from core import Program, MatchConfig

import os
import sys
import json
import regex as re
import traceback

import operator
from pprint import pprint
from collections import Counter

def topoccurrences(captures, patternname, maxitem=5):
    ''' Return top n occurrences of pattern name

    :param captures: pattern captures
    :type captures: list
    :param pattername: pattern name
    :type patternname: str
    :param maxitem: max item. default top 5
    :type maxitem: int
    :returns: top n occurrences
    :rType: list of tuple (item, occurrence percent, occurence count)

    # Top 2 occurrences of PYTHON_ERROR
    >>> topoccurrences(captures, {'%{PYTHON_ERROR}':'PYTHON_ERROR'}, 2)
    >>> [("RuntimeError: Unknown error when initializing Maya", 0.18281535648994515, 1),
    >>>  ("AttributeError: 'module' object has no attribute 'addtoshelf'", 99.81718464351006, 546)],
    '''
    counter = Counter([json.loads(capt[1]).get(patternname) for capt in captures])

    topfivecount = dict(sorted(counter.iteritems(),
        key=operator.itemgetter(1), reverse=True)[:maxitem])

    stats = [(i, topfivecount[i] / float(len(captures)) * 100.0, topfivecount[i])\
            for i in topfivecount]

    return stats

def saveoutput(result, path):
    ''' Save log analyze output result in file

    :param result: program analyze results
    :type results: dict
    :param path: output path
    :type path: str
    :returns: output path
    :rType: str
    '''
    data = json.dumps(result, sort_keys=True,
            indent=4, separators=(',', ': '))

    with open(path, 'w') as f:
        f.write(data)

    return path

def programanalyze(program, toppatterns=None):
    ''' Analyze program captures

    :param program: program to analyze
    :type program: `log.parser.core.Program`
    :param toppatterns: top occurrences patterns
    :type toppatterns: dict
    '''
    captures = program.getcaptures()
    toppatterns = toppatterns or {}

    result = {'total' : program.nbinputs()}

    for key in captures.keys() :
        patterncaptures = captures.get(key)
        inputs = [i for (i, capt) in patterncaptures]
        matches = [capt for (i, capt) in patterncaptures]
        patternresult = { 'total' : len(patterncaptures),
                          'inputs' : inputs,
                          'captures' : matches }

        if key in toppatterns :
            topfive = topoccurrences(patterncaptures, toppatterns.get(key))
            patternresult.update({'topfive' : topfive })
        result.update({ key : patternresult})

    return result

def run(patterns=None, matches=None, config=None, root=None, logfile=None, action=None, output=None, verbose=False):
    ''' Run program analyze with specific config
        on a list of logfiles

    :param config: program config file to use
    :type config: str
    :param root: log files root
    :type root: str
    :param output: save output analyze as file
    :type ouput: str
    :param verbose: Turn on verbose
    :type verbose: bool
    '''
    logfiles = []

    if logfile is not None :
        logfiles = [logfile]
    else :
        logfiles = sorted([ os.path.join(root, f) for f in os.listdir(root) \
                if os.path.isfile(os.path.join(root, f))])

    if verbose :
        print '------ (%d) files to analyze' % len(logfiles)

    # grok pattern name defined in library
    # ex : WORD, PATH, ...
    if patterns is not None:
        matchconfig = MatchConfig(['%{'+p+'}' for p in patterns],
                        shell=action if action is not None else 'stdout',
                        action=action if action is not None else '%{@LINE}')
        logparser = Program([matchconfig])

    # match can be regex or/and grok patterns
    # ex : DATE : %{DATE}[- ]%{HOUR}:%{MINUTE}
    elif matches is not None :
        matchconfig = MatchConfig(matches,
                        shell=action if action else 'stdout',
                        action=action if action is not None else '%{@LINE}')
        logparser = Program([matchconfig])

    # Use match config file
    elif config is not None:
        logparser = Program.load(config)
    else :
        return

    for logfile in logfiles :
        if verbose :
            print '------ analyze %s' % logfile

        logparser.addinputfile(logfile)

    result = programanalyze(logparser, toppatterns={'%{PYTHON_ERROR}':'PYTHON_ERROR'})

    if output is not None :
        path = saveoutput(result, output)
        if verbose :
            print 'output saved as %s' % path

    if verbose:
        print(json.dumps(result, indent=4))

def main():
    '''
        .. note::

            * logparser command line

    # save analyze as ouytput file
    >>> logparser -r /studio/code/packages/coalition/latest/src/logs -v -o '/tmp/analyze.log'

    # echo @MATCH and @LINE for each GUERILLA_ERROR pattern match
    >>> logparser -r /studio/code/packages/coalition/latest/src/logs -p GUERILLA_ERROR -a 'echo Found %{@MATCH} in %{@LINE}'

    # echo @PATTERNS for each PYTHON_ERROR pattern match
    >>> logparser -r /studio/code/packages/coalition/latest/src/logs -p PYTHON_ERROR -a 'echo %{@PATTERNS}'

    # echo @MATCH and @LINE for each match DATE : %{DATE}[- ]%{HOUR}:%{MINUTE}
    >>> logparser -r /studio/code/packages/coalition/latest/src/logs -m "DATE : %{DATE}[- ]%{HOUR}:%{MINUTE}" -a 'echo Found %{@MATCH} in %{@LINE}'

    # echo @MATCH and @LINE for each PYTHON_ERROR which startswith AttributeError
    >>> logparser -m '%{PYTHON_ERROR =~ /^AttributeError/}' -a 'echo Found %{@MATCH} in %{@LINE}'

    # echo @MATCH and @LINE for each PYTHON_ERROR wich contains userSetup.py
    >>> logparser -m '%{PYTHON_TRACEBACK_ERROR =~ /userSetup.py/}' -a 'echo Found %{@MATCH} in %{@LINE}'

    # echo @PATTERNS for each REZ_PACKAGE_VERSION == REZ_ONMAYAUTILS_VERSION=0.1.126
    >>> logparser -m '%{REZ_PACKAGE_VERSION $== REZ_ONMAYAUTILS_VERSION=0.1.126}' -a 'echo %{@PATTERNS}'

    # echo @PATTERNS for each source file ending with .env or each REZ_PACKAGE_VERSION matching REZ_GITLABUTILS_VERSION=0.0.17
    >>> logparser -m 'source %{PATH =~ /.env$/}' '%{REZ_PACKAGE_VERSION $== REZ_GITLABUTILS_VERSION=0.0.17}' -a 'echo %{@PATTERNS}'

    # execute updatejobenv %{@INPUT} on each job with dispatcher-dev in REZ_USED_RESOLVE
    >>> logparser -m '%{REZ_USED_RESOLVE =~ /dispatcher-dev/}' -r /studio/code/packages/coalition/latest/src/logs -a 'updatejobenv -l %{@INPUT}'

    # apply shellescape filter on %{@PATTERNS} captured data
    >>> logparser -m '%{DATE}[- ]%{HOUR}:%{MINUTE}' -a 'python -c "print(\"Result is : \" + %{@PATTERNS|shellescape})"'

    # apply jsonencode filter on %{@JSON} capture data
    >>> logparser -m '%{DATE}[- ]%{HOUR}:%{MINUTE}' -a 'python -c "print(\"Result is : \" + %{@JSON|jsonencode})"'
    '''

    import argparse
    parser = argparse.ArgumentParser(   description="logparser command line",
                                        formatter_class=argparse.ArgumentDefaultsHelpFormatter)


    parser.add_argument("-c", "--config", dest="config", default=os.environ.get('DEFAULT_CONFIG_FILE'), type=str,
            help="Specify config file to use arg --config /../configs/pythonprogram.config")

    parser.add_argument("-p", "--patterns", dest="patterns", type=str, nargs="*",
            help="Specify pattern names --patterns PYTHON_ERROR")

    parser.add_argument("-m", "--matches", dest="matches", type=str, nargs="*",
            help="Specify matches --matches 'Date : %%{DATE}[- ]%%{HOUR}:%%{MINUTE}'")

    parser.add_argument("-a", "--action", dest="action", type=str,
            help="Perform specific action on match --action %%{@JSON} or %%{@MATCH} or %%{@LINE}")

    parser.add_argument("-r", "--root", dest="root", default=None, type=str,
            help="Specify root directory to analyze log files arg --root /../logs")
    parser.add_argument("-f", "--logfile", dest="logfile", type=str,
            help="Specify a log file to analyze --file /../logs/1234.log")
    parser.add_argument("-v", "--verbose", dest="verbose", action="store_true",
            help="Turns on verbose output")
    parser.add_argument("-o", "--output", dest="output", type=str,
            help="Save as output file report")

    args = parser.parse_args()
    run(**vars(args))

if __name__ == '__main__':
    try :
        main()
    except Exception, e :
        (exctype, excval, exctb) = sys.exc_info()
        msg = traceback.format_exception(exctype, excval, exctb)
        pprint(msg)
        exit(1)
