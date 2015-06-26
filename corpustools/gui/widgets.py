
import sys
import re
import operator
from collections import OrderedDict, defaultdict
from itertools import combinations, permutations, chain, product
from corpustools.gui.views import TableWidget

from .imports import *
from .views import TableWidget
from .models import SegmentPairModel, EnvironmentModel, FilterModel

#from .corpusgui import AddTierDialog
from .delegates import SwitchDelegate

from corpustools.corpus.classes import Attribute, EnvironmentFilter
from corpustools.corpus.io.helper import AnnotationType, get_corpora_list, corpus_name_to_path, NUMBER_CHARACTERS


def truncate_string(string, length = 10):
    return (string[:length] + '...') if len(string) > length + 3 else string

class NonScrollingComboBox(QComboBox):
    def __init__(self, parent = None):
        QComboBox.__init__(self, parent)
        self.setFocusPolicy(Qt.StrongFocus)

    def wheelEvent(self, e):
        e.ignore()

class CorpusSelect(QComboBox):
    def __init__(self, parent, settings):
        QComboBox.__init__(self,parent)
        self.settings = settings
        self.addItem('None')

        for i,s in enumerate(get_corpora_list(self.settings['storage'])):
            self.addItem(s)

    def value(self):
        val = self.currentText()
        if val == 'None':
            return ''
        return val

    def path(self):
        if self.value() != '':
            return corpus_name_to_path(self.settings['storage'],self.value())
        return None

class ParsingDialog(QDialog):
    def __init__(self, parent, annotation_type, att_type):
        QDialog.__init__(self, parent)
        self.characters = annotation_type.characters
        self.setWindowTitle('Parsing {}'.format(annotation_type.name))

        layout = QFormLayout()
        self.example = QLabel(' '.join(annotation_type[:5]))
        self.example.setWordWrap(True)
        layout.addRow('Example:', self.example)

        self.punctuationWidget = PunctuationWidget(annotation_type.punctuation)
        self.punctuationWidget.setPunctuation(annotation_type.ignored_characters)
        self.delimiterWidget = QLineEdit()
        self.morphDelimiterWidget = PunctuationWidget(annotation_type.punctuation & set('-='),
                                                        'Morpheme delimiter')
        self.morphDelimiterWidget.setPunctuation(annotation_type.morph_delimiters)
        self.digraphWidget = DigraphWidget()
        self.numberBehaviorSelect = QComboBox()
        self.numberBehaviorSelect.addItem('Same as other characters')
        self.numberBehaviorSelect.addItem('Tone')
        self.numberBehaviorSelect.addItem('Stress')
        self.numberBehaviorSelect.currentIndexChanged.connect(self.updatePunctuation)

        self.digraphWidget.characters = annotation_type.characters
        self.digraphWidget.setDigraphs(annotation_type.digraphs)

        self.punctuationWidget.selectionChanged.connect(self.punctuationChanged)
        delimiter = annotation_type.delimiter
        if delimiter is not None:
            self.delimiterWidget.setText(delimiter)
            self.punctuationWidget.updateButtons([delimiter])
        self.delimiterWidget.textChanged.connect(self.updatePunctuation)
        if att_type == 'tier':
            layout.addRow('Transcription delimiter',self.delimiterWidget)
        layout.addRow(self.morphDelimiterWidget)
        self.morphDelimiterWidget.selectionChanged.connect(self.updatePunctuation)

        if att_type == 'tier':
            if len(self.characters & set(['0','1','2'])):
                layout.addRow('Number parsing', self.numberBehaviorSelect)
            else:
                layout.addRow('Number parsing', QLabel('No numbers'))
        layout.addRow(self.punctuationWidget)
        if att_type == 'tier':
            layout.addRow(self.digraphWidget)

        self.acceptButton = QPushButton('Ok')
        self.cancelButton = QPushButton('Cancel')
        acLayout = QHBoxLayout()
        acLayout.addWidget(self.acceptButton)
        acLayout.addWidget(self.cancelButton)
        self.acceptButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(acLayout)

        layout.addRow(acFrame)

        self.setLayout(layout)

    def ignored(self):
        return self.punctuationWidget.value()

    def morphDelimiters(self):
        return self.morphDelimiterWidget.value()

    def transDelimiter(self):
        return self.delimiterWidget.text()

    def numberBehavior(self):
        if self.numberBehaviorSelect.currentIndex() == 0:
            return None
        return self.numberBehaviorSelect.currentText().lower()

    def digraphs(self):
        return self.digraphWidget.value()

    def updatePunctuation(self):
        delimiter = self.delimiterWidget.text()
        if delimiter == '':
            delimiter = []
        else:
            delimiter = [delimiter]
        self.morphDelimiterWidget.updateButtons(delimiter, emit = False)

        delimiter += self.morphDelimiterWidget.value()
        self.punctuationWidget.updateButtons(delimiter)

    def punctuationChanged(self):
        self.digraphWidget.characters = self.characters - \
                                        self.punctuationWidget.value() - \
                                        self.morphDelimiterWidget.value()
        if self.numberBehaviorSelect.currentIndex() != 0:
            self.digraphWidget.characters -= NUMBER_CHARACTERS
        delimiter = self.delimiterWidget.text()
        if delimiter != '':
            self.digraphWidget.characters -= set([delimiter])

class AnnotationTypeWidget(QGroupBox):
    def __init__(self, annotation_type, parent = None,
                ignorable = True):
        #if title is None:
        #    title = 'Annotation type details'
        QGroupBox.__init__(self, annotation_type.name, parent)

        main = QHBoxLayout()

        #main.addWidget(QLabel(annotation_type.name))

        self.annotation_type = annotation_type

        proplayout = QFormLayout()

        self.nameWidget = QLineEdit()

        proplayout.addRow('Name',self.nameWidget)

        self.typeWidget = NonScrollingComboBox()
        self.typeWidget.addItem('Orthography')
        self.typeWidget.addItem('Transcription')
        self.typeWidget.addItem('Other (numeric)')
        self.typeWidget.addItem('Other (character)')
        if ignorable:
            self.typeWidget.addItem('Notes (ignored)')
        self.typeWidget.setCurrentIndex(3)
        proplayout.addRow('Annotation type',self.typeWidget)
        self.typeWidget.currentIndexChanged.connect(self.typeChanged)

        self.associationWidget = RadioSelectWidget('Word association',
                                            OrderedDict([
                                            ('Associate this with the lexical item','type'),
                                            ('Allow this property to vary within lexical items','token'),]))

        proplayout.addRow(self.associationWidget)

        self.delimiterLabel = QLabel('None')
        if self.annotation_type.delimiter is not None:
            self.delimiterLabel.setText(self.annotation_type.delimiter)
        self.morphDelimiterLabel = QLabel('None')

        self.ignoreLabel = QLabel('None')

        self.digraphLabel = QLabel('None')

        self.numberLabel = QLabel('None')

        parselayout = QFormLayout()

        self.editButton = QPushButton('Edit parsing settings')
        self.editButton.clicked.connect(self.editParsingProperties)

        parselayout.addRow('Transcription delimiter', self.delimiterLabel)
        parselayout.addRow('Morpheme delimiter', self.morphDelimiterLabel)
        parselayout.addRow('Number parsing', self.numberLabel)
        parselayout.addRow('Ignored characters', self.ignoreLabel)
        parselayout.addRow('Multicharacter segments',self.digraphLabel)
        parselayout.addRow(self.editButton)

        main.addLayout(proplayout)
        main.addLayout(parselayout)


        if self.annotation_type.token:
            self.associationWidget.click(1)
        if self.annotation_type.anchor:
            self.typeWidget.setCurrentIndex(0)
        elif self.annotation_type.base or self.annotation_type.delimiter is not None:
            self.typeWidget.setCurrentIndex(1)
        elif self.annotation_type.attribute.att_type == 'numeric':
            self.typeWidget.setCurrentIndex(2)
        #self.attributeWidget = AttributeWidget(attribute = self.annotation_type.attribute)

        self.nameWidget.setText(self.annotation_type.attribute.display_name)
        #if show_attribute:
        #    main.addWidget(self.attributeWidget)

        self.setLayout(main)

        self.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Minimum)


        self.typeChanged()

    def typeChanged(self):
        if self.typeWidget.currentIndex() in [0, 1]:
            self.editButton.setEnabled(True)
            self.updateParsingLabels()
        else:
            self.editButton.setEnabled(False)
        self.suggestName()

    def suggestName(self):
        if self.typeWidget.currentText() == 'Orthography':
            self.nameWidget.setText('Spelling')
        elif self.typeWidget.currentText() == 'Transcription':
            self.nameWidget.setText('Transcription')
        elif self.typeWidget.currentText() == 'Other (numeric)':
            self.nameWidget.setText(self.annotation_type.attribute.display_name)
        elif self.typeWidget.currentText() == 'Other (character)':
            self.nameWidget.setText(self.annotation_type.attribute.display_name)
        elif self.typeWidget.currentText() == 'Notes (ignored)':
            self.nameWidget.setText('Ignored')


    def updateParsingLabels(self):
        if self.typeWidget.currentIndex() == 0:
            self.digraphLabel.setText('N/A')
            self.numberLabel.setText('N/A')
            self.delimiterLabel.setText('N/A')
            self.morphDelimiterLabel.setText('N/A')
        elif self.typeWidget.currentIndex() == 1:
            if self.annotation_type.digraphs:
                self.digraphLabel.setText(truncate_string(' '.join(self.annotation_type.digraphs)))
            else:
                self.digraphLabel.setText('None')
            if self.annotation_type.morph_delimiters:
                self.morphDelimiterLabel.setText(
                        truncate_string(' '.join(
                            self.annotation_type.morph_delimiters
                            )
                        ))
            else:
                self.morphDelimiterLabel.setText('None')
            if self.annotation_type.trans_delimiter:
                self.delimiterLabel.setText(truncate_string(' '.join(self.annotation_type.trans_delimiter)))
            else:
                self.delimiterLabel.setText('None')
            if self.annotation_type.number_behavior:
                self.numberLabel.setText(str(self.annotation_type.number_behavior))
            else:
                self.numberLabel.setText('None')
        if self.annotation_type.ignored_characters:
            self.ignoreLabel.setText(truncate_string(' '.join(self.annotation_type.ignored_characters)))
        else:
            self.ignoreLabel.setText('None')

    def editParsingProperties(self):
        if self.typeWidget.currentText() == 'Orthography':
            atype = 'spelling'
        elif self.typeWidget.currentText() == 'Transcription':
            atype = 'tier'
        else:
            return
        dialog = ParsingDialog(self, self.annotation_type, atype)
        if dialog.exec_():
            self.annotation_type.ignored_characters = dialog.ignored()
            self.annotation_type.digraphs = dialog.digraphs()
            self.annotation_type.morph_delimiters = dialog.morphDelimiters()
            d = dialog.transDelimiter()
            if d == '':
                self.annotation_type.trans_delimiter = None
            else:
                self.annotation_type.trans_delimiter = d
            self.annotation_type.number_behavior = dialog.numberBehavior()
            self.updateParsingLabels()

    def value(self):
        a = self.annotation_type
        a.token = self.associationWidget.value() == 'token'
        display_name = self.nameWidget.text()
        a.anchor = False
        a.base = False
        name = Attribute.sanitize_name(display_name)
        if self.typeWidget.currentText() == 'Orthography':
            a.anchor = True
            a.base = False
            name = 'spelling'
            atype = 'spelling'
        elif self.typeWidget.currentText() == 'Transcription':
            a.anchor = False
            a.base = True
            atype = 'tier'
        elif self.typeWidget.currentText() == 'Other (numeric)':
            atype = 'numeric'
        elif self.typeWidget.currentText() == 'Other (character)':
            atype = 'factor'
        elif self.typeWidget.currentText() == 'Notes (ignored)':
            a.ignored = True
        if not a.ignored:
            a.attribute = Attribute(name, atype, display_name)
        return a

class AttributeWidget(QGroupBox):
    def __init__(self, attribute = None, exclude_tier = False,
                disable_name = False, parent = None):
        QGroupBox.__init__(self, 'Column details', parent)

        main = QFormLayout()

        self.nameWidget = QLineEdit()

        main.addRow('Name of column',self.nameWidget)

        if attribute is not None:
            self.attribute = attribute
            self.nameWidget.setText(attribute.display_name)
        else:
            self.attribute = None

        if disable_name:
            self.nameWidget.setEnabled(False)

        self.typeWidget = NonScrollingComboBox()
        for at in Attribute.ATT_TYPES:
            if exclude_tier and at == 'tier':
                continue
            self.typeWidget.addItem(at.title())

        main.addRow('Type of column',self.typeWidget)

        self.useAs = NonScrollingComboBox()
        self.useAs.addItem('Custom column')
        self.useAs.addItem('Spelling')
        self.useAs.addItem('Transcription')
        self.useAs.addItem('Frequency')
        self.useAs.currentIndexChanged.connect(self.updateUseAs)

        for i in range(self.useAs.count()):
            if attribute is not None and self.useAs.itemText(i).lower() == attribute.name:
                self.useAs.setCurrentIndex(i)
                if attribute.name == 'transcription' and attribute.att_type != 'tier':
                    attribute.att_type = 'tier'

        for i in range(self.typeWidget.count()):
            if attribute is not None and self.typeWidget.itemText(i) == attribute.att_type.title():
                self.typeWidget.setCurrentIndex(i)

        main.addRow('Use column as', self.useAs)

        self.setLayout(main)

        self.setSizePolicy(QSizePolicy.Minimum,QSizePolicy.Minimum)

    def type(self):
        return self.typeWidget.currentText().lower()

    def updateUseAs(self):
        t = self.useAs.currentText().lower()
        if t == 'custom column':
            self.typeWidget.setEnabled(True)
        else:
            for i in range(self.typeWidget.count()):
                if t == 'spelling' and self.typeWidget.itemText(i) == 'Spelling':
                    self.typeWidget.setCurrentIndex(i)
                elif t == 'transcription' and self.typeWidget.itemText(i) == 'Tier':
                    self.typeWidget.setCurrentIndex(i)
                elif t == 'frequency' and self.typeWidget.itemText(i) == 'Numeric':
                    self.typeWidget.setCurrentIndex(i)
            self.typeWidget.setEnabled(False)

    def use(self):
        return self.useAs.currentText().lower()

    def value(self):
        display = self.nameWidget.text()
        cat = self.type()
        use = self.use()
        if use.startswith('custom'):
            name = Attribute.sanitize_name(display)
        else:
            name = use
        att = Attribute(name, cat, display)
        return att

class ThumbListWidget(QListWidget):
    def __init__(self, ordering, parent=None):
        super(ThumbListWidget, self).__init__(parent)
        self.ordering = ordering
        #self.setIconSize(QSize(124, 124))
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAcceptDrops(True)


    def dropEvent(self, event):
        event.setDropAction(Qt.MoveAction)
        super(ThumbListWidget, self).dropEvent(event)

class FactorFilter(QWidget):
    def __init__(self, attribute,parent=None):

        QWidget.__init__(self,parent)

        layout = QHBoxLayout()
        levels = sorted(attribute.range)
        self.sourceWidget = ThumbListWidget(levels)
        for l in levels:
            self.sourceWidget.addItem(l)

        sourceFrame = QGroupBox('Available levels')
        l = QVBoxLayout()
        l.addWidget(self.sourceWidget)
        sourceFrame.setLayout(l)

        layout.addWidget(sourceFrame)

        buttonLayout = QVBoxLayout()
        self.addOneButton = QPushButton('>')
        self.addOneButton.clicked.connect(self.addOne)
        self.addAllButton = QPushButton('>>')
        self.addAllButton.clicked.connect(self.addAll)

        self.clearOneButton = QPushButton('<')
        self.clearOneButton.clicked.connect(self.clearOne)
        self.clearAllButton = QPushButton('<<')
        self.clearAllButton.clicked.connect(self.clearAll)

        buttonLayout.addWidget(self.addOneButton, alignment = Qt.AlignCenter)
        buttonLayout.addWidget(self.addAllButton, alignment = Qt.AlignCenter)
        buttonLayout.addWidget(self.clearOneButton, alignment = Qt.AlignCenter)
        buttonLayout.addWidget(self.clearAllButton, alignment = Qt.AlignCenter)

        buttonFrame = QFrame()
        buttonFrame.setLayout(buttonLayout)
        layout.addWidget(buttonFrame, alignment = Qt.AlignCenter)

        self.targetWidget = ThumbListWidget(levels)

        targetFrame = QGroupBox('Included levels')
        l = QVBoxLayout()
        l.addWidget(self.targetWidget)
        targetFrame.setLayout(l)

        layout.addWidget(targetFrame)

        self.setLayout(layout)

    def addOne(self):
        items = self.sourceWidget.selectedItems()
        for i in items:
            item = self.sourceWidget.takeItem(self.sourceWidget.row(i))
            self.targetWidget.addItem(item)

    def addAll(self):
        items = [self.sourceWidget.item(i) for i in range(self.sourceWidget.count())]
        for i in items:
            item = self.sourceWidget.takeItem(self.sourceWidget.row(i))
            self.targetWidget.addItem(item)

    def clearOne(self):
        items = self.targetWidget.selectedItems()
        for i in items:
            item = self.targetWidget.takeItem(self.targetWidget.row(i))
            self.sourceWidget.addItem(item)

    def clearAll(self):
        items = [self.targetWidget.item(i) for i in range(self.targetWidget.count())]
        for i in items:
            item = self.targetWidget.takeItem(self.targetWidget.row(i))
            self.sourceWidget.addItem(item)

    def value(self):
        items = set([self.targetWidget.item(i).text() for i in range(self.targetWidget.count())])
        return items

class NumericFilter(QWidget):
    conditionalDisplay = ('equals','does not equal','greater than',
                    'greater than or equal to', 'less than',
                    'less than or equal to')
    conditionals = (operator.eq, operator.ne, operator.gt, operator.ge,
                    operator.lt, operator.le)
    def __init__(self,parent=None):

        QWidget.__init__(self,parent)

        layout = QHBoxLayout()

        self.conditionalSelect = QComboBox()
        for c in self.conditionalDisplay:
            self.conditionalSelect.addItem(c)

        layout.addWidget(self.conditionalSelect)

        self.valueEdit = QLineEdit()

        layout.addWidget(self.valueEdit)

        self.setLayout(layout)

    def value(self):
        ind = self.conditionalSelect.currentIndex()

        return self.conditionals[ind], self.valueEdit.text()

class AttributeFilterDialog(QDialog):
    def __init__(self, attributes,parent=None):
        QDialog.__init__(self,parent)

        self.attributes = list()

        layout = QVBoxLayout()

        mainlayout = QHBoxLayout()

        self.selectWidget = QComboBox()
        for a in attributes:
            if a.att_type in ['factor','numeric']:
                self.attributes.append(a)
                self.selectWidget.addItem(a.display_name)

        self.selectWidget.currentIndexChanged.connect(self.updateFrame)

        selectFrame = QGroupBox('Attribute to filter')

        selectlayout = QVBoxLayout()
        selectlayout.addWidget(self.selectWidget)
        selectFrame.setLayout(selectlayout)

        mainlayout.addWidget(selectFrame)


        self.filterWidget = NumericFilter()
        filterLayout = QVBoxLayout()
        filterLayout.addWidget(self.filterWidget)

        self.filterFrame = QGroupBox('Filter')
        self.filterFrame.setLayout(filterLayout)

        mainlayout.addWidget(self.filterFrame)

        mainframe = QFrame()

        mainframe.setLayout(mainlayout)

        layout.addWidget(mainframe)

        self.oneButton = QPushButton('Add')
        self.anotherButton = QPushButton('Add and create another')
        self.cancelButton = QPushButton('Cancel')
        acLayout = QHBoxLayout()
        acLayout.addWidget(self.oneButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.anotherButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.cancelButton, alignment = Qt.AlignLeft)
        self.oneButton.clicked.connect(self.one)
        self.anotherButton.clicked.connect(self.another)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(acLayout)

        layout.addWidget(acFrame, alignment = Qt.AlignLeft)

        self.setLayout(layout)
        #self.setFixedSize(self.sizeHint())
        self.setWindowTitle('Create {}'.format(parent.name))

    def updateFrame(self):
        index = self.selectWidget.currentIndex()
        a = self.attributes[index]
        self.filterWidget.deleteLater()
        if a.att_type == 'numeric':
            self.filterWidget = NumericFilter()
            self.filterFrame.layout().addWidget(self.filterWidget)
        elif a.att_type == 'factor':
            self.filterWidget = FactorFilter(a)
            self.filterFrame.layout().addWidget(self.filterWidget)
        self.resize(self.sizeHint())

    def one(self):
        self.addOneMore = False
        self.accept()

    def another(self):
        self.addOneMore = True
        self.accept()

    def accept(self):
        index = self.selectWidget.currentIndex()
        a = self.attributes[index]
        val = self.filterWidget.value()
        if a.att_type == 'numeric':
            comp = val[0]
            try:
                value = float(val[1])
            except ValueError:
                reply = QMessageBox.critical(self,
                        "Invalid information", "Please specify a number.")
                return
            if (comp in [operator.gt, operator.ge] and value > a.range[1]) or \
                (comp in [operator.lt,operator.le] and value < a.range[0]) or \
                (comp in [operator.eq,operator.ne] and (value < a.range[0] or value > a.range[1])):
                reply = QMessageBox.critical(self,
                        "Invalid information", "The value specified ({}) for column '{}' is outside its range of {}-{}.".format(value,str(a),a.range[0],a.range[1]))
                return
            self.filter = (a, comp, value)
        elif a.att_type == 'factor':
            self.filter = (a, val)

        QDialog.accept(self)

    def reject(self):
        self.addOneMore = False
        QDialog.reject(self)

class AttributeFilterWidget(QGroupBox):
    name = 'filter'
    def __init__(self, corpus, parent = None):
        QGroupBox.__init__(self,'Filter corpus',parent)
        self.attributes = corpus.attributes

        vbox = QVBoxLayout()

        self.addButton = QPushButton('Add {}'.format(self.name))
        self.addButton.clicked.connect(self.filtPopup)
        self.removeButton = QPushButton('Remove selected {}s'.format(self.name))
        self.removeButton.clicked.connect(self.removeFilt)
        self.addButton.setAutoDefault(False)
        self.addButton.setDefault(False)
        self.removeButton.setAutoDefault(False)
        self.removeButton.setDefault(False)

        self.table = TableWidget()
        self.table.setSortingEnabled(False)
        try:
            self.table.horizontalHeader().setClickable(False)
            self.table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        except AttributeError:
            self.table.horizontalHeader().setSectionsClickable(False)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setModel(FilterModel())
        self.table.resizeColumnsToContents()

        vbox.addWidget(self.addButton)
        vbox.addWidget(self.removeButton)
        vbox.addWidget(self.table)

        self.setLayout(vbox)

    def filtPopup(self):
        dialog = AttributeFilterDialog(self.attributes,self)
        addOneMore = True
        while addOneMore:
            result = dialog.exec_()
            if result:
                self.table.model().addRow([dialog.filter])
            addOneMore = dialog.addOneMore

    def removeFilt(self):
        select = self.table.selectionModel()
        if select.hasSelection():
            selected = select.selectedRows()
            self.table.model().removeRows([s.row() for s in selected])

    def value(self):
        return [x[0] for x in self.table.model().filters]

class TierWidget(QGroupBox):
    def __init__(self, corpus, parent = None, include_spelling = False):
        QGroupBox.__init__(self,'Tier',parent)
        self.spellingIncluded = include_spelling
        self.spellingEnabled = include_spelling
        layout = QVBoxLayout()

        self.tierSelect = QComboBox()
        self.atts = list()
        self.spellingName = corpus.attributes[0].display_name
        if include_spelling:
            self.atts.append(corpus.attributes[0])
            self.tierSelect.addItem(corpus.attributes[0].display_name)
        for a in corpus.attributes:
            if corpus.has_transcription and a.att_type == 'tier':
                self.atts.append(a)
                self.tierSelect.addItem(a.display_name)
        layout.addWidget(self.tierSelect)
        self.setLayout(layout)

    def setSpellingEnabled(self, b):
        self.spellingEnabled = b
        if b:
            if self.tierSelect.itemText(0) != self.spellingName:
                self.tierSelect.insertItem(0,self.spellingName)
        else:
            if self.tierSelect.itemText(0) == self.spellingName:
                self.tierSelect.removeItem(0)

    def value(self):
        index = self.tierSelect.currentIndex()
        if not self.spellingEnabled and self.spellingIncluded:
            index += 1
        return self.atts[index].name

    def displayValue(self):
        index = self.tierSelect.currentIndex()
        if not self.spellingEnabled and self.spellingIncluded:
            index += 1
        return self.atts[index].display_name

class PunctuationWidget(QGroupBox):
    selectionChanged = Signal()
    def __init__(self, punctuation, title = 'Punctuation to ignore', parent = None):
        QGroupBox.__init__(self, title, parent)

        self.btnGroup = QButtonGroup()
        self.btnGroup.setExclusive(False)
        layout = QVBoxLayout()
        self.warning = QLabel('None detected (other than any transcription delimiters)')
        if len(punctuation) > 0:
            self.warning.hide()
        layout.addWidget(self.warning)
        box = QGridLayout()

        row = 0
        col = 0
        for s in punctuation:
            btn = QPushButton(s)
            btn.clicked.connect(self.selectionChanged.emit)
            btn.setAutoDefault(False)
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            btn.setMaximumWidth(btn.fontMetrics().boundingRect(s).width() + 14)
            btn.setFocusPolicy(Qt.NoFocus)

            box.addWidget(btn,row,col)
            self.btnGroup.addButton(btn)
            col += 1
            if col > 11:
                col = 0
                row += 1
        boxFrame = QFrame()
        boxFrame.setLayout(box)
        layout.addWidget(boxFrame)

        buttonlayout = QHBoxLayout()
        self.checkAll = QPushButton('Check all')
        self.checkAll.setAutoDefault(False)
        self.checkAll.clicked.connect(self.check)
        self.uncheckAll = QPushButton('Uncheck all')
        self.uncheckAll.setAutoDefault(False)
        self.uncheckAll.clicked.connect(self.uncheck)

        if len(punctuation) < 2:
            self.checkAll.hide()
            self.uncheckAll.hide()
        buttonlayout.addWidget(self.checkAll, alignment = Qt.AlignLeft)
        buttonlayout.addWidget(self.uncheckAll, alignment = Qt.AlignLeft)
        buttonframe = QFrame()
        buttonframe.setLayout(buttonlayout)

        layout.addWidget(buttonframe)
        self.setLayout(layout)

    def updateButtons(self, to_ignore, emit = True):
        count_visible = 0
        for b in self.btnGroup.buttons():
            if b.text() in to_ignore:
                b.setChecked(False)
                b.hide()
            else:
                b.show()
            if not b.isHidden():
                count_visible += 1
        if count_visible == 0:
            self.warning.show()
        else:
            self.warning.hide()
        if count_visible < 2:
            self.checkAll.hide()
            self.uncheckAll.hide()
        else:
            self.checkAll.show()
            self.uncheckAll.show()
        if emit:
            self.selectionChanged.emit()

    def setPunctuation(self, punc):
        for b in self.btnGroup.buttons():
            if b.text() in punc:
                b.setChecked(True)
        self.selectionChanged.emit()

    def check(self):
        for b in self.btnGroup.buttons():
            b.setChecked(True)
        self.selectionChanged.emit()

    def uncheck(self):
        for b in self.btnGroup.buttons():
            b.setChecked(False)
        self.selectionChanged.emit()

    def value(self):
        value = []
        for b in self.btnGroup.buttons():
            if b.isChecked():
                t = b.text()
                value.append(t)
        return set(value)

class DigraphDialog(QDialog):
    def __init__(self, characters, parent = None):
        QDialog.__init__(self, parent)
        layout = QFormLayout()
        self.digraphLine = QLineEdit()
        layout.addRow(QLabel('Multicharacter segment'),self.digraphLine)
        symbolframe = QGroupBox('Characters')
        box = QGridLayout()

        row = 0
        col = 0
        self.buttons = list()
        for s in characters:
            btn = QPushButton(s)
            btn.clicked.connect(self.addCharacter)
            btn.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
            btn.setMaximumWidth(btn.fontMetrics().boundingRect(s).width() + 14)
            self.buttons.append(btn)
            box.addWidget(btn,row,col)
            col += 1
            if col > 11:
                col = 0
                row += 1
        symbolframe.setLayout(box)
        layout.addRow(symbolframe)
        self.oneButton = QPushButton('Add')
        self.anotherButton = QPushButton('Add and create another')
        self.cancelButton = QPushButton('Cancel')
        acLayout = QHBoxLayout()
        acLayout.addWidget(self.oneButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.anotherButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.cancelButton, alignment = Qt.AlignLeft)
        self.oneButton.clicked.connect(self.one)
        self.anotherButton.clicked.connect(self.another)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(acLayout)

        layout.addRow(acFrame)
        self.setLayout(layout)
        self.setFixedSize(self.sizeHint())
        self.setWindowTitle('Construct segment')

    def addCharacter(self):
        self.digraphLine.setText(self.digraphLine.text()+self.sender().text())

    def one(self):
        self.addOneMore = False
        self.accept()

    def another(self):
        self.addOneMore = True
        self.accept()

    def value(self):
        return self.digraphLine.text()

    def reject(self):
        self.addOneMore = False
        QDialog.reject(self)

class DigraphWidget(QGroupBox):
    def __init__(self,parent = None):
        self._parent = parent
        QGroupBox.__init__(self,'Multicharacter segments',parent)
        layout = QVBoxLayout()

        self.editField = QLineEdit()
        layout.addWidget(self.editField)
        self.button = QPushButton('Construct a segment')
        self.button.setAutoDefault(False)
        self.button.clicked.connect(self.construct)
        layout.addWidget(self.button)
        self.setLayout(layout)
        self.characters = list()

    def setDigraphs(self, digraphs):
        self.editField.setText(','.join(digraphs))

    def construct(self):
        if len(self.characters) == 0:
            return
        possible = sorted(self.characters, key = lambda x: x.lower())
        dialog = DigraphDialog(possible,self)
        addOneMore = True
        while addOneMore:
            if dialog.exec_():
                v = dialog.value()
                if v != '' and v not in self.value():
                    val = self.value() + [v]
                    self.editField.setText(','.join(val))
            dialog.digraphLine.setText('')
            addOneMore = dialog.addOneMore

    def value(self):
        text = self.editField.text()
        values = [x.strip() for x in text.split(',') if x.strip() != '']
        if len(values) == 0:
            return []
        return values

class FileWidget(QFrame):
    def __init__(self,title,filefilter,parent=None):
        QFrame.__init__(self,parent)

        self.title = title

        self.filefilter = filefilter

        pathLayout = QHBoxLayout()
        self.pathEdit = QLineEdit()
        pathButton = QPushButton('Choose file...')
        pathButton.setAutoDefault(False)
        pathButton.setDefault(False)
        pathButton.clicked.connect(self.pathSet)
        pathLayout.addWidget(self.pathEdit)
        pathLayout.addWidget(pathButton)
        self.setLayout(pathLayout)

        self.textChanged = self.pathEdit.textChanged

    def pathSet(self):
        filename = QFileDialog.getOpenFileName(self,self.title, filter=self.filefilter)
        if filename:
            self.pathEdit.setText(filename[0])

    def value(self):
        return self.pathEdit.text()

class SaveFileWidget(QFrame):
    def __init__(self,title,filefilter,parent=None):
        QFrame.__init__(self,parent)

        self.title = title

        self.filefilter = filefilter

        pathLayout = QHBoxLayout()
        self.pathEdit = QLineEdit()
        pathButton = QPushButton('Choose file...')
        pathButton.setAutoDefault(False)
        pathButton.setDefault(False)
        pathButton.clicked.connect(self.pathSet)
        pathLayout.addWidget(self.pathEdit)
        pathLayout.addWidget(pathButton)
        self.setLayout(pathLayout)

        self.textChanged = self.pathEdit.textChanged

    def pathSet(self):
        filename = QFileDialog.getSaveFileName(self,self.title, filter=self.filefilter)
        if filename:
            self.pathEdit.setText(filename[0])

    def value(self):
        return self.pathEdit.text()

class DirectoryWidget(QFrame):
    def __init__(self,parent=None):
        QFrame.__init__(self,parent)

        pathLayout = QHBoxLayout()
        self.pathEdit = QLineEdit()
        pathButton = QPushButton('Choose directory...')
        pathButton.setAutoDefault(False)
        pathButton.setDefault(False)
        pathButton.clicked.connect(self.pathSet)
        pathLayout.addWidget(self.pathEdit)
        pathLayout.addWidget(pathButton)
        self.setLayout(pathLayout)

        self.textChanged = self.pathEdit.textChanged

    def setPath(self,path):
        self.pathEdit.setText(path)

    def pathSet(self):
        filename = QFileDialog.getExistingDirectory(self,"Choose a directory")
        if filename:
            self.pathEdit.setText(filename)

    def value(self):
        return self.pathEdit.text()

class InventoryTable(QTableWidget):
    def __init__(self):
        QTableWidget.__init__(self)
        self.horizontalHeader().setMinimumSectionSize(70)

        try:
            self.horizontalHeader().setSectionsClickable(False)
            #self.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
            self.verticalHeader().setSectionsClickable(False)
            #self.verticalHeader().setSectionResizeMode(QHeaderView.Fixed)
        except AttributeError:
            self.horizontalHeader().setClickable(False)
            #self.horizontalHeader().setResizeMode(QHeaderView.Fixed)
            self.verticalHeader().setClickable(False)
            #self.verticalHeader().setResizeMode(QHeaderView.Fixed)

        self.setSelectionMode(QAbstractItemView.NoSelection)
        #self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        #self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def resize(self):
        self.resizeRowsToContents()
        #self.resizeColumnsToContents()
        hor = self.horizontalHeader()
        ver = self.verticalHeader()
        width = ver.sizeHint().width()
        for i in range(hor.count()):
            width += hor.sectionSize(i)
        height = hor.sizeHint().height()
        for i in range(ver.count()):
            height += ver.sectionSize(i)
        self.setFixedSize(width, height)


class EditableInventoryTable(InventoryTable):

    def __init__(self, inventory, is_cons_table=True):
        #parent is an InventoryBox
        InventoryTable.__init__(self)
        self.inventory = inventory
        self.isConsTable = is_cons_table
        self.horizontalHeader().setSectionsClickable(True)
        self.horizontalHeader().sectionClicked.connect(self.highlightColumn)
        self.horizontalHeader().sectionDoubleClicked.connect(self.editChartCol)
        self.verticalHeader().setSectionsClickable(True)
        self.verticalHeader().sectionClicked.connect(self.highlightRow)
        self.verticalHeader().sectionDoubleClicked.connect(self.editChartRow)

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropOverwriteMode(False)
        self.setDropIndicatorShown(True)

        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropMode(QAbstractItemView.InternalMove)

        verticalHeader = self.verticalHeader()
        verticalHeader.setContextMenuPolicy(Qt.CustomContextMenu)
        verticalHeader.customContextMenuRequested.connect( self.showVerticalHeaderMenu )

        horizontalHeader = self.horizontalHeader()
        horizontalHeader.setContextMenuPolicy(Qt.CustomContextMenu)
        horizontalHeader.customContextMenuRequested.connect( self.showHorizontalHeaderMenu )

    def showVerticalHeaderMenu(self, pos):
        header = self.verticalHeader()
        row = header.logicalIndexAt(pos.y())

        deleteRowAct = QAction(self)
        deleteRowAct.setText("Remove row")
        deleteRowAct.triggered.connect(lambda : self.userRemoveRow(row))
        addRowAct = QAction(self)
        addRowAct.setText("Add row")
        addRowAct.triggered.connect(self.userAddRow)

        menu = QMenu(self)
        menu.addAction(deleteRowAct)
        menu.addAction(addRowAct)

        menu.popup(header.mapToGlobal(pos))

    def showHorizontalHeaderMenu(self, pos):
        header = self.horizontalHeader()
        col = header.logicalIndexAt(pos.x())

        deleteColAct = QAction(self)
        deleteColAct.setText("Remove column")
        deleteColAct.triggered.connect(lambda : self.userRemoveColumn(col))
        addColAct = QAction(self)
        addColAct.setText("Add column")
        addColAct.triggered.connect(self.userAddColumn)

        menu = QMenu(self)
        #menu.addAction(editAction)
        menu.addAction(addColAct)
        menu.addAction(deleteColAct)

        menu.popup(header.mapToGlobal(pos))

    def userRemoveRow(self, target):
        self.removeRow(target)
        targetRows = self.inventory.cons_rows if self.isConsTable else self.inventory.vow_rows
        for key,value in targetRows.items():
            if value[0] >= target:
                targetRows[key][0] -= 1

    def userAddRow(self):
        dialog = SegmentSelectDialog(self.inventory, parent = self)
        results = dialog.exec_()
        if results:
            targetRows = self.inventory.cons_rows if self.isConsTable else self.inventory.vow_rows
            target = len(targetRows)
            self.insertRow(target)
            for key,value in targetRows.items():
                if value[0] >= target:
                    targetRows[key][0] += 1
            new_name = dialog.name
            featureList = {f[1:]:f[0] for f in dialog.featureList}
            segList = [s for s in dialog.selectedSegs]
            if self.isConsTable:
                self.inventory.cons_rows[new_name] = [target, featureList, segList]
            else:
                self.inventory.vow_rows[new_name] = [target, featureList, segList]
            self.parent.resetInventoryBox(*self.generateInventoryBoxData())

    def userRemoveColumn(self, target):
        self.removeColumn(target)
        targetCols = self.inventory.cons_columns if self.isConsTable else self.inventory.vow_columns
        for key,value in targetCols.items():
            if value[0] >= target:
                targetCols[key][0] -= 1


    def userAddColumn(self):
        dialog = SegmentSelectDialog(self.inventory, parent = self)
        results = dialog.exec_()
        if results:
            target = self.selectionModel().selectedColumns()[0].column()
            target += 1
            self.insertColumn(target)
            targetCols = self.inventory.cons_columns if self.isConsTable else self.inventory.vow_columns
            for key,value in targetCols.items():
                if value[0] >= target:
                    targetCols[key][0] += 1
            new_name = dialog.name
            featureList = {f[1:]:f[0] for f in dialog.featureList}
            segList = [s for s in dialog.selectedSegs]
            if self.isConsTable:
                self.inventory.cons_columns[new_name] = [target, featureList, segList]
            else:
                self.inventory.vow_columns[new_name] = [target, featureList, segList]
            self.parent.resetInventoryBox(*self.generateInventoryBoxData())


    def allowReordering(self, value):
        self.setDragEnabled(value)
        self.setAcceptDrops(value)
        self.viewport().setAcceptDrops(value)
        self.setDragDropOverwriteMode(value)
        self.setDropIndicatorShown(value)

    def dragMoveEvent(self,event):
        event.accept()

    def highlightRow(self,row_num):
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.selectRow(row_num)

    def highlightColumn(self,col_num):
        self.setSelectionBehavior(QAbstractItemView.SelectColumns)
        self.selectColumn(col_num)

    def dropEvent(self, event):

        if event.source() == self and (event.dropAction() == Qt.MoveAction or self.dragDropMode() == QAbstractItemView.InternalMove):
            success, index = self.dropOn(event)
            if not success:
                return

        if self.selectionBehavior() == QAbstractItemView.SelectRows:
            dropRow = index.row()
            selRow = self.selectionModel().selectedRows()[0].row()

            if dropRow == -1:
                insertAt = self.rowCount()#take maximum, user dragged past the bottom

            if selRow < dropRow:
                insertAt = dropRow+1
                sourceRow = selRow
                if insertAt > self.rowCount():
                    insertAt = self.rowCount()

            elif selRow > dropRow:
                insertAt = dropRow
                sourceRow = selRow+1
                if sourceRow > self.rowCount():
                    sourceRow = self.rowCount()

            self.insertRow(insertAt)
            self.setVerticalHeaderItem(insertAt, QTableWidgetItem(self.verticalHeaderItem(sourceRow).text()))
            for c in range(self.columnCount()):
                sourceWidget = self.cellWidget(sourceRow,c)
                self.setCellWidget(insertAt,c,sourceWidget)

            headers = [self.verticalHeaderItem(r).text() for r in range(self.rowCount())]
            chooseRows = self.parent.corpus.specifier.consRows if self.isConsTable else self.parent.corpus.specifier.vowRows
            a = self.verticalHeaderItem(sourceRow).text()
            b = self.verticalHeaderItem(dropRow).text()
            chooseRows[a][0], chooseRows[b][0] = chooseRows[b][0], chooseRows[a][0]

            if self.isConsTable:
                self.inventory.cons_rows = {k:v for k,v in self.inventory.cons_rows.items() if k in headers}
            else:
                self.inventory.vow_rows = {k:v for k,v in self.inventory.vow_rows.items() if k in headers}

            for r in range(self.rowCount()):
                chooseRows[self.verticalHeaderItem(r).text()][0] = r

            self.resizeRowsToContents()
            event.accept()

        elif self.selectionBehavior() == QAbstractItemView.SelectColumns:
            dropCol = index.column()
            selCol = self.selectionModel().selectedColumns()[0].column()
            if dropCol == -1:
                insertAt = self.columnCount()#take maximum, user dragged past the bottom

            if selCol < dropCol:
                insertAt = dropCol+1
                sourceCol = selCol
                if insertAt > self.columnCount():
                    insertAt = self.columnCount()

            elif selCol > dropCol:
                insertAt = dropCol
                sourceCol = selCol+1
                if sourceCol > self.columnCount():
                    sourceCol = self.columnCount()

            self.insertColumn(insertAt)
            self.setHorizontalHeaderItem(insertAt, QTableWidgetItem(self.horizontalHeaderItem(sourceCol).text()))
            for r in range(self.rowCount()):
                sourceWidget = self.cellWidget(r,sourceCol)
                self.setCellWidget(r,insertAt,sourceWidget)

            self.resizeColumnsToContents()
            self.removeColumn(sourceCol)

            headers = [self.horizontalHeaderItem(c).text() for c in range(self.columnCount())]
            chooseCols = self.inventory.cons_columns if self.isConsTable else self.inventory.vow_columns
            a = self.horizontalHeaderItem(sourceCol).text()
            b = self.horizontalHeaderItem(dropCol).text()
            chooseCols[a][0], chooseCols[b][0] = chooseCols[b][0], chooseCols[a][0]

            if self.isConsTable:
                self.inventory.cons_columns = {k:v for k,v in self.inventory.cons_columns.items() if k in headers}
            else:
                self.inventory.vow_columns = {k:v for k,v in self.inventory.vow_columns.items() if k in headers}

            for c in range(self.columnCount()):
                chooseCols[self.horizontalHeaderItem(c).text()][0] = c

            event.accept()


    def droppingOnItself(self, event, index):
        dropAction = event.dropAction()

        if self.dragDropMode() == QAbstractItemView.InternalMove:
            dropAction = Qt.MoveAction

        if event.source() == self and event.possibleActions() & Qt.MoveAction and dropAction == Qt.MoveAction:
            selectedIndexes = self.selectedIndexes()
            child = index
            while child.isValid() and child != self.rootIndex():
                if child in selectedIndexes:
                    return True
                child = child.parent()

        return False

    def dropOn(self, event):
        """
        :param event:
        :return:
        (True,index) if it is possible to do a drop, where index is a QModelIndex of where the drop is happening
        (Fale,None) otherwise
        """
        if event.isAccepted():
            return False, None

        index = QModelIndex()
        #get values with index.row() or index.col()
        #the value appears to be -1 if the user drags off the table limits

        if self.viewport().rect().contains(event.pos()):
            index = self.indexAt(event.pos())
            if not index.isValid() or not self.visualRect(index).contains(event.pos()):
                index = self.rootIndex()

        if self.model().supportedDropActions() and event.dropAction():

            if not self.droppingOnItself(event, index):
                # print 'row is %d'%row
                # print 'col is %d'%col
                return True, index

        return False, None

    def position(self, pos, rect, index):
        r = QAbstractItemView.OnViewport
        margin = 2
        if pos.y() - rect.top() < margin:
            r = QAbstractItemView.AboveItem
        elif rect.bottom() - pos.y() < margin:
            r = QAbstractItemView.BelowItem
        elif rect.contains(pos, True):
            r = QAbstractItemView.OnItem

        if r == QAbstractItemView.OnItem and not (self.model().flags(index) & Qt.ItemIsDropEnabled):
            r = QAbstractItemView.AboveItem if pos.y() < rect.center().y() else QAbstractItemView.BelowItem

        return r


    def editChartRow(self, index):
        old_name = self.verticalHeaderItem(index).text()
        targetRows = self.parent.corpus.specifier.consRows if self.isConsTable else self.parent.corpus.specifier.vowRows
        default_specs = targetRows[old_name]
        dialog = CreateClassWidget(self, self.parent.corpus, class_type='inventory',
                                   default_name=old_name, default_specs=default_specs)
        results = dialog.exec_()
        if results:
            new_name = dialog.name
            if new_name != old_name:
                targetRows[new_name] = targetRows.pop(old_name)
            featureList = dialog.featureList
            targetRows[new_name][1] = {f[1:]:f[0] for f in featureList}
            targetRows[new_name][2] = [s for s in dialog.selectedSegs]
            self.parent.resetInventoryBox(*self.generateInventoryBoxData())

    def saveReordering(self):
        pass

    def editChartCol(self, index):

        old_name = self.horizontalHeaderItem(index).text()
        targetCols = self.parent.corpus.specifier.consCols if self.isConsTable else self.parent.corpus.specifier.vowCols
        default_specs = targetCols[old_name]
        dialog = CreateClassWidget(self, self.parent.corpus, class_type='inventory', default_name=old_name, default_specs=default_specs)
        results = dialog.exec_()
        if results:
            new_name = dialog.name
            if new_name != old_name:
                targetCols[new_name] = targetCols.pop(old_name)
            featureList = dialog.featureList
            targetCols[new_name][1] = {f[1:]:f[0] for f in featureList}
            targetCols[new_name][2] = [s for s in dialog.selectedSegs]
            self.parent.resetInventoryBox(*self.generateInventoryBoxData())

    def generateInventoryBoxData(self):
        #see also InventoryBox.generateInventoryBox()
        consColNames = self.parent.corpus.specifier.consCols.keys()
        consColumns = sorted(consColNames, key=lambda x:self.parent.corpus.specifier.consCols[x][0])
        consRowNames = self.parent.corpus.specifier.consRows.keys()
        consRows = sorted(consRowNames, key=lambda x:self.parent.corpus.specifier.consRows[x][0])
        # needed_cols = list(set([feature_list[1] for seg,feature_list in consList]))
        # needed_rows = list(set([feature_list[2] for seg,feature_list in consList]))
        categorized = list()
        uncategorized = list()
        for s in self.parent.corpus.inventory:
            try:
                cat = self.parent.corpus.specifier.categorize(s)
                if 'Consonant' in cat:
                    categorized.append((s,cat))
            except KeyError:
                uncategorized.append(s)
        segs = (categorized, uncategorized)
        #segs = [s for s in self.parent.corpus.inventory]
        return [consColumns, consRows, segs, True]

class SegmentButton(QPushButton):
    def sizeHint(self):
        sh = QPushButton.sizeHint(self)

        #sh.setHeight(self.fontMetrics().boundingRect(self.text()).height()+14)
        sh.setHeight(35)
        sh.setWidth(self.fontMetrics().boundingRect(self.text()).width()+14)
        return sh

class FeatureEdit(QLineEdit):
    featureEntered = Signal(list)
    featuresFinalized = Signal(list)
    delimPattern = re.compile('([,; ]+)')

    def __init__(self,inventory, parent=None):
        QLineEdit.__init__(self, parent)
        self.completer = None
        self.inventory = inventory
        self.valid_strings = self.inventory.valid_feature_strings()

    def setCompleter(self,completer):
        if self.completer is not None:
            self.disconnect(self.completer,0,0)
        self.completer = completer
        if self.completer is None:
            return
        self.completer.setWidget(self)
        self.completer.setCompletionMode(QCompleter.PopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.completer.activated.connect(self.insertCompletion)

    def features(self):
        if self.text() == '':
            return []
        text = self.delimPattern.split(self.text())
        features = [x for x in text if x in self.valid_strings]
        return features

    def parseText(self):
        m = self.delimPattern.search(self.text())
        if m is None:
            d = ''
        else:
            d = m.group(0)
        text = self.delimPattern.split(self.text())
        return d, text


    def insertCompletion(self, string):
        d, text = self.parseText()
        text[-1] = string
        text = [x for x in text if x in self.valid_strings]
        self.featureEntered.emit(text)
        self.setText(d.join(text))

    def currentFeature(self):
        return self.delimPattern.split(self.text())[-1]

    def keyPressEvent(self,e):
        if self.completer and self.completer.popup().isVisible():
                if e.key() in ( Qt.Key_Space, Qt.Key_Enter,
                                Qt.Key_Return,Qt.Key_Escape,
                                Qt.Key_Tab,Qt.Key_Backtab):
                    e.ignore()
                    return
        else:
            if e.key() in (Qt.Key_Enter, Qt.Key_Return):
                if self.text() != '':
                    self.featuresFinalized.emit(self.features())
                    self.setText('')
                    self.featureEntered.emit([])
                    return
        isShortcut=((e.modifiers() & Qt.ControlModifier) and e.key()==Qt.Key_E)
        if (self.completer is None or not isShortcut):
            super().keyPressEvent(e)

        if e.key() in (Qt.Key_Space, Qt.Key_Semicolon, Qt.Key_Comma):
            e.ignore()
            return

        d, text = self.parseText()
        self.featureEntered.emit([x for x in text if x in self.valid_strings])

        completionPrefix = self.currentFeature()

        self.completer.update(completionPrefix)
        self.completer.popup().setCurrentIndex(self.completer.completionModel().index(0, 0))

        cr = self.cursorRect()
        cr.setWidth(self.completer.popup().sizeHintForColumn(0)
                    + self.completer.popup().verticalScrollBar().sizeHint().width())
        self.completer.complete(cr)

class FeatureCompleter(QCompleter):
    def __init__(self,inventory,parent=None):
        QCompleter.__init__(self, parent)
        self.stringList = inventory.valid_feature_strings()
        self.setModel(QStringListModel())

    def update(self,completionText):
        to_filter = completionText.lower()
        filtered = [x for x in self.stringList
                        if x.lower().startswith(to_filter)
                        or x[1:].lower().startswith(to_filter)]
        self.model().setStringList(filtered)
        self.popup().setCurrentIndex(self.model().index(0, 0))

class SegmentSelectionWidget(QWidget):
    def __init__(self, inventory, parent = None):
        QWidget.__init__(self, parent)
        self.inventory = inventory

        self.searchWidget = FeatureEdit(self.inventory)
        self.completer = FeatureCompleter(self.inventory)
        self.searchWidget.setCompleter(self.completer)

        self.inventoryFrame = InventoryBox('', self.inventory)

        layout = QVBoxLayout()

        if len(inventory.features) > 0:
            headlayout = QHBoxLayout()
            formlay = QFormLayout()

            formlay.addRow('Select by feature',self.searchWidget)

            formframe = QFrame()

            formframe.setLayout(formlay)
            headlayout.addWidget(formframe)

            self.clearAllButton = QPushButton('Clear selections')

            headlayout.addWidget(self.clearAllButton)
            headframe = QFrame()

            headframe.setLayout(headlayout)
            self.clearAllButton.clicked.connect(self.inventoryFrame.clearAll)

        else:
            headframe = QLabel('No feature matrix associated with this corpus.')

        layout.addWidget(headframe)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inventoryFrame)
        #scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(140)
        policy = scroll.sizePolicy()
        policy.setVerticalStretch(1)
        scroll.setSizePolicy(policy)
        #self.columnFrame.
        layout.addWidget(scroll)

        self.setLayout(layout)

        self.searchWidget.featureEntered.connect(self.inventoryFrame.highlightSegments)
        self.searchWidget.featuresFinalized.connect(self.inventoryFrame.selectSegmentFeatures)


    def select(self, segments):
        self.inventoryFrame.selectSegments(segments)

    def clearAll(self):
        self.inventoryFrame.clearAll()

    def value(self):
        return self.inventoryFrame.value()

class InventoryBox(QWidget):

    def __init__(self, title, inventory, parent = None, editable = False):
        QWidget.__init__(self,parent)
        self.inventory = inventory
        self.editable = editable
        self.consonantColumns = inventory.cons_columns
        self.consonantRows = inventory.cons_rows
        self.vowelColumns = inventory.vow_columns
        self.vowelRows = inventory.vow_rows
        self.generateInventoryBox()

    def resetInventoryBox(self, cols, rows, segs, editable):
        for i in reversed(range(self.smallbox.count())):
            self.smallbox.itemAt(i).widget().setParent(None)
        categorized, uncategorized = segs
        cons = self.makeConsBox(cols, rows, categorized, editable)
        vow = self.makeVowelBox(cols, rows, categorized, editable)
        unk = self.makeUncategorizedBox(uncategorized)
        self.addTables(cons,vow,unk)

    def generateInventoryBox(self):
        #find cats (meow)
        consColumns = set()
        consRows = set()
        vowColumns = set()
        vowRows = set()
        consList = []
        vowList = []
        uncategorized = []

        for s in self.inventory:
            try:
                c = self.inventory.categorize(s)
            except KeyError:
                c = None
                uncategorized.append(s)
            if c is not None:
                if c[0] == 'Vowel':
                    vowColumns.add(c[2])
                    vowRows.add(c[1])
                    vowList.append((s,c))
                elif c[0] == 'Consonant':
                    consColumns.add(c[1])
                    consRows.add(c[2])
                    consList.append((s,c))

        self.btnGroup = QButtonGroup()#This has all of the SegmentButtons, see also self.value()
        self.btnGroup.setExclusive(False)

        self.smallbox = QVBoxLayout()
        self.smallbox.setSizeConstraint(QLayout.SetFixedSize)
        self.smallbox.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        cons = self.makeConsBox(consColumns,consRows,consList,self.editable)
        vow = self.makeVowelBox(vowColumns,vowRows,vowList,self.editable)
        unk = self.makeUncategorizedBox(uncategorized)

        self.addTables(cons,vow,unk)
        self.setLayout(self.smallbox)

    def addTables(self,cons,vow,unk):
        if cons is not None:
            self.smallbox.addWidget(cons, alignment = Qt.AlignLeft | Qt.AlignTop)
            self.consTable.resize()

        if vow is not None:
            self.smallbox.addWidget(vow, alignment = Qt.AlignLeft | Qt.AlignTop)
            self.vowelTable.resize()

        if unk is not None:
            self.smallbox.addWidget(unk, alignment = Qt.AlignLeft | Qt.AlignTop)

    def makeConsBox(self,consColumns,consRows,consList,editable):
        cons = QFrame()#This widget is what gets returned from this function
        consBox = QVBoxLayout()
        if editable:
            self.consTable = EditableInventoryTable(self.inventory,True)
        else:
            self.consTable = InventoryTable()
        consBox.addWidget(self.consTable)
        cons.setLayout(consBox)

        needed_cols = list(set([feature_list[1] for seg,feature_list in consList]))
        needed_rows = list(set([feature_list[2] for seg,feature_list in consList]))

        self.consTable.setColumnCount(len(needed_cols))
        self.consTable.setRowCount(len(needed_rows))

        horizontalHeaderLabelText = sorted(needed_cols, key=lambda x:self.consonantColumns[x][0])
        self.consTable.setHorizontalHeaderLabels(horizontalHeaderLabelText)
        consColMapping = {x:i for i,x in enumerate(horizontalHeaderLabelText)}

        verticalHeaderLabelText = sorted(needed_rows, key=lambda x:self.consonantRows[x][0])
        self.consTable.setVerticalHeaderLabels(verticalHeaderLabelText)
        consRowMapping = {x:i for i,x in enumerate(verticalHeaderLabelText)}

        self.consTable.resizeColumnsToContents()
        button_map = {(h,v): list() for (h,v) in product(horizontalHeaderLabelText, verticalHeaderLabelText)}#defaultdict(list)

        for seg,category in consList:
            for h,v in product(horizontalHeaderLabelText, verticalHeaderLabelText):
                if h in category and v in category:
                    btn = self.generateSegmentButton(seg.symbol)
                    button_map[(h,v)].append(btn)
                    break

        for key,buttons in button_map.items():
            c,r = key
            self.consTable.setCellWidget(consRowMapping[r],consColMapping[c],MultiSegmentCell(buttons))

        return cons

    def makeVowelBox(self,vowelColumns,vowelRows,vowelList,editable):
        vowel = QFrame()
        vowelBox = QGridLayout()
        vowelBox.setAlignment(Qt.AlignTop)
        if editable:
            self.vowelTable = EditableInventoryTable(self.inventory,False)
        else:
            self.vowelTable = InventoryTable()

        vowelBox.addWidget(self.vowelTable)
        vowel.setLayout(vowelBox)

        needed_cols = list(set([feature_list[1] for seg,feature_list in vowelList]))
        needed_rows = list(set([feature_list[2] for seg,feature_list in vowelList]))

        self.vowelTable.setColumnCount(len(needed_cols))
        self.vowelTable.setRowCount(len(needed_rows))

        horizontalHeaderLabelText = sorted(needed_cols, key=lambda x:self.vowelColumns[x][0])
        self.vowelTable.setHorizontalHeaderLabels(horizontalHeaderLabelText)
        vowelColMapping = {x:i for i,x in enumerate(horizontalHeaderLabelText)}

        verticalHeaderLabelText = sorted(needed_rows, key=lambda x:self.vowelRows[x][0])
        self.vowelTable.setVerticalHeaderLabels(verticalHeaderLabelText)
        vowelRowMapping = {x:i for i,x in enumerate(verticalHeaderLabelText)}

        self.vowelTable.resizeColumnsToContents()
        button_map = {(h,v): list() for (h,v) in product(horizontalHeaderLabelText, verticalHeaderLabelText)}#defaultdict(list)

        for seg,category in vowelList:
            for h,v in product(horizontalHeaderLabelText, verticalHeaderLabelText):
                if h in category and v in category:
                    btn = self.generateSegmentButton(seg.symbol)
                    button_map[(h,v)].append(btn)
                    break

        for key,buttons in button_map.items():
            c,r = key
            self.vowelTable.setCellWidget(vowelRowMapping[r],vowelColMapping[c],MultiSegmentCell(buttons))

        return vowel

    def makeUncategorizedBox(self,uncategorized):
        unk = QGroupBox('Uncategorized')
        unk.setFlat(True)
        # unk.setCheckable(True)
        # unk.setChecked(False)
        # unk.toggled.connect(self.showHideUnk)
        self.unkTable = QGridLayout()
        unk.setLayout(self.unkTable)

        unkRow = 0
        unkCol = -1
        for s in uncategorized:
            btn = SegmentButton(s.symbol)
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            btn.setSizePolicy(QSizePolicy.MinimumExpanding,QSizePolicy.MinimumExpanding)
            #btn.setMaximumWidth(btn.fontMetrics().boundingRect(s.symbol).width() + 14)
            #btn.setMaximumHeight(btn.fontMetrics().boundingRect(s.symbol).height() + 14)
            #btn.setMinimumWidth(btn.fontMetrics().boundingRect(s.symbol).width() +7)
            #btn.setMinimumHeight(btn.fontMetrics().boundingRect(s.symbol).height() + 14)
            self.btnGroup.addButton(btn)

            unkCol += 1
            if unkCol > 11:
                unkCol = 0
                unkRow += 1
            self.unkTable.addWidget(btn,unkRow,unkCol)
        return unk

    def generateSegmentButton(self,symbol):
        wid = SegmentButton(symbol)#This needs to be a SegmentButton for the i,j segment
        wid.setSizePolicy(QSizePolicy.MinimumExpanding,QSizePolicy.MinimumExpanding)
        b = QGridLayout()
        b.setAlignment(Qt.AlignCenter)
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(0)
        l = QWidget()
        l.setSizePolicy(QSizePolicy.MinimumExpanding,QSizePolicy.MinimumExpanding)
        lb = QVBoxLayout()
        lb.setAlignment(Qt.AlignCenter)
        lb.setContentsMargins(0, 0, 0, 0)
        lb.setSpacing(0)
        l.setLayout(lb)
        #l.hide()
        b.addWidget(l,0,0)#, alignment = Qt.AlignCenter)
        r = QWidget()
        r.setSizePolicy(QSizePolicy.MinimumExpanding,QSizePolicy.MinimumExpanding)
        rb = QVBoxLayout()
        rb.setAlignment(Qt.AlignCenter)
        rb.setContentsMargins(0, 0, 0, 0)
        rb.setSpacing(0)
        r.setLayout(rb)
        #r.hide()
        b.addWidget(r,0,1)#, alignment = Qt.AlignCenter)
        wid.setLayout(b)
        wid.setCheckable(True)
        wid.setAutoExclusive(False)
        wid.setSizePolicy(QSizePolicy.MinimumExpanding,QSizePolicy.MinimumExpanding)
        self.btnGroup.addButton(wid)
        return wid

    def highlightSegments(self, features):
        segs = self.inventory.features_to_segments(features)
        for btn in self.btnGroup.buttons():
            btn.setStyleSheet("QPushButton{}")
            if features and btn.text() in segs:
                btn.setStyleSheet("QPushButton{background-color: red;}")

    def selectSegmentFeatures(self, features):
        segs = self.inventory.features_to_segments(features)
        self.selectSegments(segs)

    def selectSegments(self, segs):
        if len(segs) > 0:
            for btn in self.btnGroup.buttons():
                if btn.text() in segs:
                    btn.setChecked(True)

    def clearAll(self):
        reexc = self.btnGroup.exclusive()
        if reexc:
            self.setExclusive(False)
        for btn in self.btnGroup.buttons():
            btn.setChecked(False)
        if reexc:
            self.setExclusive(True)

    def setExclusive(self, b):
        self.btnGroup.setExclusive(b)
        for btn in self.btnGroup.buttons():
            btn.setAutoExclusive(b)

    def value(self):
        if self.btnGroup.exclusive():
            checked = self.btnGroup.checkedButton()
            if checked is None:
                return ''
            return checked.text()
        else:
            value = []
            for b in self.btnGroup.buttons():
                if b.isChecked():
                    value.append(b.text())
            return value

class MultiSegmentCell(QWidget):

    def __init__(self,buttons,parent=None):
        super().__init__(parent)
        layout = QHBoxLayout()

        #layout.setContentsMargins(0,0,0,0)
        #layout.setSpacing(0)
        self.button_names = list()
        for b in buttons:
            layout.addWidget(b)
            self.button_names.append(b.text())

        self.setLayout(layout)

    def __str__(self):
        return ','.join(self.button_names)

class TranscriptionWidget(QGroupBox):
    transcriptionChanged = Signal(object)
    def __init__(self, title,corpus,parent=None):
        QGroupBox.__init__(self,title,parent)
        self.inventory = corpus.inventory
        self.corpus = corpus
        layout = QFormLayout()

        self.transEdit = QLineEdit()
        self.transEdit.textChanged.connect(self.transcriptionChanged.emit)
        self.showInv = QPushButton('Show inventory')
        self.showInv.setAutoDefault(False)
        self.showInv.clicked.connect(self.showHide)
        layout.addRow(self.transEdit,self.showInv)

        self.segments = InventoryBox('Inventory',self.corpus)
        for btn in self.segments.btnGroup.buttons():
            btn.setCheckable(False)
            btn.setAutoDefault(False)
            btn.clicked.connect(self.addCharacter)
        self.segments.hide()
        layout.addRow(self.segments)

        self.setLayout(layout)

    def text(self):
        return self.transEdit.text()

    def setText(self, text):
        self.transEdit.setText(text)

    def addCharacter(self):
        t = self.transEdit.text()
        if t != '':
            t += '.'
        self.transEdit.setText(t+self.sender().text())

    def showHide(self):
        if self.segments.isHidden():
            self.segments.show()
            self.showInv.setText('Hide inventory')
        else:
            self.segments.hide()
            self.showInv.setText('Show inventory')
        self.updateGeometry()

class FeatureBox(QWidget):
    def __init__(self, title,inventory,parent=None):
        QWidget.__init__(self,parent)

        self.inventory = inventory
        self.features = self.inventory.features
        self.values = self.inventory.possible_values
        layout = QHBoxLayout()

        #layout.setSizeConstraint(QLayout.SetFixedSize)

        self.featureList = QListWidget()

        for f in self.features:
            self.featureList.addItem(f)
        self.featureList.setFixedWidth(self.featureList.minimumSizeHint().width()+20)
        layout.addWidget(self.featureList)

        buttonLayout = QVBoxLayout()
        buttonLayout.setSpacing(0)
        self.buttons = list()
        for v in self.values:
            b = QPushButton('Add [{}feature]'.format(v))
            b.value = v
            b.clicked.connect(self.addFeature)
            buttonLayout.addWidget(b, alignment = Qt.AlignCenter)
            self.buttons.append(b)

        self.clearOneButton = QPushButton('Remove selected')
        self.clearOneButton.clicked.connect(self.clearOne)
        buttonLayout.addWidget(self.clearOneButton, alignment = Qt.AlignCenter)

        self.clearButton = QPushButton('Remove all')
        self.clearButton.clicked.connect(self.clearAll)
        buttonLayout.addWidget(self.clearButton, alignment = Qt.AlignCenter)

        buttonFrame = QFrame()
        buttonFrame.setLayout(buttonLayout)
        layout.addWidget(buttonFrame, alignment = Qt.AlignCenter)

        self.envList = QListWidget()
        self.envList.setFixedWidth(self.featureList.minimumSizeHint().width()+25)
        self.envList.setSelectionMode(QAbstractItemView.ExtendedSelection)

        layout.addWidget(self.envList)

        self.setLayout(layout)

    def addFeature(self):
        curFeature = self.featureList.currentItem()
        if curFeature:
            val = self.sender().value
            feat = curFeature.text()
            key = val+feat
            if key not in self.currentSpecification():
                self.envList.addItem(key)

    def clearOne(self):
        items = self.envList.selectedItems()
        for i in items:
            item = self.envList.takeItem(self.envList.row(i))
            #self.sourceWidget.addItem(item)

    def clearAll(self):
        self.envList.clear()

    def currentSpecification(self):
        return [self.envList.item(i).text() for i in range(self.envList.count())]

    def value(self):
        val = self.currentSpecification()
        if not val:
            return ''
        return '[{}]'.format(','.join(val))

class SegmentPairDialog(QDialog):
    def __init__(self, corpus, parent=None):
        QDialog.__init__(self,parent)

        layout = QVBoxLayout()

        self.inventoryFrame = SegmentSelectionWidget(inventory)

        layout.addWidget(self.inventoryFrame)

        self.setLayout(layout)

        self.oneButton = QPushButton('Add')
        self.anotherButton = QPushButton('Add and create another')
        self.cancelButton = QPushButton('Cancel')
        acLayout = QHBoxLayout()
        acLayout.addWidget(self.oneButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.anotherButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.cancelButton, alignment = Qt.AlignLeft)
        self.oneButton.clicked.connect(self.one)
        self.anotherButton.clicked.connect(self.another)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(acLayout)

        layout.addWidget(acFrame, alignment = Qt.AlignLeft)

        self.setLayout(layout)
        self.setWindowTitle('Select segment pair')

    def one(self):
        self.addOneMore = False
        self.accept()

    def another(self):
        self.addOneMore = True
        self.accept()

    def reset(self):
        self.inventoryFrame.clearAll()

    def reject(self):
        self.addOneMore = False
        QDialog.reject(self)

    def accept(self):
        selected = self.inventoryFrame.value()
        self.pairs = combinations(selected,2)
        QDialog.accept(self)

class SegPairTableWidget(TableWidget):
    def __init__(self, parent = None):
        TableWidget.__init__(self, parent)
        self.setModel(SegmentPairModel())
        self.setItemDelegateForColumn(2, SwitchDelegate(self))
        self.model().rowsInserted.connect(self.addSwitch)
        self.setSortingEnabled(False)
        self.horizontalHeader().setSectionsClickable(False)

        switch = QPushButton()
        if sys.platform == 'darwin' or sys.platform.startswith('win'):
            icon = QIcon()
            icon.addPixmap(QPixmap(":/Icon/resources/object-flip-horizontal.png"),
                        QIcon.Normal, QIcon.Off)
        else:
            icon = QIcon.fromTheme('object-flip-horizontal')
        switch.setIcon(icon)
        self.horizontalHeader().setDefaultSectionSize(switch.iconSize().width()+16)
        self.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeToContents)
        self.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents)

    def minimumSizeHint(self):
        sh = TableWidget.minimumSizeHint(self)
        width = self.horizontalOffset()
        header = self.horizontalHeader()
        for i in range(3):
            width += header.sectionSize(i)
        sh.setWidth(width)
        return sh

    def addSwitch(self, index, begin, end):
        self.openPersistentEditor(self.model().index(begin, 2))

class SegmentPairSelectWidget(QGroupBox):
    def __init__(self,corpus,parent=None):
        QGroupBox.__init__(self,'Segments',parent)

        self.inventory = corpus.inventory
        self.corpus = corpus

        vbox = QVBoxLayout()
        self.addButton = QPushButton('Add pair of sounds')
        self.addButton.clicked.connect(self.segPairPopup)
        self.removeButton = QPushButton('Remove selected sound pair')
        self.removeButton.clicked.connect(self.removePair)
        self.addButton.setAutoDefault(False)
        self.addButton.setDefault(False)
        self.removeButton.setAutoDefault(False)
        self.removeButton.setDefault(False)

        self.table = SegPairTableWidget()

        vbox.addWidget(self.addButton)
        vbox.addWidget(self.removeButton)
        vbox.addWidget(self.table)
        self.setLayout(vbox)

        self.setFixedWidth(self.minimumSizeHint().width())

    def segPairPopup(self):
        dialog = SegmentPairDialog(self.corpus)
        addOneMore = True
        while addOneMore:
            dialog.reset()
            result = dialog.exec_()
            if result:
                self.addPairs(dialog.pairs)
            addOneMore = dialog.addOneMore

    def addPairs(self, pairs):
        for p in pairs:
            self.table.model().addRow(p)

    def removePair(self):
        select = self.table.selectionModel()
        if select.hasSelection():
            selected = [s.row() for s in select.selectedRows()]
            self.table.model().removeRows(selected)

    def value(self):
        return self.table.model().rows

class SegFeatSelect(QGroupBox):
    def __init__(self,corpus, title, parent = None, exclusive = False):
        QGroupBox.__init__(self,title,parent)
        self.segExclusive = exclusive
        self.corpus = corpus
        self.inventory = self.corpus.inventory
        self.features = list()
        for i in self.inventory:
            if len(i.features.keys()) > 0:
                self.features = [x for x in i.features.keys()]
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self.typeSelect = QComboBox()
        self.typeSelect.addItem('Segments')
        if len(self.features) > 0:
            self.typeSelect.addItem('Features')
        else:
            layout.addWidget(QLabel('Features are not available for selection without a feature system.'))
        self.typeSelect.currentIndexChanged.connect(self.generateFrame)

        layout.addWidget(QLabel('Basis segment selection:'))
        layout.addWidget(self.typeSelect, alignment = Qt.AlignLeft)

        self.sel = InventoryBox('',self.corpus)
        self.sel.setExclusive(self.segExclusive)

        layout.addWidget(self.sel)

        self.setLayout(layout)

    def generateFrame(self):
        self.sel.deleteLater()
        if self.typeSelect.currentText() == 'Segments':
            self.sel = InventoryBox('',self.corpus)
            self.sel.setExclusive(self.segExclusive)
        elif self.typeSelect.currentText() == 'Features':
            self.sel = FeatureBox('',self.inventory)
        self.layout().addWidget(self.sel)

    def value(self):
        return self.sel.value()

    def segments(self):
        if self.typeSelect.currentText() == 'Segments':
            return self.sel.value()
        elif self.typeSelect.currentText() == 'Features':
            return self.corpus.features_to_segments(self.sel.value()[1:-1])

class EnvironmentDialog(QDialog):
    rowToAdd = Signal(str)
    def __init__(self, inventory,parent=None):
        QDialog.__init__(self,parent)

        self.inventory = inventory

        layout = QVBoxLayout()

        layout.setSizeConstraint(QLayout.SetFixedSize)

        layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        lhsEnvFrame = QGroupBox('Left hand side')

        rhsEnvFrame = QGroupBox('Right hand side')

        lhsEnvLayout = QVBoxLayout()

        lhsEnvLayout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        rhsEnvLayout = QVBoxLayout()

        rhsEnvLayout.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        if parent.name == 'environment' or parent.name == 'class':
            self.lhsEnvType = QComboBox()
            self.rhsEnvType = QComboBox()
            self.lhsEnvType.addItem('Segments')
            self.rhsEnvType.addItem('Segments')
            if len(self.inventory.features) > 0:
                self.lhsEnvType.addItem('Features')
                self.rhsEnvType.addItem('Features')
            else:
                layout.addWidget(QLabel('Features for {} selection are not available without a feature system.'.format(parent.name)))

            self.lhsEnvType.currentIndexChanged.connect(self.generateLhsFrame)
            self.rhsEnvType.currentIndexChanged.connect(self.generateRhsFrame)

            lhsEnvLayout.addWidget(QLabel('Basis for building {}:'.format(parent.name)))
            lhsEnvLayout.addWidget(self.lhsEnvType, alignment = Qt.AlignLeft)

            rhsEnvLayout.addWidget(QLabel('Basis for building {}:'.format(parent.name)))
            rhsEnvLayout.addWidget(self.rhsEnvType, alignment = Qt.AlignLeft)

        self.lhs = QStackedWidget()
        self.lhsInventory = InventoryBox('',self.inventory)
        self.lhsInventory.setExclusive(True)
        self.lhsFeature = FeatureBox('',self.inventory)
        self.lhs.addWidget(self.lhsInventory)

        if len(self.inventory.features) > 0:
            self.lhs.addWidget(self.lhsFeature)

        self.rhs = QStackedWidget()
        self.rhsInventory = InventoryBox('',self.inventory)
        self.rhsInventory.setExclusive(True)
        self.rhsFeature = FeatureBox('',self.inventory)
        self.rhs.addWidget(self.rhsInventory)

        if len(self.inventory.features) > 0:
            self.rhs.addWidget(self.rhsFeature)

        lhsEnvLayout.addWidget(self.lhs)
        rhsEnvLayout.addWidget(self.rhs)

        lhsEnvFrame.setLayout(lhsEnvLayout)

        rhsEnvFrame.setLayout(rhsEnvLayout)
        envFrame = QFrame()

        envLayout = QHBoxLayout()

        envLayout.addWidget(lhsEnvFrame)
        envLayout.addWidget(rhsEnvFrame)

        envFrame.setLayout(envLayout)

        layout.addWidget(envFrame)

        self.oneButton = QPushButton('Add')
        self.anotherButton = QPushButton('Add and create another')
        self.cancelButton = QPushButton('Cancel')
        self.acLayout = QHBoxLayout()
        self.acLayout.addWidget(self.oneButton, alignment = Qt.AlignLeft)
        self.acLayout.addWidget(self.anotherButton, alignment = Qt.AlignLeft)
        self.acLayout.addWidget(self.cancelButton, alignment = Qt.AlignLeft)
        self.oneButton.clicked.connect(self.one)
        self.anotherButton.clicked.connect(self.another)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(self.acLayout)

        layout.addWidget(acFrame, alignment = Qt.AlignLeft)
        self.addOneMore = False
        self.setLayout(layout)
        #self.setFixedSize(self.sizeHint())
        self.setWindowTitle('Create {}'.format(self.parent().name))

    def generateLhsFrame(self,ind=0):
        self.lhs.setCurrentIndex(self.lhsEnvType.currentIndex())

    def generateRhsFrame(self,ind=0):
        self.rhs.setCurrentIndex(self.rhsEnvType.currentIndex())

    def one(self):
        self.addOneMore = False
        self.accept()

    def another(self):
        self.addOneMore = True
        self.accept()

    def reset(self):
        self.lhsInventory.clearAll()
        self.lhsFeature.clearAll()
        self.rhsInventory.clearAll()
        self.rhsFeature.clearAll()

    def accept(self):
        lhs = self.lhsInventory.value()
        rhs = self.rhsInventory.value()

        if self.parent().name == 'environment':
            if self.lhsEnvType.currentIndex() != 0:
                lhs = self.lhsFeature.value()
            if  self.rhsEnvType.currentIndex() != 0:
                rhs = self.rhsFeature.value()
            env = '{}_{}'.format(lhs, rhs)
        else:
            if lhs == '':
                reply = QMessageBox.critical(self,
                        "Missing information", "Please specify a left hand of the bigram.")
                return
            if rhs == '':
                reply = QMessageBox.critical(self,
                        "Missing information", "Please specify a right hand of the bigram.")
                return

            env = '{}{}'.format(lhs,rhs)
        self.rowToAdd.emit(env)
        if not self.addOneMore:
            QDialog.accept(self)
        else:
            self.reset()

    def reject(self):
        QDialog.reject(self)


class SegmentSelectDialog(QDialog):
    def __init__(self, inventory, selected = None, parent=None):
        QDialog.__init__(self,parent)

        layout = QVBoxLayout()

        segFrame = QFrame()

        segLayout = QHBoxLayout()

        self.segFrame = SegmentSelectionWidget(inventory)

        if selected is not None:
            self.segFrame.select(selected)

        segLayout.addWidget(self.segFrame)

        segFrame.setLayout(segLayout)

        layout.addWidget(segFrame)


        self.acceptButton = QPushButton('Ok')
        self.cancelButton = QPushButton('Cancel')
        acLayout = QHBoxLayout()
        acLayout.addWidget(self.acceptButton, alignment = Qt.AlignLeft)
        acLayout.addWidget(self.cancelButton, alignment = Qt.AlignLeft)
        self.acceptButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(acLayout)

        layout.addWidget(acFrame, alignment = Qt.AlignLeft)

        self.setLayout(layout)
        self.setWindowTitle('Select segment pair')

    def value(self):
        return self.segFrame.value()

    def reset(self):
        self.segFrame.clearAll()


class EnvironmentSegmentWidget(QWidget):
    def __init__(self, inventory, parent = None, middle = False, enabled = True):
        QWidget.__init__(self, parent)
        self.inventory = inventory
        self.segments = set()
        self.enabled = enabled

        self.middle = middle

        layout = QVBoxLayout()
        if self.middle:
            lab = '_\n\n{}'
        else:
            lab = '{}'
        self.mainLabel = QLabel(lab)
        self.mainLabel.setMargin(4)
        self.mainLabel.setFrameShape(QFrame.Box)
        self.mainLabel.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

        layout.addWidget(self.mainLabel)

        self.setLayout(layout)

        self.mainLabel.setContextMenuPolicy(Qt.CustomContextMenu)
        self.mainLabel.customContextMenuRequested.connect(self.showMenu)

    def mouseReleaseEvent(self, ev):
        if not self.enabled:
            ev.ignore()
            return
        if ev.button() == Qt.LeftButton:
            self.selectSegments()
            ev.accept()

    def updateLabel(self):
        if self.middle:
            lab = '_\n\n{%s}'
        else:
            lab = '{%s}'
        lab = lab % ', '.join(self.segments)
        self.mainLabel.setText(lab)

    def selectSegments(self):
        dialog = SegmentSelectDialog(self.inventory, self.segments, self)
        if dialog.exec_():
            self.segments = dialog.value()
            self.updateLabel()

    def showMenu(self, pos):
        if self.middle:
            return
        removeAction = QAction(self)
        removeAction.setText('Delete')
        removeAction.triggered.connect(self.deleteLater)

        menu = QMenu(self)
        menu.addAction(removeAction)

        menu.popup(self.mapToGlobal(pos))

    def value(self):
        return self.segments

class EnvironmentWidget(QWidget):
    def __init__(self, inventory, parent = None, middle = True):
        QWidget.__init__(self, parent)
        self.inventory = inventory
        layout = QHBoxLayout()

        self.lhsAddNew = QPushButton('+')

        self.lhsAddNew.clicked.connect(self.addLhs)

        self.lhsWidget = QWidget()

        lhslayout = QHBoxLayout()
        self.lhsWidget.setLayout(lhslayout)

        self.rhsAddNew = QPushButton('+')

        self.rhsAddNew.clicked.connect(self.addRhs)

        self.rhsWidget = QWidget()

        rhslayout = QHBoxLayout()
        self.rhsWidget.setLayout(rhslayout)

        self.middleWidget = EnvironmentSegmentWidget(self.inventory, middle = True, enabled = middle)

        self.removeButton = QPushButton('Remove environment')

        self.removeButton.clicked.connect(self.deleteLater)

        layout.addWidget(self.lhsAddNew)
        layout.addWidget(self.lhsWidget)
        layout.addWidget(self.middleWidget)
        layout.addWidget(self.rhsWidget)
        layout.addWidget(self.rhsAddNew)

        layout.addStretch()

        optionlayout = QVBoxLayout()

        optionlayout.addWidget(self.removeButton)

        layout.addLayout(optionlayout)

        self.setLayout(layout)

    def addLhs(self):
        segWidget = EnvironmentSegmentWidget(self.inventory)
        self.lhsWidget.layout().insertWidget(0,segWidget)

    def addRhs(self):
        segWidget = EnvironmentSegmentWidget(self.inventory)
        self.rhsWidget.layout().addWidget(segWidget)

    def value(self):
        lhs = []
        for ind in range(self.lhsWidget.layout().count()):
            wid = self.lhsWidget.layout().itemAt(ind).widget()
            lhs.append(wid.value())
        rhs = []
        for ind in range(self.rhsWidget.layout().count()):
            wid = self.rhsWidget.layout().itemAt(ind).widget()
            rhs.append(wid.value())
        middle = self.middleWidget.value()

        return EnvironmentFilter(middle, lhs, rhs)

class EnvironmentSelectWidget(QGroupBox):
    def __init__(self, inventory, parent = None, middle = True):
        QGroupBox.__init__(self,'Environments',parent)
        self.middle = middle
        self.inventory = inventory

        layout = QVBoxLayout()

        scroll = QScrollArea()
        self.environmentFrame = QWidget()
        lay = QBoxLayout(QBoxLayout.TopToBottom)
        self.addButton = QPushButton('New environment')
        self.addButton.clicked.connect(self.addNewEnvironment)
        lay.addWidget(self.addButton)
        lay.addStretch()
        self.environmentFrame.setLayout(lay)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.environmentFrame)
        scroll.setMinimumWidth(140)
        scroll.setMinimumHeight(200)

        policy = scroll.sizePolicy()
        policy.setVerticalStretch(1)
        scroll.setSizePolicy(policy)
        layout.addWidget(scroll)

        self.setLayout(layout)

    def addNewEnvironment(self):
        envWidget = EnvironmentWidget(self.inventory, middle = self.middle)
        pos = self.environmentFrame.layout().count() - 2
        self.environmentFrame.layout().insertWidget(pos,envWidget)

    def value(self):
        envs = []
        for ind in range(self.environmentFrame.layout().count() - 2):
            wid = self.environmentFrame.layout().itemAt(ind).widget()
            envs.append(wid.value())
        return envs


class BigramWidget(QGroupBox):
    name = 'bigram'
    def __init__(self,inventory,parent=None):
        QGroupBox.__init__(self,'{}s'.format(self.name.title()),parent)

        self.inventory = corpus.inventory
        self.corpus = corpus
        vbox = QVBoxLayout()

        self.addButton = QPushButton('Add {}'.format(self.name))
        self.addButton.clicked.connect(self.envPopup)
        self.removeButton = QPushButton('Remove selected {}s'.format(self.name))
        self.removeButton.clicked.connect(self.removeEnv)
        self.addButton.setAutoDefault(False)
        self.addButton.setDefault(False)
        self.removeButton.setAutoDefault(False)
        self.removeButton.setDefault(False)

        self.table = TableWidget()
        self.table.setSortingEnabled(False)
        try:
            self.table.horizontalHeader().setClickable(False)
            self.table.horizontalHeader().setResizeMode(QHeaderView.Stretch)
        except AttributeError:
            self.table.horizontalHeader().setSectionsClickable(False)
            self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setModel(EnvironmentModel())
        #self.table.resizeColumnsToContents()

        vbox.addWidget(self.addButton)
        vbox.addWidget(self.removeButton)
        vbox.addWidget(self.table)

        self.setLayout(vbox)

    def addRow(self, row):
        self.table.model().addRow([row])

    def envPopup(self):
        dialog = EnvironmentDialog(self.inventory,self)
        dialog.rowToAdd.connect(self.addRow)
        result = dialog.exec_()
        dialog.rowToAdd.disconnect()
        dialog.deleteLater()

    def removeEnv(self):
        select = self.table.selectionModel()
        if select.hasSelection():
            selected = select.selectedRows()
            self.table.model().removeRows([s.row() for s in selected])

    def value(self):
        return [x[0] for x in self.table.model().rows]

class RadioSelectWidget(QGroupBox):
    def __init__(self,title,options, actions=None, enabled=None,parent=None):
        QGroupBox.__init__(self,title,parent)
        self.is_enabled = True
        self.actions = None
        self.enabled = None
        self.setLayout(QFormLayout())
        self.setOptions(options, actions, enabled)

    def initOptions(self):
        self.widgets = []
        for key in self.options.keys():
            w = QRadioButton(key)
            if self.actions is not None:
                w.clicked.connect(self.actions[key])
            if self.enabled is not None:
                w.setEnabled(self.enabled[key])
            if not self.is_enabled:
                w.setEnabled(False)
            self.widgets.append(w)
            self.layout().addRow(w)
        self.widgets[0].setChecked(True)

    def setOptions(self, options, actions = None, enabled = None):
        for i in reversed(range(self.layout().count())):
            w = self.layout().itemAt(i).widget()
            self.layout().removeWidget(w)
            w.setParent(None)
            w.deleteLater()
        self.options = options
        if actions is not None:
            self.actions = actions
        if enabled is not None:
            self.enabled = enabled
        self.initOptions()


    def initialClick(self):
        self.widgets[0].click()

    def click(self,index):
        if index >= len(self.widgets):
            return
        self.widgets[index].click()

    def value(self):
        for w in self.widgets:
            if w.isChecked():
                return self.options[w.text()]
        return None

    def displayValue(self):
        for w in self.widgets:
            if w.isChecked():
                return w.text()
        return ''

    def disable(self):
        self.is_enabled = False
        for w in self.widgets:
            w.setEnabled(False)

    def enable(self):
        self.is_enabled = True
        for w in self.widgets:
            if self.enabled is not None:
                w.setEnabled(self.enabled[key])
            else:
                w.setEnabled(True)

class RestrictedContextWidget(RadioSelectWidget):
    canonical = 'Use canonical forms only'
    frequent = 'Use most frequent forms only'
    canonical_value = 'canonical'
    frequent_value = 'mostfrequent'
    def __init__(self, corpus, actions = None, parent = None):
        typetokenEnabled = {self.canonical: corpus.has_transcription,
                    self.frequent: corpus.has_wordtokens}
        RadioSelectWidget.__init__(self,'Pronunciation variants',
                                            OrderedDict([(self.canonical, self.canonical_value),
                                            (self.frequent, self.frequent_value)]),
                                            actions,
                                            typetokenEnabled)

class ContextWidget(RestrictedContextWidget):
    separate = 'Count each word token as a separate entry'
    relative = 'Weight each word type\nby the relative frequency of its variants'
    separate_value = 'separatetoken'
    relative_value = 'relativetype'
    def __init__(self, corpus, actions = None, parent = None):
        typetokenEnabled = {self.canonical: corpus.has_transcription,
                    self.frequent: corpus.has_wordtokens,
                    self.separate: corpus.has_wordtokens,
                    self.relative: corpus.has_wordtokens}
        RadioSelectWidget.__init__(self,'Pronunciation variants',
                                            OrderedDict([(self.canonical, self.canonical_value),
                                            (self.frequent, self.frequent_value),
                                            (self.separate, self.separate_value),
                                            (self.relative, self.relative_value)
                                            ]),
                                            actions,
                                            typetokenEnabled)

class CreateClassWidget(QDialog):
    def __init__(self, parent, corpus, class_type=None, default_name=None, default_specs=None):
        QDialog.__init__(self, parent)

        self.corpus = corpus
        self.class_type = class_type

        self.mainLayout = QVBoxLayout()

        if self.class_type == 'tier':
            explanation = ('You can create Tiers in this window. A Tier is subpart of a word that consists only of '
            'the segments you want, maintaining their original ordering. You can define the properties of the Tier below. '
            'Tiers are commonly created on the basis of a feature class, e.g. all the vowels or of all the obstruents in a word. '
            'PCT will allow you to create Tiers consisting of any arbitrary set of sounds.\n'
            'Once created, the Tier will be added as a column in your corpus, and it will be visible in the main window. '
            'You can then select this Tier inside of certain analysis functions.')
        elif self.class_type == 'class':
            explanation = ('You can create Classes in this window. A Class is simply a set of sounds from the inventory '
            'of your corpus. Classes are normally created on the basis of shared phonological features, in which case they are '
            'usually called  \"natural\" classes. An arbitrary set of sounds with no common features may be called \"unnatural\".\n'
            'PCT allows the creation of classes of either type. Once created, Classes can be selected from within certain analysis functions. '
            'Classes can also be used to organize the inventory chart for your corpus')
        elif self.class_type == 'inventory':
            self.class_type = 'row or column'
            explanation = ('This window allows you to specify the details of the column or row you selected in your '
                            'inventory. You can change the name, and you can set a filter for which kinds of segments '
                            'should appear in this column or row.')
        else:
            explanation = ''

        explanation = QLabel(explanation)

        explanation.setWordWrap(True)
        self.mainLayout.addWidget(explanation)

        self.nameFrame = QGroupBox('Name of {}'.format(self.class_type))
        self.nameEdit = QLineEdit()
        nameLayout = QFormLayout()
        nameLayout.addRow(self.nameEdit)
        if default_name is not None:
            self.nameEdit.setText(default_name)
        self.nameFrame.setLayout(nameLayout)
        self.mainLayout.addWidget(self.nameFrame)

        self.defineFrame = SegmentSelectionWidget(self.corpus.inventory)

        self.mainLayout.addWidget(self.defineFrame)

        self.createButton = QPushButton('Create {}'.format(self.class_type))
        self.cancelButton = QPushButton('Cancel')
        acLayout = QHBoxLayout()
        acLayout.addWidget(self.createButton)
        acLayout.addWidget(self.cancelButton)
        self.createButton.clicked.connect(self.accept)
        self.cancelButton.clicked.connect(self.reject)

        acFrame = QFrame()
        acFrame.setLayout(acLayout)

        self.mainLayout.addWidget(acFrame)

        self.setLayout(self.mainLayout)

        self.setWindowTitle('Create {}'.format(self.class_type))

    def generateClass(self):
        previewList = self.defineFrame.value()
        if (previewList):
            reply = QMessageBox.critical(self,
                    "Missing information", "Please specify at least one segment.")
            return
        notInPreviewList = [x.symbol for x in self.corpus.inventory if x.symbol not in previewList]
        return previewList, notInPreviewList

    def preview(self):
        inClass, notInClass = self.generateClass()
        reply = QMessageBox.information(self,
                "{} preview".format(self.class_type),
                "Segments included: {}\nSegments excluded: {}".format(', '.join(inClass),
                                                                      ', '.join(notInClass)))

