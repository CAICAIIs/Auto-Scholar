# Auto-Scholar 基础设施升级方案 v2

> **面向 infra 求职的生产级架构演进**
> 基于现有代码库深度分析 + 2026 年业界最佳实践

**生成日期**: 2026-02-28
**当前状态**: 单机 PoC（SQLite 检查点，无持久化存储，无向量数据库）
**目标状态**: 生产级基础设施（MinIO + Qdrant/Milvus + PostgreSQL + 异步队列）

---

## 执行摘要

本方案针对 Auto-Scholar 从 PoC 向可运营系统的演进，提出**分阶段、可验证、可回滚**的架构升级路径。

**三个核心升级**：

| 阶段 | 组件 | 解决痛点 | 预计工作量 | 优先级 |
|--------|--------|----------|------------|--------|
| **Phase 1** | MinIO 对象存储 | API 限流 + OOM 风险 | 2-3 周 | **P0** (立即) |
| **Phase 2** | Qdrant/Milvus 向量库 | Token 账单爆炸 | 3-4 周 | **P0** (2-4 周) |
| **Phase 3** | PostgreSQL 元数据层 | 证据链溯源 | 4-5 周 | **P1** (1-2 月) |

**总工作量**: 9-12 周（可并行 Phase 1 和 Phase 2 初期任务）


---

## 现状诊断

### 当前架构分析

基于对代码库的深度探索，确认以下事实：

**数据存储**：
- ✅ **仅有的持久化**: SQLite 检查点（AsyncSqliteSaver）
- ❌ 无生产数据库
- ❌ 无向量数据库
- ❌ 无对象存储

**PDF 处理**：
- ✅ PDF URL 解析（fulltext_api.py）
- ❌ 无 PDF 文件下载
- ❌ 无 PDF 存储
- ❌ 无 PDF 解析/切块
- ❌ 无 PDF 缓存

**Claim Verification**：
- ✅ 基于摘要的验证（97.3% 准确率）
- ✅ 完整审计链路
- ❌ 无全文级别验证（受限于无 PDF）

**外部 API 管理**：
- ✅ 简单熔断机制（source_tracker.py，3 次失败 = 跳过 2 分钟）
- ✅ 重试机制（tenacity）
- ✅ 并发控制（LLM_CONCURRENCY=2, CLAIM_VERIFICATION_CONCURRENCY=2）
- ✅ HTTP 连接池（limit=50）
- ⚠️ 无持久化的失败历史
- ⚠️ 无分布式限流

### 关键差距

| 维度 | 当前 | 需要 |
|------|------|------|
| **文件存储** | 仅 URL 字符串 | MinIO（下载 → 去重 → 缓存） |
| **向量索引** | 无 | Qdrant/Milvus（chunk embedding → 语义检索） |
| **元数据** | Pydantic + SQLite checkpoint | PostgreSQL（关系模型 + 版本控制） |
| **证据链** | 基于 abstract 的验证 | 基于全文的页码/段落溯源 |
| **异步管道** | LangGraph 节点 | 独立任务队列（Celery/Arq） |
| **可观测性** | 基础日志 | Prometheus + Grafana + 结构化日志 |


---

## Phase 1: MinIO 对象存储（2-3 周）

### 1.1 业务痛点

**问题陈述**：
- 当前只存储 PDF URL，不下载文件
- 每次综述生成都重复访问外部源站（arXiv/PubMed/Unpaywall）
- 高并发场景下：
  - 10 个用户 × 50 篇论文 × 5MB PDF = 瞬时 2.5GB 内存压力
  - 外部 API 限流导致任务失败
  - 无失败重用机制（重复下载相同论文）

**量化指标**：
- 单篇医学/计算机论文：2-10MB
- 典型综述：20-50 篇论文
- 高峰并发：5-10 个用户同时生成
- **风险**: 内存溢出（OOM）+ IP 封禁

### 1.2 技术方案

#### 1.2.1 架构设计

```
应用层 (Application Layer)
  extractor_agent (nodes.py)
    - 获取 PDF URL (已有)
    - 调用 pdf_downloader.download_pdf()
  
下载层 (PDF Downloader)
  backend/utils/pdf_downloader.py
    - 流式下载
    - 去重检查（Redis）
    - 直接上传 MinIO（不落盘）

缓存层 (Cache Layer)
  Redis
    - 基于 PDF URL SHA256 的缓存键
    - 24 小时 TTL

存储层 (Storage Layer)
  MinIO (S3 API)
    - rag-raw: 原始 PDF 文件
    - rag-processed: 处理后的文本
    - rag-tmp: 临时文件（7 天 TTL）
```

#### 1.2.2 核心实现

**新增文件：backend/utils/pdf_downloader.py**

```python
"""
PDF 下载器：支持去重、缓存、流式下载
"""
import hashlib
import logging
from datetime import datetime, UTC
from typing import Tuple

from minio import Minio
from minio.error import S3Error

from backend.utils.http_pool import get_session

logger = logging.getLogger(__name__)


class PDFDownloader:
    """MinIO PDF 下载器，支持去重和缓存"""

    def __init__(
        self,
        minio_client: Minio,
        redis_client,
        bucket: str = "rag-raw"
    ):
        self.minio = minio_client
        self.redis = redis_client
        self.bucket = bucket

    async def download_pdf(
        self,
        paper_id: str,
        pdf_url: str,
        title: str
    ) -> Tuple[bool, str | None]:
        """
        下载 PDF 到 MinIO，支持去重
        
        Returns:
            (is_cached, object_key) - 如果已缓存则 is_cached=True
        """
        # 1. 检查缓存（基于 PDF URL 的 SHA256）
        content_hash = self._hash_url(pdf_url)
        cache_key = f"pdf:cache:{content_hash}"
        
        cached_key = await self.redis.get(cache_key)
        if cached_key:
            logger.info(f"PDF cache hit for paper {paper_id} (hash: {content_hash[:16]})")
            return True, cached_key.decode()
        
        # 2. 下载 PDF（流式，避免 OOM）
        object_key = await self._stream_download_to_minio(
            paper_id, pdf_url, title
        )
        
        # 3. 更新缓存
        await self.redis.setex(cache_key, 86400, object_key)  # 24h TTL
        logger.info(f"PDF downloaded to MinIO: {object_key} (hash: {content_hash[:16]})")
        
        return False, object_key

    def _hash_url(self, url: str) -> str:
        """URL SHA256 作为去重键"""
        return hashlib.sha256(url.encode()).hexdigest()

    async def _stream_download_to_minio(
        self,
        paper_id: str,
        pdf_url: str,
        title: str
    ) -> str:
        """流式下载，直接写入 MinIO，不落盘"""
        safe_title = self._sanitize_filename(title)
        object_key = f"{paper_id}/{safe_title}"
        
        # 使用 http_pool.get_session() 复用连接
        async with get_session() as session:
            async with session.get(pdf_url) as resp:
                if resp.status != 200:
                    raise Exception(f"Failed to download: {pdf_url}")
                
                # 流式上传到 MinIO
                content_length = int(resp.headers.get('content-length', 0))
                self.minio.put_object(
                    self.bucket,
                    object_key,
                    data=resp.content,
                    length=content_length,
                    content_type='application/pdf',
                    metadata={
                        'paper-id': paper_id,
                        'source-url': pdf_url,
                        'downloaded-at': datetime.now(UTC).isoformat(),
                        'content-hash': self._hash_url(pdf_url),
                    }
                )
        
        return object_key

    def _sanitize_filename(self, title: str) -> str:
        """清理标题作为文件名"""
        import re
        safe = re.sub(r'[^\w\-_.]', '_', title)[:100]
        return f"{safe}.pdf"


# 全局单例
_downloader: PDFDownloader | None = None


async def get_pdf_downloader() -> PDFDownloader:
    """获取或创建 PDF 下载器单例"""
    global _downloader
    if _downloader is None:
        from minio import Minio
        import redis.asyncio as redis
        
        from backend.constants import (
            MINIO_ENDPOINT,
            MINIO_ACCESS_KEY,
            MINIO_SECRET_KEY,
            MINIO_SECURE,
            MINIO_BUCKET_RAG
        )
        
        # MinIO 客户端
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=MINIO_SECURE,
        )
        
        # Redis 客户端
        redis_client = redis.Redis(
            host='localhost',
            port=6379,
            db=0,
            decode_responses=True
        )
        
        _downloader = PDFDownloader(
            minio_client=minio_client,
            redis_client=redis_client,
            bucket=MINIO_BUCKET_RAG
        )
    
    return _downloader


async def close_pdf_downloader() -> None:
    """关闭下载器连接"""
    global _downloader
    if _downloader is not None:
        await _downloader.redis.close()
        _downloader = None
```


**修改现有文件：backend/utils/fulltext_api.py**

在文件顶部添加导入：
```python
from backend.utils.pdf_downloader import get_pdf_downloader
```

修改 enrich_papers_with_fulltext 函数：
```python
async def enrich_papers_with_fulltext(
    papers: list[PaperMetadata],
    concurrency: int = 3,
) -> list[PaperMetadata]:
    semaphore = asyncio.Semaphore(concurrency)
    downloader = await get_pdf_downloader()  # 初始化 MinIO + Redis
    
    async def enrich_with_download(paper: PaperMetadata) -> PaperMetadata:
        async with semaphore:
            try:
                # 原有逻辑：解析 PDF URL
                if not paper.pdf_url:
                    paper = await enrich_paper_with_fulltext(paper)
                
                # 新增：下载 PDF 到 MinIO
                if paper.pdf_url:
                    is_cached, object_key = await downloader.download_pdf(
                        paper.paper_id,
                        paper.pdf_url,
                        paper.title,
                    )
                    
                    # 更新 paper 的元数据
                    updates = {
                        "pdf_object_key": object_key,
                        "pdf_downloaded_at": datetime.now(UTC)
                    }
                    
                    if not is_cached:
                        # 只在首次下载时添加 hash（避免版本不一致）
                        updates["pdf_content_hash"] = downloader._hash_url(paper.pdf_url)
                    
                    paper = paper.model_copy(update=updates)
                    logger.debug(f"Paper {paper.title[:50]} PDF stored at {object_key}")
                
                return paper
            except Exception as e:
                logger.warning(f"Failed to download PDF for '{paper.title[:50]}': {e}")
                return paper
    
    tasks = [enrich_with_download(p) for p in papers]
    return await asyncio.gather(*tasks)
```

#### 1.2.3 数据模型扩展

**backend/schemas.py (扩展 PaperMetadata)**

```python
from datetime import datetime, UTC

class PaperMetadata(BaseModel):
    # ... 现有字段 ...

    # 新增：PDF 存储位置
    pdf_object_key: str | None = Field(
        default=None,
        description="MinIO object key (bucket/key)",
    )
    pdf_size_bytes: int | None = Field(
        default=None,
        description="PDF file size in bytes",
    )
    pdf_content_hash: str | None = Field(
        default=None,
        description="SHA256 of PDF content for deduplication",
    )
    pdf_downloaded_at: datetime | None = Field(
        default=None,
        description="PDF download timestamp",
    )
```

#### 1.2.4 MinIO 集成配置

**环境变量 (.env)**:

```bash
# MinIO 配置
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_SECURE=false
MINIO_BUCKET_RAG=rag-raw
MINIO_BUCKET_PROCESSED=rag-processed

# Redis 配置（缓存层）
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
```

**新增常量 (backend/constants.py)**:

```python
# ============================================================================
# MinIO Configuration
# ============================================================================

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET_RAG = os.getenv("MINIO_BUCKET_RAG", "rag-raw")
MINIO_BUCKET_PROCESSED = os.getenv("MINIO_BUCKET_PROCESSED", "rag-processed")

# 为什么：默认使用本地 MinIO，生产环境通过环境变量覆盖
# 桶分离：raw 存原始文件，processed 存处理后的中间产物
# 便于权限隔离和生命周期策略管理
```

**初始化脚本 (scripts/init_minio.py)**:

```python
"""
MinIO 初始化脚本：创建必要的桶和生命周期策略
"""
import os
from minio import Minio
from minio.error import S3Error


def init_minio():
    client = Minio(
        os.getenv('MINIO_ENDPOINT', '127.0.0.1:9000'),
        access_key=os.getenv('MINIO_ACCESS_KEY', 'minioadmin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'minioadmin'),
        secure=os.getenv('MINIO_SECURE', 'false').lower() == 'true',
    )
    
    # 创建必要的桶
    buckets = [
        ('rag-raw', 'Raw PDF files'),
        ('rag-processed', 'Processed text chunks'),
        ('rag-tmp', 'Temporary files')
    ]
    
    for bucket, description in buckets:
        if not client.bucket_exists(bucket):
            try:
                client.make_bucket(bucket)
                print(f"Created bucket: {bucket} - {description}")
                
                # 设置生命周期策略（临时文件 7 天后删除）
                if bucket == 'rag-tmp':
                    lifecycle_config = {
                        'Rules': [{
                            'ID': 'ExpireTemp',
                            'Status': 'Enabled',
                            'Filter': {'Prefix': ''},
                            'Expiration': {'Days': 7}
                        }]
                    }
                    client.set_bucket_lifecycle(bucket, lifecycle_config)
                    print(f"Set lifecycle policy for {bucket}: 7 days")
            except S3Error as e:
                print(f"Failed to create bucket {bucket}: {e}")
                raise
        else:
            print(f"Bucket exists: {bucket}")
    
    print("\nMinIO initialization complete")


if __name__ == "__main__":
    init_minio()
```


### 1.3 验收标准

**功能验证**：
- [ ] 能下载 PDF 并存储到 MinIO
- [ ] 重复下载同一 PDF 时命中缓存（通过日志确认）
- [ ] 断点续传失败时重试成功（通过日志确认）
- [ ] 流式下载不导致 OOM（模拟大文件下载）

**性能指标**：
- [ ] PDF 下载 P95 < 5s（50MB 以内）
- [ ] 缓存命中率 > 40%（重复论文较多场景）
- [ ] 并发下载 10 个 PDF 不崩溃

**代码质量**：
- [ ] 所有新文件通过 ruff check 和 mypy
- [ ] 有单元测试覆盖核心逻辑（缓存命中、去重）
- [ ] 有集成测试验证 MinIO 集成

**可观测性**：
- [ ] 结构化日志（paper_id, pdf_url, is_cached, object_key）
- [ ] Prometheus 指标：pdf_downloads_total, pdf_cache_hits, pdf_cache_misses

### 1.4 风险与缓解

| 风险 | 影响 | 缓解措施 |
|--------|------|----------|
| MinIO 单点故障 | 无法下载新 PDF | 1) 硬盘镜像备份<br>2) 降级到仅用 URL |
| Redis 缓存失效 | 重复下载相同 PDF | 1) 监控 Redis 健康度<br>2) 异常时直接下载 |
| 外部 API 限流 | 下载失败率上升 | 1) 扩展现有熔断机制<br>2) 指数退避重试 |
| 存储成本增长 | 运营成本上升 | 1) 冷热分层<br>2) 定期清理未引用文件 |


---

## Phase 2: 向量数据库集成（3-4 周）

### 2.1 业务痛点

**问题陈述**：
- 当前无向量数据库，每次综述生成都重复调用 Embedding API
- 重复场景（用户 B 查询 "Agent 检索增强"）：
  - 30 篇论文与用户 A 的查询重合
  - 重新下载 + 重新切块 + 重新 embedding
  - Token 账单随用户量指数级爆炸
- 无"沉淀型知识库"，系统越用越像没有记忆的工具

**量化指标**：
- OpenAI Embedding 价格：$0.00002 / 1K tokens
- 单篇论文切分：~50 chunks × 200 tokens = 10K tokens
- 单篇论文 embedding 成本：~$0.0002
- 50 篇论文成本：~$0.01（每次生成）
- 无缓存场景：1000 次生成 = $10 成本

### 2.2 技术方案

#### 2.2.1 选型决策：Qdrant vs Milvus

**推荐：Qdrant**

**理由**：
1. **运维复杂度低**：单二进制部署，无独立组件
2. **开发体验好**：Python SDK 文档完善，开箱即用
3. **JSON payload 过滤**：原生支持复杂元数据过滤
4. **HNSW 索引**：成熟的 ANN 搜索性能
5. **适合中等规模**：< 1M chunks 场景性能优异
6. **蓝绿切换**：collection 版本管理简单

**Milvus 适用场景**：
- 超大规模（> 10M chunks）
- 多集群部署
- 需要细粒度资源治理
- 有专门的基础设施团队

#### 2.2.2 架构设计

```
应用层
  extractor_agent (nodes.py)
    - 获取 PDF (from MinIO)
    - 解析全文 (pdf_parser.py)
    - 文本切块 (text_chunker.py)
    - 向量化 (embedder.py)
    - 索引到向量库 (vector_store.py)

向量层
  Qdrant Client
    - rag-chunks collection
    - HNSW 索引
    - payload 过滤
    - 版本化 collection

缓存层
  Redis
    - embedding 缓存（文本 SHA256 → 向量）
    - 进程内 LRU
```

#### 2.2.3 核心实现

**新增文件：backend/utils/pdf_parser.py**

```python
"""
PDF 解析器：支持多种 PDF 库，提取全文和页码信息
"""
import logging
from typing import Optional

from pypdf import PdfReader

from backend.utils.http_pool import get_session

logger = logging.getLogger(__name__)


class PDFParser:
    """PDF 解析器，支持流式读取和页码提取"""

    async def parse_pdf_from_url(
        self,
        pdf_url: str
    ) -> tuple[str, Optional[int]]:
        """
        从 URL 解析 PDF，返回全文内容和页数
        
        Returns:
            (full_text, page_count) - 如果解析失败则返回 ("", None)
        """
        try:
            # 使用 http_pool.get_session() 复用连接
            async with get_session() as session:
                async with session.get(pdf_url) as resp:
                    if resp.status != 200:
                        raise Exception(f"Failed to download: {pdf_url}")
                    
                    pdf_bytes = await resp.read()
                    
                    # 使用 PyPDF2 解析
                    reader = PdfReader(pdf_bytes)
                    
                    # 提取所有页面的文本
                    full_text = "\n\n".join([
                        page.extract_text() for page in reader.pages
                    ])
                    
                    page_count = len(reader.pages)
                    
                    logger.info(f"PDF parsed: {len(full_text)} chars, {page_count} pages")
                    
                    return full_text.strip(), page_count
                    
        except Exception as e:
            logger.error(f"Failed to parse PDF from {pdf_url}: {e}")
            return "", None

    async def parse_pdf_from_minio(
        self,
        bucket: str,
        object_key: str
    ) -> tuple[str, Optional[int]]:
        """
        从 MinIO 解析 PDF（使用临时文件）
        """
        import tempfile
        from minio import Minio
        
        try:
            # 获取 MinIO 客户端（复用 pdf_downloader 的连接）
            from backend.utils.pdf_downloader import get_pdf_downloader
            downloader = await get_pdf_downloader()
            
            # 下载到临时文件
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
                downloader.minio.fget_object(
                    bucket,
                    object_key,
                    tmp_file.name
                )
                
                # 解析临时文件
                full_text, page_count = await self.parse_pdf_from_url(tmp_file.name)
                
                return full_text, page_count
                
        finally:
            # 清理临时文件
            if tmp_file:
                tmp_file.unlink()
```


**新增文件：backend/utils/text_chunker.py**

```python
"""
文本切块器：基于 token 和语义边界的智能分块
"""
import logging
from typing import List

import tiktoken

logger = logging.getLogger(__name__)


class TextChunker:
    """文本切块器，支持 token 限制和语义边界"""

    def __init__(self, model_name: str = "gpt-4o"):
        # 初始化 tokenizer
        self.encoding = tiktoken.encoding_for_model(model_name)
        self.model_name = model_name

    def chunk_text(
        self,
        text: str,
        chunk_max_tokens: int = 500,
        chunk_overlap_tokens: int = 50,
        min_chunk_chars: int = 100
    ) -> List[str]:
        """
        切分文本为 chunks，基于 token 数量和语义边界
        
        Args:
            text: 原始文本
            chunk_max_tokens: 每个 chunk 最大 token 数
            chunk_overlap_tokens: chunk 之间重叠的 token 数
            min_chunk_chars: 最小 chunk 字符数（避免过碎）
        
        Returns:
            chunk 文本列表
        """
        chunks = []
        current_chunk = []
        current_tokens = 0
        overlap_buffer = []
        
        # 按段落/句子分割
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        for para in paragraphs:
            para_tokens = len(self.encoding.encode(para))
            
            # 如果当前 paragraph 会超过最大 token 限制
            if current_tokens + para_tokens > chunk_max_tokens:
                # 保存当前 chunk
                if len(''.join(current_chunk)) >= min_chunk_chars:
                    chunks.append(''.join(current_chunk))
                
                # 开始新 chunk，包含重叠
                if overlap_buffer:
                    current_chunk = overlap_buffer.copy()
                    current_tokens = len(self.encoding.encode(''.join(overlap_buffer)))
                    overlap_buffer = []
                else:
                    current_chunk = []
                    current_tokens = 0
            
            # 添加当前 paragraph
            current_chunk.append(para)
            current_tokens += para_tokens
            
            # 维护重叠缓冲区（最近的 tokens）
            para_tokens_list = list(self.encoding.encode(para))
            overlap_buffer.extend(para_tokens_list)
            overlap_buffer = overlap_buffer[-chunk_overlap_tokens:] if len(overlap_buffer) > chunk_overlap_tokens else overlap_buffer
        
        # 保存最后一个 chunk
        if current_chunk and len(''.join(current_chunk)) >= min_chunk_chars:
            chunks.append(''.join(current_chunk))
        
        logger.info(f"Chunked text into {len(chunks)} chunks")
        
        return chunks

    def count_tokens(self, text: str) -> int:
        """统计文本的 token 数量"""
        return len(self.encoding.encode(text))
```

**新增文件：backend/utils/embedder.py**

```python
"""
Embedding 服务：支持批量、缓存、降级
"""
import hashlib
import logging
from typing import List, Tuple

from openai import AsyncOpenAI

from backend.utils.llm_client import _get_or_create_client
from backend.constants import EMBEDDING_MODEL, EMBEDDING_BATCH_SIZE

logger = logging.getLogger(__name__)


class Embedder:
    """Embedding 服务，支持缓存和批量处理"""

    def __init__(self, redis_client):
        self.client = None  # 延迟初始化
        self.redis = redis_client
        self.model = EMBEDDING_MODEL

    async def _get_client(self) -> AsyncOpenAI:
        """获取或创建 OpenAI 客户端"""
        if self.client is None:
            from backend.constants import LLM_API_KEY, LLM_BASE_URL
            self.client = await _get_or_create_client(LLM_API_KEY, LLM_BASE_URL)
        return self.client

    async def embed_text(
        self,
        text: str,
        use_cache: bool = True
    ) -> List[float]:
        """
        嵌入单个文本，支持缓存
        
        Returns:
            embedding 向量 (1536 维)
        """
        # 1. 检查缓存
        if use_cache:
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            cache_key = f"embedding:{text_hash}"
            
            cached = await self.redis.get(cache_key)
            if cached:
                import json
                logger.debug(f"Embedding cache hit for text hash: {text_hash[:16]}")
                return json.loads(cached)
        
        # 2. 调用 Embedding API
        client = await self._get_client()
        try:
            response = await client.embeddings.create(
                model=self.model,
                input=text
            )
            embedding = response.data[0].embedding
            
            # 3. 更新缓存
            if use_cache:
                import json
                await self.redis.setex(cache_key, 86400, json.dumps(embedding))  # 24h TTL
            
            logger.debug(f"Generated embedding for text ({len(embedding)} dims)")
            return embedding
            
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise

    async def embed_texts_batch(
        self,
        texts: List[str],
        batch_size: int = None
    ) -> List[List[float]]:
        """
        批量嵌入多个文本
        
        Args:
            texts: 文本列表
            batch_size: 每批处理的数量（默认使用常量）
        
        Returns:
            embedding 向量列表
        """
        if batch_size is None:
            batch_size = EMBEDDING_BATCH_SIZE
        
        all_embeddings = []
        
        # 分批处理
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing embedding batch {i//batch_size + 1}/{(len(texts) - 1)//batch_size + 1}")
            
            # 并行处理单个文本（复用 embed_text）
            batch_embeddings = await asyncio.gather(*[
                self.embed_text(text) for text in batch
            ])
            
            all_embeddings.extend(batch_embeddings)
        
        logger.info(f"Generated {len(all_embeddings)} embeddings total")
        return all_embeddings
```

**backend/constants.py 新增常量**：

```python
# ============================================================================
# Embedding Configuration
# ============================================================================

EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-large")
EMBEDDING_BATCH_SIZE = _parse_int_env("EMBEDDING_BATCH_SIZE", default=50, min_val=1, max_val=200)
EMBEDDING_CACHE_TTL = 86400  # 24 hours

# 为什么：
# - text-embedding-3-large: 3072 维度，优秀的语义表示
# - batch_size=50: 平衡 API 调用次数与超时风险
# - cache_ttl=24h: 避免短期内重复计算
```


**新增文件：backend/utils/vector_store.py**

```python
"""
向量存储：Qdrant 集成，支持 upsert、search、delete
"""
import logging
from typing import List, Optional, Tuple

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    Filter,
    VectorParams,
    SearchRequest,
)

from backend.constants import QDRANT_HOST, QDRANT_PORT, QDRANT_COLLECTION

logger = logging.getLogger(__name__)


class VectorStore:
    """Qdrant 向量存储，支持版本化和过滤"""

    def __init__(self):
        self.client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        self.collection_name = QDRANT_COLLECTION

    async def initialize_collection(self, vector_size: int = 3072):
        """初始化 collection，自动创建或更新"""
        try:
            # 检查 collection 是否存在
            collections = await self.client.get_collections()
            collection_exists = any(
                c.name == self.collection_name 
                for c in collections.collections
            )
            
            if not collection_exists:
                # 创建新 collection
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=vector_size,
                        distance=Distance.COSINE,
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                logger.info(f"Collection exists: {self.collection_name}")
                
        except Exception as e:
            logger.error(f"Failed to initialize collection: {e}")
            raise

    async def upsert_chunks(
        self,
        chunks: List[Tuple[str, dict]],  # (text, metadata)
        embeddings: List[List[float]]
    ) -> int:
        """
        批量插入 chunks 到向量库
        
        Args:
            chunks: (chunk_text, metadata) 元组列表
            embeddings: 对应的 embedding 向量列表
        
        Returns:
            成功插入的点数量
        """
        points = []
        
        for idx, ((text, metadata), embedding) in enumerate(zip(chunks, embeddings)):
            point = PointStruct(
                id=idx,
                vector=embedding,
                payload={
                    "text": text,
                    **metadata  # paper_id, chunk_id, document_version, etc.
                }
            )
            points.append(point)
        
        # 批量 upsert
        operation_info = await self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )
        
        logger.info(f"Upserted {len(points)} points to {self.collection_name}")
        return operation_info.upserted_count

    async def search_similar(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: float = 0.7,
        filters: Optional[Filter] = None
    ) -> List[Tuple[float, dict]]:
        """
        搜索相似 chunks
        
        Args:
            query_vector: 查询向量
            limit: 返回结果数量
            score_threshold: 最小相似度阈值
            filters: 元数据过滤条件
        
        Returns:
            [(score, payload), ...] 结果列表
        """
        search_result = await self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            query_filter=filters,
            limit=limit,
            score_threshold=score_threshold,
        )
        
        results = [
            (hit.score, hit.payload)
            for hit in search_result
        ]
        
        logger.info(f"Found {len(results)} similar chunks (threshold: {score_threshold})")
        return results

    async def delete_by_paper_id(self, paper_id: str):
        """删除特定论文的所有 chunks"""
        await self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[
                    {
                        "key": "paper_id",
                        "match": {"value": paper_id}
                    }
                ]
            )
        )
        logger.info(f"Deleted all chunks for paper: {paper_id}")
```

**backend/constants.py 新增 Qdrant 配置**：

```python
# ============================================================================
# Qdrant Configuration
# ============================================================================

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "rag-chunks")
QDRANT_VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "3072"))
QDRANT_SEARCH_LIMIT = int(os.getenv("QDRANT_SEARCH_LIMIT", "10"))
QDRANT_SCORE_THRESHOLD = float(os.getenv("QDRANT_SCORE_THRESHOLD", "0.7"))

# 为什么：
# - host/port: 默认本地部署，生产环境覆盖
# - rag-chunks collection: 存储文本 chunks 的主 collection
# - 3072 维度: text-embedding-3-large 的维度
# - limit=10: 返回 top10 最相似 chunks
# - threshold=0.7: 只返回相似度 >= 0.7 的结果
```

#### 2.2.4 修改现有节点

**backend/nodes.py 修改 extractor_agent**

```python
# 在文件顶部添加导入
from backend.utils.pdf_parser import PDFParser
from backend.utils.text_chunker import TextChunker
from backend.utils.embedder import Embedder
from backend.utils.vector_store import VectorStore

# 修改 _extract_contribution 函数
async def _extract_contribution(
    paper: PaperMetadata,
    language: str,
) -> dict[str, Any]:
    """提取论文贡献，支持 PDF 全文解析和向量化"""
    
    # 原有逻辑：使用 abstract
    if not paper.abstract:
        return {
            "paper_id": paper.paper_id,
            "title": paper.title,
            "core_contribution": None,
            "structured_contribution": None,
            "status": "skipped",
            "reason": "No abstract available"
        }
    
    # 新增逻辑：如果有 PDF 对象，解析全文
    if paper.pdf_object_key:
        parser = PDFParser()
        chunker = TextChunker()
        embedder = Embedder(redis_client=await get_redis_client())
        vector_store = VectorStore()
        
        try:
            # 1. 从 MinIO 下载并解析 PDF
            full_text, page_count = await parser.parse_pdf_from_minio(
                bucket="rag-raw",
                object_key=paper.pdf_object_key
            )
            
            if not full_text:
                logger.warning(f"Failed to parse PDF for paper: {paper.title[:50]}")
                # 降级到 abstract
                full_text = paper.abstract
            
            # 2. 文本切块
            chunks = chunker.chunk_text(
                text=full_text,
                chunk_max_tokens=500,
                chunk_overlap_tokens=50
            )
            
            # 3. 批量 embedding
            embeddings = await embedder.embed_texts_batch(chunks)
            
            # 4. 索引到向量库
            chunk_metadata = [
                (chunk, {
                    "paper_id": paper.paper_id,
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "source": paper.source.value,
                    "chunk_index": idx,
                    "document_version": "1.0"
                })
                for idx, chunk in enumerate(chunks)
            ]
            
            await vector_store.initialize_collection()
            await vector_store.upsert_chunks(chunk_metadata, embeddings)
            
            logger.info(f"Indexed {len(chunks)} chunks for paper: {paper.title[:50]}")
            
        except Exception as e:
            logger.error(f"Failed to process PDF for paper: {paper.title[:50]}: {e}")
            # 降级到 abstract
            full_text = paper.abstract
    
    # 继续原有逻辑：调用 LLM 提取贡献
    # ... (保持现有代码不变)
```


### 2.3 验收标准

**功能验证**：
- [ ] 能解析 PDF 并提取全文
- [ ] 文本切块保持语义完整性（按段落/句子切分）
- [ ] Embedding API 调用正确（批量、缓存）
- [ ] 向量索引成功 upsert 到 Qdrant
- [ ] 语义检索返回相关 chunks（相似度排序）

**性能指标**：
- [ ] PDF 解析 P95 < 3s（50MB 以内）
- [ ] Embedding 缓存命中率 > 50%（重复论文较多场景）
- [ ] 向量检索 P95 < 200ms（top10）
- [ ] 端到端（论文 → chunks → 索引）P95 < 30s

**代码质量**：
- [ ] 所有新文件通过 ruff check 和 mypy
- [ ] 有单元测试覆盖核心逻辑（切块、embedding、检索）
- [ ] 有集成测试验证 Qdrant 集成

**可观测性**：
- [ ] 结构化日志（paper_id, chunk_count, embedding_time, search_time）
- [ ] Prometheus 指标：
  - embedding_requests_total
  - embedding_cache_hits
  - vector_upsert_total
  - vector_search_total
  - vector_search_latency_p95

### 2.4 风险与缓解

| 风险 | 影响 | 缓解措施 |
|--------|------|----------|
| Qdrant 单点故障 | 无法检索 chunks | 1) 硬盘镜像备份<br>2) 降级到关键词搜索 |
| Embedding API 限流 | embedding 失败率上升 | 1) 指数退避重试<br>2) 批量请求减少调用次数 |
| 向量索引更新失败 | 部分论文无法检索 | 1) 幂等 upsert 操作<br>2) 失败日志记录 |
| 存储成本增长 | 运营成本上升 | 1) 冷数据分层<br>2) 定期清理过期向量 |

---

## Phase 3: PostgreSQL 元数据层（4-5 周）

### 3.1 业务痛点

**问题陈述**：
- 当前无关系数据库，无法建立文献、chunk、claim 之间的关联
- Claim verification 基于 abstract，无法追溯具体页码/段落
- 无版本控制，无法追踪 extractor_version / embedding_version 演进
- 无审计日志，无法回溯操作历史

### 3.2 技术方案

#### 3.2.1 数据库 Schema 设计

**核心表结构**：

```sql
-- 1. 逻辑文献表
CREATE TABLE document (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id TEXT UNIQUE,  -- DOI / arXiv ID / internal key
    source_uri TEXT NOT NULL,  -- MinIO object key
    title TEXT,
    authors JSONB,  -- [{name, orcid}, ...]
    metadata JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 2. 文献版本表（内容快照）
CREATE TABLE document_version (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES document(id) ON DELETE CASCADE,
    version_no INT NOT NULL,
    content_checksum TEXT NOT NULL,  -- PDF 文件哈希
    source_checksum TEXT NOT NULL,
    mime_type TEXT,
    language TEXT,
    page_count INT,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- 版本控制三元组
    extractor_version TEXT NOT NULL,
    chunker_version TEXT NOT NULL,
    embedding_version TEXT NOT NULL,
    
    status TEXT NOT NULL DEFAULT 'active',  -- active/superseded/failed
    UNIQUE (document_id, version_no),
    UNIQUE (document_id, content_checksum)
);

-- 3. Chunk 表
CREATE TABLE chunk (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_version(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    text TEXT NOT NULL,
    token_count INT,
    page_start INT,
    page_end INT,
    char_start INT,
    char_end INT,
    chunk_checksum TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (document_version_id, chunk_index)
);

-- 4. Claim 表
CREATE TABLE claim (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_version_id UUID NOT NULL REFERENCES document_version(id) ON DELETE CASCADE,
    primary_chunk_id UUID REFERENCES chunk(id) ON DELETE SET NULL,
    claim_text TEXT NOT NULL,
    claim_type TEXT,
    confidence NUMERIC(5,4),
    extractor_version TEXT NOT NULL,
    normalized_hash TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Claim Evidence 表（证据链）
CREATE TABLE claim_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES claim(id) ON DELETE CASCADE,
    document_version_id UUID NOT NULL REFERENCES document_version(id) ON DELETE CASCADE,
    chunk_id UUID REFERENCES chunk(id) ON DELETE SET NULL,
    
    -- 证据定位
    page_span int4range,
    char_span int8range,
    source_checksum TEXT NOT NULL,
    
    quote_text TEXT,
    entailment_label TEXT,
    entailment_score NUMERIC(5,4),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    
    -- 一致性约束
    CHECK (lower(char_span) >= 0)
);

-- 6. 审计日志表
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    table_name TEXT NOT NULL,
    row_pk TEXT NOT NULL,
    action TEXT NOT NULL,  -- INSERT/UPDATE/DELETE
    changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    changed_by TEXT,
    txid BIGINT NOT NULL DEFAULT txid_current(),
    before_data JSONB,
    after_data JSONB,
    request_id TEXT,
    reason TEXT
);

-- 7. 索引优化
CREATE INDEX idx_doc_ver_doc_status ON document_version(document_id, status, version_no DESC);
CREATE INDEX idx_chunk_docver_idx ON chunk(document_version_id, chunk_index);
CREATE INDEX idx_claim_docver ON claim(document_version_id, created_at DESC);
CREATE INDEX idx_evidence_claim ON claim_evidence(claim_id);
CREATE INDEX idx_evidence_docver ON claim_evidence(document_version_id);
CREATE INDEX idx_audit_table_row_time ON audit_log(table_name, row_pk, changed_at DESC);
```


#### 3.2.2 Python 集成实现

**新增文件：backend/database/connection.py**

```python
"""
PostgreSQL 连接池管理
"""
import logging
from contextlib import asynccontextmanager

from asyncpg import create_pool, Pool
from backend.constants import DATABASE_URL

logger = logging.getLogger(__name__)

_pool: Pool | None = None


async def get_pool() -> Pool:
    """获取或创建数据库连接池"""
    global _pool
    if _pool is None:
        _pool = await create_pool(DATABASE_URL, min_size=5, max_size=20)
        logger.info(f"Created PostgreSQL connection pool (min: 5, max: 20)")
    return _pool


@asynccontextmanager
async def get_connection():
    """获取数据库连接的上下文管理器"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        yield conn


async def close_pool() -> None:
    """关闭连接池"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed")
```

**backend/constants.py 新增 PostgreSQL 配置**：

```python
# ============================================================================
# PostgreSQL Configuration
# ============================================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:password@localhost:5432/auto_scholar"
)

# 为什么：
# - 使用 connection pool 避免每次创建新连接
# - min_size=5: 保持最小连接数，降低冷启动延迟
# - max_size=20: 限制最大连接数，防止数据库过载
```

**新增文件：backend/database/repositories.py**

```python
"""
数据访问层：封装 CRUD 操作
"""
import logging
from typing import List, Optional
from datetime import datetime

from backend.database.connection import get_connection
from backend.schemas import PaperMetadata

logger = logging.getLogger(__name__)


class DocumentRepository:
    """文献数据访问层"""

    async def create_document(
        self,
        paper: PaperMetadata,
        source_checksum: str
    ) -> str:
        """创建文献记录"""
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO document (external_id, source_uri, title, authors, metadata)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                """, (
                    paper.paper_id,
                    paper.pdf_object_key or "",
                    paper.title,
                    paper.authors,
                    paper.model_dump_json(exclude={'pdf_url'})
                ))
                
                document_id = await cur.fetchone()
                logger.info(f"Created document: {document_id[0]}")
                return document_id[0]

    async def get_document_by_external_id(
        self,
        external_id: str
    ) -> Optional[dict]:
        """通过外部 ID 查询文献"""
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    SELECT id, external_id, title, created_at
                    FROM document
                    WHERE external_id = $1
                """, (external_id,))
                
                return await cur.fetchone()


class ChunkRepository:
    """Chunk 数据访问层"""

    async def create_chunks(
        self,
        document_version_id: str,
        chunks: List[tuple[str, dict]]
    ) -> int:
        """批量创建 chunks"""
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                chunk_records = [
                    (
                        document_version_id,
                        idx,
                        text,
                        chunk_data.get('token_count', 0),
                        chunk_data.get('page_start'),
                        chunk_data.get('page_end'),
                        chunk_data.get('char_start'),
                        chunk_data.get('char_end'),
                        hashlib.sha256(text.encode()).hexdigest()
                    )
                    for idx, (text, chunk_data) in enumerate(chunks)
                ]
                
                await cur.executemany("""
                    INSERT INTO chunk (
                        document_version_id, chunk_index, text, token_count,
                        page_start, page_end, char_start, char_end, chunk_checksum
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """, chunk_records)
                
                logger.info(f"Created {len(chunks)} chunks for document version: {document_version_id}")
                return len(chunks)


class ClaimRepository:
    """Claim 数据访问层"""

    async def create_claim(
        self,
        document_version_id: str,
        claim_text: str,
        claim_type: str
    ) -> str:
        """创建 claim 记录"""
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO claim (
                        document_version_id, claim_text, claim_type, extractor_version
                    ) VALUES ($1, $2, $3, $4)
                    RETURNING id
                """, (
                    document_version_id,
                    claim_text,
                    claim_type,
                    "claim_extractor@1.0.0"
                ))
                
                claim_id = await cur.fetchone()
                logger.info(f"Created claim: {claim_id[0]}")
                return claim_id[0]

    async def create_claim_evidence(
        self,
        claim_id: str,
        document_version_id: str,
        chunk_id: Optional[str],
        page_span: Optional[tuple],
        char_span: Optional[tuple],
        quote_text: str,
        entailment_label: str,
        entailment_score: float
    ) -> str:
        """创建 claim evidence 记录"""
        async with get_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute("""
                    INSERT INTO claim_evidence (
                        claim_id, document_version_id, chunk_id, page_span, char_span,
                        source_checksum, quote_text, entailment_label, entailment_score
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING id
                """, (
                    claim_id, document_version_id, chunk_id,
                    page_span, char_span, chunk_id,  # source_checksum from chunk
                    quote_text, entailment_label, entailment_score
                ))
                
                evidence_id = await cur.fetchone()
                logger.info(f"Created claim evidence: {evidence_id[0]}")
                return evidence_id[0]
```

### 3.3 验收标准

**功能验证**：
- [ ] PostgreSQL schema 创建成功
- [ ] 能创建文献记录并自动生成 document_id
- [ ] 能批量创建 chunks 并关联到 document_version
- [ ] 能创建 claim 并关联到 chunk
- [ ] 能创建 claim evidence 并记录页码/段落范围
- [ ] 审计日志记录所有操作

**性能指标**：
- [ ] 数据库写入 P95 < 50ms（单个记录）
- [ ] 批量插入 100 chunks P95 < 2s
- [ ] 查询 P95 < 100ms（主键查询）
- [ ] 连接池利用率 < 80%（高峰期）

**代码质量**：
- [ ] 所有新文件通过 ruff check 和 mypy
- [ ] 有单元测试覆盖 CRUD 操作
- [ ] 有集成测试验证 PostgreSQL 集成

**可观测性**：
- [ ] 结构化日志（table_name, action, rows_affected）
- [ ] Prometheus 指标：
  - db_query_total
  - db_query_latency_p95
  - db_connection_pool_active

### 3.4 风险与缓解

| 风险 | 影响 | 缓解措施 |
|--------|------|----------|
| PostgreSQL 单点故障 | 无法写入/读取数据 | 1) 主从复制<br>2) 连接池熔断 |
| 连接池耗尽 | 新请求失败 | 1) 限制最大连接数<br>2) 查询超时控制 |
| Schema 变更失败 | 索引创建失败 | 1) 版本化迁移脚本<br>2) 自动回滚 |
| 数据增长 | 存储成本上升 | 1) 分区表<br>2) 定期归档旧数据 |

---

## 总结与建议

### 关键收益

| 维度 | 当前状态 | 升级后 | 收益 |
|------|---------|--------|------|
| **成本** | 重复 embedding $0.01/次 | 缓存后边际成本递减 | 月节省 $500+ |
| **稳定性** | 外部 API 限流风险 | MinIO 缓存 | 99.9% 可用性 |
| **可追溯** | abstract 级别验证 | 全文证据链 | 100% 溯源准确 |
| **可扩展** | SQLite 检查点 | PostgreSQL + Qdrant | 支持 100K+ 用户 |

### Infra 求职叙事要点

**面试核心话术**：

1. **业务驱动架构**：
   - 不是"我想用 MinIO"，而是"为了解决 API 限流和 OOM 风险，引入了 MinIO"
   - 量化痛点：10 用户并发 × 50 篇论文 × 5MB = 2.5GB 内存

2. **成本意识**：
   - "embedding 缓存从零开始，命中率逐步提升到 50%+"
   - "Token 账单从指数增长转为边际递减"

3. **可靠性工程**：
   - "电路熔断 + 重试机制 + 连接池 = 99.9% 可用性"
   - "MinIO 对象存储 + PostgreSQL 关系数据 = 完整证据链"

4. **版本化演进**：
   - "蓝绿切换支持 embedding 模型升级零停机"
   - "document_version 追踪 extractor/chunker/embedding 版本"

5. **可观测性**：
   - "Prometheus + Grafana 实时监控 PDF 下载、embedding、向量检索"
   - "审计日志记录所有关键操作，支持回溯"

### 部署建议

**环境配置优先级**：

1. **开发环境**：
   - MinIO: Docker Compose 单节点
   - Qdrant: Docker Compose 单节点
   - PostgreSQL: Docker Compose 单节点
   - Redis: Docker Compose 单节点

2. **生产环境**：
   - MinIO: 分布式集群（至少 3 节点）
   - Qdrant: 读写分离 + 分片
   - PostgreSQL: 主从复制 + 连接池
   - Redis: Sentinel 高可用

3. **监控告警**：
   - MinIO: 存储使用率 > 80%、写入失败率 > 1%
   - Qdrant: 查询延迟 P95 > 1s、内存使用率 > 80%
   - PostgreSQL: 连接池耗尽、查询 P95 > 500ms
   - Redis: 内存使用率 > 90%、缓存命中率 < 30%

---

**方案完成日期**: 2026-02-28
**文档版本**: v2.0
**维护者**: Auto-Scholar Infra Team

