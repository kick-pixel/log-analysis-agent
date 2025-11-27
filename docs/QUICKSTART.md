# 🚀 快速启动指南

## 5分钟快速上手

### 1. 环境准备

确保你已安装:
- Python 3.13 (推荐使用uv管理)
- OpenAI API Key

### 2. 安装依赖

```bash
cd log-analysis-agent

# 使用uv创建虚拟环境（推荐）
uv venv --python 3.13
source .venv/bin/activate

# 安装依赖
uv pip install -r requirements.txt
```

### 3. 配置API Key

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑.env文件，填入你的API Key
# OPENAI_API_KEY=sk-your-actual-key-here
```

### 4. 启动应用

```bash
streamlit run src/interface_layer/app.py
```

浏览器会自动打开 `http://localhost:8501`

### 5. 开始使用

1. **上传日志**: 在左侧边栏上传`.log`或`.txt`格式的Android Logcat日志
2. **解析日志**: 点击"🚀 解析并加载日志"按钮
3. **开始提问**: 在对话框中输入问题，例如:
   - "帮我找找有没有崩溃"
   - "14:28:45到14:28:50发生了什么？"
   - "CameraService有什么错误吗？"

## 测试数据

项目提供了测试日志样本：

```
tests/sample_logs/android_logcat_sample.log
```

这是一个包含典型故障场景的日志文件（倒车影像黑屏故障），可以直接用来测试系统功能。

## 常见问题

**Q: 提示API Key无效?**  
A: 检查`.env`文件中的`OPENAI_API_KEY`是否正确设置，确保没有多余空格。

**Q: ChromaDB下载embedding模型很慢?**  
A: 首次运行时会自动下载`all-MiniLM-L6-v2`模型（约79MB），请耐心等待。

**Q: Streamlit启动失败?**  
A: 确保已激活虚拟环境，并且所有依赖都已正确安装。

**Q: 想使用本地LLM?**  
A: 修改`.env`文件中的`OPENAI_BASE_URL`指向本地API服务（如Ollama、vLLM等）。

## 进阶使用

### 命令行测试

不使用Web界面，直接测试各个模块：

```bash
# 测试日志解析器
python -m src.data_layer.parsers.logcat_parser

# 测试关键词搜索
python -m src.storage_layer.keyword_search

# 测试向量搜索
python -m src.storage_layer.vector_search

# 测试Agent（需要API Key）
python -m src.agent_layer.orchestrator
```

### 自定义配置

编辑 `config/config.yaml` 可以调整:
- LLM模型选择
- Agent参数（温度、最大迭代次数等）
- 日志解析规则
- 示例问题

## 下一步

- 查看 [README.md](README.md) 了解完整功能
- 查看 [docs/架构设计.md](docs/架构设计.md) 了解系统架构
- 查看 [docs/技术设计.md](docs/技术设计.md) 了解技术细节

## 需要帮助?

如果遇到问题，请查看:
1. README的"常见问题"章节
2. 项目Issues页面
3. 代码注释和文档字符串

---

**祝你使用愉快！🎉**

