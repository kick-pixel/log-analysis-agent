"""
Streamlit Web界面

提供用户友好的日志分析交互界面

作者: Log Analysis Team
"""

import streamlit as st
import os
import yaml
from pathlib import Path
from datetime import datetime
from loguru import logger
import sys
from dotenv import load_dotenv

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 加载环境变量（必须在最开始）
env_path = project_root / ".env"
if env_path.exists():
    load_dotenv(env_path)
    logger.info(f"Loaded environment variables from {env_path}")
else:
    logger.warning(f".env file not found at {env_path}")

# 设置环境变量以避免tokenizers警告
os.environ['TOKENIZERS_PARALLELISM'] = 'false'

from src.agent_layer.orchestrator import LogAnalysisAgent
from langchain_core.messages import HumanMessage, AIMessage


# 页面配置
st.set_page_config(
    page_title="🚗 智能座舱日志分析 AI Agent",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 加载配置
@st.cache_resource
def load_config():
    """加载配置文件"""
    config_path = project_root / "config" / "config.yaml"
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
        return {}


from src.agent_layer.tools.log_tools import init_tools  # 确保导入init_tools

# 初始化Agent
@st.cache_resource
def init_agent():
    """初始化Agent（单例模式）
    
    关键修复：使用st.session_state保存Agent实例，
    确保整个会话使用同一个Agent对象，避免每次查询都重新创建
    """
    try:
        # 调试：打印session_state的所有键
        logger.info(f"🔍 DEBUG: session_state keys = {list(st.session_state.keys())}")
        
        # 如果session_state中已有agent实例，直接返回（单例模式）
        if 'agent_instance' in st.session_state:
            agent = st.session_state['agent_instance']
            logger.info(f"♻️ 复用现有Agent实例 (session_id={agent.current_session_id})")
            
            # ⚡️ 关键修复：每次获取缓存Agent时，必须重新绑定Tools！
            # Streamlit重载可能导致log_tools模块的全局变量丢失，必须重新注入
            init_tools(agent.keyword_engine, agent.vector_engine, agent)
            logger.info("🔗 已重新绑定Tools到Agent实例")
            
            return agent
        
        logger.info("❌ session_state中没有agent_instance，需要创建新实例")
        
        # 检查API Key
        if not os.getenv('OPENAI_API_KEY'):
            st.error("⚠️ 未找到OPENAI_API_KEY环境变量")
            st.info("请在项目根目录创建.env文件，并设置OPENAI_API_KEY")
            st.stop()
        
        logger.info("🆕 创建新的Agent实例")
        agent = LogAnalysisAgent(
            config_path=str(project_root / "config" / "config.yaml"),
            db_path=str(project_root / "data" / "logs.db"),
            vector_db_path=str(project_root / "data" / "chroma_db")
        )
        
        # 保存到session_state（单例模式）
        st.session_state['agent_instance'] = agent
        
        # 首次创建也要绑定Tools（Agent初始化内部其实已经做了一次，但为了保险）
        init_tools(agent.keyword_engine, agent.vector_engine, agent)
        
        logger.info(f"💾 Agent实例已保存到session_state, keys now = {list(st.session_state.keys())}")
        
        return agent
    except Exception as e:
        st.error(f"❌ Agent初始化失败: {str(e)}")
        st.stop()


def main():
    """主函数"""
    # 标题和说明
    st.title("🚗 智能座舱日志分析 AI Agent")
    st.markdown("""
    这是一个基于AI的日志分析助手，能够帮助你快速定位车载系统故障。
    
    **功能特点**：
    - 📝 支持Android Logcat日志解析
    - 🔍 关键词检索 + 语义搜索双引擎
    - 🤖 AI驱动的智能分析
    - 💬 自然语言对话交互
    """)
    
    # 侧边栏
    with st.sidebar:
        st.header("📁 日志文件管理")
        
        # 文件上传
        uploaded_file = st.file_uploader(
            "上传日志文件",
            type=['log', 'txt'],
            help="支持 .log 和 .txt 格式的Android Logcat日志"
        )
        
        if uploaded_file:
            # 保存上传的文件
            temp_dir = project_root / "data" / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)
            
            temp_file_path = temp_dir / uploaded_file.name
            with open(temp_file_path, 'wb') as f:
                f.write(uploaded_file.getbuffer())
            
            # 加载日志
            if st.button("🚀 解析并加载日志", use_container_width=True):
                with st.spinner("正在解析日志..."):
                    agent = init_agent()
                    
                    # 生成会话ID（使用文件名+时间戳）
                    session_id = f"{uploaded_file.name.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    
                    result = agent.load_logs(str(temp_file_path), session_id=session_id)
                    
                    if result['success']:
                        st.success(f"✅ {result['message']}")
                        
                        # 保存session_id到session state（关键修复）
                        st.session_state['current_session_id'] = session_id
                        st.session_state['log_loaded'] = True
                        
                        # 同步到Agent实例（确保立即生效）
                        agent.current_session_id = session_id
                        
                        # 显示统计信息
                        stats = result['statistics']
                        st.info(f"""
                        **统计信息**:
                        - 总日志数: {stats['total_count']}
                        - 时间范围: {stats['time_range']['start']} ~ {stats['time_range']['end']}
                        """)
                        
                        # 显示级别分布
                        level_dist = stats['level_distribution']
                        st.write("**日志级别分布**:")
                        for level, count in level_dist.items():
                            percentage = (count / stats['total_count']) * 100
                            st.write(f"- {level}: {count} ({percentage:.1f}%)")
                    else:
                        st.error(f"❌ {result['message']}")
        
        st.divider()
        
        # 显示当前会话信息
        if 'current_session_id' in st.session_state:
            st.success(f"✅ 当前会话: {st.session_state['current_session_id']}")
        else:
            st.warning("⚠️ 尚未加载日志")
        
        st.divider()
        
        # 示例问题
        st.header("💡 示例问题")
        config = load_config()
        example_questions = config.get('interface', {}).get('example_questions', [
            "查找所有崩溃(Crash)相关的日志",
            "分析14:00到14:30之间的错误",
            "CameraService有什么异常吗？",
            "帮我看看为什么蓝牙断开连接了"
        ])
        
        for i, question in enumerate(example_questions):
            if st.button(question, key=f"example_{i}", use_container_width=True):
                st.session_state['example_query'] = question
        
        st.divider()
        
        # 清除对话历史
        if st.button("🗑️ 清除对话历史", use_container_width=True):
            st.session_state['messages'] = []
            st.rerun()
    
    # 主区域 - 对话界面
    if 'log_loaded' not in st.session_state or not st.session_state['log_loaded']:
        st.info("👈 请先在侧边栏上传并加载日志文件")
        
        # 显示使用说明
        with st.expander("📖 使用说明", expanded=True):
            st.markdown("""
            ### 如何使用
            
            1. **上传日志**: 在左侧侧边栏点击"上传日志文件"，选择你的Android Logcat日志文件
            2. **解析日志**: 点击"🚀 解析并加载日志"按钮，系统会自动解析并建立索引
            3. **开始提问**: 在下方对话框中输入你的问题，AI会帮你分析日志
            
            ### 提问示例
            
            - "帮我找找有没有崩溃"
            - "14:28:45 到 14:28:50 发生了什么？"
            - "CameraService有什么错误吗？"
            - "为什么倒车影像黑屏了？"
            
            ### 提示
            
            - 尽量提供具体的时间范围或模块名称
            - 描述清楚故障现象
            - AI会自动调用工具检索相关日志
            """)
    else:
        # 初始化对话历史
        if 'messages' not in st.session_state:
            st.session_state['messages'] = []
        
        # 显示对话历史
        chat_container = st.container()
        with chat_container:
            for message in st.session_state['messages']:
                if isinstance(message, HumanMessage):
                    with st.chat_message("user"):
                        st.write(message.content)
                elif isinstance(message, AIMessage):
                    with st.chat_message("assistant"):
                        st.write(message.content)
        
        # 处理示例问题
        if 'example_query' in st.session_state:
            user_query = st.session_state['example_query']
            del st.session_state['example_query']
            
            # 添加到历史
            st.session_state['messages'].append(HumanMessage(content=user_query))
            
            # 显示用户消息
            with st.chat_message("user"):
                st.write(user_query)
            
            # 调用Agent
            with st.chat_message("assistant"):
                with st.spinner("AI正在分析..."):
                    agent = init_agent()
                    logger.info(f"🔑 当前会话ID: {agent.current_session_id}")
                    
                    result = agent.analyze(user_query, chat_history=st.session_state['messages'][:-1])
                    
                    if result['success']:
                        answer = result['answer']
                        st.write(answer)
                        
                        # 添加到历史
                        st.session_state['messages'].append(AIMessage(content=answer))
                    else:
                        error_msg = f"分析失败: {result.get('error', '未知错误')}"
                        st.error(error_msg)
                        st.session_state['messages'].append(AIMessage(content=error_msg))
            
            st.rerun()
        
        # 用户输入
        user_input = st.chat_input("请输入你的问题...")
        
        if user_input:
            # 添加到历史
            st.session_state['messages'].append(HumanMessage(content=user_input))
            
            # 显示用户消息
            with st.chat_message("user"):
                st.write(user_input)
            
            # 调用Agent
            with st.chat_message("assistant"):
                with st.spinner("AI正在分析..."):
                    agent = init_agent()
                    logger.info(f"🔑 当前会话ID: {agent.current_session_id}")
                    
                    result = agent.analyze(user_input, chat_history=st.session_state['messages'][:-1])
                    
                    if result['success']:
                        answer = result['answer']
                        st.write(answer)
                        
                        # 添加到历史
                        st.session_state['messages'].append(AIMessage(content=answer))
                    else:
                        error_msg = f"分析失败: {result.get('error', '未知错误')}"
                        st.error(error_msg)
                        st.session_state['messages'].append(AIMessage(content=error_msg))
            
            st.rerun()


if __name__ == "__main__":
    main()

