import unittest
import os
import shutil
import tempfile
from main import extract_from_filename, get_extension_examples

class TestRenamer(unittest.TestCase):
    def setUp(self):
        # 创建临时测试目录
        self.test_dir = tempfile.mkdtemp()
        self.mock_vol = os.path.join(self.test_dir, "MockVolume")
        os.makedirs(self.mock_vol)
        
        # 创建模拟视频文件
        self.video_file = os.path.join(self.mock_vol, "A001C002_240319.mp4")
        with open(self.video_file, 'w') as f: f.write("mock")
        
        # 创建模拟 XML 文件
        self.xml_file = os.path.join(self.mock_vol, "metadata.xml")
        with open(self.xml_file, 'w') as f: f.write("mock")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_get_extension_examples(self):
        examples = get_extension_examples(self.mock_vol)
        self.assertIn(".mp4", examples)
        self.assertIn(".xml", examples)
        self.assertEqual(examples[".mp4"], "A001C002_240319.mp4")
        self.assertEqual(examples[".xml"], "metadata.xml")

    def test_extract_prefix(self):
        # 从前往后提取 8 位
        new_name = extract_from_filename(self.mock_vol, "mp4", "prefix", 8)
        self.assertEqual(new_name, "A001C002")

    def test_extract_suffix(self):
        # 从后往前提取 6 位 (排除 .mp4)
        new_name = extract_from_filename(self.mock_vol, "mp4", "suffix", 6)
        self.assertEqual(new_name, "240319")

    def test_extract_different_ext(self):
        # 找不到匹配的扩展名
        new_name = extract_from_filename(self.mock_vol, "mov", "prefix", 5)
        self.assertIsNone(new_name)

if __name__ == "__main__":
    unittest.main()
