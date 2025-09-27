# Phone Record Summary

一个用于分析通话记录转录文件并生成智能分析报告的Python工具。

## 功能特点

- **多格式文件名解析**：支持三种不同的文件命名格式
- **联系人智能分组**：根据电话号码自动分组，支持多个姓名变体
- **AI驱动分析**：使用Ollama进行通话内容分析
- **Markdown报告生成**：为每个联系人生成完整的分析报告

## 支持的文件格式（13种格式，100%匹配率）

### 手机号格式
- **格式1**：`+86 XXX XXXX XXXX_timestamp_transcription.txt`
- **格式2**：`XXX XXXX XXXX_timestamp_transcription.txt`
- **格式3**：`姓名@+86 XXX XXXX XXXX_timestamp_transcription.txt`
- **格式4**：`姓名@XXX XXXX XXXX_timestamp_transcription.txt`

### 固定电话和区号格式
- **格式5**：`姓名@区号 电话号码_timestamp_transcription.txt`
- **格式8**：`区号 电话号码_timestamp_transcription.txt`
- **格式11**：`固定电话_timestamp_transcription.txt`

### 400电话格式
- **格式6**：`姓名@400 XXX XXXX_timestamp_transcription.txt`
- **格式9**：`400 XXX XXXX_timestamp_transcription.txt`

### 特殊服务号格式
- **格式7**：`姓名@服务号_timestamp_transcription.txt`d- **格式12**：`服务号_timestamp_transcription.txt`

### 短号码格式
- **格式10**：`XXXX XXXX_timestamp_transcription.txt`

## 安装

### 环境要求
- Python 3.8+
- Ollama (用于AI分析)

### 安装步骤

1. 克隆项目：
```bash
git clone <repository-url>
cd phone_record_summary
```

2. 安装依赖：
```bash
uv sync
```

3. 确保Ollama运行：
```bash
ollama serve
```

## 使用方法

### 基本用法

```bash
python main.py
```

程序会自动：
1. 扫描`test_data`目录下的所有转录文件
2. 解析文件名提取联系信息和时间
3. 按电话号码分组通话记录
4. 使用AI分析每通电话的内容
5. 为每个联系人生成综合分析报告

### 目录结构

```
phone_record_summary/
├── test_data/              # 存放转录文件

│   └── ... （支持13种不同格式）
├── output/                 # 生成的分析报告
│   ├── 联系人_139****5678_通话分析报告.md
│   ├── 联系人_186****1585_通话分析报告.md
│   ├── 张三_189****3851_通话分析报告.md
└── main.py
```

## 输出示例

每个联系人会生成一个独立的Markdown报告，采用两层分析架构：

### 报告结构
1. **基本信息**
   - 所有相关姓名变体和电话号码
   - 通话次数统计和时间范围

2. **综合分析报告**（优先显示）
   - 核心洞察和关键发现
   - 通话主题与趋势分析
   - 关系动态与特征识别
   - 重要承诺和决策快照
   - 建议的后续行动

3. **详细通话记录分析**
   - 每通电话的单独AI分析
   - 内容优化和关键点提取
   - 时间戳和详细分析结果

### 报告文件命名规则

- 有真实姓名：`姓名_手机尾4位_通话分析报告.md`
- 无真实姓名：`联系人_手机尾4位_通话分析报告.md`

## 高级功能

### 🎯 100%文件匹配率
- 支持13种不同的文件命名格式
- 涵盖手机号、固定电话、400电话、特殊服务号等各种类型

### 🧠 两层AI分析架构
- **第一层**：单个通话详细分析 - 内容优化、关键点提取
- **第二层**：联系人综合汇总 - 模式识别、关系分析、行动建议
- 基于Ollama Qwen3模型的深度分析

### 👥 智能姓名变体处理
- 自动识别同一联系人的多个姓名变体
- 保留所有出现过的姓名形式并在报告中展示
- 优先使用真实姓名作为文件名
- 支持复杂姓名格式（如公司名称、特殊字符等）

### 🔧 宽松模式名称处理
- 保留大部分特殊字符和标点符号
- 仅移除文件系统不安全的字符（如`/`, `\`, `:`等）
- 确保原始姓名信息的完整性和可读性

### 📊 处理能力统计
- **处理文件数**：
- **识别联系人**：
- **支持格式**：13种
- **匹配成功率**：100%

## 开发

### 运行测试

```bash
uv run pytest
```

### 项目结构

- `main.py`：主程序入口和核心逻辑
- `test_main.py`：单元测试
- `pyproject.toml`：项目配置
- `CLAUDE.md`：开发者文档

## 许可证

MIT License