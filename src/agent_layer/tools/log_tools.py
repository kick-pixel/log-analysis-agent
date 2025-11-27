"""
日志分析Agent工具集

提供给LLM调用的工具函数，用于查询和分析日志

作者: Log Analysis Team
"""

from typing import Optional, List, Dict, Any
from langchain.tools import tool
from loguru import logger

# 全局存储引擎实例（将在初始化时设置）
_keyword_engine = None
_vector_engine = None
_orchestrator = None


def init_tools(keyword_engine, vector_engine, orchestrator):
    """初始化工具，注入存储引擎实例
    
    Args:
        keyword_engine: 关键词搜索引擎实例
        vector_engine: 向量搜索引擎实例
        orchestrator: Agent orchestrator实例（用于获取current_session_id）
    """
    global _keyword_engine, _vector_engine, _orchestrator
    _keyword_engine = keyword_engine
    _vector_engine = vector_engine
    _orchestrator = orchestrator
    logger.info("Agent tools initialized with storage engines")


@tool
def query_logs_by_time_range(
    start_time: str,
    end_time: str,
    level: Optional[str] = None
) -> str:
    """根据时间范围查询日志
    
    用于查看特定时间段内的日志记录。
    
    Args:
        start_time: 开始时间（ISO格式，如"2025-11-26T14:28:00"）
        end_time: 结束时间（ISO格式）
        level: 可选的日志级别过滤（I/W/E/F）
        
    Returns:
        查询结果的描述性文本
    """
    if not _keyword_engine:
        return "错误：搜索引擎未初始化"
    
    try:
        # 获取当前会话ID
        session_id = _orchestrator.current_session_id if _orchestrator else None
        logger.info(f"🔍 query_logs_by_time_range - session_id: {session_id}")
        
        results = _keyword_engine.get_logs_by_time_range(
            start_time=start_time,
            end_time=end_time,
            level=level,
            session_id=session_id,
            limit=50
        )
        
        if not results:
            return f"在时间范围 {start_time} 到 {end_time} 内没有找到日志"
        
        # 格式化输出
        output = [f"找到 {len(results)} 条日志：\n"]
        
        # 按级别统计
        level_count = {}
        for log in results:
            lv = log.get('level', 'Unknown')
            level_count[lv] = level_count.get(lv, 0) + 1
        
        output.append(f"级别分布: {dict(level_count)}\n")
        output.append("\n前10条日志：\n")
        
        for i, log in enumerate(results[:10], 1):
            timestamp = log.get('timestamp', 'N/A')
            lv = log.get('level', '?')
            tag = log.get('tag', 'Unknown')
            msg = log.get('message', '')[:100]  # 限制消息长度
            output.append(f"{i}. [{timestamp}] {lv}/{tag}: {msg}\n")
        
        if len(results) > 10:
            output.append(f"\n...还有 {len(results) - 10} 条日志未显示\n")
        
        return ''.join(output)
        
    except Exception as e:
        logger.error(f"query_logs_by_time_range error: {e}")
        return f"查询时发生错误: {str(e)}"


@tool
def search_error_keywords(
    keywords: str,
    level: Optional[str] = None,
    tag: Optional[str] = None
) -> str:
    """搜索包含特定关键词的错误日志
    
    用于查找包含特定关键词（如"crash"、"exception"、"error"）的日志。
    
    Args:
        keywords: 搜索关键词（支持多个词，用空格分隔；支持OR逻辑）
        level: 可选的日志级别过滤（E表示Error，F表示Fatal）
        tag: 可选的模块Tag过滤
        
    Returns:
        搜索结果的描述性文本
    """
    if not _keyword_engine:
        return "错误：搜索引擎未初始化"
    
    try:
        # 获取当前会话ID
        session_id = _orchestrator.current_session_id if _orchestrator else None
        logger.info(f"🔍 search_error_keywords - session_id: {session_id}, keywords: {keywords}")
        
        results = _keyword_engine.search_keywords(
            keywords=keywords,
            level=level,
            tag=tag,
            session_id=session_id,
            limit=30
        )
        
        if not results:
            return f"没有找到包含 '{keywords}' 的日志"
        
        # 格式化输出
        output = [f"找到 {len(results)} 条匹配日志：\n"]
        
        # 按Tag统计
        tag_count = {}
        for log in results:
            t = log.get('tag', 'Unknown')
            tag_count[t] = tag_count.get(t, 0) + 1
        
        # 显示Top 5 Tags
        top_tags = sorted(tag_count.items(), key=lambda x: x[1], reverse=True)[:5]
        output.append(f"主要模块: {dict(top_tags)}\n")
        output.append("\n日志详情：\n")
        
        for i, log in enumerate(results[:15], 1):  # 显示前15条
            timestamp = log.get('timestamp', 'N/A')
            lv = log.get('level', '?')
            tag = log.get('tag', 'Unknown')
            msg = log.get('message', '')[:120]
            output.append(f"{i}. [{timestamp}] {lv}/{tag}:\n   {msg}\n")
        
        if len(results) > 15:
            output.append(f"\n...还有 {len(results) - 15} 条匹配日志\n")
        
        return ''.join(output)
        
    except Exception as e:
        logger.error(f"search_error_keywords error: {e}")
        return f"搜索时发生错误: {str(e)}"


@tool
def semantic_search_logs(query: str, n_results: int = 10) -> str:
    """使用自然语言语义搜索日志
    
    当用户的描述不够精确，或者需要模糊匹配时使用。
    例如："为什么相机打不开"、"内存相关的问题"等。
    
    Args:
        query: 自然语言查询描述
        n_results: 返回结果数量（默认10）
        
    Returns:
        搜索结果的描述性文本
    """
    if not _vector_engine:
        return "错误：向量搜索引擎未初始化"
    
    try:
        # 获取当前会话ID
        session_id = _orchestrator.current_session_id if _orchestrator else None
        logger.info(f"🔍 semantic_search_logs - session_id: {session_id}, query: {query}")
        
        results = _vector_engine.semantic_search(
            query=query,
            n_results=n_results,
            session_id=session_id
        )
        
        if not results:
            return f"没有找到与 '{query}' 相关的日志"
        
        # 格式化输出
        output = [f"找到 {len(results)} 条语义相关的日志：\n"]
        output.append(f"（按相似度排序，距离越小越相似）\n\n")
        
        for i, result in enumerate(results, 1):
            metadata = result.get('metadata', {})
            timestamp = metadata.get('timestamp', 'N/A')
            level = metadata.get('level', '?')
            tag = metadata.get('tag', 'Unknown')
            doc = result.get('document', '')
            distance = result.get('distance', 0)
            
            output.append(f"{i}. [{timestamp}] {level}/{tag}\n")
            output.append(f"   {doc}\n")
            output.append(f"   [相似度距离: {distance:.4f}]\n\n")
        
        return ''.join(output)
        
    except Exception as e:
        logger.error(f"semantic_search_logs error: {e}")
        return f"语义搜索时发生错误: {str(e)}"


@tool
def filter_logs_by_tag(tag: str, limit: int = 20) -> str:
    """按模块Tag过滤日志
    
    用于查看特定模块（如CameraService、SystemUI等）的所有日志。
    
    Args:
        tag: 模块Tag名称（支持模糊匹配）
        limit: 返回结果数量限制
        
    Returns:
        过滤结果的描述性文本
    """
    if not _keyword_engine:
        return "错误：搜索引擎未初始化"
    
    try:
        # 获取当前会话ID
        session_id = _orchestrator.current_session_id if _orchestrator else None
        logger.info(f"🔍 filter_logs_by_tag - session_id: {session_id}, tag: {tag}")
        
        results = _keyword_engine.filter_by_tag(tag=tag, session_id=session_id, limit=limit)
        
        if not results:
            return f"没有找到Tag包含 '{tag}' 的日志"
        
        # 格式化输出
        output = [f"找到 {len(results)} 条 '{tag}' 相关日志：\n"]
        
        # 统计级别分布
        level_count = {}
        for log in results:
            lv = log.get('level', 'Unknown')
            level_count[lv] = level_count.get(lv, 0) + 1
        
        output.append(f"级别分布: {dict(level_count)}\n\n")
        
        for i, log in enumerate(results, 1):
            timestamp = log.get('timestamp', 'N/A')
            lv = log.get('level', '?')
            full_tag = log.get('tag', 'Unknown')
            msg = log.get('message', '')[:100]
            output.append(f"{i}. [{timestamp}] {lv}/{full_tag}:\n   {msg}\n")
        
        return ''.join(output)
        
    except Exception as e:
        logger.error(f"filter_logs_by_tag error: {e}")
        return f"过滤时发生错误: {str(e)}"


@tool
def get_log_context(log_id: int, window_size: int = 20) -> str:
    """获取某条日志的上下文
    
    用于查看某条关键日志前后发生了什么，帮助理解故障的因果关系。
    
    Args:
        log_id: 日志ID（从搜索结果中获取）
        window_size: 上下文窗口大小（前后各N行）
        
    Returns:
        上下文日志的描述性文本
    """
    if not _keyword_engine:
        return "错误：搜索引擎未初始化"
    
    try:
        results = _keyword_engine.get_context(
            log_id=log_id,
            window_size=window_size
        )
        
        if not results:
            return f"未找到日志ID {log_id} 或无上下文"
        
        # 格式化输出
        output = [f"日志ID {log_id} 的上下文（前后{window_size}行）：\n\n"]
        
        for log in results:
            timestamp = log.get('timestamp', 'N/A')
            lv = log.get('level', '?')
            tag = log.get('tag', 'Unknown')
            msg = log.get('message', '')
            
            # 标记目标日志
            marker = " >>> " if log.get('id') == log_id else "     "
            
            output.append(f"{marker}[{timestamp}] {lv}/{tag}:\n")
            output.append(f"{marker}  {msg}\n\n")
        
        return ''.join(output)
        
    except Exception as e:
        logger.error(f"get_log_context error: {e}")
        return f"获取上下文时发生错误: {str(e)}"


@tool
def get_error_statistics(session_id: Optional[str] = None) -> str:
    """获取错误统计信息
    
    用于了解整体日志的错误分布情况。
    
    Args:
        session_id: 可选的会话ID，不指定则统计全部
        
    Returns:
        统计信息的描述性文本
    """
    if not _keyword_engine:
        return "错误：搜索引擎未初始化"
    
    try:
        stats = _keyword_engine.get_statistics(session_id=session_id)
        
        # 格式化输出
        output = ["=== 日志统计信息 ===\n\n"]
        
        output.append(f"总日志数: {stats.get('total_count', 0)}\n\n")
        
        output.append("日志级别分布:\n")
        level_dist = stats.get('level_distribution', {})
        for level, count in sorted(level_dist.items()):
            percentage = (count / stats.get('total_count', 1)) * 100
            output.append(f"  {level}: {count} ({percentage:.1f}%)\n")
        
        output.append("\nTop 10 模块（按日志数量）:\n")
        top_tags = stats.get('top_tags', {})
        for i, (tag, count) in enumerate(top_tags.items(), 1):
            output.append(f"  {i}. {tag}: {count}\n")
        
        time_range = stats.get('time_range', {})
        if time_range.get('start') and time_range.get('end'):
            output.append(f"\n时间范围:\n")
            output.append(f"  开始: {time_range['start']}\n")
            output.append(f"  结束: {time_range['end']}\n")
        
        return ''.join(output)
        
    except Exception as e:
        logger.error(f"get_error_statistics error: {e}")
        return f"获取统计信息时发生错误: {str(e)}"


# 导出所有工具
ALL_TOOLS = [
    query_logs_by_time_range,
    search_error_keywords,
    semantic_search_logs,
    filter_logs_by_tag,
    get_log_context,
    get_error_statistics
]


def get_tool_descriptions() -> List[str]:
    """获取所有工具的描述
    
    Returns:
        工具描述列表
    """
    descriptions = []
    for tool_func in ALL_TOOLS:
        descriptions.append(f"- {tool_func.name}: {tool_func.description}")
    return descriptions

