import unittest
import pytest
import os
import sys

from corpustools.corpus.io import (download_binary, save_binary, load_binary,
                                load_corpus_csv,load_spelling_corpus, load_transcription_corpus,
                                export_corpus_csv, export_feature_matrix_csv,
                                load_feature_matrix_csv,
                                load_corpus_ilg)

from corpustools.corpus.io.csv import inspect_csv

from corpustools.exceptions import DelimiterError, ILGWordMismatchError

from corpustools.corpus.classes import (Word, Corpus, FeatureMatrix)

TEST_DIR = 'tests/data'

def test_inspect_example():
    example_path = os.path.join(TEST_DIR,'example.txt')
    atts, coldelim = inspect_csv(example_path)
    assert(coldelim == ',')
    for a in atts:
        if a.name == 'frequency':
            assert(a.att_type == 'numeric')
        elif a.name == 'transcription':
            assert(a.att_type == 'tier')
            assert(a._delim == '.')
        elif a.name == 'spelling':
            assert(a.att_type == 'spelling')

def test_ilg_basic():
    basic_path = os.path.join(TEST_DIR,'ilg','test_basic.txt')
    corpus = load_corpus_ilg('test', basic_path,delimiter=None,ignore_list=[], trans_delimiter = '.')
    #print(corpus.words)
    assert(corpus.lexicon.find('a').frequency == 2)

def test_ilg_mismatched():
    mismatched_path = os.path.join(TEST_DIR,'ilg','test_mismatched.txt')
    with pytest.raises(ILGWordMismatchError):
        t = load_corpus_ilg('test', mismatched_path, delimiter=None,ignore_list=[], trans_delimiter = '.')

def test_corpus_csv(unspecified_test_corpus):
    example_path = os.path.join(TEST_DIR,'example.txt')
    with pytest.raises(DelimiterError):
        load_corpus_csv('example',example_path,delimiter='\t')
    with pytest.raises(DelimiterError):
        load_corpus_csv('example',example_path,delimiter=',',trans_delimiter='/')


    c = load_corpus_csv('example',example_path,delimiter=',')

    assert(isinstance(c,Corpus))
    assert(c == unspecified_test_corpus)

def test_load_spelling_no_ignore():
    spelling_path = os.path.join(TEST_DIR,'test_text_spelling.txt')
    with pytest.raises(DelimiterError):
        load_spelling_corpus('test', spelling_path,"?",[])

    c = load_spelling_corpus('test',spelling_path,' ',[])

    assert(c.lexicon['ab'].frequency == 2)


def test_load_spelling_ignore():
    spelling_path = os.path.join(TEST_DIR,'test_text_spelling.txt')
    c = load_spelling_corpus('test',spelling_path,' ',["'",'.'])

    assert(c.lexicon['ab'].frequency == 3)
    assert(c.lexicon['cabd'].frequency == 1)

def test_load_transcription():
    transcription_path = os.path.join(TEST_DIR,'test_text_transcription.txt')
    with pytest.raises(DelimiterError):
        load_transcription_corpus('test',
                            transcription_path," ",[],
                            trans_delimiter = ',')

    c = load_transcription_corpus('test',transcription_path,' ',[],trans_delimiter='.')

    assert(sorted(c.lexicon.inventory) == sorted(['#','a','b','c','d']))

def test_load_transcription_morpheme():
    transcription_morphemes_path = os.path.join(TEST_DIR,'test_text_transcription_morpheme_boundaries.txt')
    c = load_transcription_corpus('test',transcription_morphemes_path,' ',['-','=','.'],trans_delimiter='.')

    assert(c.lexicon['cab'].frequency == 2)

#def test_load_with_fm(self):
    #c = load_transcription_corpus('test',self.transcription_path,' ',
                #['-','=','.'],trans_delimiter='.',
                #feature_system_path = self.full_feature_matrix_path)

    #self.assertEqual(c.lexicon.specifier,load_binary(self.full_feature_matrix_path))

    #self.assertEqual(c.lexicon['cab'].frequency, 1)

    #self.assertEqual(c.lexicon.check_coverage(),[])

    #c = load_transcription_corpus('test',self.transcription_path,' ',
                #['-','=','.'],trans_delimiter='.',
                #feature_system_path = self.missing_feature_matrix_path)

    #self.assertEqual(c.lexicon.specifier,load_binary(self.missing_feature_matrix_path))

    #self.assertEqual(sorted(c.lexicon.check_coverage()),sorted(['b','c','d']))


#class BinaryCorpusLoadTest(unittest.TestCase):
    #def setUp(self):
        #self.example_path = os.path.join(TEST_DIR,'example.corpus')

    #def test_load(self):
        #return
        #if not os.path.exists(TEST_DIR):
            #return
        #c = load_binary(self.example_path)

        #example_c = create_unspecified_test_corpus()

        #self.assertEqual(c,example_c)

def test_save(unspecified_test_corpus):
    save_path = os.path.join(TEST_DIR,'testsave.corpus')
    save_binary(unspecified_test_corpus,save_path)

    c = load_binary(save_path)

    assert(unspecified_test_corpus == c)

#class BinaryCorpusDownloadTest(unittest.TestCase):
    #def setUp(self):
        #self.name = 'example'
        #self.path = os.path.join(TEST_DIR,'testdownload.corpus')
        #self.example_path = os.path.join(TEST_DIR,'example.corpus')

    #def test_download(self):
        #return
        #if not os.path.exists(TEST_DIR):
            #return
        #download_binary(self.name,self.path)

        #c = load_binary(self.path)

        #example_c = load_binary(self.example_path)
        #self.assertEqual(c,example_c)

def test_basic():
    basic_path = os.path.join(TEST_DIR,'test_feature_matrix.txt')

    with pytest.raises(DelimiterError):
        load_feature_matrix_csv('test',basic_path,' ')

    fm = load_feature_matrix_csv('test',basic_path,',')

    assert(fm.name == 'test')
    assert(fm['a','feature1'] == '+')

def test_missing_value():
    missing_value_path = os.path.join(TEST_DIR,'test_feature_matrix_missing_value.txt')
    fm = load_feature_matrix_csv('test',missing_value_path,',')

    assert(fm['d','feature2'] == 'n')

def test_extra_feature():
    extra_feature_path = os.path.join(TEST_DIR,'test_feature_matrix_extra_feature.txt')
    fm = load_feature_matrix_csv('test',extra_feature_path,',')

    with pytest.raises(KeyError):
        fm.__getitem__(('a','feature3'))

#class BinaryFeatureMatrixSaveTest(unittest.TestCase):
    #def setUp(self):
        #self.basic_path = os.path.join(TEST_DIR,'test_feature_matrix.txt')
        #self.basic_save_path = os.path.join(TEST_DIR,'basic.feature')
        #self.missing_segment_path = os.path.join(TEST_DIR,'test_feature_matrix_missing_segment.txt')
        #self.missing_save_path = os.path.join(TEST_DIR,'missing_segments.feature')

    #def test_save(self):
        #if not os.path.exists(TEST_DIR):
            #return
        #fm = load_feature_matrix_csv('test',self.basic_path,',')
        #save_binary(fm,self.basic_save_path)
        #saved_fm = load_binary(self.basic_save_path)
        #self.assertEqual(fm,saved_fm)

        #fm = load_feature_matrix_csv('test',self.missing_segment_path,',')
        #save_binary(fm,self.missing_save_path)
        #saved_fm = load_binary(self.missing_save_path)
        #self.assertEqual(fm,saved_fm)
