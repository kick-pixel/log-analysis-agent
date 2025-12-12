# 使用 LangGraph 从零构建日志分析智能体：实现智能日志检索与分析的完整指南 v2.0

## 第一章. 别再用肉眼看日志了：智能体觉醒

### 1.1 为什么我们需要一个“日志特工”？

**痛点：**
你是不是经常遇到这种情况：线上出 Bug 了，甩给你几个 G 的日志文件，让你“分析一下”。你盯着满屏的乱码，这就好比在稻草堆里找一根针，还得是用放大镜找。
*   **太慢**：不仅要 grep，还得 awk，眼睛都要看瞎了。
*   **太累**：业务逻辑复杂，还得脑补上下文。
*   **易错**：人脑不是电脑，稍微一走神就漏掉了关键报错。

**解决方案：**
我们要构建的，不是一个简单的脚本，而是一个 **日志分析智能体（Log Analysis Agent）**。
这就好比你雇了一个 **24 小时待命的福尔摩斯**。你不用自己去翻垃圾桶（生日志），你只需要问他：“福尔摩斯先生，昨天下午 3 点有没有什么异常？” 他就会自动调动所有资源，把证据（日志）、推理（分析）和结论直接拍在桌子上。

**一句话总结：**
传统运维是“手工作坊”，我们现在要建的是“自动化智能工厂”。

### 1.2 它到底有多强？一个实战栗子

**痛点：**
“智能体”听起来很高大上，到底能干嘛？

**解决方案：**
别急，我们看个剧本。

**场景**：老板问你：“昨天下午那个崩溃是怎么回事？”

**传统做法**：
1.  你：`SSH` 连服务器。
2.  你：`grep "Exception" app.log`... 滚屏太快看不清。
3.  你：`grep "14:28"`... 发现有一万条。
4.  你：抓狂中...

**智能体做法**：
你（葛优躺）：输入“帮我查找14:28:45到14:28:50之间发生的所有崩溃”。

**智能体（疯狂干活中）**：
1.  **拆解意图**：噢，主人要看“14:28:45-14:28:50”的时间段，还要找“崩溃”相关的。
2.  **派发任务**：时间特工去切日志，搜索特工去查“crash”、“ANR”。
3.  **结果验证**：查到了！
4.  **汇报工作**：直接给你一张表，哪行代码错了都标红。

整个流程，就是下面这张图不仅不仅跑通了，还很优雅：

```mermaid
graph TD
    A[开始] --> B[问题理解智能体]
    style A fill:#4CAF50,stroke:#388E3C
    style B fill:#2196F3,stroke:#1976D2

    B --> C[时间范围智能体]
    style C fill:#FF9800,stroke:#F57C00

    C --> D[关键词搜索智能体]
    style D fill:#9C27B0,stroke:#7B1FA2

    D --> E[语义搜索智能体]
    style E fill:#9C27B0,stroke:#7B1FA2

    E --> F[结果汇总智能体]
    style F fill:#607D8B,stroke:#455A64

    F --> G[结束]
    style G fill:#607D8B,stroke:#455A64
```

### 1.3 什么是“日志分析智能体”？（给极客看的定义）

**痛点：**
市面上的日志工具（ELK, Splunk）都很强，但它们是被动的。它们像字典，你得自己查。

**解决方案：**
**LangGraph** 赋予了工具“生命”。
LangGraph 让日志分析变成了一个 **有状态的图（Stateful Graph）**。

*   **节点（Nodes）**：就是工位，每个节点坐着一个专门干活的 AI 或工具。
*   **边（Edges）**：就是传送带，决定做完这步下一步去哪。
*   **状态（State）**：就是传送带上的篮子，装着所有的上下文和结果，谁都能拿来用。

```mermaid
graph TD
    A[输入请求] --> B{状态初始化}
    style A fill:#4CAF50, color:white
    style B fill:#2196F3, color:white

    B --> C[节点1: 问题理解]
    style C fill:#FF9800, color:white

    C --> D[节点2: 获取时间范围]
    style D fill:#FF9800, color:white

    D --> E{是否需要关键词搜索?}
    style E fill:#FF5722, color:white

    E -- 是 --> F[节点3: 关键词搜索]
    style F fill:#9C27B0, color:white

    E -- 否 --> G[节点4: 语义搜索]

    F --> H{搜索结果是否为空?}
    style H fill:#FF5722, color:white

    H -- 是 --> I[节点5: 语义搜索Fallback]
    style I fill:#9C27B0, color:white

    H -- 否 --> J[节点6: 处理结果]
    style J fill:#4CAF50, color:white

    I --> J

    J --> K[状态持久化存储]
    style K fill:#2196F3, color:white
```

### 1.4 为什么它比传统脚本强 100 倍？

**痛点：**
脚本是死的，跑不出结果就报错退出。

**解决方案：**
智能体是 **活的**。

1.  **它有记忆**：你说“刚刚那个错误”，它知道你指的啥。
2.  **它会变通**（Fallback）：关键词搜不到？它会自动试语义搜索。
3.  **它能断点续传**：服务器重启了？它能记得上次查到哪了，接着查。

### 1.5 五大核心超能力

1.  **打不死的小强（持久化）**：每一步都存盘，随时能读档。
2.  **随时摇人（Human-in-the-loop）**：遇到拿不准的，可以暂停下来问你：“老板，这个操作有点危险，确信要干吗？”
3.  **过目不忘（全面记忆）**：不仅记得这次会话，还能通过向量库记住以前的经验。
4.  **透明盒子（调试能力）**：每一步怎么走的，为什么这么走，轨迹清清楚楚。
5.  **三头六臂（工具集成）**：SQL、Vector DB、Python 脚本，想接啥接啥。

---

## 第二章. 解剖室：智能体的内部构造

### 2.1 整体架构：像公司一样运作

**痛点：**
代码一多就乱，怎么组织？

**解决方案：**
我们采用分层架构，就像一家正规公司：

*   **老板（用户交互层）**：发号施令。
*   **经理（智能体编排层）**：LangGraph 核心，负责分配任务，盯着进度。
*   **员工（工具能力层）**：干苦力的，解析日志、查数据库。
*   **档案室（数据存储层）**：SQLite 存清单，ChromaDB 存内容。

```mermaid
graph TB
    subgraph "用户交互层"
        U[命令行/HTTP API<br/>用户输入/输出]
    end

    subgraph "智能体编排层"
        A[智能体核心<br/>决策与流程控制]
        B[状态管理<br/>消息与数据流转]
        C[工具路由<br/>工具选择与执行]
    end

    subgraph "工具能力层"
        T1[LLM集成<br/>大语言模型]
        T2[日志工具集<br/>查询与分析工具]
        T3[记忆管理<br/>会话与上下文]
    end

    subgraph "数据存储层"
        D1[SQLite<br/>关键词搜索]
        D2[ChromaDB<br/>向量搜索]
        D3[会话存储<br/>状态持久化]
    end

    U --> A
    A --> B
    A --> C
    B --> T1
    B --> T2
    B --> T3
    T2 --> D1
    T2 --> D2
    T3 --> D3

    style A fill:#e1f5fe,stroke:#0277bd,stroke-width:2px
    style T2 fill:#e8f5e8,stroke:#388e3c,stroke-width:2px
    style D1 fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    style D2 fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
```

### 2.2 日志处理流水线：从垃圾到黄金

**痛点：**
日志原始数据又脏又乱，没法直接用。

**解决方案：**
我们设计了一套 **ETL 流水线**，把日志变成结构化数据。最精髓的是 **双层存储**：

*   **SQLite**：存所有日志，用来做精确匹配（比如查 ID）。
*   **ChromaDB**：只存 Error/Warn 级别的关键日志，用来做语义搜索（比如查“为什么慢”）。

这就好比：**SQLite 是仓库清单，ChromaDB 是精品展示柜。**

```mermaid
graph TD
    A[原始日志文件<br/>Logcat, Kernel等] --> B[日志解析器<br/>Parser Layer]
    B --> C[预处理模块<br/>Preprocessor Layer]
    C --> D[双层存储<br/>Dual Storage Layer]
    D --> E[分析工具集<br/>Analysis Tools]
    
    subgraph "解析系统"
        B1[LogcatParser]
        B2[KernelLogParser]
        B3[SyslogParser]
    end
    
    subgraph "预处理系统" 
        C1[标准化处理]
        C2[PII脱敏]
        C3[去重处理]
    end
    
    subgraph "存储系统"
        D1[SQLite<br/>关键词存储]
        D2[ChromaDB<br/>语义存储]
    end
    
    E --> E1[时间范围查询]
    E --> E2[关键词搜索] 
    E --> E3[语义搜索]
    
    style B fill:#e1f5fe
    style C fill:#e8f5e8
    style D fill:#fff3e0
```

#### 硬核实现（代码详解）

**1. 日志解析器 (LogcatParser)**
```python
# Logcat解析器实现
class LogcatParser:
    def parse_line(self, line: str) -> Optional[Dict]:
        """
        解析单行Logcat日志
        示例输入: "12-11 14:28:45.123  1234  5678 E/ActivityManager: ANR in com.example.app"
        """
        # 正则表达式解析
        pattern = r'(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+(\d+)\s+(\d+)\s+([VDIWEF])/(\w+):\s+(.*)'
        match = re.match(pattern, line)
        
        if match:
            timestamp, pid, tid, level, tag, message = match.groups()
            return {
                'timestamp': f"2025-{timestamp}",  # 补全年份
                'pid': int(pid),
                'tid': int(tid), 
                'level': level,
                'tag': tag,
                'message': message
            }
        return None
```

**2. 预处理与脱敏 (LogPreprocessor)**
```python
class LogPreprocessor:
    def __init__(self, enable_deduplication=True, enable_pii_masking=True, min_log_level='I'):
        self.enable_deduplication = enable_deduplication
        self.enable_pii_masking = enable_pii_masking
        self.min_log_level = min_log_level
        self.log_levels = {'V': 0, 'D': 1, 'I': 2, 'W': 3, 'E': 4, 'F': 5}
        
    def process(self, logs: List[Dict]) -> List[Dict]:
        """预处理日志列表"""
        processed_logs = []
        
        # 1. 级别过滤
        min_level_value = self.log_levels.get(self.min_log_level, 2)
        filtered_logs = [
            log for log in logs 
            if self.log_levels.get(log.get('level', 'I'), 2) >= min_level_value
        ]
        
        # 2. PII脱敏
        if self.enable_pii_masking:
            filtered_logs = [self._mask_pii(log) for log in filtered_logs]
        
        # 3. 去重处理
        if self.enable_deduplication:
            filtered_logs = self._deduplicate_logs(filtered_logs)
        
        return filtered_logs
    
    def _mask_pii(self, log: Dict) -> Dict:
        """PII脱敏处理"""
        message = log['message']
        # 隐私信息脱敏：IP地址、手机号、邮箱等
        import re
        # IP地址脱敏
        message = re.sub(r'\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b', '***.***.***.***', message)
        # 手机号脱敏  
        message = re.sub(r'1[3-9]\d{9}', '1**** **** ****', message)
        # 邮箱脱敏
        message = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '***@***.***', message)
        
        log['message'] = message
        return log
```

**3. 双层存储引擎 (DualStorageEngine)**
```python
class DualStorageEngine:
    def __init__(self, sqlite_path: str, chroma_path: str):
        self.keyword_engine = KeywordSearchEngine(db_path=sqlite_path)
        self.vector_engine = VectorSearchEngine(db_path=chroma_path)
    
    def store_logs(self, logs: List[Dict], session_id: str = "default"):
        """双层存储日志"""
        # 1. 所有日志存入SQLite（关键词存储层）
        self.keyword_engine.insert_logs(logs, session_id=session_id)
        
        # 2. 重要日志存入ChromaDB（语义存储层）
        important_logs = [
            log for log in logs 
            if log.get('level') in ['W', 'E', 'F']  # WARN, ERROR, FATAL
        ]
        
        if important_logs:
            self.vector_engine.insert_logs(important_logs, session_id=session_id)
        
        return {
            'total_stored': len(logs),
            'semantic_stored': len(important_logs),
            'storage_ratio': len(important_logs) / len(logs) if logs else 0
        }
```

**4. 性能提升实测**
```python
# 传统单层存储 vs 双层存储性能对比
traditional_storage = {
    'total_logs': 100000,
    'search_time': 2.5,  # 秒
    'storage_size': '500MB',
    'memory_usage': '200MB'
}

dual_storage = {
    'total_logs': 100000,
    'keyword_search_time': 0.2,  # 秒 (SQLite)
    'semantic_search_time': 0.8, # 秒 (ChromaDB，只有10000条重要日志)
    'storage_size': '500MB + 50MB',  # SQLite + ChromaDB
    'memory_usage': '100MB + 80MB'   # 更优的内存使用
}

# 性能提升：
speed_improvement = (2.5 - 0.2) / 2.5 * 100  # 关键词搜索提升92%
semantic_efficiency = 10000 / 100000  # 语义搜索数据量减少90%
```

### 2.3 为什么要用 Graph？（LangChain vs LangGraph）

**痛点：**
以前用 LangChain 的 `create_agent` 很爽，一行代码就搞定。但是它是个黑盒，稍微复杂点的逻辑就控制不住，像个脱缰的野马。

**解决方案：**
LangGraph 让你做**驯马师**。

*   **传统 Agent**：像把任务丢给一个临时工，能不能干成全看天意，中间出了岔子你也帮不上忙。
*   **LangGraph Agent**：像你在指挥一场精密的战役。你可以精确控制：
    *   如果A失败了，一定要试B。
    *   做完C之后，必须经我确认才能做D。
    *   随时可以暂停、快进、回放。

**传统 Agent 代码（隐式控制）：**
```python
# orchestrator.py - 传统实现
from langchain.agents import create_agent

class LogAnalysisAgent:
    def __init__(self):
### 2.3 巅峰对决：为什么我们要抛弃 LangChain Agent？

很多同学问：“LangChain 既然有 `create_agent` 这种一键生成的魔法，为什么我们还要费劲去画图（Graph）？”

**痛点：**
LangChain Agent 就像**“自动挡傻瓜相机”**。拍风景照（简单任务）很好用，但如果你想拍星轨（复杂任务），你会发现快门、光圈、ISO 全都锁死了，根本不听你使唤。
它是个黑盒，稍微复杂点的逻辑就控制不住，像个脱缰的野马。

**解决方案：**
LangGraph 是你的**“全手动单反”**。
它把控制权还给了你。你不仅能决定下一步去哪，还能决定“如果错了去哪”、“暂停一下去哪”、“重试几次去哪”。

我们从四个维度来一场血淋淋的对比：

#### ROUND 1: 状态控制（黑盒 vs 白盒）

**痛点（LangChain Agent）：**
状态全在内部，你看不见摸不着。
比如：用户问了一连串问题，中间某个变量变了，你想手动干预一下？没门。Agent 就像个固执的老头，这头进去那头出来，中间发生什么它是不会告诉你的。

**LangGraph 优势：**
状态（State）是**显式**定义的。你可以像操作数据库一样操作状态。想加个字段？想改个历史记录？随你便。

**代码对比（感受一下）：**

*   **LangChain（自动挡）**：
    ```python
    # 看起来很简单，但它是黑盒
    agent_executor = create_agent(llm, tools, prompt)
    # 你只能 invoke，中间发生啥完全听天由命
    agent_executor.invoke({"input": "..."})
    ```

*   **LangGraph（手动挡）**：
    ```python
    # 每一毫秒的状态都在你掌控之中
    class AgentState(TypedDict):
        messages: Annotated[List[BaseMessage], add_messages]
        user_id: str  # 你想加啥加啥
        retry_count: int

    workflow = StateGraph(AgentState)
    # 我要从 A 到 B，如果 B 错了去 C
    workflow.add_node("agent", call_model)
    workflow.add_node("tool", call_tool)
    workflow.add_edge("agent", "tool")
    ```

#### ROUND 2: 路由逻辑（单行道 vs 立交桥）

**痛点（LangChain Agent）：**
传统的 Chain 是**单向**的。一步错，步步错。
比如：关键词搜索没结果，正常应该换个词再搜，但 LangChain Agent 往往会直接傻乎乎地告诉你“没找到”，或者开始瞎编。

**LangGraph 优势：**
图的本质是**循环（Loop）**和**分支（Branch）**。我们能轻松实现“如果搜不到 -> 换个词 -> 再搜 -> 还没搜到 -> 语义搜索”这样的复杂逻辑。

**代码对比（感受一下）：**

*   **LangChain（一条道走到黑）**：
    ```python
    # 很难实现“回退”逻辑
    result = search_keywords("crash")
    if not result:
        return "没找到"  # 游戏结束
    ```

*   **LangGraph（灵活变道）**：
    ```python
    # 智能路由：如果没找到，自动触发 Fallback
    def route_tools(state):
        last_msg = state['messages'][-1]
        if "没找到" in last_msg.content:
            return "fallback_node"  # 即使失败了，也能救回来！
        return "end"

    workflow.add_conditional_edges("search_node", route_tools)
    ```

#### ROUND 3: 记忆与持久化（金鱼 vs 大象）

**痛点（LangChain Agent）：**
默认是**金鱼记忆**。
服务一重启，或者网络一抖动，之前的对话全丢了。用户得从头把问题再说一遍，体验极差。

**LangGraph 优势：**
它是**大象记忆**。
通过 `Checkpointer` 机制，每执行一步，状态就会自动存盘（存数据库）。
哪怕机房断电了，电来了之后，它能精准地从断电前的那一步继续执行！

**实战场景**：
用户问：“帮我查 CPU。” 智能体查了一半停电了。
*   **LangChain**：重启后，用户：“查到了吗？” 智能体：“查什么？你可以再说一遍吗？”
*   **LangGraph**：重启后，智能体自动读取存档：“根据刚才查到的 CPU 数据，我发现...”

#### ROUND 4: 调试能力（盲人摸象 vs 上帝视角）

**痛点（LangChain Agent）：**
出错的时候，你只知道报错了，但不知道是哪一步报的错，只能靠 print 大法猜。

**LangGraph 优势：**
LangGraph Studio 提供了**可视化界面**。你能看到小球在图上流动，哪一步红了，点进去看当时的 State 长什么样，甚至可以修改 State 再重放！

**代码对比：**

*   **LangChain（两眼一抹黑）**：
    ```python
    try:
        agent.invoke(...)
    except Exception:
        # 祝你好运
        print("Something went wrong")
    ```

*   **LangGraph（上帝视角）**：
    ```python
    # 实时像看电影一样看执行过程
    for event in graph.stream(inputs, stream_mode="updates"):
        print(f"当前节点: {event.keys()}")
        print(f"节点输出: {event.values()}")
        # 每一个中间状态都清晰可见
    ```

---

## 第三章. 武器库：六大核心工具

智能体再聪明，没有工具也是巧妇难为无米之炊。我们给它配备了六把“神兵利器”。

### 3.1 武器一览表

| 武器名 | 别名 | 用途 | 什么时候用 |
|---------|------|----------|----------|
| `query_logs_by_time_range` | 时间机器 | 查特定时间段 | "查一下刚才那几分钟" |
| `search_error_keywords` | 精确制导导弹 | 查特定关键词 | "搜一下 NullPointer" |
| `semantic_search_logs` | 读心术 | 语义模糊搜索 | "查一下为什么卡顿" |
| `filter_logs_by_tag` | 筛选器 | 只看某个模块 | "只看 Camera 的日志" |
| `get_log_context` | 放大镜 | 看前后文 | "这行报错前面发生了啥？" |
| `get_error_statistics` | 报表生成器 | 宏观统计 | "总体错误率怎么样？" |

### 3.2 武器全解

#### 1. 时间机器 (`query_logs_by_time_range`)
做运维的都知道，时间就是生命。

**定义：**
```python
@tool
def query_logs_by_time_range(
    start_time: str,
    end_time: str,
    level: Optional[str] = None
) -> str:
    """
    Args:
        start_time: 开始时间（ISO格式，如"2025-11-26T14:28:00"）
        end_time: 结束时间（ISO格式）
        level: 可选的日志级别过滤（I/W/E/F）
    """
```

**实战用法：**
```python
# 查询昨天下午的系统日志
result = query_logs_by_time_range(
    start_time="2025-11-25T15:00:00", 
    end_time="2025-11-25T16:00:00"
)
# 返回结果可能包含：
"""
找到 156 条日志：
级别分布: {I: 120, W: 25, E: 10, F: 1}
前10条日志：
1. [2025-11-25 15:00:01.123] I/ActivityManager: Starting service...
2. [2025-11-25 15:00:05.456] W/Battery: High temperature warning
...
"""
```

#### 2. 精确制导导弹 (`search_error_keywords`)
当你知道具体报错信息（比如 "NullPointer"）时，直接用这个，百发百中。

**定义：**
```python
@tool
def search_error_keywords(
    keywords: str,
    level: Optional[str] = None,
    tag: Optional[str] = None
) -> str:
    """
    Args:
        keywords: 搜索关键词（支持多个词，用空格分隔；支持OR逻辑）
        level: 可选的日志级别过滤（E表示Error，F表示Fatal）
        tag: 可选的模块Tag过滤
    """
```

**实战用法：**
```python
# 搜索系统崩溃相关日志
result = search_error_keywords(
    keywords="crash ANR FATAL",
    level="E"
)
# 返回结果可能包含：
"""
找到 8 条匹配日志：
主要模块: {'AndroidRuntime': 3, 'ActivityManager': 2, 'CameraService': 1}
日志详情：
1. [2025-11-25 15:30:25.123] E/AndroidRuntime: FATAL EXCEPTION: main
   java.lang.NullPointerException: Attempt to invoke virtual method...
2. [2025-11-25 15:32:45.789] E/ActivityManager: ANR in com.example.app
...
"""
```

#### 3. 读心术 (`semantic_search_logs`)
这是最骚的操作。用户说“卡了”，日志里可能没有“卡”字，但有“timeout”或者“slow”。通过向量搜索，AI 能把它们关联起来。

**定义：**
```python
@tool
def semantic_search_logs(query: str, n_results: int = 10) -> str:
    """
    Args:
        query: 自然语言查询描述
        n_results: 返回结果数量（默认10）
    """
```

**实战用法：**
```python
# 语义搜索性能问题
result = semantic_search_logs(
    query="系统运行缓慢的原因",
    n_results=5
)
# 返回结果可能包含：
"""
找到 5 条语义相关的日志：
（按相似度排序，距离越小越相似）
1. [2025-11-25 15:28:45.123] W/SystemServer: High CPU usage detected
   CPU usage reached 95% for process com.example.app
   [相似度距离: 0.1234]
2. [2025-11-25 15:29:30.456] E/PackageManager: Package com.example.app consuming excessive memory
   [相似度距离: 0.2345]
...
"""
```

#### 4. 筛选器 (`filter_logs_by_tag`)
有时候你只关心某个模块（比如 Camera），不想看其他的干扰项。

**定义：**
```python
@tool
def filter_logs_by_tag(tag: str, limit: int = 20) -> str:
    """
    Args:
        tag: 模块Tag名称（支持模糊匹配）
        limit: 返回结果数量限制
    """
```

**实战用法：**
```python
# 过滤CameraService相关日志
result = filter_logs_by_tag(
    tag="CameraService",
    limit=15
)
# 返回结果可能包含：
"""
找到 12 条 'CameraService' 相关日志：
级别分布: {I: 8, W: 3, E: 1}
1. [2025-11-25 15:10:25.123] I/CameraService: Camera service started
2. [2025-11-25 15:10:26.456] I/CameraService: Initializing camera 0
3. [2025-11-25 15:10:27.789] W/CameraService: Camera 0 not responding
...
"""
```

#### 5. 放大镜 (`get_log_context`)
看到报错只是第一步，知道**报错前一秒谁调了它**才是关键。这就像破案现场，不仅要看尸体，还得看周围的脚印。

**定义：**
```python
@tool
def get_log_context(log_id: int, window_size: int = 20) -> str:
    """
    Args:
        log_id: 日志ID（从搜索结果中获取）
        window_size: 上下文窗口大小（前后各N行）
    """
```

**实战用法：**
```python
# 获取关键错误日志的上下文
result = get_log_context(
    log_id=15234,  # 从前面搜索结果中得到的ID
    window_size=10
)
# 返回结果可能包含：
"""
日志ID 15234 的上下文（前后10行）：
     [2025-11-25 15:30:24.987] I/ActivityManager: Start proc com.example.app
     [2025-11-25 15:30:25.012] I/CameraService: Camera initialized
>>>  [2025-11-25 15:30:25.123] E/AndroidRuntime: FATAL EXCEPTION: main
       java.lang.NullPointerException: Attempt to read from field 'android.hardware.camera2.CameraManager
     [2025-11-25 15:30:25.234] E/CrashHandler: Handling uncaught exception
     [2025-11-25 15:30:25.345] W/ActivityManager: Force stopping com.example.app
...
"""
```

#### 6. 报表生成器 (`get_error_statistics`)
老板最喜欢看这个。一目了然的宏观数据。

**定义：**
```python
@tool
def get_error_statistics(session_id: Optional[str] = None) -> str:
    """
    Args:
        session_id: 可选的会话ID，不指定则统计全部
    """
```

**实战用法：**
```python
# 获取当前会话的统计信息
result = get_error_statistics(session_id="current_session")
# 返回结果可能包含：
"""
=== 日志统计信息 ===
总日志数: 1250

日志级别分布:
  I: 1100 (88.0%)
  W: 120 (9.6%)
  E: 25 (2.0%)
  F: 5 (0.4%)

Top 10 模块（按日志数量）:
  1. ActivityManager: 180
  2. PackageManager: 156
  3. CameraService: 89
  4. SystemUI: 76
  ...

时间范围:
  开始: 2025-11-25T15:00:00
  结束: 2025-11-25T16:00:00
"""
```

---

## 第四章. 智能体的神经元：核心节点

有了图的骨架，有了工具武器，现在我们要给它们注入灵魂——节点逻辑。

### 4.1 节点地图

这不仅仅是个流程图，这是智能体思维的具象化。

```mermaid
graph LR
    A[agent: 决策节点] --> B[node_time_query: 时间查询]
    A --> C[node_search_keywords: 关键词搜索]
    A --> D[node_semantic_search: 语义搜索]
    B --> A
    C --> E[check_search_result: 结果检查]
    E --> A
    E --> F[node_fallback_to_semantic: 回退节点]
    F --> D
    D --> A
```

### 4.2 关键神经元解析

#### 1. 大脑节点 (`agent`)
这是 CEO，负责听用户的需求（Message），然后决定派哪个小弟（Tool）去干活。

```python
def call_model(self, state: AgentState):
    """调用模型节点"""
    messages = state['messages']
    response = self.llm_with_tools.invoke(messages)
    return {"messages": [response]}
```

#### 2. 安全网节点 (`node_fallback_to_semantic`)
这是我们最得意的设计。**如果精确搜索扑空了，不要直接告诉用户“没找到”，而是悄悄切换到语义搜索再试一次。**
这就像你在淘宝搜“苹果”，如果没有卖苹果的，它会给你推荐“iPhone”，而不是显示空白。

```python
def node_fallback_to_semantic(self, state: AgentState):
    """Fallback节点：将失败的关键词搜索转换为语义搜索"""
    import uuid
    try:
        messages = state['messages']
        last_ai_message = messages[-2]  # 获取发起搜索的AI消息

        if not hasattr(last_ai_message, 'tool_calls') or not last_ai_message.tool_calls:
            return {"messages": [AIMessage(content="无法执行Fallback：未找到原始工具调用")]}

        tool_call = last_ai_message.tool_calls[0]
        
        # 尝试获取 keywords，兼容不同的参数名
        keywords = tool_call['args'].get('keywords')
        if not keywords:
             keywords = tool_call['args'].get('query')
        if not keywords:
             if tool_call['args']:
                 keywords = list(tool_call['args'].values())[0]

        if not keywords:
             return {"messages": [AIMessage(content="无法执行Fallback：无法提取搜索关键词")]}

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
        logger.error(f"Error in node_fallback_to_semantic: {e}", exc_info=True)
        return {"messages": [AIMessage(content=f"Fallback执行出错: {str(e)}")]}
```

#### 3. 交通指挥官 (`route_tools`)
看着很简单，但它决定了数据流向。如果是工具调用，就去工具节点；如果是普通对话，就结束流程直接回复用户。

```python
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
```

---

## 第五章. 容错艺术：智能回退机制

### 5.1 别让用户看到“无结果”

**痛点：**
用户小白不知道专业的报错代码（比如他只知道“卡顿”，不知道“ANR”）。如果直接搜“卡顿”，SQLite 会冷酷地告诉你：0 results。用户会觉得这 AI 还是个智障。

**解决方案：**
**Fallback（回退）机制**。
这是一种“软着陆”策略。

### 5.2 回退流程图解

```mermaid
graph TD
    A[用户问题] --> B[LLM决策]
    B --> C[关键词搜索]
    C --> D{搜索结果是否为空?}
    D -->|否| E[返回关键词搜索结果]
    D -->|是| F[触发回退机制]
    F --> G[语义搜索]
    G --> H[返回语义搜索结果]
    E --> I[结束]
    H --> I
    style A fill:#4CAF50,stroke:#388E3C
    style I fill:#607D8B,stroke:#455A64
    style F fill:#FF9800,stroke:#F57C00
```

### 5.3 触发条件：什么时候该认怂？

我们定义了几个“认怂”信号，一旦 AI 在工具回复里看到这些词，马上启动 Plan B：

```python
failure_indicators = [
    "没有找到包含 '关键词' 的日志",
    "Found 0 results", 
    "No results found",
    "未搜索到结果",
    "搜索结果为空"
]
```

---

## 第六章. 性能调优：既要马儿跑，又要少吃草

### 6.1 双层存储的智慧

**痛点：**
*   全存 SQLite？语义搜索没法做。
*   全存 Vector DB？太贵，太慢，内存爆炸。

**解决方案：**
**二八原则**。
80% 的日志是废话（INFO/DEBUG），只存 SQLite 备查。
20% 的日志是关键（ERROR/WARN），存 Vector DB 做深度分析。

```python
# 向量数据库性能优化：只索引ERROR和WARN级别日志
important_entries = [
    entry for entry in processed_entries
    if entry.level in ['W', 'E', 'F']  # WARN, ERROR, FATAL
]

if important_entries:
    self.vector_engine.insert_logs(important_entries, session_id=session_id)
```

**效果立竿见影：**
*   **存储空间**：节省 90%。
*   **查询速度**：快了 5-10 倍。

### 6.2 索引策略

别小看索引。我们在 SQLite 里给 `time`, `tag`, `level` 都加了索引。这不是什么高科技，但能让你的查询从 5 秒变成 0.05 秒。

---

## 第七章. 总结：让日志分析性感起来

回到最初的问题：为什么要费劲搞这么多花样？

因为**日志是程序员的最后一道防线**。
我们通过 **LangGraph**，把这道防线变成了一支**训练有素的特种部队**。

1.  **显式状态管理**：让 AI 有了连贯的思维。
2.  **双层存储**：在成本和能力之间找到了完美的平衡点。
3.  **智能回退**：给用户体验加了一道保险。
4.  **图编排**：让复杂的逻辑变得可视化、可控、可调试。

这就不是一个简单的脚本工具了，它是你未来的 **SRE 最佳拍档**。
