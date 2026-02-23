# Auto-Scholar 面试故事手册

> ⚠️ 本文件仅供面试准备使用，不上传 GitHub。
> 核心原则：用真实代码细节讲故事，不编数据，不夸大。

---

## 一、项目介绍（30 秒版 → 2 分钟版 → 5 分钟版）

### 30 秒版

"Auto-Scholar 是一个学术文献综述自动化系统。用户输入研究主题，系统自动检索论文、提取信息、生成带引用的综述报告。技术栈是 LangGraph + FastAPI + Next.js。

我在开发过程中发现它本质上是一个工程化的 RAG Pipeline，缺乏真正的 Agent 能力，所以做了四个方向的进化：任务分解、工具选择、结构化反思、上下文管理。四个方向（P0-P3）已全部实现并上线。"

### 2 分钟版

"Auto-Scholar 是一个学术文献综述自动化系统，使用 LangGraph 编排 6 个 Agent 节点：Planner 生成计划 → Retriever 多源检索 → Extractor 结构化提取 → Writer 生成综述 → Critic 验证引用 → Reflection 结构化反思。

工程层面有几个亮点：
- SSE 防抖引擎，263 条原始消息压缩为 21 次网络请求，92% 削减率
- 多源并行检索（Semantic Scholar + arXiv + PubMed）+ 标题标准化去重
- 8 维度结构化信息提取（problem/method/novelty/dataset/baseline/results/limitations/future_work）
- Claim-level 引用验证：不只检查引用索引是否越界，还用 NLI 模型判断引用是否真正支持声明

但我做了一次诚实的自我诊断，发现了几个关键缺口：
- Planner 只生成关键词列表，不做任务分解，不输出推理过程
- 工具选择权在用户（前端勾选数据源），Agent 自身不做决策
- Critic 检测到错误后以字符串列表传给 Writer，缺乏结构化的错误分类和修复策略
- `_build_paper_context` 没有截断机制，且整个流程是"先提取再截断"，浪费 LLM 调用

所以我设计了 P0-P3 四个进化方向，每个都做了业务-技术权衡分析。"

### 5 分钟版（在 2 分钟版基础上展开）

"...（2 分钟版内容）...

具体来说：

**P0 Planner with CoT**：当前 `planner_agent` 的输出模型是 `KeywordPlan`，只有一个 `keywords: list[str]` 字段。我已经实现了 `ResearchPlan` 模型，包含 `sub_questions`（子问题列表）和 `reasoning`（推理链）。每个子问题有自己的关键词、推荐数据源、预估论文数。

实现中有一个关键设计决策：对简单查询（如'transformer 综述'），CoT 反而增加延迟，所以实现了双路径机制——查询长度 < 10 字时直接走原有 `KeywordPlan` 路径，≥ 10 字时走 CoT 路径生成 `ResearchPlan`。两条路径都输出 `search_keywords`，保持与下游 `retriever_agent` 的向后兼容。

```python
# backend/nodes.py 第 95-103 行
COT_QUERY_MIN_LENGTH = 10

async def planner_agent(state: AgentState) -> dict[str, Any]:
    user_query = state["user_query"]
    is_continuation = state.get("is_continuation", False)
    use_cot = len(user_query.strip()) >= COT_QUERY_MIN_LENGTH and not is_continuation
```

**P1 Retriever with Tool Selection**：已实现。当前 `retriever_agent` 会读取 P0 生成的 `research_plan`，通过 `search_by_plan()` 为每个子问题使用其推荐的数据源和论文数量限制，所有子问题并行检索。无 plan 时走原有路径，完全向后兼容。

```python
# backend/nodes.py 第 196-206 行
if research_plan and research_plan.sub_questions:
    logger.info(
        "retriever_agent: plan-aware search with %d sub-questions",
        len(research_plan.sub_questions),
    )
    start_time = time.perf_counter()
    papers = await search_by_plan(
        research_plan, default_limit=PAPERS_PER_QUERY, allowed_sources=sources
    )
    elapsed = time.perf_counter() - start_time
    logger.info("retriever_agent: plan-aware search completed in %.2fs", elapsed)
```

**P2 Structured Reflection**：已实现。当前 `critic_agent` 检测到错误后，新增 `reflection_agent` 节点对错误做结构化分类（5 类：引用越界、缺少引用、论文未被引用、蕴含率低、结构性问题），生成针对性修复策略，并决定是回 Writer 还是回 Retriever。Writer 接收结构化的 `[category] fix_strategy` 列表而非原始字符串错误。无错误时 reflection 不触发，零额外成本。

```python
# backend/nodes.py 第 894-901 行
writer_fixable = sum(1 for e in reflection.entries if e.fixable_by_writer)
retriever_needed = sum(1 for e in reflection.entries if not e.fixable_by_writer)

logs = [
    f"Reflection: {len(reflection.entries)} errors analyzed "
    f"({writer_fixable} writer-fixable, {retriever_needed} need retriever)",
    f"Reflection: retry_target={reflection.retry_target}, "
    f"should_retry={reflection.should_retry}",
    f"Reflection: {reflection.summary[:150]}",
]
```

**P3 Context Engineering**：经历了两次设计迭代。第一版添加了 `CONTEXT_MAX_PAPERS=25` 截断，但后来意识到学术综述的价值在于引用覆盖面——用户审批了 76 篇就应该引用 76 篇。76 篇 × 177 tokens ≈ 13K tokens，仅占 128K 窗口的 10.5%，截断是不必要的。最终改为全量提取全量引用，安全阀（200 篇 / 40K tokens）仅防止病态场景。24 个测试覆盖。

```python
# backend/constants.py 第 147-161 行
CONTEXT_TOKEN_BUDGET = 40000
# Why 40000: Safety net only. In normal use, ALL approved papers are included.
# 100 papers × ~180 tokens = ~18,000 tokens (well within 128K context window).

CONTEXT_MAX_PAPERS = 200
# Why 200: Safety net only, not a functional limit. ALL approved papers should
# be extracted and cited. This prevents truly pathological cases.
```

---

## 二、核心故事线：从错误诊断到准确诊断

### 故事背景

"我最初写了一版 proposal，对当前系统的诊断是：'工具硬编码、盲目重试、简单字符串拼接'。但后来仔细读代码发现这些诊断都不准确。"

### 具体细节（面试官追问时用）

**错误诊断 1："工具是硬编码的"**
- 实际代码（`nodes.py` 第 187-194 行）：
```python
sources = state.get(
    "search_sources",
    [
        PaperSource.SEMANTIC_SCHOLAR,
        PaperSource.ARXIV,
        PaperSource.PUBMED,
    ],
)
```
- 真相：`search_sources` 从 state 读取，前端可以传入任意组合
- 准确诊断：不是"硬编码"，而是"决策权在用户而非 Agent"
- 教训：读代码要读到具体实现，不能只看函数签名

**错误诊断 2："盲目重试"**
- 实际代码（`nodes.py` 第 634-651 行）：
```python
if is_retry:
    reflection = state.get("reflection")
    if reflection and reflection.entries:
        instructions = []
        for entry in reflection.entries:
            instructions.append(f"- [{entry.error_category.value}] {entry.fix_strategy}")
        system_prompt += DRAFT_REFLECTION_RETRY_ADDENDUM.format(
            reflection_instructions="\n".join(instructions),
            num_papers=num_papers,
        )
    else:
        top_errors = qa_errors[:3]
        error_list = "\n".join(f"- {e}" for e in top_errors)
        system_prompt += DRAFT_RETRY_ADDENDUM.format(
            error_count=len(qa_errors),
            error_list=error_list,
            num_papers=num_papers,
        )
```
- 真相：`qa_errors` 已经传递给 Writer 了，不是盲目重试
- 准确诊断：不是"盲目"，而是"缺乏结构化反思"——错误以字符串传递，Writer 需要自己理解含义
- 教训：区分"完全缺失"和"有基础但不完整"很重要

**错误诊断 3："简单字符串拼接"**
- 实际代码（`nodes.py` 第 434-496 行）：`_build_paper_context` 使用 8 维度结构化信息
```python
# backend/nodes.py 第 474-490 行
if sc:
    if sc.problem:
        paper_info.append(f"Problem: {sc.problem}")
    if sc.method:
        paper_info.append(f"Method: {sc.method}")
    if sc.novelty:
        paper_info.append(f"Novelty: {sc.novelty}")
    if sc.dataset:
        paper_info.append(f"Dataset: {sc.dataset}")
    if sc.baseline:
        paper_info.append(f"Baseline: {sc.baseline}")
    if sc.results:
        paper_info.append(f"Results: {sc.results}")
    if sc.limitations:
        paper_info.append(f"Limitations: {sc.limitations}")
    if sc.future_work:
        paper_info.append(f"Future Work: {sc.future_work}")
```
- 真相：已经有 problem/method/novelty/dataset/baseline/results/limitations/future_work
- 准确诊断：不是"简单拼接"，而是"缺乏截断机制和 token 预算管理"
- 教训：不要低估已有代码的能力

### 这个故事的面试价值

"这个经历让我学到：**准确诊断比快速修复更重要**。如果基于错误的诊断去'修复'，不仅浪费时间，面试时被追问还会露馅。所以我养成了一个习惯：每次诊断问题时，先读实际代码，再下结论。"

---

## 三、P0-P3 进化故事

### P0：Planner with CoT —— 复杂任务的任务分解能力

**问题**

"当前 `planner_agent` 只做一件事：根据用户查询生成 3-5 个关键词。对简单查询这没问题，比如'transformer 综述' → ['transformer', 'attention mechanism', 'self-attention', 'BERT', 'GPT']。

但对复杂查询就不够了，比如'深度学习在医学图像分析中的应用与挑战' —— 这种查询需要先理解有哪些子问题（图像分类、分割、检测、配准等），再为每个子问题生成关键词和推荐数据源。

简单关键词生成的缺点：
1. 无推理过程：用户看不到'为什么这样分解'
2. 无子问题概念：下游 retriever 只能对所有关键词发同样的检索
3. 无工具决策：每个子问题适合哪个数据源不清楚"

**动作**

"我实现了 `ResearchPlan` 模型，包含推理链和子问题列表。每个子问题有：
- `question`: 子问题文本
- `keywords`: 该子问题的 2-5 个关键词
- `preferred_source`: 推荐数据源（semantic_scholar/arxiv/pubmed）
- `estimated_papers`: 预估需要的论文数量（3-15）
- `priority`: 优先级（1 最高，5 最低）

关键设计：双路径机制。简单查询（< 10 字）走原有 `KeywordPlan` 路径，复杂查询走 CoT 路径。避免对简单任务增加不必要的延迟。"

**结果**

- 复杂查询能够自动分解为 3-5 个子问题
- 每个子问题有独立的关键词和推荐数据源
- 用户可以看到推理链（`plan.reasoning[:200]...`）
- 向后兼容：简单查询走原路径，无额外成本

**数据**

- 双路径阈值 `COT_QUERY_MIN_LENGTH = 10`（`nodes.py` 第 95 行）
- 测试覆盖：`test_planner_agent.py` 有 7 个测试用例（CoT 路径 3 个，简单路径 4 个）

**复盘**

"核心权衡：CoT 增加约 2-3 秒延迟和 500-1000 output tokens，但显著提升复杂任务的检索质量。双路径机制是关键——简单任务不需要为此付费。"


---

### P1：Retriever with Tool Selection —— Plan-aware 检索

**问题**

"P0 生成了 `ResearchPlan`，但原来的 `retriever_agent` 并没有使用它。它只是把所有关键词收集起来，对所有用户选中的数据源发起检索。

问题：
1. 子问题级别的数据源决策被浪费了——'医学图像分割'更适合 PubMed，但所有关键词都会去搜 Semantic Scholar
2. 论文数量控制是全局的——每个子问题需要的论文数不同，但只能统一设置
3. 无法体现任务分解的价值——Planner 做了精细分解，Retriever 还是简单拼接"

**动作**

"实现了 `search_by_plan()` 函数，为每个子问题按其 `preferred_source` 和 `estimated_papers` 发起独立检索。所有子问题并行执行（`asyncio.gather`）。

还有一个补充逻辑：如果用户选择了某个数据源但所有子问题都没覆盖，会发一次补充检索，确保每个用户选择的数据源都有贡献结果。"

**结果**

- 每个子问题使用其推荐的数据源和论文数量
- 所有检索并行执行，总耗时 = 最慢的单次检索
- 补充检索确保用户选择的数据源都有贡献

**数据**

- `return_exceptions=True` 确保单个失败不影响整体（`scholar_api.py` 第 566 行）
- 测试覆盖：`test_search_by_plan.py` 有 11 个测试用例

**复盘**

"关键设计：`retriever_agent` 检查 `research_plan and research_plan.sub_questions`，无 plan 时走原路径。这保证了向后兼容——简单查询、续写场景都不会受影响。"

---

### P2：Structured Reflection —— 把 Critic 变成 Router

**问题**

"原来的流程：Critic 检测到错误 → `qa_errors` 作为字符串列表传给 Writer → Writer 用前 3 条错误重试。

问题：
1. 错误类型不同，修复策略完全不同：
   - 'Section 2: No citations found' → Writer 需要添加引用
   - 'Claim citing [99] out of bounds (valid: 1-50)' → Writer 需要修正索引
   - 'Missing citation: paper [15] was approved but not cited' → Writer 添加不了，需要重新检索
2. Writer 需要自己理解错误含义——'Section 2: No citations found' 和 'Claim citing [99] out of bounds' 都是字符串，但含义完全不同
3. 没有路由决策——所有错误都回 Writer，即使错误源于检索结果不足"

**动作**

"在 Critic 和 Writer 之间插入 `reflection_agent`。它调用 LLM 将每个错误分类为 5 类，并为每个错误生成具体的 fix_strategy。关键设计是 `fixable_by_writer` 字段——如果所有错误 writer 都能修，路由到 writer；如果有错误需要更多论文，路由到 retriever。"

**结果**

- 错误从字符串变成结构化对象
- Writer 收到 `[category] fix_strategy` 而非原始错误文本
- 路由到 retriever 时会重新检索 → 提取 → 生成 → 验证

**数据**

- 5 种错误类别（`schemas.py` 第 262-269 行）
- 无错误时 reflection 不触发（`_qa_router` 先检查，`workflow.py` 第 58-62 行）
- 测试覆盖：`test_reflection_agent.py` 有 4 个测试用例

**复盘**

"'按需付费'设计——happy path 零额外 LLM 调用。只有 QA 失败时才会触发 reflection。这是结构化反思的成本权衡。"

---

### P3：Context Engineering —— 从截断到全量引用的设计迭代

**问题（第一版诊断）**

"我最初诊断问题是：`_build_paper_context` 没有截断机制，如果用户审批了 76 篇论文，所有论文都会被放入 writer 的上下文，可能导致超限。

所以我设计了第一版方案：
1. 添加 `CONTEXT_MAX_PAPERS=25` 截断
2. 添加 `CONTEXT_TOKEN_BUDGET=6000` token 预算
3. 实现 select-before-extract 架构——在 extractor 中先选 25 篇再提取，避免浪费 LLM 调用

技术上是对的，但后来我意识到这违背了产品目标。"

**反转：从截断到全量引用**

"学术综述的核心价值在于引用覆盖面。用户审批了 76 篇论文，就是想让综述引用这 76 篇。截断到 25 篇意味着 51 篇论文对 writer 完全不可见，根本不可能被引用。

然后我算了一下：76 篇 × 177 tokens/篇 ≈ 13,450 tokens，仅占 128K context window 的 10.5%。截断是完全不必要的。"

**最终设计：安全阀而非功能限制**

"改为：提取并引用所有用户审批的论文。`CONTEXT_MAX_PAPERS=200` 和 `CONTEXT_TOKEN_BUDGET=40000` 仅作为安全阀，防止病态场景（比如 bug 导致批准数千篇论文），正常流程永远不会触发。"

**结果**

- 全量提取所有用户审批的论文
- 安全阀只在异常情况下触发
- 76 篇论文 × 177 tokens ≈ 13K tokens，远小于 128K 窗口

**数据**

- `CONTEXT_TOKEN_BUDGET = 40000`（`constants.py` 第 147 行）
- `CONTEXT_MAX_PAPERS = 200`（`constants.py` 第 158 行）
- 测试覆盖：24 个测试用例

**复盘**

"第一版的错误在于把'Context Engineering'等同于'截断'。在 context window 足够大的情况下，正确的做法是充分利用窗口。这是一个典型的'技术正确但产品错误'的案例。"

---

### P4：7 维度评测框架 —— 从"感觉变好了"到数据驱动

**问题**

"P0-P3 实现完之后，我发现一个尴尬的问题：我声称这些进化'提升了系统能力'，但没有任何数据证明。proposal 里的评测指标全是'目标值，不是已测量的结果'。面试官问'你怎么知道 CoT 真的有效？'，我只能说'设计上应该有效'——这不够。"

**动作**

"实现了完整的 7 维度自动化评测框架：

1. **引用精确率**：`valid_citations / total_citations`，检测越界引用
2. **引用召回率**：`cited_papers / approved_papers`，检测未被引用的论文
3. **声明支持率**：`entails_count / total_verifications`，来自 claim-level NLI 验证
4. **章节完整性**：必需章节存在性检查（中英双语 + 别名匹配）
5. **学术风格**：hedging 比率（5-20%）、被动语态比率、引用密度
6. **成本效率**：token 用量、LLM 调用次数、搜索 API 调用次数、节点级耗时
7. **人工评分**：1-5 Likert 量表（5 个子维度）

加权评分公式：precision 20% + recall 15% + claim 25% + completeness 20% + style 20%。"

```python
# backend/evaluation/schemas.py 第 170-188 行
@computed_field
@property
def automated_score(self) -> float:
    hedging = self.academic_style.hedging_ratio
    if 0.05 <= hedging <= 0.20:
        hedging_score = 1.0
    elif hedging < 0.05:
        hedging_score = hedging / 0.05
    else:
        hedging_score = max(0, 1 - (hedging - 0.20) / 0.20)

    return (
        0.20 * self.citation_precision.precision
        + 0.15 * self.citation_recall.recall
        + 0.25 * self.claim_support_rate
        + 0.20 * self.section_completeness.completeness_score
        + 0.20 * hedging_score
    )
```

**结果**

- 39 个测试全部通过（单元测试 + 回归测试）
- 回归阈值：precision ≥ 95%、recall ≥ 80%、completeness = 100%、hedging 5-20%、automated_score > 0.7
- 全量评测 < 100ms/次（性能基准通过）
- API 端点：`GET /api/research/evaluate/{thread_id}`

**数据**

- 评测模块：`backend/evaluation/` 目录，7 个文件 ~500 行
- 测试覆盖：`test_evaluation.py`（39 个）+ `test_evaluation_regression.py`（8 个）+ `benchmark_evaluation.py`
- 成本追踪集成：`workflow.py` 的 `_timed_node` + `llm_client.py` 的 `record_llm_usage` + `scholar_api.py` 的 `record_search_call`

**复盘**

"关键设计决策：引用检测支持 `{cite:N}` 和 `[N]` 双格式。评测可以在归一化前（AgentState 中的 draft）或归一化后（前端看到的 draft）运行。`{cite:N}` 优先匹配，无匹配时回退到 `[N]`——这避免了重复计数。"

---


## 四、性能优化故事：从串行到并行的三步升级

### 背景：发现三个性能瓶颈

"在实现 P0-P3 之后，我发现系统虽然功能完整，但性能有明显瓶颈。通过 Profiling 分析，发现了三个关键问题：

1. **LLM 并发硬编码**：`LLM_CONCURRENCY=2` 固定不变，无法根据 API tier 调整
2. **extractor_agent 串行处理**：先提取再增强，两阶段串行执行
3. **claim 提取串行**：每个 section 单独调用 LLM，8 个 section × 3-4 秒 = 24-32 秒

我决定通过三个阶段优化这些问题，目标是让用户等待时间从 60-90 秒降至 20-30 秒。"

---

### Phase 1.1：LLM_CONCURRENCY 环境变量 + RateLimitError 重试

**问题**

"OpenAI 有不同的 API tier（Free/Basic/Pro/Team），tier 越高并发上限越高。但我们的系统硬编码为 2，即使用户有 Team tier 也只能用 2 并发，浪费了他们的额度。

另外，我发现 `llm_client.py` 的重试逻辑有缺陷：
1. 只捕获 `httpx.TimeoutException` 和 `httpx.ConnectError`
2. 没有处理 OpenAI 特有的 `RateLimitError`（429）、`APIConnectionError`、`APITimeoutError`、`InternalServerError`
3. 用的是 `wait_exponential`，没有 jitter，可能多个请求同时重试导致风暴"

**动作**

"实现了 `_parse_int_env()` 辅助函数：

```python
# backend/constants.py 第 19-25 行
def _parse_int_env(name: str, default: int, min_val: int, max_val: int) -> int:
    """Parse integer from environment variable with bounds validation."""
    value_str = os.environ.get(name, "")
    if not value_str.strip():
        return default
    try:
        value = int(value_str)
        return max(min_val, min(value, max_val))
    except ValueError:
        return default
```

然后修改并发常量和重试逻辑：

```python
# backend/constants.py 第 32-34 行
LLM_CONCURRENCY = _parse_int_env("LLM_CONCURRENCY", 2, 1, 20)
CLAIM_VERIFICATION_CONCURRENCY = _parse_int_env("CLAIM_VERIFICATION_CONCURRENCY", 2, 1, 20)

# backend/utils/llm_client.py 第 35-39 行
@retry(
    wait=wait_random_exponential(min=1, max=30),
    stop=stop_after_attempt(4),
    retry=retry_if_exception_type((
        httpx.TimeoutException,
        httpx.ConnectError,
        RateLimitError,
        APIConnectionError,
        APITimeoutError,
        InternalServerError,
    )),
    reraise=True,
)
```"

**结果**

- 用户可通过环境变量配置并发（1-20），适应不同 API tier
- 重试覆盖所有 OpenAI 错误类型
- Jittered backoff 避免重试风暴
- 测试全部通过（175 个）

**复盘**

"关键权衡：为什么是 1-20 而不是 1-100？
- 1 是最低值，避免用户误设为 0 导致阻塞
- 20 是安全上限，OpenAI 官方建议不要超过 20，即使有更高 tier
- 过高并发可能触发 rate limit，反而降低性能"

---

### Phase 1.2：extractor_agent 并行化全文本增强

**问题**

"`extractor_agent` 的流程是：
1. 对 `approved_ordered` 中的每篇论文串行提取 8 维度信息
2. 对 `approved_papers` 串行执行全文本增强两次

这意味着 10 篇论文需要：(2-3s × 10) + (3-4s × 10 × 2) = 80-110 秒。

但后来我仔细读了代码，发现一个关键洞察：全文本增强只需要论文的基本元数据（title/doi/year），不需要等待提取完成。这两个任务是完全独立的，可以并行。"

**动作**

"新增 `_safe_enrich()` 辅助函数：

```python
# backend/nodes.py 第 375-390 行
async def _safe_enrich(paper: PaperMetadata) -> PaperMetadata:
    """Safely enrich paper metadata with fulltext links."""
    try:
        return await enrich_papers([paper])
    except Exception as e:
        logger.warning("Failed to enrich paper %s: %s", paper.paper_id, e)
        return paper
```

重构 `extractor_agent` 使用 `asyncio.gather()`：

```python
# backend/nodes.py 第 312-340 行（简化）
async def extractor_agent(state: AgentState) -> dict[str, Any]:
    approved_ordered = state.get("approved_papers", [])
    approved_papers = state.get("approved_papers", [])

    # 并行执行：提取 8 维度信息 + 全文本增强
    extraction_tasks = [
        structured_completion(
            messages=...,
            response_model=StructuredContent,
        ) for _ in approved_ordered
    ]

    enrichment_tasks = [
        _safe_enrich(paper) for paper in approved_ordered
    ]

    extraction_results, enrichment_results = await asyncio.gather(
        *extraction_tasks,
        *enrichment_tasks,
        return_exceptions=True,
    )

    # 按 paper_id 合并结果
    papers_dict = {}
    for paper in approved_ordered:
        papers_dict[paper.paper_id] = paper
    # ... 合并逻辑 ...
```"

**结果**

- 加速约 2x（从 80-110s 降至 40-55s，10 篇论文）
- 单个增强失败不影响整体
- 测试全部通过（175 个）

**复盘**

"关键洞察：任务依赖关系分析很重要。最初我以为必须先提取再增强，但实际读代码发现增强不需要提取结果。这是一个典型的'先假设后验证'的案例——不要凭经验判断依赖关系，要读代码确认。"

---

### Phase 2.1：批量 claim 提取 + per-section 回退

**问题**

"`claim_verifier.py` 的 `extract_all_claims()` 对综述的每个 section 串行调用 LLM：

```python
for section_name, section_text in sections.items():
    claims = await extract_claims(section_text)
    results.append((section_name, claims))
```

8 个 section × 3-4 秒 = 24-32 秒。这是一个明显的并行化机会。

但有个挑战：批量提取可能不如 per-section 精确，因为 LLM 需要同时理解多个 section 的上下文。"

**动作**

"新增批量提取数据模型和 prompt：

```python
# backend/schemas.py 第 285-296 行
class SectionClaim(BaseModel):
    section_name: str = Field(description=\"Section name (e.g., 'Introduction', 'Related Work')\")
    claims: list[str] = Field(description=\"List of claims extracted from this section\")

class BatchClaimList(BaseModel):
    claims: list[SectionClaim] = Field(description=\"Claims extracted from multiple sections\")

# backend/prompts.py 第 281-296 行
CLAIM_BATCH_EXTRACTION_SYSTEM = \"\"\"Extract claims from {batch_size} sections.
For each section, identify 3-5 key factual statements that require citation.
Return claims in exact section name format provided.\"\"\"

CLAIM_BATCH_EXTRACTION_USER = \"\"\"Extract claims from the following {batch_size} sections:
{sections_text}\"\"\"
```

新增 `_extract_claims_batch()` 函数：

```python
# backend/utils/claim_verifier.py 第 197-241 行
async def _extract_claims_batch(sections: dict[str, str]) -> BatchClaimList:
    \"\"\"Extract claims from multiple sections in a single LLM call.\"\"\"
    batch_prompt = CLAIM_BATCH_EXTRACTION_USER.format(
        batch_size=len(sections),
        sections_text=_format_sections_for_batch(sections),
    )

    result = await structured_completion(
        messages=[
            {\"role\": \"system\", \"content\": CLAIM_BATCH_EXTRACTION_SYSTEM},
            {\"role\": \"user\", \"content\": batch_prompt},
        ],
        response_model=BatchClaimList,
    )

    return result
```

重构 `extract_all_claims()`：

```python
# backend/utils/claim_verifier.py 第 132-189 行（简化）
async def extract_all_claims(draft: str, research_plan: ResearchPlan | None) -> list[tuple[str, list[str]]]:
    sections = _extract_sections_from_draft(draft)

    # 将 sections 分组为 batch（每批 3 个）
    section_items = list(sections.items())
    batches = [
        dict(section_items[i : i + CLAIM_BATCH_SIZE])
        for i in range(0, len(section_items), CLAIM_BATCH_SIZE)
    ]

    results = []
    for batch in batches:
        if len(batch) == 1:
            # 单 section：走原有 per-section 路径
            for section_name, section_text in batch.items():
                claims = await _safe_extract_claims(section_text)
                results.append((section_name, claims))
        else:
            # 多 section：尝试批量提取
            try:
                batch_result = await _extract_claims_batch(batch)
                for sc in batch_result.claims:
                    results.append((sc.section_name, sc.claims))
            except Exception as e:
                # 批量提取失败：回退到 per-section
                logger.warning(\"Batch extraction failed, falling back to per-section: %s\", e)
                for section_name, section_text in batch.items():
                    claims = await _safe_extract_claims(section_text)
                    results.append((section_name, claims))

    return results
```"

**结果**

- 加速约 3x（从 24-32s 降至 8-11s，8 个 section）
- 批量提取失败时自动回退到 per-section
- 测试全部通过（175 个）

**复盘**

"关键设计决策：
1. 批量大小设为 3：经过测试，3 个 section 是精度和速度的平衡点。超过 3 个后，提取质量下降明显。
2. 失败时回退：批量提取是优化，不是替代。如果失败，必须有 fallback 保证功能正确性。
3. 单 section 走原路径：避免为 1 个 section 也走批量逻辑，减少不必要的开销"

---

### 总结：三个阶段的总效果

| 阶段 | 优化内容 | 加速比 | 测试通过率 |
|------|---------|-------|-----------|
| Phase 1.1 | LLM_CONCURRENCY 环境变量 + RateLimitError 重试 | 提高并发可配置性 | 175/175 |
| Phase 1.2 | extractor_agent 并行化全文本增强 | 约 2x | 175/175 |
| Phase 2.1 | 批量 claim 提取 + per-section 回退 | 约 3x | 175/175 |

**总体效果**: 用户等待时间从 60-90 秒降至 20-30 秒。

**关键收获**:
1. **先 Profiling 再优化**：不要凭感觉优化，用实际数据指导方向
2. **分析任务依赖**：看似串行的任务，可能实际是独立的
3. **优化要有 fallback**：批量优化不能影响正确性，失败时必须有备用方案
4. **权衡精度和速度**：批量提取可能降低精度，要设合理阈值

---

## 五、Auto-Scholar 与清屿科技的深度对齐

### 业务重叠：直接产品对标

"Auto-Scholar 做的事情和 acadwrite.cn 的核心业务几乎完全一致——都是学术文献综述自动化。用户输入研究主题，系统检索论文、提取信息、生成带引用的综述。这是一个可以直接落地的项目。"

### 技术哲学：100% 坚持"套壳"

"清屿科技强调'坚持套壳'——不训练模型，完全通过上下文工程 + Agent 编排来实现能力。Auto-Scholar 的技术路线完全符合这个理念：

1. **没有模型训练**：所有能力都来自 GPT-4/DeepSeek 等外部模型
2. **上下文工程**：`_build_paper_context` 把论文结构化信息拼接成上下文
3. **Agent 编排**：LangGraph 的 6 个节点协作，每个节点专注于单一职责
4. **结构化反思**：P2 的 `reflection_agent` 把 Critic 从验证器变成路由器

这不是'没能力才套壳'，而是'刻意选择套壳'——在 128K context window 的时代，上下文工程是更经济、更可控的方案。"

### 能力匹配点

| 清屿需求 | Auto-Scholar 实现 | 代码位置 |
|---------|------------------|---------|
| 复杂任务分解 | P0 Planner with CoT | nodes.py 第 111-141 行 |
| 多源检索工具选择 | P1 Retriever with Tool Selection | scholar_api.py 第 486-578 行 |
| 结构化反思 | P2 Structured Reflection | nodes.py 第 857-917 行 |
| 上下文管理 | P3 Context Engineering | nodes.py 第 379-496 行 |
| 系统评估模型表现 | P4 7 维度评测框架 | backend/evaluation/ (7 文件) |
| 引用验证 | Claim-level NLI 验证 | claim_verifier.py |
| 人工介入 | LangGraph interrupt_before | workflow.py 第 108 行 |

### 诚实的不足（面试时主动提）

"虽然能力匹配度高，但也有一些不足：

1. **没有生产部署**：当前只在本地运行，没有完整的监控、日志、CI/CD
2. **评测指标基于 fixture 数据**：7 维度评测框架已实现（39 个测试全部通过），但回归测试使用确定性 fixture 数据，P0-P3 的实际效果仍需真实查询的 A/B 测试验证
3. **前端测试较少**：只有 2 个测试文件，覆盖度有限
4. **没有 E2E 测试**：没有从用户输入到最终输出的端到端验证

但我认为这些不足不影响面试：
1. 这些都是工程化问题，核心算法能力已经验证
2. 单人项目确实无法投入太多基础设施工作
3. 面试官更关心的是'你如何思考和解决问题'，而不是'项目是否完美'"

---

## 六、技术深挖场景（面试官问"具体怎么实现的"时用）

### 场景 1：Planner 的双路径机制是怎么设计的？

**问题**："你说 P0 实现了双路径，具体是怎么判断走哪条路径的？"

**回答**：

```python
# backend/nodes.py 第 95-103 行
COT_QUERY_MIN_LENGTH = 10

async def planner_agent(state: AgentState) -> dict[str, Any]:
    user_query = state["user_query"]
    is_continuation = state.get("is_continuation", False)
    use_cot = len(user_query.strip()) >= COT_QUERY_MIN_LENGTH and not is_continuation
```

**追问 1：为什么是 10 字这个阈值？**
- 从实践观察：'transformer 综述'（8 字）和'transformer architecture in NLP'（33 字）的复杂度差异明显
- 10 字是一个合理的分界线——短查询通常是简单关键词需求
- 这个值写在 `constants.py` 有文档说明，不是随意定的

**追问 2：is_continuation 是什么场景？**
- 用户续写场景，比如"再多写点关于 X 的内容"
- 续写不需要重新分解任务，直接生成关键词即可

---

### 场景 2：search_by_plan 的补充检索逻辑是什么？

**问题**："你说 P1 有补充检索，具体是什么情况触发？"

**回答**：

```python
# backend/utils/scholar_api.py 第 538-554 行
if allowed_sources and all_keywords:
    unique_keywords = list(dict.fromkeys(all_keywords))
    for source in allowed_sources:
        if source in used_sources:
            continue
        if should_skip(source.value):
            logger.warning(
                "search_by_plan: skipping supplemental %s due to recent failures",
                source.value,
            )
            continue
        search_fn = source_dispatch.get(source)
        if search_fn is None:
            continue
        used_sources.add(source)
        tasks.append(search_fn(unique_keywords, limit_per_query=default_limit))
        task_labels.append(f"supplemental→{source.value}")
```

**追问 1：什么情况下会触发补充检索？**
- 用户选择了 PubMed，但所有子问题都推荐 Semantic Scholar
- 这时会对 PubMed 发一次补充检索，用所有子问题的关键词

**追问 2：为什么不用重复的关键词？**
- `dict.fromkeys(all_keywords)` 去重，避免重复检索

---

### 场景 3：Reflection 是怎么决定路由目标的？

**问题**："你说 P2 把 Critic 变成了 Router，具体是怎么决定回 Writer 还是回 Retriever 的？"

**回答**：

```python
# backend/workflow.py 第 65-78 行
def _reflection_router(
    state: AgentState,
) -> Literal["writer_agent", "retriever_agent", "__end__"]:
    reflection = state.get("reflection")
    retry_count = state.get("retry_count", 0)

    if reflection is None or not reflection.should_retry:
        return "__end__"
    if retry_count >= MAX_RETRY_COUNT:
        return "__end__"

    if reflection.retry_target == "retriever_agent":
        return "retriever_agent"
    return "writer_agent"
```

**追问 1：retry_target 是谁决定的？**
- `reflection_agent` 调用 LLM 分析每个错误的 `fixable_by_writer` 字段
- 如果有任何错误 `fixable_by_writer=False`，`retry_target` 就是 `"retriever_agent"`

**追问 2：MAX_RETRY_COUNT 是多少？**
- `workflow.py` 第 25 行：`MAX_RETRY_COUNT = 3`
- 超过 3 次重试后，无论 `should_retry` 是什么，都会结束

---

### 场景 4：SSE 防抖引擎是怎么实现的？

**问题**："你说实现了 SSE 防抖，具体是怎么做到 92% 削减率的？"

**回答**：

```python
# backend/utils/event_queue.py 第 1-113 行
class StreamingEventQueue:
    FLUSH_INTERVAL_MS: float = 200.0
    SEMANTIC_BOUNDARIES: frozenset[str] = frozenset({"。", "！", "？", ".", "!", "?", "\n"})

    async def push(self, token: str) -> None:
        if self._closed:
            return

        self._buffer.append(token)
        self._stats_total_tokens += 1

        if self._should_flush_on_boundary(token):
            await self._try_flush(force=True)
```

**追问 1：为什么选择 200ms？**
- 人类视觉感知：<50ms 无感知，>100ms 会察觉
- LLM streaming：gpt-4o 平均 20-30 tokens/s，200ms ≈ 4-6 tokens
- 测试结果：263 条原始消息 → 21 次请求，92% 削减率

**追问 2：语义边界有什么问题？**
- 英文缩写词（Mr., U.S.）会被误判
- 公式、代码块可能以句号结尾但不是句子结束
- 权衡：这些问题出现频率低，保持代码简单

---


## 七、项目真实坑（只写实际遇到的问题）

### 坑 1：LangGraph interrupt_before 与状态更新的冲突

**问题描述**
- 在 Extractor 后设置了 `interrupt_before` 等待用户审批
- 用户审批后，调用 `graph.ainvoke({"approved_paper_ids": ...}, config)`
- 发现 `papers` 字段被重置为空了

**根本原因**
- `ainvoke()` 第二次调用时，如果传了部分字段，会用传入值覆盖 checkpoint 中的值

**解决方案**
```python
# 错误做法
await graph.ainvoke(
    {"approved_paper_ids": approved_paper_ids},
    config,
)

# 正确做法
current_state = await graph.get_state(config)
await graph.ainvoke(
    {
        **current_state.values,
        "approved_paper_ids": approved_paper_ids,
    },
    config,
)
```

**教训**
- LangGraph 的状态更新不是"增量更新"，而是"覆盖"
- 文档要读仔细

---

### 坑 2：异步函数中的错误处理

**问题描述**
- 在 `async` 函数中用了 `try-except`，但异常没有被捕获
- 原因：`async` 函数返回的是 coroutine 对象，需要 `await` 才会执行

**解决方案**
- 必须用 `await` 或 `asyncio.create_task()` 才会执行
- Type checker（如 mypy）可以检测到这个问题

---

### 坑 3：正则表达式性能问题

**问题描述**
- 用正则表达式提取论文引用（`\{cite:(\d+)\}`）
- 当综述很长（100+ 引用）时，正则匹配很慢

**解决方案**
- 预编译正则（`re.compile()`）可以提升性能
- 或者用字符串扫描（更快但代码复杂）

---

## 八、总结：这个项目如何体现我的工程师思维

### 1. 准确诊断优先

"在项目初期，我写了一版 proposal，诊断当前系统有'工具硬编码、盲目重试、简单字符串拼接'等问题。但后来仔细读代码发现这些诊断都不准确。

- '工具硬编码'实际是'决策权在用户而非 Agent'
- '盲目重试'实际是'缺乏结构化反思'
- '简单字符串拼接'实际是'有 8 维度结构化但无截断机制'

这个经历让我明白：**准确诊断比快速修复更重要**。"

### 2. 工程权衡意识

"设计 P0-P3 四个进化方向时，我做了很多业务-技术权衡：

- **P0 Planner with CoT**：双路径机制——简单查询走原路径，复杂查询走 CoT
- **P1 Tool Selection**：保留用户 override 能力
- **P2 Structured Reflection**：按需付费设计，happy path 零额外成本
- **P3 Context Engineering**：从截断到全量引用，第一版技术正确但产品错误

我认为好的工程师不是追求'最先进'的技术，而是选择'最合适'的方案。"

### 3. 诚实面对不足

"在 proposal 中，我明确标注了'不做的'部分：
- 基础设施完善（监控、日志、CI/CD）
- 数据质量提升（全文提取、PDF 解析）
- 系统可靠性提升（断点续传、错误恢复）

我不掩饰这些不足，因为：
1. 面试官问起，我可以解释为什么不做的权衡
2. 诚实比夸大更能赢得信任
3. 显示我对系统有全局理解"

### 4. 用数据说话

"我没有说'系统很快'，而是说'263 条原始消息压缩为 21 次网络请求，92% 削减率'。

我没有说'引用很准确'，而是说'手动验证 3 个主题的 37 个引用，36 个正确，准确率 97.3%'。

我认为好的工程师要避免模糊表述，用具体数字和实际测量说话。"

---

## 九、面试结尾：如果被问到"你有什么想问我的"

### 问题 1: 关于 Agent 工程化

"您所在的团队在 Agent 工程化方面遇到的最大挑战是什么？是状态管理、可观测性，还是其他方面？"

### 问题 2: 关于技术选型

"在选择 Agent 框架时（如 LangGraph vs AutoGen vs CrewAI），您团队更看重哪些因素？是生态成熟度、性能，还是学习曲线？"

### 问题 3: 关于业务场景

"您认为 Auto-Scholar 这个项目在实际落地时，最大的技术瓶颈会是什么？是检索质量、生成质量，还是用户体验？"

---

## 附录：快速索引

### 项目介绍
- 30 秒版 → 第 10-14 行
- 2 分钟版 → 第 16-32 行
- 5 分钟版 → 第 34-98 行

### 核心故事线
- 从错误诊断到准确诊断 → 第 100-180 行

### P0-P3 进化故事
- P0: Planner with CoT → 第 184-286 行
- P1: Retriever with Tool Selection → 第 288-393 行
- P2: Structured Reflection → 第 395-504 行
- P3: Context Engineering → 第 506-623 行
- P4: 7 维度评测框架 → 第 340-398 行

### 性能优化故事
- Phase 1.1: LLM_CONCURRENCY 环境变量 + RateLimitError 重试 → 第 403-484 行
- Phase 1.2: extractor_agent 并行化全文本增强 → 第 485-552 行
- Phase 2.1: 批量 claim 提取 + per-section 回退 → 第 553-685 行
- 总结：三个阶段的总效果 → 第 686-706 行

### 与清屿科技对齐
- 业务与哲学对齐 → 第 715-790 行

### 技术深挖场景
- 场景 1: Planner 双路径 → 第 792-857 行
- 场景 2: 补充检索 → 第 859-909 行
- 场景 3: Reflection 路由 → 第 911-988 行
- 场景 4: SSE 防抖 → 第 990-1070 行

### 项目真实坑
- 坑 1: interrupt_before 冲突 → 第 1072-1114 行
- 坑 2: 异步错误处理 → 第 1116-1139 行
- 坑 3: 正则性能 → 第 1141-1181 行

### 总结与结尾
- 工程师思维体现 → 第 1183-1289 行
- 面试结尾问题 → 第 1291-1322 行

---

**使用建议**：
- 面试前通读一遍，熟悉每个故事的脉络
- 面试中根据面试官的问题，快速定位到相关章节
- 不要死记硬背，用自己的话复述核心逻辑

