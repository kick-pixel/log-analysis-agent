"""
Agent编排器

负责Agent的初始化、工具调用和对话管理

作者: Log Analysis Team
"""

import os
import yaml
from typing import List, Dict, Optional
from pathlib import Path
from loguru import logger

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from src.agent_layer.tools.log_tools import ALL_TOOLS, init_tools
from src.storage_layer.keyword_search import KeywordSearchEngine
from src.storage_layer.vector_search import VectorSearchEngine


class LogAnalysisAgent:
    """日志分析Agent编排器

    集成LLM、工具和记忆，提供智能日志分析能力
    """

    def __init__(
        self,
        config_path: str = "./config/config.yaml",
        db_path: str = "./data/logs.db",
        vector_db_path: str = "./data/chroma_db"
    ):
        """初始化Agent

        Args:
            config_path: 配置文件路径
            db_path: SQLite数据库路径
            vector_db_path: ChromaDB路径
        """
        # 加载配置
        self.config = self._load_config(config_path)

        # 初始化存储引擎
        logger.info("Initializing storage engines...")
        self.keyword_engine = KeywordSearchEngine(db_path=db_path)
        self.vector_engine = VectorSearchEngine(db_path=vector_db_path)

        # 当前会话ID（用于查询时过滤）
        self.current_session_id = None

        # 初始化工具
        init_tools(self.keyword_engine, self.vector_engine, self)

        # 初始化LLM
        logger.info("Initializing LLM...")
        self.llm = self._init_llm()

        # 创建Agent
        logger.info("Creating agent...")
        self.agent_executor = self._create_agent()

        logger.info("LogAnalysisAgent initialized successfully")

    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            配置字典
        """
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            logger.info(f"Loaded configuration from {config_path}")
            return config
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            logger.info("Using default configuration")
            return {
                'llm': {
                    'model': 'gpt-4o',
                    'temperature': 0.1,
                    'max_tokens': 4000
                },
                'agent': {
                    'max_iterations': 10,
                    'verbose': True
                }
            }

    def _init_llm(self) -> ChatOpenAI:
        """初始化LLM

        Returns:
            LLM实例
        """
        llm_config = self.config.get('llm', {})

        # 从环境变量获取API Key
        api_key = os.getenv('OPENAI_API_KEY')
        base_url = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
        model = os.getenv('OPENAI_MODEL')
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not found in environment variables. "
                "Please set it in .env file or environment."
            )

        return ChatOpenAI(
            model=model or llm_config.get('model', 'gpt-4o'),
            temperature=llm_config.get('temperature', 0.1),
            max_tokens=llm_config.get('max_tokens', 4000),
            api_key=api_key,
            base_url=base_url
        )

    def _create_agent(self):
        """创建Agent执行器

        Returns:
            CompiledStateGraph实例（可直接invoke的agent）
        """
        # 获取System Prompt
        agent_config = self.config.get('agent', {})
        system_prompt = agent_config.get('system_prompt', """
你是一位资深的车载系统（Android/Linux）日志分析专家，拥有15年的故障排查经验。
你擅长分析Android Logcat、Kernel Log等多种日志格式。

你的工作流程：
1. 理解用户的问题描述（故障现象、发生时间）
2. 使用工具检索相关日志（时间范围、关键词、模块）
3. 定位关键错误日志和堆栈信息
4. 分析上下文，推断根本原因
5. 给出清晰的结论和建议

输出格式要求：
- **故障时间点**：精确到秒
- **关键日志**：展示核心错误信息
- **根因分析**：解释为什么发生故障
- **建议方案**：给出可行的修复建议

注意：如果无法确定根本原因，请明确说明，不要编造信息。
        """.strip())

        # 使用新的create_agent API（返回CompiledStateGraph）
        agent = create_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            system_prompt=system_prompt
        )

        return agent

    def analyze(
        self,
        query: str,
        chat_history: Optional[List] = None
    ) -> Dict:
        """分析用户查询

        Args:
            query: 用户查询
            chat_history: 对话历史（可选）

        Returns:
            包含回答和中间步骤的字典
        """
        try:
            logger.info(f"Processing query: {query}")

            # 构建消息列表
            messages = chat_history or []
            messages.append(HumanMessage(content=query))

            # 执行Agent（create_agent返回的CompiledStateGraph接受messages）
            result = self.agent_executor.invoke({"messages": messages})

            # 提取最后的AI回复
            final_messages = result.get('messages', [])
            answer = ""
            if final_messages:
                for msg in reversed(final_messages):
                    if isinstance(msg, AIMessage) and msg.content:
                        answer = msg.content
                        break

            return {
                'answer': answer,
                'messages': final_messages,
                'success': True
            }

        except Exception as e:
            logger.error(f"Analysis error: {e}", exc_info=True)
            return {
                'answer': f"分析过程中发生错误: {str(e)}",
                'messages': [],
                'success': False,
                'error': str(e)
            }

    def load_logs(
        self,
        log_file_path: str,
        session_id: str = "default"
    ) -> Dict:
        """加载日志文件

        Args:
            log_file_path: 日志文件路径
            session_id: 会话ID

        Returns:
            加载结果字典
        """
        from src.data_layer.parsers.logcat_parser import LogcatParser
        from src.data_layer.preprocessor import LogPreprocessor

        try:
            logger.info(f"Loading log file: {log_file_path}")

            # 解析日志
            parser = LogcatParser()
            entries = parser.parse_file(log_file_path)

            if not entries:
                return {
                    'success': False,
                    'message': '未能解析到有效的日志条目'
                }

            logger.info(f"Parsed {len(entries)} log entries")

            # 预处理（保留所有INFO及以上级别）
            preprocessor = LogPreprocessor(
                enable_deduplication=True,
                enable_pii_masking=True,
                min_log_level='I'
            )
            processed_entries = preprocessor.process(entries)

            logger.info(f"Preprocessed to {len(processed_entries)} entries")

            # 存入关键词搜索引擎（索引所有日志，关键词搜索很快）
            self.keyword_engine.insert_logs(
                processed_entries, session_id=session_id)

            # 向量数据库性能优化：只索引ERROR和WARN级别日志
            # 原因：
            # 1. 语义搜索主要用于分析问题和错误
            # 2. INFO/DEBUG日志通过关键词搜索已足够
            # 3. 可大幅提升写入速度（减少80%数据量）
            important_entries = [
                entry for entry in processed_entries
                if entry.level in ['W', 'E', 'F']  # WARN, ERROR, FATAL
            ]

            logger.info(
                f"Indexing {len(important_entries)} important logs (W/E/F) to vector database...")

            if important_entries:
                self.vector_engine.insert_logs(
                    important_entries, session_id=session_id)
            else:
                logger.warning(
                    "No ERROR/WARN logs found, skipping vector indexing")

            # 统计信息
            total_logs = len(processed_entries)
            vector_logs = len(important_entries)
            logger.info(
                f"📊 存储统计: 关键词索引={total_logs}, 向量索引={vector_logs} ({vector_logs/total_logs*100:.1f}%)")

            # 获取统计信息
            stats = self.keyword_engine.get_statistics(session_id=session_id)

            # 设置当前会话ID（用于后续查询）
            self.current_session_id = session_id
            logger.info(f"✅ Current session set to: {session_id}")

            return {
                'success': True,
                'message': f'成功加载 {len(processed_entries)} 条日志',
                'statistics': stats
            }

        except Exception as e:
            logger.error(f"Failed to load logs: {e}")
            return {
                'success': False,
                'message': f'加载日志失败: {str(e)}',
                'error': str(e)
            }

    def get_statistics(self, session_id: Optional[str] = None) -> Dict:
        """获取日志统计信息

        Args:
            session_id: 会话ID

        Returns:
            统计信息字典
        """
        return self.keyword_engine.get_statistics(session_id=session_id)

    def clear_session(self, session_id: str):
        """清除会话数据

        Args:
            session_id: 会话ID
        """
        logger.info(f"Clearing session: {session_id}")
        self.keyword_engine.clear_session(session_id)
        self.vector_engine.clear_session(session_id)


def main():
    """测试函数"""
    from dotenv import load_dotenv

    # 加载环境变量
    load_dotenv()

    # 检查API Key
    if not os.getenv('OPENAI_API_KEY'):
        print("\n⚠️  警告: 未找到OPENAI_API_KEY环境变量")
        print("请在.env文件中设置OPENAI_API_KEY")
        print("\n跳过Agent测试，仅测试日志加载功能\n")

        # 只测试日志加载
        from src.storage_layer.keyword_search import KeywordSearchEngine
        keyword_engine = KeywordSearchEngine(db_path="./data/test_logs.db")
        stats = keyword_engine.get_statistics()
        print(f"数据库统计: {stats}")
        return

    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent / \
        "tests" / "sample_logs" / "android_logcat_sample.log"

    # 创建Agent
    print("\n=== 初始化Log Analysis Agent ===")
    agent = LogAnalysisAgent(
        db_path="./data/test_agent_logs.db",
        vector_db_path="./data/test_agent_chroma"
    )

    # 加载日志
    print("\n=== 加载测试日志 ===")
    load_result = agent.load_logs(
        str(sample_path), session_id="test_agent_session")
    print(f"加载结果: {load_result['message']}")
    if load_result['success']:
        stats = load_result['statistics']
        print(f"总日志数: {stats['total_count']}")
        print(f"级别分布: {stats['level_distribution']}")

    # 测试查询
    print("\n=== 测试查询1: 查找崩溃 ===")
    result1 = agent.analyze("查找所有崩溃(Crash)相关的日志")
    print(f"\nAgent回答:\n{result1['answer']}\n")

    # 测试查询2
    print("\n=== 测试查询2: 分析时间段 ===")
    result2 = agent.analyze("分析14:00到14:30之间的错误")
    print(f"\nAgent回答:\n{result2['answer']}\n")


if __name__ == "__main__":
    main()
