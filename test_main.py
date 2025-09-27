import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
import sys
import os

# 添加主模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import (
    FileParser, FileReader, CallRecord, ContactGrouper,
    OllamaAnalyzer, MarkdownReportGenerator, setup_logging
)

class TestFileParser:
    """测试文件名解析器"""

    def setup_method(self):
        self.parser = FileParser()

    def test_parse_format1_plus86(self):
        """测试格式1: +86 130 1111 6636_20231128203503_transcription.txt"""
        filename = "+86 130 1111 6636_20231128203503_transcription.txt"
        result = self.parser.parse_filename(filename)

        assert result is not None
        phone_number, timestamp, contact_name = result
        assert phone_number == "13011116636"
        assert timestamp == datetime(2023, 11, 28, 20, 35, 3)
        assert contact_name is None

    def test_parse_format2_simple(self):
        """测试格式2: 186 1111 1585_20230510151000_transcription.txt"""
        filename = "186 1111 1585_20230510151000_transcription.txt"
        result = self.parser.parse_filename(filename)

        assert result is not None
        phone_number, timestamp, contact_name = result
        assert phone_number == "18666661585"
        assert timestamp == datetime(2023, 5, 10, 15, 10, 0)
        assert contact_name is None

    def test_parse_format3_with_name(self):
        """测试格式3: 张三@+86 189 1111 3851_20240525160431_transcription.txt"""
        filename = "张三@+86 189 1111 3851_20240525160431_transcription.txt"
        result = self.parser.parse_filename(filename)

        assert result is not None
        phone_number, timestamp, contact_name = result
        assert phone_number == "18911113851"
        assert timestamp == datetime(2024, 5, 25, 16, 4, 31)
        assert contact_name == "张三"

    def test_parse_invalid_filename(self):
        """测试解析无效文件名"""
        invalid_filenames = [
            "invalid_filename.txt",
            "+86 130_20231128203503_transcription.txt",
            "+86 130 1111 6636_invalid_date_transcription.txt",
            "not_a_phone_file.txt"
        ]

        for filename in invalid_filenames:
            result = self.parser.parse_filename(filename)
            assert result is None

    def test_clean_name_lax_mode(self):
        """测试宽松模式姓名清理"""
        # 移除文件系统不安全字符
        assert self.parser.clean_name("张三/李四") == "张三李四"
        assert self.parser.clean_name("María José") == "María José"  # 保留其他特殊字符
        assert self.parser.clean_name("测试<>:\"name\"") == "测试name"

        # 处理长名称
        long_name = "非常长的姓名" * 20
        cleaned = self.parser.clean_name(long_name)
        assert len(cleaned) <= 50

        # 处理空名称
        assert self.parser.clean_name("") == "未知联系人"
        assert self.parser.clean_name("   ") == "未知联系人"

    def test_get_contact_name_with_real_name(self):
        """测试带真实姓名的联系人名称生成"""
        phone = "13013696636"
        # 有姓名时返回姓名
        contact_name = self.parser.get_contact_name(phone, "张三")
        assert contact_name == "张三"

        # 无姓名时返回默认格式
        contact_name = self.parser.get_contact_name(phone)
        assert contact_name == "联系人_6636"

class TestFileReader:
    """测试文件读取器"""

    def setup_method(self):
        # 创建临时目录和测试文件
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_data_dir = self.temp_dir / "test_data"
        self.test_data_dir.mkdir()

        # 创建测试文件
        self.create_test_files()
        self.reader = FileReader(self.test_data_dir)

    def teardown_method(self):
        # 清理临时文件
        shutil.rmtree(self.temp_dir)

    def create_test_files(self):
        """创建测试用的通话记录文件（包含多种格式）"""
        test_files = [
            # 格式1: +86 格式
            ("+86 130 1111 6636_20231128203503_transcription.txt", "这是一个测试通话记录内容。"),
            ("+86 131 1111 0998_20230531171822_transcription.txt", "另一个测试通话记录，包含更多信息。"),
            # 格式2: 简单格式
            ("186 6666 1585_20230510151000_transcription.txt", "简单格式的通话记录。"),
            # 格式3: 带姓名格式
            ("张三@+86 189 1111 3851_20240525160431_transcription.txt", "张三的通话记录内容。"),
            ("李四@+86 138 0000 0001_20240101120000_transcription.txt", "李四的新年通话。"),
            # 无效文件
            ("invalid_file.txt", "这个文件名格式不正确")
        ]

        for filename, content in test_files:
            file_path = self.test_data_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

    def test_load_all_records_enhanced(self):
        """测试加载所有记录（包含新格式）"""
        records = self.reader.load_all_records()

        # 应该只加载有效格式的文件（5个）
        assert len(records) == 5

        # 检查记录内容
        phone_numbers = [record.phone_number for record in records]
        assert "13011116636" in phone_numbers
        assert "18666661585" in phone_numbers  # 格式2
        assert "18911113851" in phone_numbers  # 格式3

        # 检查联系人姓名
        names_with_phone = {(r.phone_number, list(r.contact_names)[0] if r.contact_names else None) for r in records}
        assert ("18911113851", "张三") in names_with_phone
        assert ("13800000001", "李四") in names_with_phone

    def test_read_file_content(self):
        """测试文件内容读取"""
        file_path = self.test_data_dir / "+86 130 1111 6636_20231128203503_transcription.txt"
        content = self.reader.read_file_content(file_path)

        assert content == "这是一个测试通话记录内容。"

    def test_load_all_records(self):
        """测试加载所有记录"""
        records = self.reader.load_all_records()

        # 应该只加载有效格式的文件（5个，因为添加了新格式）
        assert len(records) == 5

        # 检查记录内容
        phone_numbers = [record.phone_number for record in records]
        assert "13013696636" in phone_numbers
        assert "13120090998" in phone_numbers
        assert "18666661585" in phone_numbers  # 新格式2
        assert "18942393851" in phone_numbers  # 新格式3
        assert "13800000001" in phone_numbers  # 新格式3

    def test_nonexistent_directory(self):
        """测试不存在的目录"""
        reader = FileReader(Path("nonexistent_directory"))
        records = reader.load_all_records()
        assert len(records) == 0

class TestContactGrouper:
    """测试联系人分组器"""

    def setup_method(self):
        self.parser = FileParser()
        self.grouper = ContactGrouper(self.parser)

        # 创建测试记录（包含多姓名变体）
        self.test_records = [
            CallRecord(
                phone_number="13013696636",
                timestamp=datetime(2023, 11, 28, 20, 35, 3),
                file_path=Path("test1.txt"),
                content="测试内容1",
                contact_names={"张三"},
                primary_name="张三"
            ),
            CallRecord(
                phone_number="13013696636",
                timestamp=datetime(2023, 11, 29, 10, 15, 0),
                file_path=Path("test2.txt"),
                content="测试内容2",
                contact_names={"小张"},
                primary_name="小张"
            ),
            CallRecord(
                phone_number="13120090998",
                timestamp=datetime(2023, 5, 31, 17, 18, 22),
                file_path=Path("test3.txt"),
                content="测试内容3",
                contact_names=set(),
                primary_name=None
            )
        ]

    def test_group_records_by_contact_enhanced(self):
        """测试按联系人分组（增强版，包含姓名变体）"""
        groups = self.grouper.group_records_by_contact(self.test_records)

        # 应该有两个分组（按电话号码分组）
        assert len(groups) == 2

        # 检查第一个联系人（张三，有多个姓名变体）
        zhang_group = None
        for name, data in groups.items():
            if data['phone'] == "13013696636":
                zhang_group = data
                break

        assert zhang_group is not None
        assert zhang_group['phone'] == "13013696636"
        assert zhang_group['total_calls'] == 2
        assert len(zhang_group['records']) == 2
        # 检查所有姓名变体都被保留
        assert zhang_group['all_names'] == {"张三", "小张"}
        # 检查主要姓名（应该是第一个非空的）
        assert zhang_group['primary_name'] in ["张三", "小张"]

        # 检查第二个联系人（无姓名）
        no_name_group = None
        for name, data in groups.items():
            if data['phone'] == "13120090998":
                no_name_group = data
                break

        assert no_name_group is not None
        assert no_name_group['phone'] == "13120090998"
        assert no_name_group['total_calls'] == 1
        assert no_name_group['all_names'] == set()

    def test_multiple_names_same_phone(self):
        """测试同一电话号码多个姓名的处理"""
        # 创建同一号码不同姓名的记录
        records = [
            CallRecord(
                phone_number="13800000001",
                timestamp=datetime(2024, 1, 1, 12, 0, 0),
                file_path=Path("test1.txt"),
                content="张三的通话",
                contact_names={"张三"},
                primary_name="张三"
            ),
            CallRecord(
                phone_number="13800000001",
                timestamp=datetime(2024, 1, 2, 13, 0, 0),
                file_path=Path("test2.txt"),
                content="无姓名通话",
                contact_names=set(),
                primary_name=None
            ),
            CallRecord(
                phone_number="13800000001",
                timestamp=datetime(2024, 1, 3, 14, 0, 0),
                file_path=Path("test3.txt"),
                content="小张的通话",
                contact_names={"小张"},
                primary_name="小张"
            )
        ]

        groups = self.grouper.group_records_by_contact(records)
        assert len(groups) == 1

        contact = list(groups.values())[0]
        assert contact['all_names'] == {"张三", "小张"}
        assert contact['total_calls'] == 3
        assert contact['primary_name'] == "张三"  # 第一个非空姓名

class TestOllamaAnalyzer:
    """测试 Ollama 分析器"""

    def setup_method(self):
        self.analyzer = OllamaAnalyzer()

    @patch('ollama.list')
    def test_check_ollama_connection_success(self, mock_list):
        """测试 Ollama 连接成功"""
        mock_list.return_value = {
            'models': [{'name': 'qwen2:latest'}, {'name': 'llama2:latest'}]
        }

        result = self.analyzer.check_ollama_connection()
        assert result is True

    @patch('ollama.list')
    def test_check_ollama_connection_failure(self, mock_list):
        """测试 Ollama 连接失败"""
        mock_list.side_effect = Exception("Connection failed")

        result = self.analyzer.check_ollama_connection()
        assert result is False

    @patch('ollama.chat')
    def test_analyze_single_call_success(self, mock_chat):
        """测试单个通话分析成功"""
        mock_chat.return_value = {
            'message': {'content': '分析结果：这是一个商务通话'}
        }

        result = self.analyzer.analyze_single_call("测试通话内容")
        assert result['status'] == 'success'
        assert '分析结果：这是一个商务通话' in result['analysis']

    @patch('ollama.chat')
    def test_analyze_single_call_failure(self, mock_chat):
        """测试单个通话分析失败"""
        mock_chat.side_effect = Exception("API error")

        result = self.analyzer.analyze_single_call("测试通话内容")
        assert result['status'] == 'error'
        assert 'API error' in result['analysis']

class TestMarkdownReportGenerator:
    """测试 Markdown 报告生成器"""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.generator = MarkdownReportGenerator(self.temp_dir)

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def test_generate_contact_report_with_ai_analysis(self):
        """测试生成包含AI分析的报告"""
        contact_data = {
            'phone': '13013696636',
            'records': [
                CallRecord(
                    phone_number="13013696636",
                    timestamp=datetime(2023, 11, 28, 20, 35, 3),
                    file_path=Path("test.txt"),
                    content="测试通话内容"
                )
            ],
            'first_call': datetime(2023, 11, 28, 20, 35, 3),
            'last_call': datetime(2023, 11, 28, 20, 35, 3),
            'total_calls': 1
        }

        analysis_result = {
            'status': 'success',
            'summary': '# AI分析报告\n这是AI生成的分析内容'
        }

        report_path = self.generator.generate_contact_report(
            "联系人_6636", contact_data, analysis_result
        )

        # 检查文件是否创建
        assert report_path.exists()

        # 检查文件内容
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert 'AI分析报告' in content

    def test_generate_enhanced_report_with_multiple_names(self):
        """测试生成包含多姓名变体的增强报告"""
        contact_data = {
            'phone': '13013696636',
            'all_names': {'张三', '小张'},
            'primary_name': '张三',
            'records': [
                CallRecord(
                    phone_number="13013696636",
                    timestamp=datetime(2023, 11, 28, 20, 35, 3),
                    file_path=Path("test.txt"),
                    content="测试通话内容",
                    contact_names={'张三'},
                    primary_name='张三'
                )
            ],
            'first_call': datetime(2023, 11, 28, 20, 35, 3),
            'last_call': datetime(2023, 11, 28, 20, 35, 3),
            'total_calls': 1
        }

        analysis_result = {
            'status': 'error',
            'summary': ''
        }

        report_path = self.generator.generate_contact_report(
            "张三", contact_data, analysis_result
        )

        # 检查文件是否创建（应该使用真实姓名，但min函数会选择字典序最小的）
        assert report_path.exists()
        assert "小张_6636_通话分析报告.md" in str(report_path)

        # 检查文件内容
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '张三 通话分析报告' in content
        assert '主要姓名' in content
        assert '所有姓名变体: 小张, 张三' in content

    def test_safe_filename_generation(self):
        """测试安全文件名生成"""
        # 测试优先使用真实姓名（min会选择字典序最小的，即"小张"）
        filename = self.generator._get_safe_filename({'张三', '小张'}, '13013696636', '张三')
        assert filename == "小张_6636"

        # 测试无有效姓名时的处理
        filename = self.generator._get_safe_filename(set(), '13013696636', '联系人_6636')
        assert filename == "联系人_6636"

        # 测试特殊字符清理
        filename = self.generator._get_safe_filename({'张三/李四'}, '13013696636', '张三/李四')
        assert filename == "张三李四_6636"

    def test_generate_basic_report_without_ai(self):
        """测试生成基础报告（无AI分析）"""
        contact_data = {
            'phone': '13013696636',
            'all_names': set(),
            'primary_name': None,
            'records': [
                CallRecord(
                    phone_number="13013696636",
                    timestamp=datetime(2023, 11, 28, 20, 35, 3),
                    file_path=Path("test.txt"),
                    content="测试通话内容",
                    contact_names=set(),
                    primary_name=None
                )
            ],
            'first_call': datetime(2023, 11, 28, 20, 35, 3),
            'last_call': datetime(2023, 11, 28, 20, 35, 3),
            'total_calls': 1
        }

        analysis_result = {
            'status': 'error',
            'summary': ''
        }

        report_path = self.generator.generate_contact_report(
            "联系人_6636", contact_data, analysis_result
        )

        # 检查文件是否创建
        assert report_path.exists()

        # 检查文件内容
        with open(report_path, 'r', encoding='utf-8') as f:
            content = f.read()
        assert '联系人_6636 通话分析报告' in content
        assert '基本信息' in content

class TestIntegration:
    """集成测试"""

    def setup_method(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.test_data_dir = self.temp_dir / "data" / "txt"
        self.test_data_dir.mkdir(parents=True)
        self.output_dir = self.temp_dir / "output"

        # 创建测试数据
        self.create_test_data()

    def teardown_method(self):
        shutil.rmtree(self.temp_dir)

    def create_test_data(self):
        """创建集成测试数据"""
        test_files = [
            ("+86 130 1369 6636_20231128203503_transcription.txt",
             "这是张三的第一次通话，讨论了项目合作的相关事宜。"),
            ("+86 130 1369 6636_20231129101500_transcription.txt",
             "这是张三的第二次通话，确认了合作细节。"),
            ("+86 131 2009 0998_20230531171822_transcription.txt",
             "李四的通话记录，关于技术咨询。")
        ]

        for filename, content in test_files:
            file_path = self.test_data_dir / filename
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

    @patch('ollama.list')
    @patch('ollama.chat')
    def test_full_workflow_with_mock_ollama(self, mock_chat, mock_list):
        """测试完整工作流程（模拟Ollama）"""
        # 模拟 Ollama 可用
        mock_list.return_value = {
            'models': [{'name': 'qwen2:latest'}]
        }
        mock_chat.return_value = {
            'message': {'content': '# 模拟AI分析报告\n这是模拟的分析内容'}
        }

        # 初始化组件
        reader = FileReader(self.test_data_dir)
        analyzer = OllamaAnalyzer()
        grouper = ContactGrouper(reader.parser)
        report_generator = MarkdownReportGenerator(self.output_dir)

        # 执行流程
        records = reader.load_all_records()
        assert len(records) == 3

        contact_groups = grouper.group_records_by_contact(records)
        assert len(contact_groups) == 2

        # 生成报告
        for contact_name, contact_data in contact_groups.items():
            analysis_result = analyzer.summarize_contact_calls(
                contact_data['records'], contact_name
            )
            report_path = report_generator.generate_contact_report(
                contact_name, contact_data, analysis_result
            )
            assert report_path.exists()

def test_setup_logging():
    """测试日志配置"""
    # 测试不会抛出异常
    setup_logging(log_level="DEBUG", log_file=False)

    # 测试带文件输出
    with tempfile.TemporaryDirectory() as temp_dir:
        os.chdir(temp_dir)
        setup_logging(log_level="INFO", log_file=True)

        # 检查日志目录是否创建
        logs_dir = Path("logs")
        assert logs_dir.exists()

if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])