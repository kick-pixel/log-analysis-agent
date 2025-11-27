"""
时间对齐模块

功能:
1. 统一不同来源日志的时间基准
2. 处理时区差异
3. 计算时间偏移量

注：当前MVP版本主要处理单一日志文件，
    后续版本将支持多文件的时间对齐（如AP侧和MCU侧日志）

作者: Log Analysis Team
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from loguru import logger

from src.data_layer.parsers.logcat_parser import LogEntry


class TimeAligner:
    """时间对齐器
    
    用于处理多个日志文件的时间同步问题
    """
    
    def __init__(self, reference_year: int = 2025):
        """初始化时间对齐器
        
        Args:
            reference_year: 参考年份
        """
        self.reference_year = reference_year
        self.time_offset_map: Dict[str, timedelta] = {}  # 文件名 -> 时间偏移
        
        logger.info(f"TimeAligner initialized (reference_year={reference_year})")
    
    def calculate_offset(
        self,
        entries: List[LogEntry],
        reference_time: Optional[datetime] = None
    ) -> timedelta:
        """计算时间偏移量
        
        Args:
            entries: 日志条目列表
            reference_time: 参考时间点（如GNSS时间）
            
        Returns:
            时间偏移量
        """
        if not entries or not reference_time:
            return timedelta(0)
        
        # 取第一条有效日志的时间
        first_entry = entries[0]
        if first_entry.datetime_obj:
            offset = reference_time - first_entry.datetime_obj
            logger.info(f"Calculated time offset: {offset}")
            return offset
        
        return timedelta(0)
    
    def apply_offset(
        self,
        entries: List[LogEntry],
        offset: timedelta
    ) -> List[LogEntry]:
        """应用时间偏移
        
        Args:
            entries: 日志条目列表
            offset: 时间偏移量
            
        Returns:
            调整后的日志列表
        """
        if offset == timedelta(0):
            return entries
        
        logger.info(f"Applying time offset: {offset} to {len(entries)} entries")
        
        for entry in entries:
            if entry.datetime_obj:
                entry.datetime_obj += offset
                # 更新时间戳字符串
                entry.timestamp = entry.datetime_obj.strftime("%m-%d %H:%M:%S.%f")[:-3]
        
        return entries
    
    def align_multiple_sources(
        self,
        log_sources: Dict[str, List[LogEntry]],
        reference_source: str
    ) -> Dict[str, List[LogEntry]]:
        """对齐多个日志源的时间
        
        Args:
            log_sources: 日志源字典 {源名称: 日志列表}
            reference_source: 作为基准的日志源名称
            
        Returns:
            时间对齐后的日志源字典
        """
        if reference_source not in log_sources:
            logger.warning(f"Reference source '{reference_source}' not found")
            return log_sources
        
        # 获取参考时间（取参考源的第一条日志时间）
        ref_entries = log_sources[reference_source]
        if not ref_entries or not ref_entries[0].datetime_obj:
            logger.warning("Reference source has no valid datetime")
            return log_sources
        
        reference_time = ref_entries[0].datetime_obj
        logger.info(f"Using reference time: {reference_time} from source '{reference_source}'")
        
        # 对齐其他源
        aligned_sources = {}
        for source_name, entries in log_sources.items():
            if source_name == reference_source:
                aligned_sources[source_name] = entries
                continue
            
            # 计算偏移
            offset = self.calculate_offset(entries, reference_time)
            self.time_offset_map[source_name] = offset
            
            # 应用偏移
            aligned_entries = self.apply_offset(entries, offset)
            aligned_sources[source_name] = aligned_entries
        
        logger.info(f"Time alignment complete for {len(log_sources)} sources")
        return aligned_sources
    
    def get_time_range(self, entries: List[LogEntry]) -> Dict:
        """获取日志的时间范围
        
        Args:
            entries: 日志条目列表
            
        Returns:
            包含开始时间、结束时间、时长的字典
        """
        valid_entries = [e for e in entries if e.datetime_obj]
        
        if not valid_entries:
            return {
                'start_time': None,
                'end_time': None,
                'duration': None
            }
        
        start_time = min(e.datetime_obj for e in valid_entries)
        end_time = max(e.datetime_obj for e in valid_entries)
        duration = end_time - start_time
        
        return {
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'duration': str(duration),
            'duration_seconds': duration.total_seconds()
        }
    
    def merge_and_sort(
        self,
        log_sources: Dict[str, List[LogEntry]]
    ) -> List[LogEntry]:
        """合并多个日志源并按时间排序
        
        Args:
            log_sources: 日志源字典
            
        Returns:
            合并且排序后的日志列表
        """
        merged = []
        for source_name, entries in log_sources.items():
            # 为每条日志添加源标识
            for entry in entries:
                entry.tag = f"[{source_name}]{entry.tag}"
            merged.extend(entries)
        
        # 按时间排序
        merged.sort(key=lambda e: e.datetime_obj if e.datetime_obj else datetime.min)
        
        logger.info(f"Merged {len(merged)} entries from {len(log_sources)} sources")
        return merged


def main():
    """测试函数"""
    from src.data_layer.parsers.logcat_parser import LogcatParser
    from pathlib import Path
    
    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent / "tests" / "sample_logs" / "android_logcat_sample.log"
    
    # 解析日志
    parser = LogcatParser()
    entries = parser.parse_file(str(sample_path))
    
    # 创建时间对齐器
    aligner = TimeAligner()
    
    # 获取时间范围
    time_range = aligner.get_time_range(entries)
    print("\n=== 日志时间范围 ===")
    print(f"开始时间: {time_range['start_time']}")
    print(f"结束时间: {time_range['end_time']}")
    print(f"时长: {time_range['duration']}")
    print(f"总秒数: {time_range['duration_seconds']:.2f}秒")
    
    # 模拟多源对齐（实际使用时会有多个不同的日志文件）
    log_sources = {
        'main_logcat': entries[:len(entries)//2],
        'secondary_logcat': entries[len(entries)//2:]
    }
    
    print(f"\n=== 多源对齐测试 ===")
    print(f"源1: {len(log_sources['main_logcat'])} 条")
    print(f"源2: {len(log_sources['secondary_logcat'])} 条")
    
    # 执行对齐
    aligned = aligner.align_multiple_sources(log_sources, 'main_logcat')
    
    # 合并排序
    merged = aligner.merge_and_sort(aligned)
    print(f"合并后总计: {len(merged)} 条")
    
    # 显示前5条
    print("\n=== 合并后的前5条日志 ===")
    for entry in merged[:5]:
        print(f"[{entry.timestamp}] {entry.tag}: {entry.message[:60]}")


if __name__ == "__main__":
    main()

