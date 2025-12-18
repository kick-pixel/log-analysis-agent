"""
Agent编排器 (LangGraph版)

负责Agent的初始化、工具调用和对话管理
采用LangGraph架构实现，提供更强的状态管理和可控性

作者: Log Analysis Team
"""

from src.storage_layer.vector_search import VectorSearchEngine
from src.storage_layer.keyword_search import KeywordSearchEngine
from src.agent_layer.tools.log_tools import (
    ALL_TOOLS,
    init_tools,
    query_logs_by_time_range,
    search_error_keywords,
    semantic_search_logs,
    filter_logs_by_tag,
    get_log_context,
    get_error_statistics
)
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langgraph.graph import StateGraph, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, BaseMessage, ToolMessage
from langchain_openai import ChatOpenAI
import logging
import os
import yaml
import functools
from typing import List, Dict, Optional, Any, Union, TypedDict, Annotated
from pathlib import Path
from loguru import logger

# CRITICAL FIX: Remove all Loguru handlers to prevent KeyError from LangChain/LangGraph logging
# Loguru intercepts standard library logging and tries to format strings with braces
logger.remove()  # Remove all handlers
# Add back a simple handler without interception
logger.add(lambda msg: print(msg, end=""),
           format="{time:HH:mm:ss} | {level} | {message}")

# Disable Loguru's interception of standard library logging
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)


class AgentState(TypedDict):
    """Agent状态定义"""
    messages: Annotated[list, add_messages]


class LogAnalysisAgent:
    """日志分析Agent编排器 (LangGraph实现)

    集成LLM、工具和记忆，提供智能日志分析能力
    使用LangGraph StateGraph管理对话状态
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
        logger.info("Initializing storage engines (LangGraph)...")
        self.keyword_engine = KeywordSearchEngine(db_path=db_path)
        self.vector_engine = VectorSearchEngine(db_path=vector_db_path)

        # 当前会话ID（用于查询时过滤）
        self.current_session_id = None

        # 初始化工具
        init_tools(self.keyword_engine, self.vector_engine, self)

        # 初始化LLM
        logger.info("Initializing LLM...")
        self.llm = self._init_llm()

        # 绑定工具到LLM
        self.llm_with_tools = self.llm.bind_tools(ALL_TOOLS)

        # 创建Agent Graph
        logger.info("Creating LangGraph agent...")
        self.graph = self._create_graph()

        logger.info("LogAnalysisAgent (Graph) initialized successfully")

    def _load_config(self, config_path: str) -> Dict:
        """加载配置文件"""
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
        """初始化LLM"""
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

    # --- Node Functions ---

    def call_model(self, state: AgentState):
        """调用模型节点"""
        messages = state['messages']
        response = self.llm_with_tools.invoke(messages)
        return {"messages": [response]}

    def node_fallback_to_semantic(self, state: AgentState):
        """Fallback节点：将失败的关键词搜索转换为语义搜索"""
        import uuid
        try:
            messages = state['messages']

            # 获取上一个AIMessage（发起关键词搜索的那个）
            last_ai_message = messages[-2]

            if not hasattr(last_ai_message, 'tool_calls') or not last_ai_message.tool_calls:
                return {"messages": [AIMessage(content="无法执行Fallback：未找到原始工具调用")]}

            tool_call = last_ai_message.tool_calls[0]
            print(f"DEBUG: Tool Call Args: {tool_call.get('args')}")

            # 尝试获取 keywords，兼容不同的参数名（有些模型可能会用 query 甚至其他）
            keywords = tool_call['args'].get('keywords')
            if not keywords:
                keywords = tool_call['args'].get('query')
            if not keywords:
                # 最后的尝试：取第一个参数值
                if tool_call['args']:
                    keywords = list(tool_call['args'].values())[0]

            if not keywords:
                return {"messages": [AIMessage(content="无法执行Fallback：无法提取搜索关键词")]}

            print(
                f"Using fallback: Keyword search failed for '{keywords}', trying semantic search.")

            # 构造新的AIMessage，调用semantic_search_logs
            new_tool_call_id = str(uuid.uuid4())
            new_tool_call = {
                'name': 'semantic_search_logs',
                'args': {'query': str(keywords)},
                'id': new_tool_call_id,
                'type': 'tool_call'
            }

            return {"messages": [AIMessage(content=f"关键词 '{keywords}' 未搜索到结果，尝试使用语义搜索...", tool_calls=[new_tool_call])]}

        except Exception as e:
            logger.error(
                f"Error in node_fallback_to_semantic: {e}", exc_info=True)
            return {"messages": [AIMessage(content=f"Fallback执行出错: {str(e)}")]}

    # --- Routing Logic ---

    def route_tools(self, state: AgentState) -> str:
        """路由逻辑：决定下一步是调用工具还是结束"""
        messages = state['messages']
        last_message = messages[-1]

        # 如果没有工具调用，结束
        if not hasattr(last_message, "tool_calls") or not last_message.tool_calls:
            return "end"

        tool_call = last_message.tool_calls[0]
        tool_name = tool_call['name']

        # 映射工具名到节点名
        tool_node_map = {
            "query_logs_by_time_range": "node_time_query",
            "search_error_keywords": "node_search_keywords",
            "semantic_search_logs": "node_semantic_search",
            "filter_logs_by_tag": "node_filter",
            "get_log_context": "node_context",
            "get_error_statistics": "node_stats"
        }

        node_name = tool_node_map.get(tool_name)

        if node_name:
            return node_name

        logger.warning(f"Unknown tool called: {tool_name}, stopping.")
        return "end"

    def check_search_result(self, state: AgentState) -> str:
        """检查搜索结果，决定是否Fallback"""
        messages = state['messages']
        last_message = messages[-1]  # ToolMessage

        # 检查工具输出
        # 如果包含 "没有找到" (log_tools.py 中的标准回复)，则认为搜索失败
        if "没有找到" in last_message.content or "found 0" in last_message.content.lower():
            return "fallback"

        return "agent"

    def _create_graph(self):
        """创建LangGraph图 (使用拆分的Node + Smart Fallback)

        Returns:
            CompiledGraph: 编译后的LangGraph对象
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

        # 初始化图
        workflow = StateGraph(AgentState)

        # 1. 添加Agent节点
        workflow.add_node("agent", self.call_model)

        # 2. 添加工具节点 - 直接使用ToolNode
        workflow.add_node("node_time_query", ToolNode(
            [query_logs_by_time_range]))
        workflow.add_node("node_search_keywords",
                          ToolNode([search_error_keywords]))
        workflow.add_node("node_semantic_search",
                          ToolNode([semantic_search_logs]))
        workflow.add_node("node_filter", ToolNode([filter_logs_by_tag]))
        workflow.add_node("node_context", ToolNode([get_log_context]))
        workflow.add_node("node_stats", ToolNode([get_error_statistics]))

        # 3. 添加Fallback节点
        workflow.add_node("node_fallback_to_semantic",
                          self.node_fallback_to_semantic)

        # 4. 设置入口
        workflow.set_entry_point("agent")

        # 5. 添加条件边 (路由)
        workflow.add_conditional_edges(
            "agent",
            self.route_tools,
            {
                "node_time_query": "node_time_query",
                "node_search_keywords": "node_search_keywords",
                "node_semantic_search": "node_semantic_search",
                "node_filter": "node_filter",
                "node_context": "node_context",
                "node_stats": "node_stats",
                "end": END
            }
        )

        # 6. 添加Smart Edges (Fallback逻辑)
        # node_search_keywords -> check_search_result -> [agent, node_fallback_to_semantic]
        workflow.add_conditional_edges(
            "node_search_keywords",
            self.check_search_result,
            {
                "agent": "agent",
                "fallback": "node_fallback_to_semantic"
            }
        )

        # Fallback节点生成semantic search调用，直接连向semantic search工具节点
        workflow.add_edge("node_fallback_to_semantic", "node_semantic_search")

        # 7. 添加其他普通边 (回归)
        # 注意：node_search_keywords 已经在上面处理了（它是conditional edge的起点）
        workflow.add_edge("node_time_query", "agent")
        # node_search_keywords -> conditional check -> agent OR fallback
        workflow.add_edge("node_semantic_search", "agent")
        workflow.add_edge("node_filter", "agent")
        workflow.add_edge("node_context", "agent")
        workflow.add_edge("node_stats", "agent")

        # 8. 编译
        checkpointer = MemorySaver()
        return workflow.compile(checkpointer=checkpointer)

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
            print(f"Processing query: {query}")

            # 确定线程ID (用于记忆)
            thread_id = self.current_session_id or "default"
            config = {
                "configurable": {"thread_id": thread_id},
                "recursion_limit": 50  # Increase recursion limit to handle complex queries
            }

            # 构建输入消息
            # 如果是新会话的第一次交互，我们可能需要注入SystemMessage
            # 这里我们简单判断：如果是第一次，MemorySaver里也没东西，我们先发SystemMessage?
            # 实际上LangGraph的状态是持久化的，我们可以每次都把SystemMessage作为第一个消息传进去吗？
            # 更好的做法是让LLM bind tools时如果不包含system prompt，就在这里加

            # 获取System Prompt
            agent_config = self.config.get('agent', {})
            system_prompt_content = agent_config.get(
                'system_prompt', "You are a helpful assistant.")

            # 获取当前状态
            current_state = self.graph.get_state(config)

            input_messages = []
            # Only add SystemMessage if this is a new conversation (empty state)
            if not current_state.values or len(current_state.values.get('messages', [])) == 0:
                input_messages.append(SystemMessage(
                    content=system_prompt_content))

            input_messages.append(HumanMessage(content=query))

            # 使用 stream 获取节点执行信息
            logger.info("="*80)
            logger.info("开始执行 Graph...")
            logger.info("="*80)

            final_messages = []
            for event in self.graph.stream(
                {"messages": input_messages},
                config=config,
                stream_mode="updates"  # 获取每个节点的更新
            ):
                # event 是一个字典: {node_name: node_output}
                for node_name, node_output in event.items():
                    # 记录节点执行
                    logger.info(
                        f"======================== Node: {node_name} ========================")

                    if isinstance(node_output, dict):
                        # 打印更新的键
                        logger.info(
                            f"  Updated keys: {list(node_output.keys())}")

                        # 如果有 messages，记录消息数量
                        if 'messages' in node_output:
                            messages = node_output['messages']
                            logger.info(f"  Added {len(messages)} message(s)")

                            # 记录最后一条消息的类型和简要内容
                            if messages:
                                last_msg = messages[-1]
                                msg_type = type(last_msg).__name__
                                logger.info(f"  Last message type: {msg_type}")

                                # 如果有 tool_calls，记录工具名
                                if hasattr(last_msg, 'tool_calls') and last_msg.tool_calls:
                                    tool_names = [
                                        tc.get('name', 'unknown') for tc in last_msg.tool_calls]
                                    logger.info(
                                        f"  Tool calls: {', '.join(tool_names)}")

                                # 如果有内容，记录预览
                                if hasattr(last_msg, 'content') and last_msg.content:
                                    content_preview = str(last_msg.content)[
                                        :100].replace('\n', ' ')
                                    logger.info(
                                        f"  Content preview: {content_preview}...")
                    else:
                        logger.info(f"  Update: {node_output}")

                    logger.info("="*70)

            logger.info("Graph 执行完成")
            logger.info("="*80)

            # 获取完整的最终状态
            complete_state = self.graph.get_state(config)
            final_messages = complete_state.values.get("messages", [])

            # 提取结果
            answer = ""
            if final_messages:
                last_msg = final_messages[-1]
                if isinstance(last_msg, AIMessage):
                    answer = last_msg.content

            return {
                'answer': answer,
                'messages': final_messages,
                'success': True
            }

        except Exception as e:
            print(f"ERROR: Analysis error: {e}")
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
        (代码复用自orchestrator.py，逻辑一致)

        Args:
            log_file_path: 日志文件路径
            session_id: 会话ID

        Returns:
            加载结果字典
        """
        from src.data_layer.parsers.logcat_parser import LogcatParser
        from src.data_layer.preprocessor import LogPreprocessor

        try:
            print(f"Loading log file: {log_file_path}")

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
            print(f"✅ Current session set to: {session_id}")

            return {
                'success': True,
                'message': f'成功加载 {len(processed_entries)} 条日志',
                'statistics': stats
            }

        except Exception as e:
            print(f"ERROR: Failed to load logs: {e}")
            return {
                'success': False,
                'message': f'加载日志失败: {str(e)}',
                'error': str(e)
            }

    def get_statistics(self, session_id: Optional[str] = None) -> Dict:
        """获取日志统计信息"""
        return self.keyword_engine.get_statistics(session_id=session_id)

    def clear_session(self, session_id: str):
        """清除会话数据"""
        print(f"Clearing session: {session_id}")
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
        return

    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent / \
        "tests" / "sample_logs" / "android_logcat_sample.log"

    # 检查测试文件是否存在
    if not sample_path.exists():
        print(f"\n⚠️  测试文件不存在: {sample_path}")
        return

    # 创建Agent
    print("\n=== 初始化Log Analysis Agent (LangGraph版) ===")
    agent = LogAnalysisAgent(
        db_path="./data/test_graph_agent_logs.db",
        vector_db_path="./data/test_graph_agent_chroma"
    )

    # 加载日志
    print("\n=== 加载测试日志 ===")

    # Clear previous session to avoid message accumulation
    try:
        agent.clear_session("test_graph_session")
        print("✅ Cleared previous session state")
    except:
        pass

    load_result = agent.load_logs(
        str(sample_path), session_id="test_graph_session")
    print(f"加载结果: {load_result['message']}")
    if load_result['success']:
        stats = load_result['statistics']
        print(f"总日志数: {stats.get('total_count', 0)}")
        print(f"级别分布: {stats.get('level_distribution', {})}")

    # 测试查询1
    print("\n=== 测试查询1: 查找崩溃 ===")
    result1 = agent.analyze("查找所有崩溃(Crash)相关的日志")
    print(f"\nAgent回答:\n{result1['answer']}\n")

    # 测试查询2
    print("\n=== 测试查询2: 分析时间段 ===")
    result2 = agent.analyze("分析14:00到14:30之间的错误")
    print(f"\nAgent回答:\n{result2['answer']}\n")

    # 测试查询3: 测试Fallback
    print("\n=== 测试查询3: Search Fallback (Keyword -> Semantic) ===")
    # 这里的关键词 'weird_glitch_888' 肯定不存在，应该触发Fallback
    result3 = agent.analyze("帮我查找包含 'weird_glitch_888' 的日志，或者任何看起来奇怪的错误")
    print(f"\nAgent回答:\n{result3['answer']}\n")

    # 检查中间步骤是否包含Fallback
    fallback_occurred = False
    for msg in result3['messages']:
        if isinstance(msg, AIMessage) and "尝试使用语义搜索" in msg.content:
            fallback_occurred = True
            break

    if fallback_occurred:
        print("✅ 检测到Fallback机制成功触发！")
    else:
        print("❌ 未检测到Fallback触发。")


if __name__ == "__main__":
    main()
