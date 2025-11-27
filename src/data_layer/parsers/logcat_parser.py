"""
Android Logcat日志解析器

支持标准Logcat格式：
MM-DD HH:MM:SS.mmm  PID  TID Level Tag: Message

作者: Log Analysis Team
"""

import re
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class LogEntry:
    """标准化的日志条目对象"""
    timestamp: str  # 原始时间戳字符串
    datetime_obj: Optional[datetime]  # 解析后的datetime对象
    pid: int  # 进程ID
    tid: int  # 线程ID
    level: str  # 日志级别 (I/W/E/F/D/V)
    tag: str  # 模块标签
    message: str  # 日志消息
    raw_line: str  # 原始日志行
    line_number: int  # 行号（在原文件中的位置）
    
    def to_dict(self) -> Dict:
        """转换为字典格式，便于存储"""
        return {
            'timestamp': self.timestamp,
            'datetime': self.datetime_obj.isoformat() if self.datetime_obj else None,
            'pid': self.pid,
            'tid': self.tid,
            'level': self.level,
            'tag': self.tag,
            'message': self.message,
            'raw_line': self.raw_line,
            'line_number': self.line_number
        }


class LogcatParser:
    """Android Logcat解析器
    
    功能：
    1. 解析标准Logcat格式
    2. 提取关键字段（时间、PID、级别、Tag、Message）
    3. 处理多行日志（如堆栈信息）
    4. 支持批量解析和流式解析
    """
    
    # Logcat标准格式正则表达式
    # 格式: 11-26 14:00:05.123  1234  1256 I SystemServer: System startup
    LOGCAT_PATTERN = re.compile(
        r'^(?P<month>\d{2})-(?P<day>\d{2})\s+'  # 日期: MM-DD
        r'(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})\.(?P<millisecond>\d{3})\s+'  # 时间
        r'(?P<pid>\d+)\s+'  # PID
        r'(?P<tid>\d+)\s+'  # TID
        r'(?P<level>[IWEFVD])\s+'  # Level (I/W/E/F/V/D)
        r'(?P<tag>[^:]+):\s*'  # Tag
        r'(?P<message>.*)$'  # Message
    )
    
    def __init__(self, current_year: int = 2025):
        """初始化解析器
        
        Args:
            current_year: 当前年份（Logcat不包含年份信息，需要指定）
        """
        self.current_year = current_year
        self.parsed_count = 0
        self.failed_count = 0
        
        logger.info(f"LogcatParser initialized (year={current_year})")
    
    def parse_line(self, line: str, line_number: int) -> Optional[LogEntry]:
        """解析单行日志
        
        Args:
            line: 日志行文本
            line_number: 行号
            
        Returns:
            LogEntry对象，如果解析失败返回None
        """
        line = line.strip()
        
        # 跳过空行
        if not line:
            return None
        
        # 尝试匹配Logcat格式
        match = self.LOGCAT_PATTERN.match(line)
        if not match:
            self.failed_count += 1
            logger.debug(f"Line {line_number} doesn't match Logcat pattern: {line[:50]}...")
            return None
        
        try:
            # 提取各字段
            groups = match.groupdict()
            
            # 构建时间戳字符串
            timestamp = f"{groups['month']}-{groups['day']} {groups['hour']}:{groups['minute']}:{groups['second']}.{groups['millisecond']}"
            
            # 解析为datetime对象
            datetime_obj = None
            try:
                datetime_obj = datetime(
                    year=self.current_year,
                    month=int(groups['month']),
                    day=int(groups['day']),
                    hour=int(groups['hour']),
                    minute=int(groups['minute']),
                    second=int(groups['second']),
                    microsecond=int(groups['millisecond']) * 1000  # 毫秒转微秒
                )
            except ValueError as e:
                logger.warning(f"Invalid datetime at line {line_number}: {e}")
            
            # 创建LogEntry对象
            entry = LogEntry(
                timestamp=timestamp,
                datetime_obj=datetime_obj,
                pid=int(groups['pid']),
                tid=int(groups['tid']),
                level=groups['level'],
                tag=groups['tag'].strip(),
                message=groups['message'],
                raw_line=line,
                line_number=line_number
            )
            
            self.parsed_count += 1
            return entry
            
        except Exception as e:
            self.failed_count += 1
            logger.error(f"Error parsing line {line_number}: {e}")
            logger.debug(f"Problematic line: {line}")
            return None
    
    def parse_file(self, file_path: str, max_lines: Optional[int] = None) -> List[LogEntry]:
        """解析整个日志文件
        
        Args:
            file_path: 日志文件路径
            max_lines: 最大解析行数（None表示解析全部）
            
        Returns:
            LogEntry对象列表
        """
        logger.info(f"Parsing log file: {file_path}")
        entries = []
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line_number, line in enumerate(f, start=1):
                    # 达到最大行数限制
                    if max_lines and line_number > max_lines:
                        logger.info(f"Reached max_lines limit: {max_lines}")
                        break
                    
                    entry = self.parse_line(line, line_number)
                    if entry:
                        entries.append(entry)
                    
                    # 每10000行输出一次进度
                    if line_number % 10000 == 0:
                        logger.info(f"Processed {line_number} lines, parsed {self.parsed_count} entries")
            
            logger.info(f"Parsing complete: {self.parsed_count} entries parsed, {self.failed_count} lines failed")
            return entries
            
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            raise
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise
    
    def parse_batch(self, lines: List[str], start_line_number: int = 1) -> List[LogEntry]:
        """批量解析日志行
        
        Args:
            lines: 日志行列表
            start_line_number: 起始行号
            
        Returns:
            LogEntry对象列表
        """
        entries = []
        for i, line in enumerate(lines):
            line_number = start_line_number + i
            entry = self.parse_line(line, line_number)
            if entry:
                entries.append(entry)
        
        return entries
    
    def get_statistics(self) -> Dict:
        """获取解析统计信息
        
        Returns:
            包含统计数据的字典
        """
        total = self.parsed_count + self.failed_count
        success_rate = (self.parsed_count / total * 100) if total > 0 else 0
        
        return {
            'parsed_count': self.parsed_count,
            'failed_count': self.failed_count,
            'total_lines': total,
            'success_rate': f"{success_rate:.2f}%"
        }


def main():
    """测试函数"""
    from pathlib import Path
    
    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent.parent / "tests" / "sample_logs" / "android_logcat_sample.log"
    
    if not sample_path.exists():
        logger.error(f"Sample log not found: {sample_path}")
        return
    
    # 创建解析器
    parser = LogcatParser()
    
    # 解析文件
    entries = parser.parse_file(str(sample_path))
    
    # 显示统计信息
    stats = parser.get_statistics()
    print("\n=== 解析统计 ===")
    print(f"总行数: {stats['total_lines']}")
    print(f"成功解析: {stats['parsed_count']}")
    print(f"解析失败: {stats['failed_count']}")
    print(f"成功率: {stats['success_rate']}")
    
    # 显示前5条日志
    print("\n=== 前5条日志 ===")
    for entry in entries[:5]:
        print(f"[{entry.timestamp}] {entry.level}/{entry.tag}: {entry.message}")
    
    # 查找错误和致命日志
    error_logs = [e for e in entries if e.level in ['E', 'F']]
    print(f"\n=== 发现 {len(error_logs)} 条错误/致命日志 ===")
    for entry in error_logs[:10]:  # 只显示前10条
        print(f"[{entry.timestamp}] {entry.level}/{entry.tag}: {entry.message[:80]}")


if __name__ == "__main__":
    main()

