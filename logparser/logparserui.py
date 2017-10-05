# coding: utf8
from __future__ import unicode_literals

import os
import sys
import json
from pprint import pprint

from core import Program, MatchConfig, Grok, getpatternmacrotypes

try :
    import PySide2.QtCore as QtCore
    import PySide2.QtGui as QtGui
    import PySide2.QtUiTools as QtUiTools
    import PySide2.QtWidgets as QtWidgets
    from PySide2.QtCore import Signal as pyqtSignal
    from PySide2.QtCore import Slot as pyqtSlot

except:
    import PySide.QtCore as QtCore
    import PySide.QtGui as QtGui
    import PySide.QtUiTools as QtUiTools
    import PySide.QtGui as QtWidgets
    from PySide.QtCore import Signal as pyqtSignal
    from PySide.QtCore import Slot as pyqtSlot

groupBoxCss = '''
QGroupBox {
    border: 1px outset lightgray;
    border-radius: 4px;
    margin-top: 0.5em;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 30px;
    padding: 0 3px 0 3px;
}
'''

class OutputWrapper(QtCore.QObject):
    outputWritten = pyqtSignal(object, object)

    def __init__(self, parent, stdout=True):
        QtCore.QObject.__init__(self, parent)
        if stdout:
            self._stream = sys.stdout
            sys.stdout = self
        else:
            self._stream = sys.stderr
            sys.stderr = self
        self._stdout = stdout

    def write(self, text):
        self._stream.write(text)
        self.outputWritten.emit(text, self._stdout)

    def __getattr__(self, name):
        return getattr(self._stream, name)

    def __del__(self):
        try:
            if self._stdout:
                sys.stdout = self._stream
            else:
                sys.stderr = self._stream
        except AttributeError:
            pass

class LibraryTreeWidgetItem(QtWidgets.QTreeWidgetItem):

    def __init__(self, parent, name, data):
        QtWidgets.QTreeWidgetItem.__init__(self, parent, [name])
        self.__data = data

    def getItemData(self):
        return self.__data


class LibraryDialog(QtWidgets.QDialog):

    def __init__(self, parent=None, title='', fields=None, data=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.setLayout(QtGui.QVBoxLayout())
        self.setWindowTitle(title)
        self.treeWidget = QtGui.QTreeWidget()
        self.treeWidget.setSelectionMode(QtWidgets.QTreeWidget.SingleSelection)
        self.treeWidget.setHeaderLabels(fields or [])
        self.setMinimumWidth(600)
        items = []
        for row in data :
            item = LibraryTreeWidgetItem(None, row.get('name'), row)
            for i, key in enumerate(fields) :
                item.setText(i, row.get(key.lower(), ''))
            items.append(item)

        self.treeWidget.addTopLevelItems(items)
        [self.treeWidget.resizeColumnToContents(i) for i in range(0, len(fields))]
        self.layout().addWidget(self.treeWidget)
        self.treeWidget.itemDoubleClicked.connect(self.itemDoubleClicked)

        self.btnLayout = QtWidgets.QVBoxLayout()
        self.buttons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Cancel)
        self.btnLayout.addWidget(self.buttons)
        self.layout().addLayout(self.btnLayout)
        self.buttons.rejected.connect(self.reject)


    def itemDoubleClicked(self):
        selectedItems = self.treeWidget.selectedItems()
        if len(selectedItems):
            self.result = selectedItems[0].getItemData()
        self.accept()
        self.close()

class MatchConfigWidget(QtWidgets.QWidget):
    def __init__(self, parent=None, data=None):
        QtWidgets.QWidget.__init__(self, parent)
        self.__data = data or {}
        self.setContentsMargins(0, 0, 0, 0)
        self.setLayout(QtWidgets.QHBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.enableMatchConfigBox = QtWidgets.QCheckBox()

        self.matchConfigLayout = QtWidgets.QVBoxLayout()
        self.matchConfigLayout.setContentsMargins(0, 0, 0, 0)
        self.patternsWidget = PatternsWidget()
        self.patternsWidget.addPattern()
        self.actionWidget = QtWidgets.QWidget()
        self.actionWidget.setContentsMargins(0, 0, 0, 0)
        self.actionWidget.setLayout(QtWidgets.QHBoxLayout())
        self.actionWidget.layout().setContentsMargins(0, 0, 0, 0)
        self.enableAction = QtWidgets.QCheckBox('action')
        self.enableAction.setChecked(True)
        self.action = QtWidgets.QLineEdit()
        self.action.setText('Found %{@MATCH} in %{@INPUT}')
        self.action.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.action.customContextMenuRequested.connect(self.actionContextMenu)
        self.shell = QtWidgets.QComboBox()
        self.shell.addItems(['stdout', 'subprocess'])
        self.nomatch = QtWidgets.QCheckBox('no match')
        self.breakifmatch = QtWidgets.QCheckBox('break if match')
        self.libActionBtn = QtWidgets.QPushButton()
        self.libActionBtn.setIcon(QtGui.QIcon.fromTheme('user-bookmarks'))
        self.libActionBtn.setContentsMargins(0, 0, 0, 0)
        self.libActionBtn.setFixedSize(20, 20)
        self.actionWidget.layout().addWidget(self.enableAction)
        self.actionWidget.layout().addWidget(self.shell)
        self.actionWidget.layout().addWidget(self.action)
        self.actionWidget.layout().addWidget(self.libActionBtn)

        self.matchConfigLayout.addWidget(self.patternsWidget)
        self.matchConfigLayout.addWidget(self.actionWidget)
        self.matchConfigLayout.addWidget(self.nomatch)
        self.matchConfigLayout.addWidget(self.breakifmatch)

        self.removeBtn = QtWidgets.QPushButton()
        self.removeBtn.setIcon(QtGui.QIcon.fromTheme('list-remove'))
        self.removeBtn.setContentsMargins(0, 0, 0, 0)
        self.removeBtn.setFixedSize(20, 20)

        self.layout().addWidget(self.enableMatchConfigBox)
        self.layout().addLayout(self.matchConfigLayout)
        self.layout().addWidget(self.removeBtn)

        self.enableAction.stateChanged.connect(self.actionCheckStateChanged)
        self.enableMatchConfigBox.stateChanged.connect(self.checkStateChanged)
        self.libActionBtn.clicked.connect(self.openLibAction)
        self.removeBtn.clicked.connect(self.removeMatchConfigWidget)
        self.adjustSize()

    def openLibAction(self):

        actionlibrary = os.getenv('DEFAULT_ACTION_LIBRARY', '')

        if not os.path.exists(actionlibrary):
            return

        data = None
        with open(actionlibrary, 'r') as f:
            data = json.load(f)

        if data is not None :
            fields = ['Name', 'Type', 'Action', 'Description']
            libdialog= LibraryDialog(title='Actions Library',
                                fields=fields, data=data)
            if libdialog.exec_() == libdialog.Accepted:
                self.action.setText(libdialog.result.get('action'))
                index = self.shell.findText(libdialog.result.get('type'))
                if index > -1 : self.shell.setCurrentIndex(index)

    def actionContextMenu(self):
        self.menu = QtWidgets.QMenu()
        for macrotype in sorted(getpatternmacrotypes()):
            self.menu.addAction(macrotype,
                    lambda x=macrotype: self.addMacroType(x))
        self.menu.exec_(QtGui.QCursor.pos())

    def addMacroType(self, macrotype):
        text = str(self.action.text())
        text += '%{'+macrotype+'}'
        self.action.setText(text)

    def actionCheckStateChanged(self):
        enable = self.enableAction.isChecked()
        self.action.setEnabled(enable)

    def checkStateChanged(self):
        enable = self.enableMatchConfigBox.isChecked()
        self.actionWidget.setEnabled(enable)
        self.patternsWidget.setEnabled(enable)
        self.nomatch.setEnabled(enable)
        self.breakifmatch.setEnabled(enable)

    def removeMatchConfigWidget(self):
        self.removeBtn.clicked.disconnect(self.removeMatchConfigWidget)
        self.deleteLater()

    def matchConfigEnable(self):
        return self.enableMatchConfigBox.isChecked()

    def setMatchConfigEnable(self, enable):
        self.enableMatchConfigBox.setChecked(enable)


    def getData(self):
        data = {
            'patterns' : self.patternsWidget.getPatterns(),
            'nomatch' : self.nomatch.isChecked(),
            'breakifmatch' : self.breakifmatch.isChecked(),
            'noaction' : not self.enableAction.isChecked(),
            'action' : str(self.action.text()),
            'shell' : str(self.shell.currentText()),
        }
        return data

class MatchConfigsWidget(QtWidgets.QGroupBox):

    def __init__(self, parent=None):
        QtWidgets.QGroupBox.__init__(self, parent)
        self.setTitle("Match Configs")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)
        self.addBtn = QtWidgets.QPushButton()
        self.addBtn.setIcon(QtGui.QIcon.fromTheme('list-add'))
        self.addBtn.setContentsMargins(0, 0, 0, 0)
        self.addBtn.setFixedSize(20, 20)
        addLayout = QtWidgets.QHBoxLayout()
        addLayout.setContentsMargins(0, 0, 0, 0)
        addLayout.addWidget(self.addBtn)
        addLayout.addStretch(1)
        self.layout().addLayout(addLayout)
        self.matchConfigsLayout = QtWidgets.QFormLayout()
        self.matchConfigsLayout.setContentsMargins(0, 0, 0, 0)
        self.layout().addLayout(self.matchConfigsLayout)
        self.addBtn.clicked.connect(lambda : self.addMatchConfig({}))
        self.adjustSize()
        self.addMatchConfig({})
        self.setStyleSheet(groupBoxCss)

    def setMatchConfigs(self, matchconfigs):
        for data in matchconfigs:
            self.addMatchConfig(data)

    def addMatchConfig(self, data):
        matchConfigWidget = MatchConfigWidget(self, data)
        matchConfigWidget.setMatchConfigEnable(True)
        self.matchConfigsLayout.addWidget(matchConfigWidget)

    def getMatchConfigs(self):
        matchconfigs = []
        for i in range(0, self.matchConfigsLayout.count()):
            item = self.matchConfigsLayout.itemAt(i).widget()
            if not item.matchConfigEnable():
                continue
            matchconfigs.append(item.getData())
        return matchconfigs

class PatternWidget(QtWidgets.QWidget):

    def __init__(self, parent=None):
        QtWidgets.QWidget.__init__(self, parent)

        self.setLayout(QtWidgets.QHBoxLayout())
        self.setContentsMargins(0, 0, 0, 0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.enablePatternBox = QtWidgets.QCheckBox()
        self.pattern = QtWidgets.QLineEdit()
        self.pattern.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.pattern.customContextMenuRequested.connect(self.contextMenu)
        self.removeBtn = QtWidgets.QPushButton()
        self.removeBtn.setIcon(QtGui.QIcon.fromTheme('list-remove'))
        self.removeBtn.setContentsMargins(0, 0, 0, 0)
        self.removeBtn.setFixedSize(20, 20)
        self.libBtn = QtWidgets.QPushButton()
        self.libBtn.setIcon(QtGui.QIcon.fromTheme('user-bookmarks'))
        self.libBtn.setContentsMargins(0, 0, 0, 0)
        self.libBtn.setFixedSize(20, 20)

        self.layout().addWidget(self.enablePatternBox)
        self.layout().addWidget(self.pattern)
        self.layout().addWidget(self.libBtn)
        self.layout().addWidget(self.removeBtn)

        self.enablePatternBox.stateChanged.connect(self.checkStateChanged)
        self.libBtn.clicked.connect(self.openLibPattern)
        self.removeBtn.clicked.connect(self.removePatternWidget)
        self.adjustSize()


    def openLibPattern(self):

        patternlibrary = os.getenv('DEFAULT_PATTERN_LIBRARY', '')

        if not os.path.exists(patternlibrary):
            return

        data = None
        with open(patternlibrary, 'r') as f:
            data = json.load(f)

        if data is not None :
            fields = ['Name', 'Type', 'Pattern', 'Description']
            libdialog = LibraryDialog(title='Patterns Library',
                                fields=fields, data=data)
            if libdialog.exec_() == libdialog.Accepted:
                self.pattern.setText(libdialog.result.get('pattern'))

    def contextMenu(self):
        self.menu = QtWidgets.QMenu()
        g = Grok()

        patternMenu = self.menu.addMenu('PATTERNS')
        families = {}
        for patternname in sorted(g.getpatternnames()):

            if len(patternname.split('_')) > 1 :
                family = patternname.split('_')[0]
                if family not in families :
                    familyMenu = patternMenu.addMenu(family)
                    families[family] = familyMenu
                else :
                    familyMenu = families.get(family)

                familyMenu.addAction(patternname,
                        lambda x=patternname: self.addPatternName(x))
            else :
                patternMenu.addAction(patternname,
                        lambda x=patternname: self.addPatternName(x))

        operatorMenu = self.menu.addMenu('OPERATORS')
        strOperatorMenu = operatorMenu.addMenu('string operators')
        numOperatorMenu = operatorMenu.addMenu('numerical operators')
        regOperatorMenu = operatorMenu.addMenu('regex operators')

        for op in ['<','>','>=','<=','==','!=']:
            numOperatorMenu.addAction(op, lambda x=op: self.pattern.insert(x))
            strOperatorMenu.addAction('$'+op, lambda x='$'+op: self.pattern.insert(x))

        regOperatorMenu.addAction('=~', lambda x='=~': self.pattern.insert(x))
        regOperatorMenu.addAction('!~', lambda x='!~': self.pattern.insert(x))

        self.menu.exec_(QtGui.QCursor.pos())

    def addPatternName(self, name):
        text = str(self.pattern.text())
        text += '%{'+name+'}'
        self.pattern.setText(text)

    def checkStateChanged(self):
        enable = self.enablePatternBox.isChecked()
        self.pattern.setEnabled(enable)

    def removePatternWidget(self):
        self.removeBtn.clicked.disconnect(self.removePatternWidget)
        self.deleteLater()

    def setValue(self, value):

        self.pattern.setText(value)

    def getValue(self):

        return str(self.pattern.text())

    def patternEnable(self):
        return self.enablePatternBox.isChecked()

    def setPatternEnable(self, enable):
        self.enablePatternBox.setChecked(enable)

class PatternsWidget(QtWidgets.QGroupBox):

    def __init__(self, parent=None):
        QtWidgets.QGroupBox.__init__(self, parent)
        self.setTitle("Patterns")
        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.addBtn = QtWidgets.QPushButton()
        self.addBtn.setIcon(QtGui.QIcon.fromTheme('list-add'))
        self.addBtn.setContentsMargins(0, 0, 0, 0)
        self.addBtn.setFixedSize(20, 20)
        addLayout = QtWidgets.QHBoxLayout()
        addLayout.setContentsMargins(0, 0, 0, 0)
        addLayout.addWidget(self.addBtn)
        addLayout.addStretch(1)
        self.layout().addLayout(addLayout)
        self.patternsLayout = QtWidgets.QFormLayout()
        self.patternsLayout.setContentsMargins(0, 0, 0, 0)
        self.layout().addLayout(self.patternsLayout)
        self.addBtn.clicked.connect(self.addPattern)
        self.adjustSize()

    def addPattern(self):
        patternWidget = PatternWidget(self)
        patternWidget.setValue('%{PYTHON_ERROR}')
        patternWidget.setPatternEnable(True)
        self.patternsLayout.addWidget(patternWidget)

    def getPatterns(self):
        patterns = []
        for i in range(0, self.patternsLayout.count()):
            item = self.patternsLayout.itemAt(i).widget()
            if not item.patternEnable():
                continue
            patterns.append(item.getValue())
        return patterns

class InputTreeWidgetItem(QtWidgets.QTreeWidgetItem):

    def __init__(self, parent, name, data):
        QtWidgets.QTreeWidgetItem.__init__(self, parent, name)
        self.__data = data

        self.setText(0, str(name))
        self.setCheckState(0, QtCore.Qt.Checked)

    def getItemData(self):
        return self.__data

class InputTreeWidget(QtWidgets.QTreeWidget):

    def __init__(self, parent=None):

        QtWidgets.QTreeWidget.__init__(self, parent)
        self.setHeaderLabels(['Input files'])
        header = self.header()
        header.setSortIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setSelectionMode(QtWidgets.QTreeWidget.ExtendedSelection)
        self.menu = QtWidgets.QMenu(self)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenuEvent)
        self.setRootIsDecorated(True)
        self.sortByColumn(0, QtCore.Qt.DescendingOrder)

    def contextMenuEvent(self, event=None):
        self.menu.clear()
        self.checkMenu = self.menu.addMenu("Check")
        self.checkMenu.addAction("Selection", self.checkSelectedItems)
        self.checkMenu.addAction("All", lambda: self.setStateAction(QtCore.Qt.Checked))
        self.checkMenu.addAction("None", lambda: self.setStateAction(QtCore.Qt.Unchecked))
        self.checkMenu.addAction("Toggle", self.toggleStateAction)

        self.menu.exec_(QtGui.QCursor.pos())

    def setStateAction(self, state):
        for item in self.getItems():
            item.setCheckState(0, state)

    def toggleStateAction(self):
        items = []
        for item in self.getItems():
            checkState = item.checkState(0)
            if checkState == QtCore.Qt.Checked :
                item.setCheckState(0, QtCore.Qt.Unchecked)
            elif checkState == QtCore.Qt.Unchecked :
                item.setCheckState(0, QtCore.Qt.Checked)

    def checkSelectedItems(self):

        for item in self.getItems():
            if item.isSelected():
                item.setCheckState(0, QtCore.Qt.Checked)
            else :
                item.setCheckState(0, QtCore.Qt.Unchecked)

    def getItems(self):
        items = []
        for i in range(0, self.topLevelItemCount()):
            items.append(self.topLevelItem(i))
        return items

    def setData(self, data):
        self.__data = data

    def update(self, callback=None):

        self.clear()

        items = []
        for i, row in enumerate(self.__data) :
            items.append(InputTreeWidgetItem(None, row['path'], row))
            callback(i/float(len(self.__data))*100)

        self.addTopLevelItems(items)

    def getInputs(self):
        return [ str(i.text(0)) for i in self.getItems() \
                    if i.checkState(0) == QtCore.Qt.Checked ]

class CaptureTreeWidgetItem(QtWidgets.QTreeWidgetItem):

    def __init__(self, parent, name, labels, data):
        QtWidgets.QTreeWidgetItem.__init__(self, parent, [name])

        self.__data = {}

        try :
            self.__data = json.loads(data)
        except Exception:
            pass

        self.setText(0, str(name))

        for i, label in enumerate(labels) :
            if label in self.__data :
                self.setText(labels.index(label),
                        self.__data.get(label, ''))

    def getItemData(self):
        return self.__data

class CaptureTreeWidget(QtWidgets.QTreeWidget):

    def __init__(self, parent=None):

        QtWidgets.QTreeWidget.__init__(self, parent)
        self.setHeaderLabels(['Matches'])
        header = self.header()
        header.setSortIndicatorShown(True)
        self.setSortingEnabled(True)
        self.setSelectionMode(QtWidgets.QTreeWidget.ExtendedSelection)
        self.menu = QtWidgets.QMenu(self)
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.contextMenuEvent)
        self.setRootIsDecorated(True)
        self.sortByColumn(0, QtCore.Qt.DescendingOrder)

    def contextMenuEvent(self, event):
        pass

    def update(self, captures):

        self.clear()

        labels = ['Matches']
        self.setColumnCount(len(labels))
        self.setHeaderLabels(labels)

        for pattern, datas in captures.iteritems() :
            patternitem = QtWidgets.QTreeWidgetItem([pattern])
            f = patternitem.font(0)
            f.setBold(True)
            patternitem.setFont(0, f)
            self.addTopLevelItem(patternitem)
            children = []
            for i, (inputname, capture) in enumerate(datas) :
                if not i :
                    labels.extend(sorted(json.loads(capture).keys()))
                children.append(CaptureTreeWidgetItem(None, inputname, labels, capture))
            patternitem.addChildren(children)
            patternitem.setExpanded(True)

        self.setColumnCount(len(labels))
        self.setHeaderLabels(labels)
        self.resizeColumnToContents(0)

class LogParserWidget(QtWidgets.QWidget):
    ''' LogParser class:

    '''
    def __init__(self, parent=None, root=None):
        QtWidgets.QWidget.__init__(self, parent)

        self.__root = root
        self.title = 'LogParser %s' % os.getenv('REZ_LOGPARSER_VERSION', '')
        self.setWindowTitle(self.title)

        self.build()
        self.connection()
        self.update()

    def buildInputsWidget(self):

        self.inputsWidget = QtWidgets.QWidget()
        self.inputsWidget.setContentsMargins(0, 0, 0, 0)
        self.inputsWidget.setLayout(QtWidgets.QVBoxLayout())
        self.inputsWidget.layout().setContentsMargins(0, 0, 0, 0)

        self.rootWidget = QtWidgets.QWidget()
        self.rootWidget.setLayout(QtWidgets.QHBoxLayout())
        self.rootWidget.setContentsMargins(0, 0, 0, 0)
        self.rootWidget.layout().setContentsMargins(0, 0, 0, 0)

        self.rootWidget.layout().addWidget(QtWidgets.QLabel('Root'))
        self.rootDirectory = QtWidgets.QLineEdit()
        self.rootDirectory.setText(self.__root or '')
        self.rootWidget.layout().addWidget(self.rootDirectory)
        self.rootDirectoryBtn = QtWidgets.QPushButton()
        self.rootDirectoryBtn.setFixedSize(25, 25)
        self.rootDirectoryBtn.setIcon(QtGui.QIcon.fromTheme('folder'))
        self.rootWidget.layout().addWidget(self.rootDirectoryBtn)

        self.inputProgressBar = QtWidgets.QProgressBar()
        self.inputProgressBar.setMinimum(0)
        self.inputProgressBar.setMaximum(100)

        self.inputTreeWidget = InputTreeWidget()

        self.inputCmdLayout = QtWidgets.QHBoxLayout()
        self.updateInputsBtn = QtWidgets.QPushButton()
        self.updateInputsBtn.setIcon(QtGui.QIcon.fromTheme('view-refresh'))
        self.updateInputsBtn.setFixedSize(25, 25)
        self.inputCmdLayout.addWidget(self.inputProgressBar)
        self.inputCmdLayout.addWidget(self.updateInputsBtn)

        self.inputsWidget.layout().addWidget(self.rootWidget)
        self.inputsWidget.layout().addLayout(self.inputCmdLayout)
        self.inputsWidget.layout().addWidget(self.inputTreeWidget)

    def buildMatchesWidget(self):

        self.matchesWidget = QtWidgets.QWidget()
        self.matchesWidget.setLayout(QtWidgets.QVBoxLayout())
        self.matchConfigsWidget = MatchConfigsWidget()
        self.matchesWidget.layout().addWidget(self.matchConfigsWidget)


    def buildCapturesWidget(self):

        self.capturesWidget = QtWidgets.QWidget()
        self.capturesWidget.setLayout(QtWidgets.QVBoxLayout())
        self.captureProgressBar = QtWidgets.QProgressBar()
        self.captureProgressBar.setMinimum(0)
        self.captureProgressBar.setMaximum(100)

        self.captureTreeWidget = CaptureTreeWidget()

        self.captureCmdLayout = QtWidgets.QHBoxLayout()
        self.parseBtn = QtWidgets.QPushButton()
        self.parseBtn.setIcon(QtGui.QIcon.fromTheme('system-search'))
        self.parseBtn.setFixedSize(25, 25)
        self.captureCmdLayout.addWidget(self.captureProgressBar)
        self.captureCmdLayout.addWidget(self.parseBtn)

        self.capturesWidget.layout().addLayout(self.captureCmdLayout)
        self.capturesWidget.layout().addWidget(self.captureTreeWidget)


    def handleOutput(self, text, stdout):
        #color = self.terminal.textColor()
        #self.terminal.setTextColor(color if stdout else self._err_color)
        self.consoleWidget.moveCursor(QtGui.QTextCursor.End)
        self.consoleWidget.insertPlainText(text)
        #self.terminal.setTextColor(color)

    def buildConsoleWidget(self):

        self.consoleWidget = QtWidgets.QTextBrowser(self)
        stdout = OutputWrapper(self, True)
        stdout.outputWritten.connect(self.handleOutput)

    def build(self):
        self.setLayout(QtWidgets.QVBoxLayout())

        self.buildInputsWidget()
        self.buildMatchesWidget()
        self.buildCapturesWidget()
        self.buildConsoleWidget()

        self.vSplitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.vSplitter.addWidget(self.matchesWidget)
        self.vSplitter.addWidget(self.capturesWidget)
        self.vSplitter.addWidget(self.consoleWidget)
        self.vSplitter.setSizes([150, 600, 100])

        self.hSplitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        self.hSplitter.addWidget(self.inputsWidget)
        self.hSplitter.addWidget(self.vSplitter)
        self.hSplitter.setSizes([300, 300])

        self.layout().addWidget(self.hSplitter)

    def inputDialog(self):

        result = QtWidgets.QFileDialog.getExistingDirectory(self, "Log Directory",
                self.__root or '', QtWidgets.QFileDialog.ShowDirsOnly)

        root = str(result)
        if os.path.exists(root):
            self.rootDirectory.setText(root)

    def updateInputs(self):

        self.inputProgressBar.setValue(0)

        root = str(self.rootDirectory.text())

        if not os.path.exists(root):
            return

        logfiles = sorted([ { 'path' : os.path.join(root, f)} for f in os.listdir(root) \
                if os.path.isfile(os.path.join(root, f))])

        self.inputTreeWidget.setData(logfiles)
        self.inputTreeWidget.update(self.inputProgressBar.setValue)

        self.inputProgressBar.setValue(100)

    def parse(self):

        self.captureProgressBar.setValue(0)
        matchconfigs = [ MatchConfig.fromdict(d) for d in \
                self.matchConfigsWidget.getMatchConfigs()]

        inputfiles = self.inputTreeWidget.getInputs()

        pg = Program( name='LogParserUI',
                matchconfigs=matchconfigs)

        self.__stop = False

        for i, inputfile in enumerate(inputfiles) :

            if self.__stop :
                self.captureTreeWidget.update(pg.getcaptures())
                return

            pg.addinputfile(filepath=inputfile)
            self.captureProgressBar.setValue(i/float(len(inputfiles))*100)
            QtGui.qApp.processEvents()

        self.captureTreeWidget.update(pg.getcaptures())

        self.captureProgressBar.setValue(100)

    def keyPressEvent(self, event):

        if event.key() == QtCore.Qt.Key_Escape:
            self.__stop = True

    def update(self):

        self.updateInputs()

    def connection(self):
        self.rootDirectoryBtn.clicked.connect(self.inputDialog)
        self.updateInputsBtn.clicked.connect(self.updateInputs)
        self.parseBtn.clicked.connect(self.parse)

logarserUI = None
def LogparserUI(root=None):
    ''' Show Logparser UI

    '''
    global logarserUI

    if logarserUI is not None:
        logarserUI = None

    logarserUI = LogParserWidget(root=root)
    logarserUI.setWindowFlags(QtCore.Qt.Window)
    logarserUI.show()


def main():
    ''' LogParserUI command line

    '''
    import argparse

    parser = argparse.ArgumentParser(description="LogparserUI command line",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter)


    #parser.add_argument("-c", "--config", dest="config", default=os.environ.get('DEFAULT_CONFIG_FILE'), type=str,
    #        help="Specify config file to use arg --config /../configs/pythonprogram.config")

    #parser.add_argument("-p", "--patterns", dest="patterns", type=str, nargs="*",
    #        help="Specify pattern names --patterns PYTHON_ERROR")

    #parser.add_argument("-m", "--matches", dest="matches", type=str, nargs="*",
    #        help="Specify matches --matches 'Date : %%{DATE}[- ]%%{HOUR}:%%{MINUTE}'")

    #parser.add_argument("-a", "--action", dest="action", type=str,
    #        help="Perform specific action on match --action %%{@JSON} or %%{@MATCH} or %%{@LINE}")

    parser.add_argument("-r", "--root", dest="root", default=None, type=str,
            help="Specify root directory to analyze log files arg --root /../logs")

    #parser.add_argument("-f", "--logfile", dest="logfile", type=str,
    #        help="Specify a log file to analyze --file /../logs/1234.log")

    #parser.add_argument("-v", "--verbose", dest="verbose", action="store_true",
    #        help="Turns on verbose output")

    #parser.add_argument("-o", "--output", dest="output", type=str,
    #        help="Save as output file report")


    args = parser.parse_args()

    app = QtGui.QApplication(sys.argv)
    LogparserUI(**vars(args))
    sys.exit(app.exec_())

if __name__ == '__main__':
    try :
        main()
    except Exception, e :
        print "ERROR %s\n" % ( e )
        exit(1)
