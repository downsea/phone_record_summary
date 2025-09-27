import re
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, NamedTuple, Set
from dataclasses import dataclass, field
from loguru import logger
import ollama
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import typer

console = Console()

def setup_logging(log_level: str = "INFO", log_file: bool = True):
    """配置日志系统"""
    # 移除默认的 logger
    logger.remove()

    # 控制台输出格式
    console_format = "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"

    # 添加控制台输出
    logger.add(
        sys.stderr,
        format=console_format,
        level=log_level,
        colorize=True,
        backtrace=True,
        diagnose=True
    )

    # 添加文件输出
    if log_file:
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)

        # 详细日志文件
        logger.add(
            log_dir / "phone_summary_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level="DEBUG",
            rotation="1 day",
            retention="30 days",
            compression="zip",
            encoding="utf-8"
        )

        # 错误日志文件
        logger.add(
            log_dir / "errors_{time:YYYY-MM-DD}.log",
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
            level="ERROR",
            rotation="1 day",
            retention="30 days",
            compression="zip",
            encoding="utf-8"
        )

@dataclass
class CallRecord:
    phone_number: str
    timestamp: datetime
    file_path: Path
    content: str
    contact_names: set = field(default_factory=set)  # 支持多个姓名
    primary_name: Optional[str] = None  # 主要显示姓名

class FileParser:
    """解析通话记录文件名，提取手机号、时间信息和联系人姓名"""

    def __init__(self):
        # 格式1（原有）: +86 130 1369 6636_20231128203503_transcription.txt
        self.pattern1 = re.compile(
            r'\+86\s*(\d{3})\s*(\d{4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式2（新增）: 186 6666 1585_20230510151000_transcription.txt
        self.pattern2 = re.compile(
            r'(\d{3})\s*(\d{4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式3（新增）: 毕恺峰@+86 189 4239 3851_20240525160431_transcription.txt
        self.pattern3 = re.compile(
            r'(.+?)@\+86\s*(\d{3})\s*(\d{4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式4（新增）: 王任栋@138 1081 5897_20250211150653_transcription.txt (无+86前缀)
        self.pattern4 = re.compile(
            r'(.+?)@(\d{3})\s*(\d{4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式5（新增）: 姓名@区号 电话号码 (如: HR service@0755 2856 0169)
        self.pattern5 = re.compile(
            r'(.+?)@(\d{3,4})\s*(\d{3,4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式6（新增）: 姓名@400电话 (如: 神州租车@400 616 6666)
        self.pattern6 = re.compile(
            r'(.+?)@(400)\s*(\d{3})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式7（新增）: 姓名@特殊服务号 (如: 移动@10086, 顺丰速运@95338)
        self.pattern7 = re.compile(
            r'(.+?)@(\d{5,6})_(\d{14})_transcription\.txt'
        )
        # 格式8（新增）: 区号 电话号码 (如: 0755 2345 1855)
        self.pattern8 = re.compile(
            r'(\d{3,4})\s*(\d{3,4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式9（新增）: 400电话 (如: 400 903 0487)
        self.pattern9 = re.compile(
            r'(400)\s*(\d{3})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式10（新增）: 短号码4+4 (如: 6335 2861)
        self.pattern10 = re.compile(
            r'(\d{4})\s*(\d{4})_(\d{14})_transcription\.txt'
        )
        # 格式11（新增）: 8位固定电话 (如: 01012367)
        self.pattern11 = re.compile(
            r'(\d{8})_(\d{14})_transcription\.txt'
        )
        # 格式12（新增）: 特殊服务号 (如: 950618, 10086, 95187)
        self.pattern12 = re.compile(
            r'(\d{5,6})_(\d{14})_transcription\.txt'
        )
        # 格式13（新增）: 国际拨号0086格式 (如: 008615810795994)
        self.pattern13 = re.compile(
            r'(0086)(\d{11})_(\d{14})_transcription\.txt'
        )

    def parse_filename(self, filename: str) -> Optional[tuple[str, datetime, Optional[str]]]:
        """从文件名提取手机号、时间戳和联系人姓名

        Returns:
            tuple: (phone_number, timestamp, contact_name) 或 None
        """
        # 按优先级尝试匹配格式（优先匹配带姓名且更具体的格式）
        patterns = [
            (self.pattern3, 'name_plus86'),    # 格式3：姓名@+86格式
            (self.pattern6, 'name_400'),       # 格式6：姓名@400电话
            (self.pattern7, 'name_service'),   # 格式7：姓名@特殊服务号
            (self.pattern5, 'name_landline'),  # 格式5：姓名@区号电话
            (self.pattern4, 'name_simple'),    # 格式4：姓名@手机号格式
            (self.pattern1, 'plus86'),         # 格式1：+86格式
            (self.pattern13, 'intl_0086'),     # 格式13：国际拨号0086格式
            (self.pattern9, 'plain_400'),      # 格式9：400电话
            (self.pattern8, 'landline'),       # 格式8：区号电话
            (self.pattern2, 'simple'),         # 格式2：简单手机号
            (self.pattern10, 'short_number'),  # 格式10：短号码4+4
            (self.pattern11, 'fixed_8digit'),  # 格式11：8位固定电话
            (self.pattern12, 'service_number') # 格式12：特殊服务号
        ]

        for pattern, format_type in patterns:
            match = pattern.match(filename)
            if match:
                return self._extract_info(match, format_type)

        logger.warning(f"文件名格式不匹配: {filename}")
        return None

    def _extract_info(self, match, format_type: str) -> tuple[str, datetime, Optional[str]]:
        """从匹配结果中提取信息"""
        if format_type == 'name_plus86':
            # 格式3: 姓名@+86 手机号_时间戳_transcription.txt
            name, part1, part2, part3, timestamp_str = match.groups()
            phone = f"{part1}{part2}{part3}"
            cleaned_name = self.clean_name(name)
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, cleaned_name
        elif format_type == 'name_400':
            # 格式6: 姓名@400电话_时间戳_transcription.txt
            name, prefix, part1, part2, timestamp_str = match.groups()
            phone = f"{prefix}{part1}{part2}"
            cleaned_name = self.clean_name(name)
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, cleaned_name
        elif format_type == 'name_service':
            # 格式7: 姓名@特殊服务号_时间戳_transcription.txt
            name, service_number, timestamp_str = match.groups()
            cleaned_name = self.clean_name(name)
            timestamp = self._parse_timestamp(timestamp_str)
            return service_number, timestamp, cleaned_name
        elif format_type == 'name_landline':
            # 格式5: 姓名@区号电话_时间戳_transcription.txt
            name, area_code, part1, part2, timestamp_str = match.groups()
            phone = f"{area_code}{part1}{part2}"
            cleaned_name = self.clean_name(name)
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, cleaned_name
        elif format_type == 'name_simple':
            # 格式4: 姓名@手机号_时间戳_transcription.txt
            name, part1, part2, part3, timestamp_str = match.groups()
            phone = f"{part1}{part2}{part3}"
            cleaned_name = self.clean_name(name)
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, cleaned_name
        elif format_type == 'plus86':
            # 格式1: +86 手机号_时间戳_transcription.txt
            part1, part2, part3, timestamp_str = match.groups()
            phone = f"{part1}{part2}{part3}"
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, None
        elif format_type == 'intl_0086':
            # 格式13: 国际拨号0086格式_时间戳_transcription.txt
            prefix, phone_number, timestamp_str = match.groups()
            timestamp = self._parse_timestamp(timestamp_str)
            return phone_number, timestamp, None
        elif format_type == 'plain_400':
            # 格式9: 400电话_时间戳_transcription.txt
            prefix, part1, part2, timestamp_str = match.groups()
            phone = f"{prefix}{part1}{part2}"
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, None
        elif format_type == 'landline':
            # 格式8: 区号电话_时间戳_transcription.txt
            area_code, part1, part2, timestamp_str = match.groups()
            phone = f"{area_code}{part1}{part2}"
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, None
        elif format_type == 'simple':
            # 格式2: 手机号_时间戳_transcription.txt
            part1, part2, part3, timestamp_str = match.groups()
            phone = f"{part1}{part2}{part3}"
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, None
        elif format_type == 'short_number':
            # 格式10: 短号码4+4_时间戳_transcription.txt
            part1, part2, timestamp_str = match.groups()
            phone = f"{part1}{part2}"
            timestamp = self._parse_timestamp(timestamp_str)
            return phone, timestamp, None
        elif format_type == 'fixed_8digit':
            # 格式11: 8位固定电话_时间戳_transcription.txt
            full_number, timestamp_str = match.groups()
            timestamp = self._parse_timestamp(timestamp_str)
            return full_number, timestamp, None
        elif format_type == 'service_number':
            # 格式12: 特殊服务号_时间戳_transcription.txt
            service_number, timestamp_str = match.groups()
            timestamp = self._parse_timestamp(timestamp_str)
            return service_number, timestamp, None
        else:
            logger.error(f"未知的格式类型: {format_type}")
            return "", datetime.now(), None

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """解析时间戳字符串"""
        try:
            return datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
        except ValueError as e:
            logger.error(f"时间戳解析失败 {timestamp_str}: {e}")
            # 返回当前时间作为默认值
            return datetime.now()

    def clean_name(self, raw_name: str) -> str:
        """宽松模式：清理姓名中的特殊字符，但保持灵活性"""
        if not raw_name:
            return "未知联系人"

        # 移除文件系统不支持的字符
        invalid_chars = r'[<>:"/\\|?*]'
        cleaned = re.sub(invalid_chars, '', raw_name.strip())

        # 限制长度避免文件名过长
        if len(cleaned) > 50:
            cleaned = cleaned[:50]

        # 确保不为空
        return cleaned if cleaned else "未知联系人"

    def get_contact_name(self, phone_number: str, contact_name: Optional[str] = None) -> str:
        """生成联系人显示名称"""
        if contact_name:
            return contact_name
        return f"联系人_{phone_number[-4:]}"

class FileReader:
    """读取和预处理通话记录文件"""

    def __init__(self, data_dir: Path = Path("data/txt")):
        self.data_dir = data_dir
        self.parser = FileParser()

    def read_file_content(self, file_path: Path) -> str:
        """读取文件内容并进行基本清理"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            return self._clean_content(content)
        except Exception as e:
            logger.error(f"读取文件失败 {file_path}: {e}")
            return ""

    def _clean_content(self, content: str) -> str:
        """清理文本内容"""
        # 移除多余的空白字符
        content = re.sub(r'\s+', ' ', content)
        # 移除特殊字符
        content = re.sub(r'[^\w\s\u4e00-\u9fff，。？！；：""''（）【】]', '', content)
        return content.strip()

    def load_all_records(self) -> List[CallRecord]:
        """加载所有通话记录"""
        records = []

        if not self.data_dir.exists():
            logger.error(f"数据目录不存在: {self.data_dir}")
            return records

        txt_files = list(self.data_dir.glob("*.txt"))
        logger.info(f"发现 {len(txt_files)} 个文件")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("加载通话记录...", total=len(txt_files))

            for file_path in txt_files:
                parsed = self.parser.parse_filename(file_path.name)
                if parsed:
                    phone_number, timestamp, contact_name = parsed
                    content = self.read_file_content(file_path)

                    if content:
                        # 处理联系人姓名
                        names = {contact_name} if contact_name else set()

                        record = CallRecord(
                            phone_number=phone_number,
                            timestamp=timestamp,
                            file_path=file_path,
                            content=content,
                            contact_names=names,
                            primary_name=contact_name
                        )
                        records.append(record)
                        logger.debug(f"成功加载: {file_path.name}")
                    else:
                        logger.warning(f"文件内容为空: {file_path.name}")

                progress.advance(task)

        logger.info(f"成功加载 {len(records)} 条通话记录")
        return records

class OllamaAnalyzer:
    """使用 Ollama Qwen3 进行通话记录分析和总结"""

    def __init__(self, model_name: str = "qwen3:latest"):
        self.model_name = model_name
        self.client = ollama

    def check_ollama_connection(self) -> bool:
        """检查 Ollama 服务连接"""
        try:
            models_response = self.client.list()
            available_models = [model.model for model in models_response.models]
            logger.info(f"可用模型: {available_models}")

            if self.model_name not in available_models:
                logger.warning(f"模型 {self.model_name} 不可用，尝试使用第一个可用模型")
                if available_models:
                    self.model_name = available_models[0]
                    logger.info(f"切换到模型: {self.model_name}")
                else:
                    logger.error("没有可用的模型")
                    return False

            return True
        except Exception as e:
            logger.error(f"连接 Ollama 失败: {e}")
            return False

    def analyze_single_call(self, content: str) -> Dict[str, str]:
        """分析单个通话记录"""
        prompt = f"""
# 角色
你是一位经验丰富的行政助理，擅长将混乱的语音转录文本整理成清晰、专业、可执行的纪要。

# 背景信息
- **通话主题**：[例如：关于“星辰项目”第四季度营销方案的讨论]
- **通话目标**：[例如：确定营销方案的最终方向和下一步分工]

# 任务指令
请根据下方提供的原始通话记录，完成以下任务：

### 任务1：文本优化
- **修正错误**：纠正所有的拼写、语法和明显的语音识别错误。
- **添加标点**：合理地添加句号、逗号、问号等，使文本更易读。
- **段落划分**：根据对话的自然停顿和话题转换，将文本划分为逻辑清晰的段落。
- **保持原意**：在优化过程中，绝对忠实于原始对话的含义和语气。

### 任务2：内容总结与提炼
请在优化后的文本下方，生成一份结构化的通话摘要，包含以下部分：

1.  **核心摘要 (Executive Summary)**：用2-3句话高度概括本次通话的核心成果和结论。
2.  **关键讨论点 (Key Points)**：
    - 以项目符号列表的形式，列出讨论中提到的3-5个最重要的话题、观点或数据。

# 原始通话记录
{content}
"""

        try:
            response = self.client.chat(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return {
                'analysis': response['message']['content'],
                'status': 'success'
            }
        except Exception as e:
            logger.error(f"分析通话记录失败: {e}")
            return {
                'analysis': f"分析失败: {str(e)}",
                'status': 'error'
            }

    def analyze_contact_calls(self, records: List[CallRecord], contact_name: str) -> Dict[str, any]:
        """完整分析联系人的所有通话：先单个分析，再生成汇总"""
        logger.info(f"开始分析联系人 {contact_name} 的 {len(records)} 条通话记录")

        # 第一步：分析每个单独的通话
        individual_analyses = []
        for i, record in enumerate(sorted(records, key=lambda x: x.timestamp), 1):
            logger.debug(f"分析第 {i} 个通话记录")
            analysis = self.analyze_single_call(record.content)
            individual_analyses.append({
                'timestamp': record.timestamp,
                'analysis': analysis['analysis'] if analysis['status'] == 'success' else record.content,
                'status': analysis['status']
            })

        # 第二步：基于单个分析生成联系人汇总
        summary = self.summarize_contact_calls(individual_analyses, contact_name, records)

        return {
            'individual_analyses': individual_analyses,
            'summary': summary,
            'total_calls': len(records)
        }

    def summarize_contact_calls(self, individual_analyses: List[Dict], contact_name: str, records: List[CallRecord]) -> Dict[str, str]:
        """基于单个通话分析结果生成联系人总结"""
        # 合并所有分析结果
        all_analyses = []
        call_dates = []

        for analysis_data in individual_analyses:
            timestamp = analysis_data['timestamp']
            analysis_text = analysis_data['analysis']
            all_analyses.append(f"通话时间: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n分析结果: {analysis_text}")
            call_dates.append(timestamp.strftime('%Y-%m-%d'))

        combined_analyses = "\n\n" + "="*50 + "\n\n".join(all_analyses)

        prompt = f"""
# 角色
你是一位顶级的沟通分析专家，擅长从对话分析结果中发现深层信息、识别关系动态并提炼出可执行的洞察。

# 背景与数据
你收到了关于联系人 "{contact_name}" 的一批通话分析结果。
- **通话记录数量**：{len(records)}
- **通话时间范围**：从 {min(call_dates)} 到 {max(call_dates)}
- **单个通话分析结果**：
\"\"\"
{combined_analyses}
\"\"\"

# 任务指令
请基于以上所有单个通话的分析结果，生成一份综合分析报告。你需要：
1.  **识别模式**：从各个分析中总结反复出现的话题、情绪和沟通方式。
2.  **提炼关键信息**：汇总所有分析中的重要承诺、决定和关键数据。
3.  **推断关系**：基于分析结果判断关系的性质和发展趋势。
4.  **提供建议**：基于综合分析，提出有价值的后续行动建议。

# 输出格式
请严格按照以下 Markdown 格式生成报告：

# 联系人沟通分析报告：{contact_name}

## 1. 核心洞察 (Executive Summary)
* **一句话总结**：[用一句话概括你与该联系人的核心关系与沟通状态]
* **关键发现**：[以2-3个要点的形式，列出本次分析最重要的发现]

## 2. 通话主题与趋势分析
* **核心议题**：[归纳你们最常讨论的 3-5 个核心话题，例如：项目A进展、家庭生活、技术探讨]
* **话题趋势**：[分析讨论的主题是否随时间有明显变化，例如：从技术讨论逐渐转向商业合作]

## 3. 关系动态与特征
* **关系推断**：[判断关系类型（如：紧密合作伙伴、普通朋友、家人、潜在客户等），并简要说明判断依据]
* **沟通模式**：[描述你们的沟通风格，例如：正式商务、轻松闲聊、一方主导、平等对话等]

## 4. 关键信息与决策快照
* **重要承诺/约定**：[列出所有明确的承诺、约定或共同确认的事项]
* **关键数据/信息**：[提取通话中提到的具体日期、数字、金额、项目名称等硬信息]
* **待解决问题**：[记录提到但尚未解决，需要跟进的问题]

## 5. 建议的后续行动
* **立即跟进**：[列出需要马上处理的1-2个最紧急事项]
* **沟通建议**：[根据沟通模式分析，提出可以改善或加强关系的建议，例如：可主动发起关于XX话题的讨论]
"""


        try:
            response = self.client.chat(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            return {
                'summary': response['message']['content'],
                'status': 'success'
            }
        except Exception as e:
            logger.error(f"生成联系人总结失败: {e}")
            return {
                'summary': f"生成总结失败: {str(e)}",
                'status': 'error'
            }

class ContactGrouper:
    """按联系人分组和汇总通话记录"""

    def __init__(self, parser: FileParser):
        self.parser = parser

    def group_records_by_contact(self, records: List[CallRecord]) -> Dict[str, Dict]:
        """按电话号码分组通话记录，保留所有姓名变体"""
        contact_groups = {}

        for record in records:
            phone = record.phone_number

            # 按电话号码分组（而不是按联系人名称）
            if phone not in contact_groups:
                contact_groups[phone] = {
                    'phone': phone,
                    'records': [],
                    'all_names': set(),  # 保存所有姓名变体
                    'primary_name': None,  # 主要姓名
                    'first_call': record.timestamp,
                    'last_call': record.timestamp,
                    'total_calls': 0
                }

            # 收集所有姓名变体
            contact_groups[phone]['all_names'].update(record.contact_names)

            # 设置主要姓名（优先使用非空的真实姓名）
            if not contact_groups[phone]['primary_name'] and record.primary_name:
                contact_groups[phone]['primary_name'] = record.primary_name

            contact_groups[phone]['records'].append(record)
            contact_groups[phone]['total_calls'] += 1

            # 更新首次和最后通话时间
            if record.timestamp < contact_groups[phone]['first_call']:
                contact_groups[phone]['first_call'] = record.timestamp
            if record.timestamp > contact_groups[phone]['last_call']:
                contact_groups[phone]['last_call'] = record.timestamp

        # 为每个分组生成显示名称
        display_groups = {}
        for phone, data in contact_groups.items():
            display_name = self._get_display_name(data['all_names'], data['primary_name'], phone)
            display_groups[display_name] = data

        return display_groups

    def _get_display_name(self, all_names: set, primary_name: Optional[str], phone: str) -> str:
        """生成分组的显示名称"""
        # 过滤掉空的姓名
        valid_names = {name for name in all_names if name and name.strip()}

        if valid_names:
            # 如果有主要姓名，优先使用
            if primary_name and primary_name in valid_names:
                return primary_name
            # 否则使用最短的有效姓名
            return min(valid_names, key=len)
        else:
            # 没有有效姓名时，使用电话号码后四位
            return f"联系人_{phone[-4:]}"

class MarkdownReportGenerator:
    """生成 Markdown 报告"""

    def __init__(self, output_dir: Path = Path("output")):
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)

    def generate_contact_report(self, contact_name: str, contact_data: Dict,
                              analysis_result: Dict[str, str]) -> Path:
        """为单个联系人生成 Markdown 报告"""
        # 使用智能文件命名策略（优先真实姓名）
        filename = self._get_safe_filename(contact_data.get('all_names', set()),
                                         contact_data['phone'], contact_name)
        report_path = self.output_dir / f"{filename}_通话分析报告.md"

        # 生成报告内容
        if analysis_result['status'] == 'success':
            report_content = self._generate_full_analysis_report(contact_name, contact_data, analysis_result)
        else:
            # 如果 AI 分析失败，生成增强的基础报告
            report_content = self._generate_enhanced_basic_report(contact_name, contact_data)

        # 写入文件
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"生成报告: {report_path}")
        return report_path

    def _get_safe_filename(self, all_names: set, phone: str, contact_name: str) -> str:
        """优先使用真实姓名作为文件名"""
        # 过滤掉纯数字的"姓名"和空名称
        valid_names = {name for name in all_names if name and name.strip() and not name.isdigit()}

        if valid_names:
            # 选择最短的有效姓名作为主文件名
            primary_name = min(valid_names, key=len)
            safe_name = re.sub(r'[<>:"/\\|?*]', '', primary_name)
            return f"{safe_name}_{phone[-4:]}"
        else:
            # 没有有效姓名时，使用联系人显示名称
            safe_name = re.sub(r'[^\w\-_\.]', '_', contact_name)
            return safe_name

    def _generate_full_analysis_report(self, contact_name: str, contact_data: Dict, analysis_result: Dict) -> str:
        """生成完整的分析报告，包含总结和单个通话分析"""
        records = contact_data['records']
        phone = contact_data['phone']
        all_names = contact_data.get('all_names', set())
        primary_name = contact_data.get('primary_name')
        individual_analyses = contact_data.get('individual_analyses', [])
        first_call = contact_data['first_call'].strftime('%Y-%m-%d %H:%M:%S')
        last_call = contact_data['last_call'].strftime('%Y-%m-%d %H:%M:%S')

        # 构建姓名显示部分
        names_display = self._build_names_display(all_names, primary_name)

        # 开始构建报告内容
        content = f"""# {contact_name} 通话分析报告

## 基本信息
{names_display}
- **电话号码**: {phone}
- **通话次数**: {len(records)}
- **首次通话**: {first_call}
- **最后通话**: {last_call}

---

# 综合分析报告

{analysis_result['summary']}

---

# 详细通话记录分析

"""

        # 添加每个单独通话的分析
        for i, analysis_data in enumerate(individual_analyses, 1):
            timestamp = analysis_data['timestamp']
            analysis_text = analysis_data['analysis']
            status = analysis_data['status']

            content += f"""## 通话 {i}

**时间**: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}

**分析结果**:
{analysis_text if status == 'success' else '分析失败，显示原始内容: ' + analysis_text}

---

"""

        content += """
## 备注
此报告基于 AI 详细分析生成，包含每次通话的具体分析和综合评估。
"""
        return content

    def _generate_enhanced_basic_report(self, contact_name: str, contact_data: Dict) -> str:
        """生成增强的基础报告，显示所有姓名变体"""
        records = contact_data['records']
        phone = contact_data['phone']
        all_names = contact_data.get('all_names', set())
        primary_name = contact_data.get('primary_name')
        first_call = contact_data['first_call'].strftime('%Y-%m-%d %H:%M:%S')
        last_call = contact_data['last_call'].strftime('%Y-%m-%d %H:%M:%S')

        # 构建姓名显示部分
        names_display = self._build_names_display(all_names, primary_name)

        content = f"""# {contact_name} 通话分析报告

## 基本信息
{names_display}
- **电话号码**: {phone}
- **通话次数**: {len(records)}
- **首次通话**: {first_call}
- **最后通话**: {last_call}

## 通话记录明细

"""
        for i, record in enumerate(sorted(records, key=lambda x: x.timestamp), 1):
            content += f"""### 通话 {i}
**时间**: {record.timestamp.strftime('%Y-%m-%d %H:%M:%S')}

**内容摘要**:
{record.content[:200]}{'...' if len(record.content) > 200 else ''}

---

"""

        content += """
## 备注
此报告为基础版本。如需详细的 AI 分析，请确保 Ollama 服务正常运行。
"""
        return content

    def _build_names_display(self, all_names: set, primary_name: Optional[str]) -> str:
        """构建姓名显示信息"""
        # 过滤掉空的姓名
        valid_names = {name for name in all_names if name and name.strip()}

        if not valid_names:
            return ""

        if len(valid_names) == 1:
            # 只有一个姓名
            return f"- **联系人姓名**: {list(valid_names)[0]}\n"
        else:
            # 多个姓名变体
            names_display = ""
            if primary_name:
                names_display += f"- **主要姓名**: {primary_name}\n"

            names_list = sorted(list(valid_names))
            names_display += f"- **所有姓名变体**: {', '.join(names_list)}\n"
            return names_display

    def _generate_basic_report(self, contact_name: str, contact_data: Dict) -> str:
        """生成基础报告（保留原有方法以兼容）"""
        return self._generate_enhanced_basic_report(contact_name, contact_data)

def main():
    """主函数"""
    # 初始化日志系统
    setup_logging()

    try:
        logger.info("开始分析电话通话记录")

        # 初始化组件
        reader = FileReader()
        analyzer = OllamaAnalyzer()
        grouper = ContactGrouper(reader.parser)
        report_generator = MarkdownReportGenerator()

        # 检查 Ollama 连接
        ollama_available = analyzer.check_ollama_connection()
        if not ollama_available:
            console.print("[yellow]警告: Ollama 服务不可用，将生成基础报告[/yellow]")
            logger.warning("Ollama 服务不可用，将生成基础报告")

        # 加载所有记录
        records = reader.load_all_records()
        if not records:
            console.print("[red]未找到有效的通话记录文件[/red]")
            logger.error("未找到有效的通话记录文件")
            return

        # 按联系人分组
        contact_groups = grouper.group_records_by_contact(records)
        logger.info(f"成功分组 {len(contact_groups)} 个联系人")

        # 显示统计信息
        console.print(f"\n[green]统计结果:[/green]")
        console.print(f"总通话记录数: {len(records)}")
        console.print(f"联系人数量: {len(contact_groups)}")

        # 生成每个联系人的报告
        console.print(f"\n[green]开始生成分析报告...[/green]")
        logger.info("开始生成分析报告")

        successful_reports = 0
        failed_reports = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("生成报告...", total=len(contact_groups))

            for contact_name, contact_data in contact_groups.items():
                try:
                    # console.print(f"  正在处理: {contact_name} ({contact_data['total_calls']} 次通话)")
                    logger.debug(f"处理联系人: {contact_name}")

                    # AI 分析（如果可用）
                    if ollama_available:
                        full_analysis = analyzer.analyze_contact_calls(
                            contact_data['records'], contact_name
                        )
                        analysis_result = full_analysis['summary']
                        contact_data['individual_analyses'] = full_analysis['individual_analyses']
                    else:
                        analysis_result = {'status': 'error', 'summary': ''}
                        contact_data['individual_analyses'] = []

                    # 生成报告
                    report_path = report_generator.generate_contact_report(
                        contact_name, contact_data, analysis_result
                    )

                    successful_reports += 1
                    logger.info(f"成功生成报告: {report_path}")

                except Exception as e:
                    failed_reports += 1
                    logger.error(f"处理联系人 {contact_name} 时出错: {e}")
                    console.print(f"[red]  处理 {contact_name} 失败: {e}[/red]")

                progress.advance(task)

        # 报告结果
        console.print(f"\n[green]✅ 分析完成！[/green]")
        console.print(f"报告已保存到: {report_generator.output_dir}")
        console.print(f"成功生成: {successful_reports} 个报告")
        if failed_reports > 0:
            console.print(f"[red]失败: {failed_reports} 个报告[/red]")

        logger.info(f"分析完成，成功生成 {successful_reports} 个报告，失败 {failed_reports} 个")

        # 显示联系人统计（按通话次数排序）
        console.print(f"\n[green]联系人通话统计:[/green]")
        for contact_name, data in sorted(contact_groups.items(),
                                       key=lambda x: x[1]['total_calls'], reverse=True):
            if data['total_calls'] > 5:
                console.print(f"  {contact_name} ({data['phone']}): {data['total_calls']} 次通话")

    except Exception as e:
        logger.exception(f"程序运行出现严重错误: {e}")
        console.print(f"[red]程序运行出现严重错误: {e}[/red]")
        sys.exit(1)

if __name__ == "__main__":
    main()
