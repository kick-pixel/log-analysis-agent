"""
日志预处理器

功能:
1. 日志降噪（过滤低优先级、重复日志）
2. 数据清洗（PII脱敏、格式标准化）
3. 日志分类和标注

作者: Log Analysis Team
"""

from typing import List, Set, Dict, Optional
from collections import Counter
from loguru import logger
import re

from src.data_layer.parsers.logcat_parser import LogEntry


class LogPreprocessor:
    """日志预处理器
    
    提供日志过滤、去重、脱敏等预处理功能
    """
    
    # 敏感信息正则模式
    PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')  # 中国手机号
    EMAIL_PATTERN = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')  # 邮箱
    IP_PATTERN = re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b')  # IP地址
    COORD_PATTERN = re.compile(r'[-+]?\d{1,3}\.\d{6,}')  # 经纬度坐标
    
    # 常见的"噪音"Tag（可根据实际情况调整）
    NOISY_TAGS = {
        'chatty',  # Android的日志速率限制标记
        'Perflock',  # 性能锁相关
        'QC-QMI',  # 高通底层通信
    }
    
    def __init__(
        self,
        enable_deduplication: bool = True,
        enable_pii_masking: bool = True,
        min_log_level: str = 'I',  # I, W, E, F
        filter_tags: Optional[Set[str]] = None
    ):
        """初始化预处理器
        
        Args:
            enable_deduplication: 是否启用去重
            enable_pii_masking: 是否启用PII脱敏
            min_log_level: 最小日志级别（D<V<I<W<E<F）
            filter_tags: 要过滤的Tag集合
        """
        self.enable_deduplication = enable_deduplication
        self.enable_pii_masking = enable_pii_masking
        self.min_log_level = min_log_level
        self.filter_tags = filter_tags or self.NOISY_TAGS.copy()
        
        # 日志级别优先级
        self.level_priority = {'D': 0, 'V': 1, 'I': 2, 'W': 3, 'E': 4, 'F': 5}
        self.min_priority = self.level_priority.get(min_log_level, 2)
        
        # 统计信息
        self.total_count = 0
        self.filtered_count = 0
        self.deduplicated_count = 0
        self.masked_count = 0
        
        logger.info(f"LogPreprocessor initialized (dedup={enable_deduplication}, "
                   f"pii_mask={enable_pii_masking}, min_level={min_log_level})")
    
    def filter_by_level(self, entry: LogEntry) -> bool:
        """根据日志级别过滤
        
        Args:
            entry: 日志条目
            
        Returns:
            True表示保留，False表示过滤掉
        """
        entry_priority = self.level_priority.get(entry.level, 0)
        return entry_priority >= self.min_priority
    
    def filter_by_tag(self, entry: LogEntry) -> bool:
        """根据Tag过滤噪音日志
        
        Args:
            entry: 日志条目
            
        Returns:
            True表示保留，False表示过滤掉
        """
        return entry.tag not in self.filter_tags
    
    def mask_pii(self, text: str) -> str:
        """脱敏个人信息（PII）
        
        Args:
            text: 原始文本
            
        Returns:
            脱敏后的文本
        """
        if not self.enable_pii_masking:
            return text
        
        masked = text
        
        # 替换手机号
        if self.PHONE_PATTERN.search(masked):
            masked = self.PHONE_PATTERN.sub('[PHONE]', masked)
            self.masked_count += 1
        
        # 替换邮箱
        if self.EMAIL_PATTERN.search(masked):
            masked = self.EMAIL_PATTERN.sub('[EMAIL]', masked)
            self.masked_count += 1
        
        # 替换IP地址
        if self.IP_PATTERN.search(masked):
            masked = self.IP_PATTERN.sub('[IP]', masked)
            self.masked_count += 1
        
        # 替换坐标
        if self.COORD_PATTERN.search(masked):
            masked = self.COORD_PATTERN.sub('[COORD]', masked)
            self.masked_count += 1
        
        return masked
    
    def deduplicate_logs(self, entries: List[LogEntry]) -> List[LogEntry]:
        """去除重复日志
        
        策略：如果连续多条日志的(tag, message)完全相同，只保留第一条和最后一条，
              并在第一条的message中添加"(repeated N times)"标记
        
        Args:
            entries: 日志条目列表
            
        Returns:
            去重后的日志列表
        """
        if not self.enable_deduplication or len(entries) < 2:
            return entries
        
        deduplicated = []
        i = 0
        
        while i < len(entries):
            current = entries[i]
            # 创建去重键（tag + message前100字符）
            dedup_key = (current.tag, current.message[:100])
            
            # 查找连续重复的日志
            repeat_count = 1
            j = i + 1
            while j < len(entries) and j - i < 1000:  # 最多检查1000行
                next_entry = entries[j]
                next_key = (next_entry.tag, next_entry.message[:100])
                
                if next_key == dedup_key:
                    repeat_count += 1
                    j += 1
                else:
                    break
            
            # 如果有重复（超过3次），添加标记
            if repeat_count > 3:
                # 修改第一条的message
                current.message = f"{current.message} (repeated {repeat_count} times)"
                deduplicated.append(current)
                
                # 只保留最后一条
                if j - 1 < len(entries):
                    deduplicated.append(entries[j - 1])
                
                self.deduplicated_count += (repeat_count - 2)
                i = j
            else:
                deduplicated.append(current)
                i += 1
        
        logger.info(f"Deduplication removed {self.deduplicated_count} redundant logs")
        return deduplicated
    
    def annotate_log(self, entry: LogEntry) -> LogEntry:
        """标注日志（添加分类信息）
        
        Args:
            entry: 日志条目
            
        Returns:
            标注后的日志条目
        """
        # 检测是否为崩溃相关
        crash_keywords = ['crash', 'fatal', 'exception', 'sigabrt', 'sigsegv', 'tombstone']
        if any(keyword in entry.message.lower() for keyword in crash_keywords):
            entry.message = f"[CRASH] {entry.message}"
        
        # 检测是否为ANR（Application Not Responding）
        if 'anr' in entry.message.lower() or 'not responding' in entry.message.lower():
            entry.message = f"[ANR] {entry.message}"
        
        # 检测是否为内存相关
        memory_keywords = ['outofmemory', 'oom', 'memory', 'allocation failed']
        if any(keyword in entry.message.lower().replace(' ', '') for keyword in memory_keywords):
            entry.message = f"[MEMORY] {entry.message}"
        
        return entry
    
    def process(self, entries: List[LogEntry]) -> List[LogEntry]:
        """执行完整的预处理流程
        
        Args:
            entries: 原始日志条目列表
            
        Returns:
            预处理后的日志列表
        """
        self.total_count = len(entries)
        logger.info(f"Starting preprocessing {self.total_count} log entries")
        
        # 1. 过滤低级别日志
        filtered = [e for e in entries if self.filter_by_level(e)]
        logger.info(f"After level filtering: {len(filtered)} entries")
        
        # 2. 过滤噪音Tag
        filtered = [e for e in filtered if self.filter_by_tag(e)]
        logger.info(f"After tag filtering: {len(filtered)} entries")
        
        self.filtered_count = self.total_count - len(filtered)
        
        # 3. PII脱敏
        if self.enable_pii_masking:
            for entry in filtered:
                entry.message = self.mask_pii(entry.message)
        
        # 4. 去重
        deduplicated = self.deduplicate_logs(filtered)
        
        # 5. 标注
        annotated = [self.annotate_log(e) for e in deduplicated]
        
        logger.info(f"Preprocessing complete: {len(annotated)} entries remaining")
        return annotated
    
    def get_statistics(self) -> Dict:
        """获取预处理统计信息"""
        return {
            'total_count': self.total_count,
            'filtered_count': self.filtered_count,
            'deduplicated_count': self.deduplicated_count,
            'masked_count': self.masked_count,
            'remaining_count': self.total_count - self.filtered_count - self.deduplicated_count
        }
    
    def analyze_tags(self, entries: List[LogEntry]) -> Dict[str, int]:
        """分析Tag分布
        
        Args:
            entries: 日志列表
            
        Returns:
            Tag频率字典
        """
        tag_counter = Counter(entry.tag for entry in entries)
        return dict(tag_counter.most_common(20))  # 返回Top 20
    
    def analyze_error_distribution(self, entries: List[LogEntry]) -> Dict:
        """分析错误分布
        
        Args:
            entries: 日志列表
            
        Returns:
            错误统计信息
        """
        level_counter = Counter(entry.level for entry in entries)
        
        # 按模块统计错误
        error_entries = [e for e in entries if e.level in ['E', 'F']]
        error_by_tag = Counter(e.tag for e in error_entries)
        
        return {
            'level_distribution': dict(level_counter),
            'total_errors': level_counter.get('E', 0) + level_counter.get('F', 0),
            'top_error_tags': dict(error_by_tag.most_common(10))
        }


def main():
    """测试函数"""
    from src.data_layer.parsers.logcat_parser import LogcatParser
    from pathlib import Path
    
    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent / "tests" / "sample_logs" / "android_logcat_sample.log"
    
    # 解析日志
    parser = LogcatParser()
    entries = parser.parse_file(str(sample_path))
    
    print(f"\n=== 原始日志: {len(entries)} 条 ===")
    
    # 创建预处理器
    preprocessor = LogPreprocessor(
        enable_deduplication=True,
        enable_pii_masking=True,
        min_log_level='I'  # 只保留INFO及以上级别
    )
    
    # 执行预处理
    processed = preprocessor.process(entries)
    
    # 显示统计
    stats = preprocessor.get_statistics()
    print("\n=== 预处理统计 ===")
    print(f"总条数: {stats['total_count']}")
    print(f"过滤掉: {stats['filtered_count']}")
    print(f"去重: {stats['deduplicated_count']}")
    print(f"脱敏: {stats['masked_count']}")
    print(f"保留: {stats['remaining_count']}")
    
    # Tag分布
    tag_dist = preprocessor.analyze_tags(processed)
    print("\n=== Top 10 Tags ===")
    for tag, count in list(tag_dist.items())[:10]:
        print(f"{tag}: {count}")
    
    # 错误分布
    error_dist = preprocessor.analyze_error_distribution(processed)
    print(f"\n=== 错误统计 ===")
    print(f"级别分布: {error_dist['level_distribution']}")
    print(f"总错误数: {error_dist['total_errors']}")
    print(f"错误Top Tags: {error_dist['top_error_tags']}")


if __name__ == "__main__":
    main()

