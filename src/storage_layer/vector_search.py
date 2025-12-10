"""
向量语义检索引擎 (基于ChromaDB)

功能:
1. 将日志转换为语义向量
2. 支持模糊语义搜索
3. 补充关键词搜索（当用户描述不精确时）
4. 知识库相似度匹配

作者: Log Analysis Team
"""

import chromadb
from chromadb.config import Settings
from typing import List, Dict, Optional
from pathlib import Path
from loguru import logger
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from src.data_layer.parsers.logcat_parser import LogEntry


class VectorSearchEngine:
    """基于ChromaDB的向量语义检索引擎
    
    使用Embedding模型将日志转换为向量，支持语义相似度搜索
    """
    
    def __init__(
        self,
        db_path: str = "./data/chroma_db",
        collection_name: str = "log_embeddings"
    ):
        """初始化向量搜索引擎
        
        Args:
            db_path: ChromaDB数据库路径
            collection_name: 集合名称
        """
        self.db_path = db_path
        self.collection_name = collection_name
        
        # 确保数据目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        try:
            # 创建ChromaDB客户端（使用新API）
            self.client = chromadb.PersistentClient(path=db_path)
            
            # 获取或创建集合
            # 使用默认的sentence-transformers embedding模型
            # HNSW参数优化：提升查询和写入性能
            self.collection = self.client.get_or_create_collection(
                name=collection_name,
                metadata={
                    "description": "Log embeddings for semantic search",
                    "hnsw:space": "cosine",  # 使用余弦相似度
                    "hnsw:construction_ef": 100,  # 构建时的ef参数（平衡性能和质量）
                    "hnsw:M": 16  # HNSW图的连接数（越大越精确但越慢）
                }
            )
            
            logger.info(f"VectorSearchEngine initialized (db={db_path}, collection={collection_name})")
            logger.info(f"Collection currently has {self.collection.count()} documents")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise
    
    def _create_document(self, entry: LogEntry) -> str:
        """将日志条目转换为文档字符串
        
        Args:
            entry: 日志条目
            
        Returns:
            用于embedding的文档字符串
        """
        # 组合Tag和Message作为文档内容
        # 这样可以同时考虑模块和具体内容的语义
        return f"{entry.tag}: {entry.message}"
    
    def _create_metadata(self, entry: LogEntry, session_id: str) -> Dict:
        """创建元数据字典
        
        Args:
            entry: 日志条目
            session_id: 会话ID
            
        Returns:
            元数据字典
        """
        return {
            'timestamp': entry.timestamp,
            'datetime': entry.datetime_obj.isoformat() if entry.datetime_obj else None,
            'level': entry.level,
            'tag': entry.tag,
            'line_number': entry.line_number,
            'session_id': session_id
        }
    
    def insert_logs(
        self,
        entries: List[LogEntry],
        session_id: str = "default",
        batch_size: int = 2000
    ) -> int:
        """批量插入日志（转换为向量）- 优化版
        
        性能优化策略：
        1. ✅ 增大batch_size到2000（减少批次数和API调用）
        2. ✅ 添加详细的进度显示和性能监控
        3. ⚠️  瓶颈在embedding生成（sentence-transformers模型）
        
        性能说明：
        - 38000条日志预计耗时：5-10分钟（取决于CPU性能）
        - 主要时间消耗在embedding模型计算向量（每批约需要60-70秒）
        - 如需更快速度，建议考虑：
          a) 使用更快的embedding模型（如OpenAI API）
          b) 使用GPU加速
          c) 减少需要索引的日志数量（只索引ERROR/WARN级别）
        
        Args:
            entries: 日志条目列表
            session_id: 会话ID
            batch_size: 批处理大小（默认2000，建议1000-5000）
            
        Returns:
            插入的日志条数
        """
        if not entries:
            logger.warning("No entries to insert")
            return 0
        
        start_time = time.time()
        total_batches = (len(entries) + batch_size - 1) // batch_size
        
        logger.info(f"")
        logger.info(f"{'='*70}")
        logger.info(f"⚡ 开始插入日志到向量数据库")
        logger.info(f"{'='*70}")
        logger.info(f"📊 总条数: {len(entries):,} 条")
        logger.info(f"📦 批次配置: batch_size={batch_size:,}, total_batches={total_batches}")
        logger.info(f"⏱️  预计耗时: {total_batches * 60 / 60:.1f}-{total_batches * 70 / 60:.1f} 分钟")
        logger.info(f"{'='*70}")
        
        # 准备数据（预处理阶段）
        prep_start = time.time()
        documents = []
        metadatas = []
        ids = []
        
        for i, entry in enumerate(entries):
            # 创建文档
            doc = self._create_document(entry)
            documents.append(doc)
            
            # 创建元数据
            metadata = self._create_metadata(entry, session_id)
            metadatas.append(metadata)
            
            # 创建唯一ID（session_id + line_number）
            doc_id = f"{session_id}_{entry.line_number}"
            ids.append(doc_id)
        
        prep_time = time.time() - prep_start
        logger.info(f"✅ 数据预处理完成: {prep_time:.2f}s")
        logger.info(f"")
        
        # 分批插入（串行处理，因为embedding生成是瓶颈）
        total_inserted = 0
        failed_batches = []
        
        insert_start = time.time()
        
        for i in range(0, len(documents), batch_size):
            batch_num = i // batch_size + 1
            batch_docs = documents[i:i + batch_size]
            batch_meta = metadatas[i:i + batch_size]
            batch_ids = ids[i:i + batch_size]
            
            batch_start = time.time()
            
            try:
                self.collection.add(
                    documents=batch_docs,
                    metadatas=batch_meta,
                    ids=batch_ids
                )
                
                batch_time = time.time() - batch_start
                total_inserted += len(batch_docs)
                
                # 计算进度和预估剩余时间
                progress = (batch_num / total_batches) * 100
                avg_time_per_batch = (time.time() - insert_start) / batch_num
                remaining_batches = total_batches - batch_num
                eta_seconds = remaining_batches * avg_time_per_batch
                eta_minutes = eta_seconds / 60
                
                logger.info(
                    f"✅ Batch {batch_num}/{total_batches} | "
                    f"{len(batch_docs):,} 条 | "
                    f"耗时 {batch_time:.1f}s | "
                    f"速度 {len(batch_docs)/batch_time:.1f} 条/s | "
                    f"进度 {progress:.1f}% | "
                    f"预计剩余 {eta_minutes:.1f}min"
                )
                
            except Exception as e:
                logger.error(f"❌ Batch {batch_num} 插入失败: {e}")
                failed_batches.append((batch_num, str(e)))
        
        insert_time = time.time() - insert_start
        total_time = time.time() - start_time
        
        # 统计信息
        logger.info(f"")
        logger.info(f"{'='*70}")
        logger.info(f"✨ 插入完成统计")
        logger.info(f"{'='*70}")
        logger.info(f"📥 总条数: {len(entries):,} 条")
        logger.info(f"✅ 成功插入: {total_inserted:,} 条 ({total_inserted/len(entries)*100:.1f}%)")
        logger.info(f"❌ 失败批次: {len(failed_batches)} 个")
        logger.info(f"⏱️  总耗时: {total_time:.2f}s ({total_time/60:.2f} 分钟)")
        logger.info(f"   - 数据预处理: {prep_time:.2f}s ({prep_time/total_time*100:.1f}%)")
        logger.info(f"   - Embedding生成+插入: {insert_time:.2f}s ({insert_time/total_time*100:.1f}%)")
        logger.info(f"🚀 平均速度: {total_inserted/total_time:.1f} 条/秒")
        logger.info(f"{'='*70}")
        
        if failed_batches:
            logger.warning(f"以下批次插入失败:")
            for batch_num, error in failed_batches:
                logger.warning(f"  - Batch {batch_num}: {error}")
        
        return total_inserted
    
    def semantic_search(
        self,
        query: str,
        n_results: int = 10,
        level: Optional[str] = None,
        session_id: Optional[str] = None
    ) -> List[Dict]:
        """语义搜索
        
        Args:
            query: 查询字符串（自然语言描述）
            n_results: 返回结果数量
            level: 日志级别过滤 (可选)
            session_id: 会话ID过滤 (可选)
            
        Returns:
            匹配的日志列表（按相似度排序）
        """
        # 构建过滤条件
        where = {}
        if level:
            where['level'] = level
        if session_id:
            where['session_id'] = session_id
        
        try:
            # 执行查询
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where if where else None
            )
            
            # 解析结果
            matched_logs = []
            if results and results['ids'] and len(results['ids']) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    log_data = {
                        'id': doc_id,
                        'document': results['documents'][0][i],
                        'metadata': results['metadatas'][0][i],
                        'distance': results['distances'][0][i] if 'distances' in results else None
                    }
                    matched_logs.append(log_data)
            
            print(f"DEBUG: Semantic search for '{query}' returned {len(matched_logs)} results")
            return matched_logs
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
    
    def find_similar_logs(
        self,
        reference_log_id: str,
        n_results: int = 5
    ) -> List[Dict]:
        """查找相似的日志
        
        Args:
            reference_log_id: 参考日志的ID
            n_results: 返回结果数量
            
        Returns:
            相似日志列表
        """
        try:
            # 获取参考日志
            ref_result = self.collection.get(ids=[reference_log_id])
            
            if not ref_result or not ref_result['documents']:
                logger.warning(f"Reference log {reference_log_id} not found")
                return []
            
            ref_document = ref_result['documents'][0]
            
            # 搜索相似日志
            results = self.collection.query(
                query_texts=[ref_document],
                n_results=n_results + 1  # +1 因为会包含自己
            )
            
            # 解析结果（排除自己）
            similar_logs = []
            if results and results['ids'] and len(results['ids']) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    if doc_id != reference_log_id:  # 排除自己
                        log_data = {
                            'id': doc_id,
                            'document': results['documents'][0][i],
                            'metadata': results['metadatas'][0][i],
                            'distance': results['distances'][0][i] if 'distances' in results else None
                        }
                        similar_logs.append(log_data)
            
            logger.info(f"Found {len(similar_logs)} similar logs for {reference_log_id}")
            return similar_logs[:n_results]  # 限制返回数量
            
        except Exception as e:
            logger.error(f"Find similar logs failed: {e}")
            return []
    
    def get_statistics(self) -> Dict:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        try:
            total_count = self.collection.count()
            
            # 获取所有元数据进行统计
            all_data = self.collection.get()
            
            # 统计各级别
            level_dist = {}
            session_dist = {}
            
            if all_data and all_data['metadatas']:
                for metadata in all_data['metadatas']:
                    level = metadata.get('level', 'Unknown')
                    level_dist[level] = level_dist.get(level, 0) + 1
                    
                    session = metadata.get('session_id', 'Unknown')
                    session_dist[session] = session_dist.get(session, 0) + 1
            
            return {
                'total_documents': total_count,
                'level_distribution': level_dist,
                'session_distribution': session_dist
            }
            
        except Exception as e:
            logger.error(f"Get statistics failed: {e}")
            return {
                'total_documents': 0,
                'level_distribution': {},
                'session_distribution': {}
            }
    
    def clear_session(self, session_id: str):
        """清除指定会话的向量
        
        Args:
            session_id: 会话ID
        """
        try:
            # 获取该session的所有ID
            results = self.collection.get(
                where={'session_id': session_id}
            )
            
            if results and results['ids']:
                self.collection.delete(ids=results['ids'])
                logger.info(f"Cleared {len(results['ids'])} vectors for session: {session_id}")
            else:
                logger.info(f"No vectors found for session: {session_id}")
                
        except Exception as e:
            logger.error(f"Clear session failed: {e}")
    
    def reset(self):
        """重置整个集合（谨慎使用）"""
        try:
            self.client.delete_collection(self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Log embeddings for semantic search"}
            )
            logger.warning("Vector database has been reset")
        except Exception as e:
            logger.error(f"Reset failed: {e}")


def main():
    """测试函数"""
    from src.data_layer.parsers.logcat_parser import LogcatParser
    from pathlib import Path
    
    # 测试样本路径
    sample_path = Path(__file__).parent.parent.parent / "tests" / "sample_logs" / "android_logcat_sample.log"
    
    # 解析日志
    parser = LogcatParser()
    entries = parser.parse_file(str(sample_path))
    
    print(f"\n解析了 {len(entries)} 条日志")
    
    # 创建向量搜索引擎
    vector_engine = VectorSearchEngine(db_path="./data/test_chroma_db")
    
    # 清除旧数据
    vector_engine.clear_session("test_session")
    
    # 插入日志
    print("\n正在插入日志并生成向量...")
    inserted = vector_engine.insert_logs(entries, session_id="test_session")
    print(f"插入了 {inserted} 条日志")
    
    # 获取统计信息
    stats = vector_engine.get_statistics()
    print("\n=== 向量数据库统计 ===")
    print(f"总文档数: {stats['total_documents']}")
    print(f"级别分布: {stats['level_distribution']}")
    print(f"会话分布: {stats['session_distribution']}")
    
    # 语义搜索：查找内存相关问题
    print("\n=== 语义搜索: '内存不足导致崩溃' ===")
    memory_results = vector_engine.semantic_search(
        query="memory allocation failure crash",
        n_results=5
    )
    for i, result in enumerate(memory_results, 1):
        print(f"{i}. [{result['metadata']['timestamp']}] {result['metadata']['level']}/{result['metadata']['tag']}")
        print(f"   {result['document'][:100]}")
        if result['distance']:
            print(f"   相似度距离: {result['distance']:.4f}")
    
    # 语义搜索：查找相机相关问题
    print("\n=== 语义搜索: '相机启动失败' ===")
    camera_results = vector_engine.semantic_search(
        query="camera failed to start unable to open",
        n_results=5
    )
    for i, result in enumerate(camera_results, 1):
        print(f"{i}. [{result['metadata']['timestamp']}] {result['metadata']['level']}/{result['metadata']['tag']}")
        print(f"   {result['document'][:100]}")
        if result['distance']:
            print(f"   相似度距离: {result['distance']:.4f}")
    
    # 查找相似日志
    if camera_results:
        first_id = camera_results[0]['id']
        print(f"\n=== 查找与第一条相机日志相似的日志 ===")
        similar_results = vector_engine.find_similar_logs(first_id, n_results=3)
        for i, result in enumerate(similar_results, 1):
            print(f"{i}. [{result['metadata']['timestamp']}] {result['metadata']['level']}/{result['metadata']['tag']}")
            print(f"   {result['document'][:100]}")
            if result['distance']:
                print(f"   相似度距离: {result['distance']:.4f}")


if __name__ == "__main__":
    main()

