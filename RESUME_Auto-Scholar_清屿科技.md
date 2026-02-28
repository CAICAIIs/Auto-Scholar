# Auto-Scholar - 多智能体学术研究 Agent 系统
项目时间: 2026.01 - 2026.02

项目描述:
针对 AI 学术写作中"幻觉严重、交互黑盒"的核心痛点，独立设计并实现的 Agent 编排系统。采用 LangGraph 构建含反思修复环路的 6 节点协作架构，通过上下文工程与结构化输出实现复杂研究任务的自主分解与迭代优化。

核心算法实现:

Agent 编排与状态管理:
基于 LangGraph 设计 6 节点 DAG 工作流（Planner → Retriever → Extractor → Writer → Critic → Reflection），通过 TypedDict 共享状态黑板实现 Agent 间数据流。引入 AsyncSqliteSaver 实现会话级状态持久化，支持 `interrupt_before` 机制实现 Human-in-the-Loop 断点续传。

上下文工程与结构化输出:
针对每个 Agent 设计专用 System Prompt，采用 JSON Schema 定义结构化输出格式（Pydantic V2）。Planner Agent 生成搜索关键词（3-5 个）；Extractor Agent 使用 8 维度 Schema 抽取论文核心信息；Critic Agent 输出错误列表与重试建议。通过 `temperature=0.1-0.3` 低温度确保输出稳定性，使用 `structured_completion` 统一 LLM 调用接口。

工具调用与并行检索:
封装 Semantic Scholar / arXiv / PubMed 三大学术数据库客户端，基于 `aiohttp` 实现异步 HTTP 调用。利用 `asyncio.gather(*tasks)` 实现三源并行检索与全文获取，通过 `tenacity` 的指数退避重试（`wait_exponential(min=2, max=10)`, `stop_after_attempt(3)`) 处理网络抖动。Claim-Level 验证时使用信号量限制并发度（`MAX_CONCURRENT=3`），避免超出 API rate limit。

复杂任务规划与智能路由:
设计 QA 错误的 5 类分类体系（引用越界/缺少引用/论文未引用/蕴含率低/结构性问题），Reflection Agent 分析错误模式后通过 `_reflection_router` 决策路由策略：结构性问题 → Writer Agent，数据缺失问题 → Retriever Agent，否则终止（最大重试 3 次）。引入 `claim_verifier` 模块将综述拆分为原子声明，逐一验证其与引用论文的语义蕴含关系。

Claim-Level NLI 验证机制:
突破传统格式校验局限，将 LLM 生成内容拆解为 Claim 列表，对每个 Claim-Citation 对执行 3-way Entailment 检查（entails/insufficient/contradicts）。定义 `MIN_ENTAILMENT_RATIO=0.8` 阈值，蕴含率低于 80% 触发自动重试。验证时传递论文 title/abstract/core_contribution 等高维上下文，通过 `temperature=0.1` 最大化一致性评测精度。

并行章节生成优化:
Writer Agent 采用 `asyncio.gather(*section_tasks)` 并行生成 N 个章节，每个章节独立调用 LLM 提升吞吐量。对异常返回做 `return_exceptions=True` 处理，单章节失败不影响整体流程，失败章节在后续重试时单独重建。

流式输出防抖算法:
针对 SSE 高并发下网络 IO 瓶颈，研发 `StreamingEventQueue` 双触发防抖引擎：
- 时间维度：200ms 固定窗口定期 flush
- 语义维度：检测边界字符（`。！？.!?\n`）立即 flush
- 缓冲管理：动态累积 token 直至触发条件

实测 263 个离散 token → 21 次网络请求，削减 92% 开销（压缩比 12.5x）。

7 维度自动化评测体系:
建立 Agent 输出质量量化框架：
- 引用精确率：`valid_citations / total_citations`
- 引用召回率：`cited_papers / approved_papers`
- 声明支持率：`entails_count / total_verifications`
- 章节完整性：检查必需章节存在性
- 学术风格：hedging 比率、被动语态比率、引用密度
- 成本效率：tokens、API 调用次数、端到端延迟
- 人类偏好：可选 1-5 分 Likert 评分

定义加权评分公式（precision 20% + recall 15% + claim 25% + completeness 20% + style 20%），实现数据驱动的 Agent 效果回归测试。

技术验证与基线测试:
编写 `benchmark_sse.py` 与 `validate_citations.py` 两套基准测试：
- SSE 防抖：模拟 LLM 流式输出验证网络削减效果
- 引用准确率：37 条引用手动验证，基线准确率 97.3%（唯一错误为上下文不完全匹配，非索引越界）

工程化落地:
后端 FastAPI 提供 REST API（start/stream/approve/export），SSE 流式返回工作流日志。前端 Next.js 16 + Zustand 实现实时日志流、论文审批弹窗、编辑/预览切换等交互。支持中英双语（next-intl）与 4 种引用格式（APA/MLA/IEEE/GB-T7714）。完整测试覆盖（pytest + Vitest + Playwright）。

量化成果:
独立完成 Agent 架构设计到端到端交付；SSE 网络削减 92%；基线引用准确率 97.3%；三源并行检索平均延迟 <5s；完整评测框架支持持续优化。

技术栈:
- Agent 框架: LangGraph + LangChain
- LLM 调用: OpenAI AsyncOpenAI + structured outputs
- 状态管理: AsyncSqliteSaver + TypedDict + operator.add reducers
- 并发控制: asyncio.gather + aiohttp + tenacity retry
- 工具调用: Semantic Scholar API / arXiv API / PubMed API
- 评测体系: pytest benchmarks + 7 维度量化指标
- 后端: FastAPI + Pydantic V2 + Python 3.11+
- 前端: Next.js 16 + React 19 + Zustand + Tailwind CSS 4
