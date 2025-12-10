"""
关键词检索引擎 (基于SQLite FTS5)

功能:
1. 建立日志全文索引
2. 支持高效的关键词搜索
3. 支持时间范围、级别、Tag等多维度过滤
4. 返回上下文信息

作者: Log Analysis Team
"""

import sqlite3
from typing import List, Dict, Optional, Tuple
from pathlib import Path
from loguru import logger
from datetime import datetime

from src.data_layer.parsers.logcat_parser import LogEntry


class KeywordSearchEngine:
    """基于SQLite FTS5的关键词检索引擎

    使用SQLite的FTS5（Full-Text Search）扩展实现高效的全文检索
    """

    def __init__(self, db_path: str = "./data/logs.db"):
        """初始化搜索引擎

        Args:
            db_path: SQLite数据库路径
        """
        self.db_path = db_path

        # 确保数据目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 创建数据库连接（允许跨线程使用）
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # 以字典形式返回结果

        # 创建表和索引
        self._create_tables()

        logger.info(f"KeywordSearchEngine initialized (db={db_path})")

    def _create_tables(self):
        """创建数据库表和FTS索引"""
        cursor = self.conn.cursor()

        # 主日志表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                datetime TEXT,
                pid INTEGER,
                tid INTEGER,
                level TEXT,
                tag TEXT,
                message TEXT,
                raw_line TEXT,
                line_number INTEGER,
                session_id TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引以加速查询
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_datetime 
            ON logs(datetime)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_level 
            ON logs(level)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tag 
            ON logs(tag)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session 
            ON logs(session_id)
        """)

        # FTS5全文索引表（用于高效的全文搜索）
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS logs_fts USING fts5(
                tag, 
                message,
                content='logs',
                content_rowid='id'
            )
        """)

        # 触发器：自动同步数据到FTS表
        # 注意：由于使用了 content='logs'，logs_fts 不存储实际数据，需要手动保持同步

        # 1. 插入同步
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS logs_ai AFTER INSERT ON logs BEGIN
                INSERT INTO logs_fts(rowid, tag, message)
                VALUES (new.id, new.tag, new.message);
            END
        """)

        # 2. 删除同步
        # 注意：'logs_fts' 是FTS5的特殊魔法列(与表名相同)，用于发送控制命令
        # 写入 'delete' 到此列告诉FTS5从索引中移除对应的条目
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS logs_ad AFTER DELETE ON logs BEGIN
                INSERT INTO logs_fts(logs_fts, rowid, tag, message)
                VALUES('delete', old.id, old.tag, old.message);
            END
        """)

        # 3. 更新同步 (先删旧索引，再插新索引)
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS logs_au AFTER UPDATE ON logs BEGIN
                INSERT INTO logs_fts(logs_fts, rowid, tag, message)
                VALUES('delete', old.id, old.tag, old.message);
                INSERT INTO logs_fts(rowid, tag, message)
                VALUES (new.id, new.tag, new.message);
            END
        """)

        self.conn.commit()
        logger.info("Database tables and FTS index created")

    def insert_logs(self, entries: List[LogEntry], session_id: str = "default") -> int:
        """批量插入日志

        Args:
            entries: 日志条目列表
            session_id: 会话ID（用于区分不同的日志文件）

        Returns:
            插入的日志条数
        """
        cursor = self.conn.cursor()

        insert_data = []
        for entry in entries:
            insert_data.append((
                entry.timestamp,
                entry.datetime_obj.isoformat() if entry.datetime_obj else None,
                entry.pid,
                entry.tid,
                entry.level,
                entry.tag,
                entry.message,
                entry.raw_line,
                entry.line_number,
                session_id
            ))

        cursor.executemany("""
            INSERT INTO logs (timestamp, datetime, pid, tid, level, tag, message, raw_line, line_number, session_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, insert_data)

        self.conn.commit()

        logger.info(
            f"Inserted {len(entries)} log entries (session={session_id})")
        return len(entries)

    def search_keywords(
        self,
        keywords: str,
        level: Optional[str] = None,
        tag: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict]:
        """关键词搜索

        Args:
            keywords: 搜索关键词（支持多个词，用空格分隔）
            level: 日志级别过滤 (可选)
            tag: Tag过滤 (可选)
            start_time: 开始时间 (ISO格式字符串，可选)
            end_time: 结束时间 (ISO格式字符串，可选)
            limit: 返回结果数量限制

        Returns:
            匹配的日志列表
        """
        cursor = self.conn.cursor()

        # 构建查询
        # 注意：WHERE fts.logs_fts MATCH ?
        # 这里使用表名同名列(logs_fts)进行MATCH，意味着对所有索引列(tag, message)进行全文检索
        # 即：只要 tag 或 message 中包含关键词，都会被匹配到
        query = """
            SELECT l.*
            FROM logs l
            JOIN logs_fts fts ON l.id = fts.rowid
            WHERE fts.logs_fts MATCH ?
        """

        params = [keywords]

        # 添加过滤条件
        if level:
            query += " AND l.level = ?"
            params.append(level)

        if tag:
            query += " AND l.tag LIKE ?"
            params.append(f"%{tag}%")

        if start_time:
            query += " AND l.datetime >= ?"
            params.append(start_time)

        if end_time:
            query += " AND l.datetime <= ?"
            params.append(end_time)

        if session_id:
            query += " AND l.session_id = ?"
            params.append(session_id)

        query += " ORDER BY l.datetime LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        results = cursor.fetchall()

        # 转换为字典列表
        logs = [dict(row) for row in results]

        logger.info(
            f"Keyword search '{keywords}' returned {len(logs)} results")
        return logs

    def get_logs_by_time_range(
        self,
        start_time: str,
        end_time: str,
        level: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict]:
        """根据时间范围获取日志

        Args:
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            level: 日志级别过滤 (可选)
            limit: 返回结果数量限制

        Returns:
            日志列表
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM logs WHERE datetime >= ? AND datetime <= ?"
        params = [start_time, end_time]

        if level:
            query += " AND level = ?"
            params.append(level)

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY datetime LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        results = cursor.fetchall()

        logs = [dict(row) for row in results]

        logger.info(f"Time range query returned {len(logs)} results")
        return logs

    def filter_by_tag(self, tag: str, session_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        """根据Tag过滤日志

        Args:
            tag: Tag名称（支持模糊匹配）
            session_id: 会话ID过滤（可选）
            limit: 返回结果数量限制

        Returns:
            日志列表
        """
        cursor = self.conn.cursor()

        query = "SELECT * FROM logs WHERE tag LIKE ?"
        params = [f"%{tag}%"]

        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY datetime LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)

        results = cursor.fetchall()
        logs = [dict(row) for row in results]

        logger.info(f"Tag filter '{tag}' returned {len(logs)} results")
        return logs

    def get_context(self, log_id: int, window_size: int = 50) -> List[Dict]:
        """获取某条日志的上下文

        Args:
            log_id: 日志ID
            window_size: 上下文窗口大小（前后各N行）

        Returns:
            包含上下文的日志列表
        """
        cursor = self.conn.cursor()

        # 获取目标日志的行号和会话ID
        cursor.execute(
            "SELECT line_number, session_id FROM logs WHERE id = ?", (log_id,))
        row = cursor.fetchone()

        if not row:
            logger.warning(f"Log ID {log_id} not found")
            return []

        target_line = row['line_number']
        session_id = row['session_id']

        # 获取前后N行
        cursor.execute("""
            SELECT * FROM logs 
            WHERE session_id = ? 
            AND line_number >= ? 
            AND line_number <= ?
            ORDER BY line_number
        """, (session_id, target_line - window_size, target_line + window_size))

        results = cursor.fetchall()
        logs = [dict(row) for row in results]

        logger.info(f"Context for log {log_id}: {len(logs)} lines")
        return logs

    def get_statistics(self, session_id: Optional[str] = None) -> Dict:
        """获取统计信息

        Args:
            session_id: 会话ID (可选，不指定则统计全部)

        Returns:
            统计信息字典
        """
        cursor = self.conn.cursor()

        # 总日志数
        if session_id:
            cursor.execute(
                "SELECT COUNT(*) as count FROM logs WHERE session_id = ?", (session_id,))
        else:
            cursor.execute("SELECT COUNT(*) as count FROM logs")
        total_count = cursor.fetchone()['count']

        # 按级别统计
        if session_id:
            cursor.execute("""
                SELECT level, COUNT(*) as count 
                FROM logs 
                WHERE session_id = ?
                GROUP BY level
            """, (session_id,))
        else:
            cursor.execute(
                "SELECT level, COUNT(*) as count FROM logs GROUP BY level")
        level_dist = {row['level']: row['count'] for row in cursor.fetchall()}

        # 按Tag统计（Top 10）
        if session_id:
            cursor.execute("""
                SELECT tag, COUNT(*) as count 
                FROM logs 
                WHERE session_id = ?
                GROUP BY tag 
                ORDER BY count DESC 
                LIMIT 10
            """, (session_id,))
        else:
            cursor.execute("""
                SELECT tag, COUNT(*) as count 
                FROM logs 
                GROUP BY tag 
                ORDER BY count DESC 
                LIMIT 10
            """)
        tag_dist = {row['tag']: row['count'] for row in cursor.fetchall()}

        # 时间范围
        if session_id:
            cursor.execute("""
                SELECT MIN(datetime) as start_time, MAX(datetime) as end_time 
                FROM logs 
                WHERE session_id = ? AND datetime IS NOT NULL
            """, (session_id,))
        else:
            cursor.execute("""
                SELECT MIN(datetime) as start_time, MAX(datetime) as end_time 
                FROM logs 
                WHERE datetime IS NOT NULL
            """)
        time_range = cursor.fetchone()

        return {
            'total_count': total_count,
            'level_distribution': level_dist,
            'top_tags': tag_dist,
            'time_range': {
                'start': time_range['start_time'],
                'end': time_range['end_time']
            }
        }

    def clear_session(self, session_id: str):
        """清除指定会话的日志

        Args:
            session_id: 会话ID
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM logs WHERE session_id = ?", (session_id,))
        self.conn.commit()

        logger.info(f"Cleared logs for session: {session_id}")

    def close(self):
        """关闭数据库连接"""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")


def main():
    """测试函数"""
    from src.data_layer.parsers.logcat_parser import LogcatParser
    from pathlib import Path

    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent / \
        "tests" / "sample_logs" / "android_logcat_sample.log"

    # 解析日志
    parser = LogcatParser()
    entries = parser.parse_file(str(sample_path))

    # 创建搜索引擎
    search_engine = KeywordSearchEngine(db_path="./data/test_logs.db")

    # 清除旧数据
    search_engine.clear_session("test_session")

    # 插入日志
    search_engine.insert_logs(entries, session_id="test_session")

    # 获取统计信息
    stats = search_engine.get_statistics("test_session")
    print("\n=== 数据库统计 ===")
    print(f"总日志数: {stats['total_count']}")
    print(f"级别分布: {stats['level_distribution']}")
    print(f"Top Tags: {stats['top_tags']}")
    print(
        f"时间范围: {stats['time_range']['start']} 到 {stats['time_range']['end']}")

    # 搜索崩溃相关日志
    print("\n=== 搜索 'crash' 或 'fatal' ===")
    crash_logs = search_engine.search_keywords("crash OR fatal", limit=10)
    for log in crash_logs[:5]:
        print(
            f"[{log['timestamp']}] {log['level']}/{log['tag']}: {log['message'][:80]}")

    # 搜索CameraService的错误
    print("\n=== 搜索 CameraService 的错误 ===")
    camera_errors = search_engine.search_keywords("camera", level="E")
    for log in camera_errors:
        print(
            f"[{log['timestamp']}] {log['level']}/{log['tag']}: {log['message'][:80]}")

    # 根据时间范围查询
    print("\n=== 查询 14:28:45 到 14:28:50 的日志 ===")
    time_logs = search_engine.get_logs_by_time_range(
        "2025-11-26T14:28:45",
        "2025-11-26T14:28:50",
        limit=20
    )
    print(f"找到 {len(time_logs)} 条日志")
    for log in time_logs[:5]:
        print(
            f"[{log['timestamp']}] {log['level']}/{log['tag']}: {log['message'][:60]}")

    # 获取上下文
    if crash_logs:
        print(f"\n=== 获取第一条崩溃日志的上下文 (前后5行) ===")
        context = search_engine.get_context(crash_logs[0]['id'], window_size=5)
        for log in context:
            marker = " >>> " if log['id'] == crash_logs[0]['id'] else "     "
            print(
                f"{marker}[{log['timestamp']}] {log['level']}/{log['tag']}: {log['message'][:60]}")

    search_engine.close()


if __name__ == "__main__":
    main()
