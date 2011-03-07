import unittest
import main

class TestPdfExtract(unittest.TestCase):
    def test_plain_text(self):
        text = 'this is plain text'
        self.assertEqual(main.get_text(text), text)
        
    def test_simple_pdf(self):
        text = "this is a simple test"
        content = open('tests/simplepdf1.pdf', 'r').read()
        self.assertEqual(main.get_text(content), text)

class TestWordStats(unittest.TestCase):
    def test_blank(self):
        self.assertEqual(main.get_word_stats(main.get_text('abc;def ghi  \n jkl3 ')), (4, 0))

    def test_change(self):
        self.assertEqual(main.get_word_stats(main.get_text('abc;def ghi  \n jkl3 foo bar'),
                                             main.get_text('abc;def ghi foo bar')), (6, 1))

    def test_change2(self):
        self.assertEqual(main.get_word_stats(main.get_text('abc;dyfinitely ghjoolies  \n jkl3 foo bar'),
                                             main.get_text('abc;definitely ghioolies foo bar')), (6, 3))
