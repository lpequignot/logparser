# coding: utf8
from __future__ import unicode_literals

import os
import sys
import unittest
from pprint import pprint

from logparser import core as lpc

class TestPatterns(unittest.TestCase):

    def setUp(self):
        self.grok = lpc.Grok()
        logdir = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '../logs'))
        self.logs = sorted([ os.path.join(logdir, f) for f in os.listdir(logdir) \
                if f.endswith('.log')])

    def test_simple_pattern(self):

        self.grok.compile('%{WORD:name} is %{WORD:gender}, %{NUMBER:age} years old')
        text = 'gary is male, 25 years old'
        result = self.grok.match(text).groupdict()
        simple_result = {u'gender': u'male', u'age': u'25', u'name': u'gary'}
        self.assertDictContainsSubset(simple_result, result)

    def test_version_pattern(self):

        self.grok.compile('version=%{VERSION:version}')
        text = 'version=1.0.1'
        str_version = {'version': '1.0.1'}
        result = self.grok.match(text).groupdict()
        self.assertDictContainsSubset(str_version, result)

    def test_date_pattern(self):

        str_date = {'month': '07',
                    'day': '26',
                    'year': '2017'}

        self.grok.compile('DATE : %{MONTHNUM:month}[/-]%{MONTHDAY:day}[/-]%{YEAR:year}')
        text = '* DATE : 07/26/2017'
        result = self.grok.match(text).groupdict()
        self.assertDictContainsSubset(str_date, result)

    def test_rez_patterns(self):
        rez_version = 'REZ_ONMAYAUTILS_VERSION=0.1.84'
        rez_root = 'REZ_ONMAYAUTILS_ROOT=/studio/code/packages/onmayautils/0.1.84'
        rez_base = 'REZ_ONMAYAUTILS_BASE=/studio/code/packages/onmayautils/0.1.84'
        rez_package = 'onmayautils-0.1.84'
        rez_used_resolve = 'REZ_USED_RESOLVE=onmaya-2017.0.11 onrigplaymoutils-0.0.11 pythonrequests-2.9.1.0'

        self.grok.compile('%{REZ_PACKAGE_VERSION}')
        version_result = {  'package_version': '0.1.84',
                            'package_name': 'ONMAYAUTILS'}
        result = self.grok.match(rez_version).groupdict()
        self.assertDictContainsSubset(version_result, result)

        self.grok.compile('%{REZ_PACKAGE_ROOT}')
        root_result = { 'package_root': '/studio/code/packages/onmayautils/0.1.84', 
                        'package_name': 'ONMAYAUTILS'}
        result = self.grok.match(rez_root).groupdict()
        self.assertDictContainsSubset(root_result, result)

        self.grok.compile('%{REZ_PACKAGE_BASE}')
        base_result = { 'package_base': '/studio/code/packages/onmayautils/0.1.84', 
                        'package_name': 'ONMAYAUTILS'}

        result = self.grok.match(rez_base).groupdict()
        self.assertDictContainsSubset(base_result, result)

        self.grok.compile('%{REZ_PACKAGE}')
        package_result = {  'package_version': '0.1.84',
                            'package_name': 'onmayautils'}

        result = self.grok.match(rez_package).groupdict()
        self.assertDictContainsSubset(package_result, result)

        self.grok.compile('%{REZ_USED_RESOLVE}')
        used_resolve_result = {'rez_used_resolve': 'onmaya-2017.0.11 onrigplaymoutils-0.0.11 pythonrequests-2.9.1.0'}
        result = self.grok.match(rez_used_resolve).groupdict()
        self.assertDictContainsSubset(used_resolve_result, result)

    def test_coalition_patterns(self):

        coalition_worker ='* WORKER : canwork140-1'
        coalition_datetime = '* DATE : 04/07/17 18:00'
        coalition_cmd = '* CMD : sudo -u jgolzman -E -- bash -c \'cd /on/work --mode auto\''
        coalition_exit = '* EXIT : 1'

        self.grok.compile('%{COALITION_JOB_WORKER}')
        worker_result = {'worker': 'canwork140'}
        result = self.grok.match(coalition_worker).groupdict()
        self.assertDictContainsSubset(worker_result, result)

        self.grok.compile('%{COALITION_JOB_DATETIME}')
        datetime_result = { 'date': '04/07/17', 
                            'hour': '18', 
                            'min': '00'}
        result = self.grok.match(coalition_datetime).groupdict()
        self.assertDictContainsSubset(datetime_result, result)

        self.grok.compile('%{COALITION_JOB_COMMAND}')
        cmd_result = {'sudo_command': 'sudo -u jgolzman -E -- bash -c ',
                      'command': u"'cd /on/work --mode auto'"}
        result = self.grok.match(coalition_cmd).groupdict()
        self.assertDictContainsSubset(cmd_result, result)

        self.grok.compile('%{COALITION_JOB_EXITCODE}')
        result = self.grok.match(coalition_exit).groupdict()
        self.assertDictContainsSubset({'exit_code' : '1'}, result)

    def test_python_patterns(self):
        python_traceback = '  File "/studio/code/packages/repoedit/0.0.19/bin/repotransfer", line 41, in <module>'
        python_name_error = 'NameError: global name \'value\' is not defined'
        python_attribute_error = 'AttributeError: \'module\' object has no attribute \'enable\''

        self.grok.compile('%{PYTHON_TRACEBACK_ERROR}')
        result = self.grok.match(python_traceback).groupdict()
        python_traceback_result = { 'traceback_file': '/studio/code/packages/repoedit/0.0.19/bin/repotransfer', 
                                    'traceback_in': '<module>', 
                                    'traceback_line': '41'}
        self.assertDictContainsSubset(python_traceback_result, result)

        self.grok.compile('%{PYTHON_NAME_ERROR}')
        name_error_result = {u'python_error': u"global name 'value' is not defined"}
        result = self.grok.match(python_name_error).groupdict()
        self.assertDictContainsSubset(name_error_result, result)

        self.grok.compile('%{PYTHON_ATTRIBUTE_ERROR}')
        attr_error_result = {u'python_error': u"'module' object has no attribute 'enable'"}
        result = self.grok.match(python_attribute_error).groupdict()
        self.assertDictContainsSubset(attr_error_result, result)

    def test_predicate_strcompare(self):

        self.grok.compile('^%{WORD=~/^hello/}')

        self.assertIsNone(self.grok.match('hallo'))
        self.assertIsNone(self.grok.match('hhelloo'))

        self.assertIsNotNone(self.grok.match('hello'))
        self.assertIsNotNone(self.grok.match('hello world'))

        self.grok.compile('^%{WORD!~/^hello/}')
        self.assertIsNotNone(self.grok.match('hallo'))
        self.assertIsNone(self.grok.match('hello'))
        self.assertIsNotNone(self.grok.match('nothello'))

        self.grok.compile('^%{WORD$==hello}')
        self.assertIsNone(self.grok.match('hel'))
        self.assertIsNotNone(self.grok.match('hello'))

    def test_predicate_numcompare_gt_int(self):

        self.grok.compile('^%{NUMBER>10}$')

        self.assertIsNone(self.grok.match('0'))
        self.assertIsNone(self.grok.match('1'))
        self.assertIsNone(self.grok.match('9'))
        self.assertIsNone(self.grok.match('10'))
        self.assertIsNone(self.grok.match('5.5'))
        self.assertIsNone(self.grok.match('0.2'))
        self.assertIsNone(self.grok.match('9.95'))

        self.assertIsNone(self.grok.match('10.1'))
        self.assertIsNone(self.grok.match('10.2'))

        self.assertIsNotNone(self.grok.match('11.2'))
        self.assertIsNotNone(self.grok.match('4425.334'))
        self.assertIsNotNone(self.grok.match('11'))
        self.assertIsNotNone(self.grok.match('15'))

    def test_predicate_numcompare_gt_float(self):

        self.grok.compile('^%{NUMBER>10.0}$')

        self.assertIsNone(self.grok.match('0'))
        self.assertIsNone(self.grok.match('1'))
        self.assertIsNone(self.grok.match('9'))
        self.assertIsNone(self.grok.match('10'))
        self.assertIsNone(self.grok.match('5.5'))
        self.assertIsNone(self.grok.match('0.2'))
        self.assertIsNone(self.grok.match('9.95'))

        self.assertIsNotNone(self.grok.match('10.1'))
        self.assertIsNotNone(self.grok.match('10.2'))

        self.assertIsNotNone(self.grok.match('11.2'))
        self.assertIsNotNone(self.grok.match('4425.334'))
        self.assertIsNotNone(self.grok.match('11'))
        self.assertIsNotNone(self.grok.match('15'))

    def test_predicate_numcompare_lt(self):

        self.grok.compile('%{NUMBER<57}')

        self.assertIsNotNone(self.grok.match('-13'))
        self.assertIsNotNone(self.grok.match('-3'))
        self.assertIsNotNone(self.grok.match('0'))
        self.assertIsNotNone(self.grok.match('3'))
        self.assertIsNotNone(self.grok.match('13'))
        self.assertIsNotNone(self.grok.match('56'))
        self.assertIsNone(self.grok.match('57'))
        self.assertIsNone(self.grok.match('58'))
        self.assertIsNone(self.grok.match('70'))
        self.assertIsNone(self.grok.match('100'))

    def test_predicate_numcompare_le(self):

        self.grok.compile('%{NUMBER<=57}')

        self.assertIsNotNone(self.grok.match('-13'))
        self.assertIsNotNone(self.grok.match('-3'))
        self.assertIsNotNone(self.grok.match('0'))
        self.assertIsNotNone(self.grok.match('3'))
        self.assertIsNotNone(self.grok.match('13'))
        self.assertIsNotNone(self.grok.match('56'))
        self.assertIsNotNone(self.grok.match('57'))
        self.assertIsNone(self.grok.match('58'))
        self.assertIsNone(self.grok.match('70'))
        self.assertIsNone(self.grok.match('100'))

    def test_program_inputfile(self):


        patterns = ['%{COALITION_JOB_WORKER}',
                    '%{COALITION_JOB_DATETIME}',
                    '%{COALITION_JOB_EXITCODE}'
                    ]

        mcworker = lpc.MatchConfig(
                patterns=['%{COALITION_JOB_WORKER}'],
                action='Found worker %{COALITION_JOB_WORKER}=%{@PATTERNS};')

        mcdate = lpc.MatchConfig(
                patterns=['%{COALITION_JOB_DATETIME}'],
                action='Found datetime %{COALITION_JOB_DATETIME}=%{@PATTERNS};')

        mcexitcode = lpc.MatchConfig(
                patterns=['%{COALITION_JOB_EXITCODE}'],
                action='Found exitcode %{COALITION_JOB_EXITCODE}=%{@PATTERNS};')

        mconfigs = [mcworker, mcdate, mcexitcode]
        pg = lpc.Program(name='CoalitionLogs', matchconfigs=mconfigs)
        for log in sorted(self.logs)[:1]:
            pg.addinputfile(filepath=log)

        pg.save('/tmp/program.txt')

    def test_program_inputprocess_pythoncommand(self):
        mc = lpc.MatchConfig(
                patterns=['%{WORD} world'],
                breakifmatch=True,
                action='Found pattern %{WORD} in line %{@LINE}')

        pg = lpc.Program(name='HelloWorld', matchconfigs=[mc])
        command ='python -c \'print("hello world")\''
        pg.addinputprocess(command=command)

    def test_program_inputprocess_pingcommand(self):

        mc = lpc.MatchConfig(
                patterns=['time=%{NUMBER:time}'],
                action='%{@JSON}')

        pg = lpc.Program(name='Ping Google', matchconfigs=[mc])
        command ='ping -c 1 www.google.ca'
        pg.addinputprocess(command=command)

    def test_program_log_stats(self):

        mcsucces = lpc.MatchConfig(
            patterns=['%{COALITION_JOB_SUCCES}'],
            noaction=True)

        mcfailure = lpc.MatchConfig(
            patterns=['%{COALITION_JOB_FAILURE}'],
            noaction=True)

        mcrezpackage = lpc.MatchConfig(
            patterns=['onmayautils-%{VERSION}'],
            action='%{@MATCH} : %{@PATTERNS}')

        mconfigs = [mcsucces, mcfailure, mcrezpackage]
        pg = lpc.Program(name='CoalitionStats', matchconfigs=mconfigs)

        logs = self.logs[:3]
        for log in sorted(logs):
            pg.addinputfile(filepath=log)

        captures = pg.getcaptures()
        print 'Total Succeses: %d/%d' % (len(captures.get('%{COALITION_JOB_SUCCES}')),
                                len(logs))
        print 'Total Failures: %d/%d' % (len(captures.get('%{COALITION_JOB_FAILURE}')),
                                len(logs))

if __name__ == "__main__":
    unittest.main()
