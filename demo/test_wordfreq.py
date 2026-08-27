"""单元测试：统计英文单词出现次数"""

import unittest
from wordfreq import count_words


class TestWordFreq(unittest.TestCase):
    def test_empty_text(self):
        """测试空文本"""
        result = count_words("")
        self.assertEqual(result, {})
    
    def test_single_word(self):
        """测试单个单词"""
        result = count_words("hello")
        self.assertEqual(result, {"hello": 1})
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        result = count_words("Hello hello HELLO")
        self.assertEqual(result, {"hello": 3})
    
    def test_with_punctuation(self):
        """测试包含标点符号"""
        result = count_words("Hello, world! Hello, everyone.")
        self.assertEqual(result, {"hello": 2, "world": 1, "everyone": 1})
    
    def test_mixed_content(self):
        """测试混合内容"""
        result = count_words("The quick brown fox jumps over the lazy dog. The dog was not amused.")
        expected = {
            "the": 3, "quick": 1, "brown": 1, "fox": 1, 
            "jumps": 1, "over": 1, "lazy": 1, "dog": 2, 
            "was": 1, "not": 1, "amused": 1
        }
        self.assertEqual(result, expected)
    
    def test_numbers_and_symbols(self):
        """测试数字和符号被忽略"""
        result = count_words("123 test 456 test! @#$ test")
        self.assertEqual(result, {"test": 3})
    
    def test_sorted_output(self):
        """测试输出按字母顺序排序"""
        result = count_words("zebra apple banana apple zebra")
        expected = {"apple": 2, "banana": 1, "zebra": 2}
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()