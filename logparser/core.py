# coding: utf8
from __future__ import unicode_literals

import os
import sys
import json
import shlex
import subprocess
import operator
import mmap
import regex as re
from pipes import quote
from pprint import pprint
from collections import namedtuple

# Pattern for capturing named grok keys
# name, pattern, optional subname and predicate
# pattern to match : %{FOO:foo <= 45}
# PATTERN_REGEX = re.compile(r'%{(?P<name>(?P<pattern>[A-z0-9]+)(?::(?P<subname>[A-z0-9_:]+))?)}')

# Full Grok pattern from https://github.com/jordansissel/grok
PATTERN_REGEX = re.compile(r"(?!<\\)%{" \
  "(?<name>" \
    "(?<pattern>[A-z0-9]+)" \
    "(?::(?<subname>[A-z0-9_:]+))?" \
  ")" \
#  "(?:=" \
#    "(?<definition>" \
#      "(?:" \
#        "(?P<curly2>{(?:(?>[^{}]+|(?>\\[{}])+)|(?P>curly2))*})+" \
#        "|" \
#        "(?:[^{}]+|\\[{}])+" \
#      ")+" \
#    ")" \
#  ")?" \
  "\s*(?<predicate>" \
    "(?:" \
      "(?P<curly>{(?:(?>[^{}]+|(?>\\[{}])+)|(?P>curly))*})" \
      "|" \
      "(?:[^{}]+|\\[{}])+" \
    ")+" \
  ")?" \
  "}")

REGEXP_PREDICATE_RE = re.compile(r'(?:\s*([!=])~\s*(.)([^\/]+|(?:\/)+)*)(?:\2)')
REGEXP_PREDICATE_OP = re.compile(r'(?:\s*)([$!~=<>]{1,3})(?:\s*)')

# The line matched
VALUE_LINE = 0
# The substring matched
VALUE_MATCH = 1
# The starting position of the
# match from the beginning of the string
VALUE_START = 2
# The ending position of the match
VALUE_END = 3
# The length of the match
VALUE_LENGTH = 4
# All patterns captured as dict
VALUE_PATTERNS = 5
# Input file/process name
VALUE_INPUT=6
# full set of patterns encoded as json dict
# as { pattern : [list of captures]}
VALUE_JSON_SIMPLE = 7
# Similar to json, but includes start and end position
# for every named pattern
VALUE_JSON_COMPLEX = 8
MACRO_TYPES = ( VALUE_LINE, VALUE_MATCH,
                VALUE_START, VALUE_END, VALUE_LENGTH,
                VALUE_PATTERNS, VALUE_INPUT,
                VALUE_JSON_SIMPLE, VALUE_JSON_COMPLEX)

GrokPattern = namedtuple('GrokPattern', 'name regexp predicate')
GrokPattern.__new__.__defaults__ = (None, None, None)
GrokPredicateNum = namedtuple('GrokPredicateNum', 'op value vtype')
GrokPredicateStr = namedtuple('GrokPredicateStr', 'op value')
GrokPredicateRegex = namedtuple('GrokPredicateRegex', 'pattern negative_match')

def getpatternmacrotypes():
    ''' Return pattern macro types

    :returns: pattern macro type
    :rType: dict
    '''
    macrotypes = {
        '@LINE' : VALUE_LINE,
        '@MATCH' : VALUE_MATCH,
        '@JSON_COMPLEX' : VALUE_JSON_COMPLEX,
        '@JSON' : VALUE_JSON_SIMPLE,
        '@START' : VALUE_START,
        '@END' : VALUE_END,
        '@LENGTH' : VALUE_LENGTH,
        '@PATTERNS' : VALUE_PATTERNS,
        '@INPUT' : VALUE_INPUT,
    }
    return macrotypes

def patternnametomacrotype(pattern):
    ''' Return macro type for given pattern name

    :param pattern: pattern name
    :type pattern: str
    :returns: macro
    :rType: str
    '''
    macrotypes = getpatternmacrotypes()
    return macrotypes.get(pattern)


class Grok(object):
    ''' Grok class

        Class which lets you build (or use existing) sets
        named regular expressions and then helps you
        use them match stings

    '''
    def __init__(self):

        # original pattern
        self.__pattern = None

        # full expanded pattern generated with compile()
        self.__expandpattern = None

        # patterns library
        self.__patterns = dict()

        self.loadpatterns()

    @property
    def pattern(self):
        ''' Original grok pattern

        '''
        return self.__pattern

    @property
    def expandpattern(self):
        ''' Grok pattern with all regex substitued

        '''
        return self.__expandpattern

    def _strtoperator(self, strop):
        ''' String to operator

        :param strop: string operator
        :type strop: str
        :returns: operator
        :rType: python operator
        '''
        _opmapping = {
            '<'  : operator.lt,
            '>'  : operator.gt,
            '>=' : operator.ge,
            '<=' : operator.le,
            '==' : operator.eq,
            '!=' : operator.ne,
        }
        return _opmapping.get(strop)

    def _predicate_numcompare(self, op, value):
        ''' Return numeric predicate comparaison

        :param op: operator
        :type op: str
        :param value: value to compare
        :type value:str
        :returns: numeric predicate
        :rType: `GrokPredicateNum`
        '''
        # assume is float
        if '.' in value :
            return GrokPredicateNum(op=self._strtoperator(op),
                    value=float(value),
                    vtype=float)
        else :
            return GrokPredicateNum(op=self._strtoperator(op),
                    value=int(value),
                    vtype=int)

    def _predicate_strcompare(self, op, value):
        ''' Return string predicate comparaison

        :param op: operator
        :type op: str
        :param value: value to compare
        :type value:str
        :returns: string predicate
        :rType: `GrokPredicateStr`
        '''
        return GrokPredicateStr(op=self._strtoperator(op),
                    value=value)

    def _predicate_regex(self, predicate):
        ''' Return regex predicate comparaison

        ..note::
            * regex comparaison syntax is =~ /regex/ or !~ /regex/
            ex : =~ /^abc/ equals to re.search('^abc', value)

        :param predicate: predicate
        :type predicate: str
        :returns: regex predicate
        :rType: `GrokPredicateRegex`
        '''
        match = REGEXP_PREDICATE_RE.search(predicate)

        if not match or len(match.groups()) != 3:
            return

        substring = match.string[match.regs[-2][1]:match.regs[-1][1]]
        pattern = re.compile(substring)

        negative_match = True if match.group(1) == '!' else False

        return GrokPredicateRegex(pattern=pattern,
                negative_match=negative_match)


    def _addpredicate(self, pattern,  predicate):
        ''' Add predicate to `GrokPattern`

        .. note::
            * numerical comparaison predicates : > < <= >= == !=
            * string comparaison predicates : $> $< $<= $>= $== $!=
            * regular expression predicates : =~ !~

        :param pattern: pattern name
        :type pattern:str
        :param predicate: match predicate
        :type predicate: str
        '''
        grokpredicate = None

        matchop =  REGEXP_PREDICATE_OP.search(predicate)

        if matchop is None:
            return grokpredicate

        op = matchop.group(1)
        value = predicate[matchop.end():]

        if op in ('!~', '=~'):
            grokpredicate = self._predicate_regex(predicate)
        elif op[0] == '$' and op[1] in ('!<>='):
            # skip first character which is '$'
            grokpredicate = self._predicate_strcompare(op[1:], value)
        elif op[0] in ('!<>='):
            grokpredicate = self._predicate_numcompare(op, value)

        if grokpredicate is not None :
            grokpattern = GrokPattern(name=pattern,
                regexp=self.__patterns.get(pattern).regexp,
                predicate=grokpredicate)
            self.__patterns[pattern] = grokpattern

    def _regexcallout(self, key, value):
        ''' Call regex callout for given match
            `key` and `value`

        :param key: key match
        :type key: str
        :param value: value match
        :type value
        :returns: callout function result
        :rType: bool
        '''
        pattern = re.sub('C1_', '', key)
        pred = self.getpattern(pattern).predicate

        if isinstance(pred, GrokPredicateNum):
            return pred.op(pred.vtype(float(value)), pred.value)
        elif isinstance(pred, GrokPredicateStr):
            return pred.op(value, pred.value)
        elif isinstance(pred, GrokPredicateRegex):
            if pred.negative_match :
                return not pred.pattern.search(value)
            else :
                return pred.pattern.search(value)
        return False

    def _formatpattern(self, match):
        ''' Generate a new pattern based
            on capture results

        :param match: grok match regex object
        :type match: regex.Match
        :returns: formatted pattern
        :rType: str
        '''
        gdict = match.groupdict()
        subname = gdict.get('subname')
        name = gdict.get('name')
        predicate = gdict.get('predicate')

        pformat = '({regex})'
        if subname is not None :
            pformat = '(?<{subname}>{regex})'
        else :
            pformat = '(?<{name}>{regex})'

        if match.group('pattern') not in self.__patterns :
            raise ValueError('Invalid pattern name %s' % match.group('pattern'))

        result = pformat.format(name=name,
            subname=subname, regex=self.__patterns.get(match.group('pattern')).regexp)

        if predicate is not None :
            # add pattern predicate + callout (?C1)
            self._addpredicate(match.group('pattern'), predicate)
            result = '(?<C1_{name}>{pattern})'.format(name=match.group('pattern'), pattern=result)
        return result

    def compile(self, pattern):
        ''' Expand grok pattern with regex substituion
            and compile

        :param pattern: pattern to compile
        :type pattern: str
        '''
        self.__pattern = pattern
        py_regex_pattern = self.__pattern

        while True:

            # replace %{pattern_name:custom_name} with regex
            # and regex group name (?P<name>)
            py_regex_pattern = re.sub(PATTERN_REGEX, lambda match :
                        self._formatpattern(match), py_regex_pattern)

            # break if PATTERN_REGEX not found
            if re.search(PATTERN_REGEX, py_regex_pattern) is None:
                break

        self.__expandpattern = re.compile(py_regex_pattern)

    def match(self, text):
        ''' Search for compiled `pattern` in `text`

        :param text: text to match
        :type text: str
        :returns: regex match object
        :rType: `regex.Match`
        '''
        match = self.__expandpattern.search(text)
        if match is None:
            return None

        # predicate callout
        callouts = [k for k in match.groupdict() if k.startswith('C1_')]
        if not len(callouts):
            return match

        if all(self._regexcallout(c, match.groupdict().get(c)) for c in callouts):
            return match

    def finditer(self, text):
        ''' Return an iterator yielding `regex.Match`
            instances over all matches for `pattern` in `text`

        :param text: text to match
        :type text: str
        :return: iterator over all matches
        :rType: regex.Scanner
        '''
        return self.__expandpattern.finditer(text)

    def loadpatternsfromfile(self, filepath):
        ''' Load pattern from file

        :param filepath: file path
        :type filepath: str
        :returns: patterns from file
        :rType: dict
        '''
        patterns = {}
        with open(filepath, 'r') as f:
            for l in f:
                self.loadpatternsfromstring(l)
        return patterns

    def loadpatternsfromstring(self, text):
        ''' load patterns from string

        :param text: pattern string
        :type text: str
        :returns: grok pattern
        :rType: `GrokPattern`
        '''
        text = text.decode('utf-8').strip()
        if text == '' or text.startswith('#'):
            return

        sep = text.find(' ')
        name = text[:sep]
        regexp = text[sep:].strip()
        pattern = GrokPattern(name, regexp)
        self.__patterns.update({name : pattern})
        return pattern

    def loadpatterns(self, patternsdir=None):
        ''' Load pattern files

        :param patternsdir: patterns files directory
        :type patternsdir: str
        :returns: patterns {name: `GrokPattern(name, regexp)`, ..}
        :rType: dict
        '''
        if patternsdir is None :
            patternsdir = os.environ.get('DEFAULT_PATTERNS_DIR')

        patterns = {}
        for f in os.listdir(patternsdir):
            if not os.path.join(patternsdir, f).endswith('.patterns'):
                continue
            filepatterns = self.loadpatternsfromfile(os.path.join(patternsdir, f))
            patterns.update(filepatterns)
        return patterns

    def getpatternnames(self):
        ''' Return patterns names list

        :returns: patterns names
        :rType: list
        '''
        return sorted(self.__patterns.keys())

    def addpattern(self, name, regexp):
        ''' Add pattern with name and associated regex

        :param name: pattern name
        :type name: str
        :param regexp: regex pattern
        :type regexp: str
        '''
        pattern = GrokPattern(name, regexp)
        self.__patterns.update({name: pattern})

    def getpattern(self, name):
        ''' Return regex pattern associated to name

        :param name: pattern name
        :type name: str
        :returns: grok pattern
        :rType: GrokPattern
        '''
        return self.__patterns.get(name)


class InputProgram(object):
    ''' InputProgram class

        Base class for `Program` input
        Inherited by `InputFileProgram` and `InputFileProcess`

        ..note::
            * Inherited classes must implement readline() function

    '''
    def __init__(self):

        self.nbmatches = 0
        self.done = 0
        self.restartdelay = None

    def run(self, matchcallback, nomatchcallback):
        ''' Run read file/output process, call `matchcallback` for
            each line and nomatchcallback at the end of file/process

        :param matchcallback: match callback
        :type matchcallback: callable
        :param nomatchcallback: no-match callback
        :type nomatchcallback: callable
        '''
        for line in self.readline():
            if not line :
                break

            matchcallback(self, line.rstrip('\n'))

        # execute nomatch if on in this program
        if self.nbmatches == 0 :
            nomatchcallback(self)

        self.done = 1

    def readline(self):
        ''' Return output line iterator

        :returns: line iterator
        :rType: iterator
        '''
        NotImplementedError

    @property
    def inputname(self):
        inputname = ''
        if isinstance( self, InputProgramFile ):
            inputname = self.path

        elif isinstance( self, InputProgramProcess ):
            inputname = self.command
        return inputname

class InputProgramFile(InputProgram):
    ''' InputProgramFile class

        This class is used to read file line
        as program input
    '''
    def __init__(self, filepath):
        ''' Init program file

        :param filepath: filepath to read
        :type filepath: str
        '''
        InputProgram.__init__(self)
        self.__path = filepath
        self.__stat = None

    @property
    def path(self):
        return self.__path

    @property
    def stat(self):
        if self.__stat is None :
            self.__stat = os.stat(self.__path)
        return self.__stat

    @property
    def size(self):
        return self.stat.st_size

    @property
    def mtime(self):
        return self.stat.st_mtime

    def readline(self):
        ''' Return file read line iterator

        :returns: line iterator
        :rType: iterator
        '''

        if self.size == 0 :
            return

        with open(self.path, 'r') as f :
            m = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
            for line in iter(m.readline, ''):
                yield line

class InputProgramProcess(InputProgram):
    ''' InputProgramProcess class

        This class is used to read process
        output line as program input
    '''
    def __init__(self, command):
        ''' Init program process

        :param command: command to execute
        :type command: str
        '''
        InputProgram.__init__(self)
        self.__command = command
        self.__restartonexit = False
        self.__minrestartdelay = 5 # seconds
        self.__runinterval = 60 # seconds
        self.__readstderr = False

    @property
    def command(self):
        return self.__command

    def readline(self):
        ''' Return process read line iterator

        :returns: line iterator
        :rType: iterator
        '''
        proc = subprocess.Popen(self.__command, shell=True,
                    stdout=subprocess.PIPE)

        for line in iter(proc.stdout.readline, ''):
            yield line

        proc.stdout.close()


class MatchConfig(object):

    def __init__(self, patterns, action='%{@LINE}', breakifmatch=False,
            noaction=False, nomatch=False, shell='stdout'):
        ''' Match config apply on every line of input file /process

        :param patterns: regex or grok patterns
        :type patterns: list
        :param action: action to execute, default is %{@LINE} which
                    is full line match
        :type action: str
        :param breakifmatch: not attempt any further matches on this line.
                            default is `False`
        :type breakifmatch: bool
        :param noaction: no action to run. default is `False`
        :type noaction: bool
        :param nomatch: executed if no output is matched. default is `False`
        :type nomatch: bool
        :param shell: default shell is stdout which means action is printed
            directly to standard output
        :type shell: str
        '''
        # list of pattern to match
        # can be regex or grok patterns %{FOO}
        self.__patterns = patterns

        # action
        self.__action = action

        # execute if no-match case
        self.__nomatch = nomatch

        # break if we match
        self.__breakifmatch = breakifmatch

        # skip action for this match
        self.__noaction = noaction

        # Shell values are stdout or cmd string to run
        self.__shell = shell

        self.__expandpatterns = []

        self._compile()

    def _compile(self):

        self.__expandpatterns = []

        for pattern in self.__patterns :
            g = Grok()
            g.compile(pattern)
            self.__expandpatterns.append(g)

    @property
    def patterns(self):
        return self.__patterns

    @property
    def expandpatterns(self):
        return self.__expandpatterns

    @property
    def breakifmatch(self):
        return self.__breakifmatch

    @property
    def noaction(self):
        return self.__noaction

    @property
    def action(self):
        return self.__action

    @property
    def shell(self):
        return self.__shell

    @property
    def nomatch(self):
        return self.__nomatch

    @property
    def inputmatches(self):
        return self.__inputmatches

    @classmethod
    def fromdict(cls, configdict):
        ''' Load a `MatchConfig` from a dict

        :param cls: match config class
        :type cls: `MatchConfig`
        :param configdict: confict dict
        :type configdict: dict
        :returns: match config instance from dict
        :rType: `MatchConfig` object
        '''
        matchconfig = MatchConfig.__new__(MatchConfig)
        matchconfig._MatchConfig__patterns = configdict['patterns']
        matchconfig._MatchConfig__action = configdict['action']
        matchconfig._MatchConfig__nomatch = configdict['nomatch']
        matchconfig._MatchConfig__breakifmatch = configdict['breakifmatch']
        matchconfig._MatchConfig__noaction = configdict['noaction']
        matchconfig._MatchConfig__shell = configdict['shell']
        matchconfig._compile()

        return matchconfig

class Program(object):

    def __init__(self, matchconfigs, name=None, captureformat='%{@PATTERNS}'):
        ''' Init program with a list of match configs,
            optional name and capture format

        :param matchconfigs:
        :type matchconfigs: list of MatchConfig
        :param name: optional program name
        :type name: str
        :param captureformnat: capture format, default is %{@PATTERNS}
        :type captureformat: str
        '''
        self.__name = name
        self.__inputs = []
        self.__matchconfigs = matchconfigs
        self.__captureformat = captureformat
        self.__captures = {}

        self._compile()

    def _compile(self):
        self.__filterpattern = Grok()
        self.__filterpattern.loadpatternsfromstring('PATTERN %{%{NAME}(?:%{FILTER})?}')
        self.__filterpattern.loadpatternsfromstring('NAME @?\w+(?::\w+)?(?:|\w+)*')
        self.__filterpattern.loadpatternsfromstring('FILTER (?:\|\w+)+')
        self.__filterpattern.compile('%{PATTERN}')

    def addinputfile(self, filepath):
        ''' Add input file to program

        :param fileptah: input filepath
        :type filepath: str
        '''
        if not os.path.exists(filepath):
            return

        inputfile = InputProgramFile(filepath)
        self.__inputs.append(inputfile)
        inputfile.run(self._matchconfigs, self._nomatchconfigs)

    def addinputprocess(self, command):
        ''' Add input process to program

        :param command: process command
        :type command: str
        '''
        inputprocess = InputProgramProcess(command)
        self.__inputs.append(inputprocess)
        inputprocess.run(self._matchconfigs, self._nomatchconfigs)

    def nbinputs(self):
        ''' Return inputs number

        :returns: inputs number
        :rType: int
        '''
        return len(self.__inputs)

    def _addcapture(self, programinput, pattern, match):
        ''' Add match capture

        :param programinput: program input
        :type progrminput: InputProgram
        :param pattern: original pattern matched
        :type pattern: str
        :param match: match object
        :type match: regex.Match
        '''
        if pattern not in self.__captures :
            self.__captures[pattern] = []

        capture = (programinput.inputname,
                self._filteraction(programinput,
                self.__captureformat, match))
        self.__captures[pattern].append(capture)

    def getcaptures(self):
        ''' Return all program captures
            as dict match pattern as key and list of
            capture as tuple (inputname, capture)

        :returns: pattern captures
        :rType: dict
        '''
        return self.__captures

    def _matchconfigs(self, programinput, text):
        ''' Run match case config action

        :param programinput: program input instance
        :type programinput: InputProgram
        :param text: input process/file text to match
        :type text: str
        '''
        _break = False

        for matchconfig in self.__matchconfigs :

            for i, pattern in enumerate(matchconfig.expandpatterns) :

                match = pattern.match(text)

                if match is not None :

                    self._addcapture(programinput, matchconfig.patterns[i], match)

                    self._matchconfigaction(programinput, matchconfig, match)

                    if matchconfig.breakifmatch :
                        _break = True
                        break

            if _break is True :
                break

    def _nomatchconfigs(self, programinput):
        ''' Run no-match case config action

        :param programinput: program input instance
        :type programinput: InputProgram
        '''
        for matchconfig in self.__matchconfigs :

            if matchconfig.nomatch :
                self._matchconfigaction(programinput, matchconfig, None)

    def _matchconfigaction(self, programinput, matchconfig, match):
        ''' Run match case config action

        :param programinput: program input instance
        :type programinput: InputProgram
        :param matchconfig: match config instance
        :type matchconfig: MatchConfig
        :param match: match object
        :type match: re.Match
        '''
        programinput.nbmatches += 1

        if matchconfig.noaction :
            return

        action = matchconfig.action

        if match is not None :
            action = self._filteraction(programinput, matchconfig.action, match)

        if matchconfig.shell == 'stdout':
            sys.stdout.write(action+'\n')
            sys.stdout.flush()
        else :
            try :
                proc = subprocess.Popen(shlex.split(action), stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

                while True :
                    line = proc.stdout.readline()
                    if not line :
                        break

                    print line,
            except Exception, e :
                print 'Failed to execute action', action
                print e

    def _getmacrovalue(self, macrotype, programinput, match):
        ''' Return macro value from macrotype
            and match

        :param macrotype: macro type
        :type macrotype: see MACRO_TYPES
        :param match: match object
        :type match: regex.Match
        :returns: macro value for type and match
        :rType: str
        '''
        value = ''
        macrovalues = {
            VALUE_LINE : match.string,
            VALUE_START : '%d' % match.start(),
            VALUE_END : '%d' % match.end(),
            VALUE_LENGTH : '%d' % (match.end() - match.start()),
            VALUE_MATCH :  match.group(),
            VALUE_PATTERNS : match.groupdict(),
            VALUE_INPUT : programinput.inputname,
            VALUE_JSON_SIMPLE : [{'@LINE': match.string},
                                 {'@MATCH' : match.group()}],

            VALUE_JSON_COMPLEX : [{'@LINE': {
                                    'start' : 0,
                                    'end' : len(match.string),
                                    'value' : match.string},
                                    },
                                 {'@MATCH': {
                                    'start' : match.start(),
                                    'end' : match.end(),
                                    'value' : match.group()},
                                    }],
            }

        if macrotype in (VALUE_LINE, VALUE_START, VALUE_END, \
                VALUE_LENGTH, VALUE_MATCH, VALUE_INPUT):
            return macrovalues.get(macrotype)

        if macrotype == VALUE_PATTERNS :
            return json.dumps(macrovalues.get(macrotype))

        if macrotype in (VALUE_JSON_SIMPLE, VALUE_JSON_COMPLEX):
            entry = macrovalues.get(macrotype)
            patterns = macrovalues.get(VALUE_PATTERNS)
            for patternname, patternvalue in patterns.iteritems():
                if macrotype == VALUE_JSON_SIMPLE:
                    patternentry = { patternname : patternvalue }
                else :
                    matchpatterns = match.groups()
                    index = matchpatterns.index(patternvalue)
                    (start, end) = match.regs[index+1]
                    patternentry = {
                            patternname : { 'start': start,
                                            'end' : end,
                                            'value' : patternvalue
                            }
                    }
                entry.append(patternentry)

            value = json.dumps(entry)

        return value

    def _applyfilter(self, filtername, value):
        ''' Apply filter to capture value

        :param filtername: filter name
        :param filtername: str
        :param value: capture value to filter
        :type value: str
        :returns: filtered capture value
        :rType: str
        '''
        if filtername == 'shellescape':

            value = quote(value)

        elif filtername == 'jsonencode':

            value = re.sub(r'(\"|\\)', lambda match : \
                '\\\\' + match.group(1), value)
            value = quote(value)

        return value

    def _filteraction(self, programinput, action, match):
        ''' Filter action with match captures

        :param action: match action
        :type action: str
        :param grokmatch: grok match
        :type grokmatch: regex.Match
        :returns: filtered action
        :rType: str
        '''

        output = action
        patterndict = match.groupdict()

        for it in self.__filterpattern.finditer(action):
            patternname = it.group(2)
            patternfilter = it.group(3)

            macrotype = patternnametomacrotype(patternname)
            value = self._getmacrovalue(macrotype, programinput, match)

            # replace %{FOO} with the value of foo
            if patterndict.get(patternname) is not None:
                value = patterndict.get(patternname)

            if len(value):

                substring = '%{'+patternname

                # apply filter %{FOO|shellescape}
                if patternfilter is not None :

                    value = self._applyfilter(patternfilter[1:], value)

                    substring += '\\' + patternfilter

                substring += '}'

                output = re.sub(substring, value, output )

        return output

    def save(self, filepath):
        ''' Save program config as json file

        :param filepath: filepath
        :type filepath: str
        '''
        excludekeys = ['inputs', 'captures', 'filterpattern',
                    'expandpatterns']
        supportedclass = ['MatchConfig', 'Program']

        def deletekeys(d, keys):
            if not isinstance(d, dict):
                return d
            return {k:v for k, v in ((k, deletekeys(v, keys)) \
                    for k, v in d.items()) if k not in keys}

        with open(filepath, 'w') as outfile:
            data = json.dumps(self, default=lambda x: deletekeys({ re.sub( '_%s__' % x.__class__.__name__, '', k) : v \
                    for (k, v) in x.__dict__.iteritems() if x.__class__.__name__ in supportedclass }, excludekeys),
                    sort_keys=True, indent=2)

            outfile.write(data)

        return filepath

    @classmethod
    def load(cls, filepath):
        ''' Load program as from config file

        :param cls: class
        :type cls: Program
        :param filepath: program config file
        :type filepath : str
        :returns: program instance from dict
        :rType: Program
        '''
        with open(filepath) as f :

            content = json.load(f)

        program = cls.fromdict(content)
        return program


    @classmethod
    def fromdict(cls, programdict):
        ''' Load a `Program` from a dict

        :param cls: class
        :type cls: Program
        :param programdict: program dict
        :type programdict: dict
        :returns: program instance from dict
        :rType: `Program` object
        '''
        program = Program.__new__(Program)
        program._Program__name = programdict.get('name')
        program._Program__captureformat = programdict.get('captureformat','%{@PATTERNS}')
        program._Program__inputs = []
        program._Program__captures = {}
        program._compile()

        matchconfigs = []

        for configd in programdict.get('matchconfigs', []):
            matchconfig = MatchConfig.fromdict(configd)
            matchconfigs.append(matchconfig)

        program._Program__matchconfigs = matchconfigs

        return program
