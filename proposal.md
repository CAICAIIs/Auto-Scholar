# Auto-Scholar 项目进化方案

> 面向清屿科技 AI Agent 算法工程师岗位的候选者项目升级计划

**项目名称**: Auto-Scholar 学术研究自动化系统
**目标岗位**: 清屿科技 - AI Agent 算法工程师（JD 聚焦 Agent 系统设计与实现）
**当前定位**: 工程化 RAG Pipeline（检索增强生成）→ 进化为真正的 Multi-Agent 系统
**核心主张**: 在保留现有工程优势的基础上，补齐 Agent 系统缺失的核心能力，展现对复杂 Agent 设计的系统性思考

---

## 引言：诚实诊断——当前项目定位

### 一、项目现状：工程化 RAG Pipeline，而非 Multi-Agent System

#### 1.1 已经做得好的地方（工程层面）

| 工程实践 | 具体实现 | 价值 |
|---------|---------|------|
| **LangGraph 工作流编排** | 5 个 Agent 节点 + 条件路由 + checkpoint 持久化 | 代码结构清晰，支持断点恢复 |
| **SSE 流式输出 + 防抖** | `StreamingEventQueue` 实现 92% 网络请求削减 | 用户体验优秀，降低后端压力 |
| **多源检索并行 + 去重** | 并行查询 Semantic Scholar / arXiv / PubMed，标题标准化去重 | 提升召回率，避免重复内容 |
| **结构化信息提取** | 8 维度元数据提取（problem/method/novelty/dataset/baseline/results/limitations/future_work） | 信息完整性高，便于后续处理 |
| **引用验证系统** | Claim-level 验证：提取原子声明 → NLI 蕴含判断 → 最低蕴含率阈值 | 超越简单的引用索引检查 |
| **Human-in-the-Loop** | `interrupt_before=["extractor_agent"]`，用户审批论文后才继续 | 质量可控，符合学术规范 |

**结论**: 工程化扎实，代码质量高，但缺失 **Agent 核心能力**。

---

#### 1.2 面向 AI Agent 算法工程师岗位的缺失

| 核心能力 | 当前实现 | 实际差距 | 缺失程度 |
|---------|---------|---------|---------|
| **任务分解** | `planner_agent` 仅生成关键词列表（`KeywordPlan`），无子问题分解 | 无法将"AI Agent 在医疗领域的应用"拆分为诊断/药物/管理等子问题 | 严重缺失 |
| **工具选择** | `search_sources` 由前端传入，Agent 自身不做选择决策 | 工具选择权在用户而非 Agent，缺乏自主性 | 中度缺失 |
| **推理链** | 无显式 CoT 推理，`planner_agent` 直接输出关键词 | 无法回答"为什么选择这些关键词"、"为什么分解为这些子问题" | 严重缺失 |
| **反思机制** | `critic_agent` 检测错误 → `qa_errors` 传递给 `writer_agent` 重试 | 已有错误传递，但缺乏结构化反思（错误分类、修复策略选择、是否值得重试的判断） | 中度缺失 |
| **上下文管理** | `_build_paper_context` 使用 8 维度结构化信息 | 已有结构化上下文，但缺乏 token 预算管理和基于相关性的选择策略 | 轻度缺失 |

### 二、核心结论

当前系统 Agent 能力分布不均：

1. **"多智能体"需要重新定义**: 5 个 Agent 节点是线性调用，缺乏真正的自主决策（如 Planner 不做任务分解，Retriever 不做工具选择）
2. **"工具选择"已有基础但不完整**: `search_sources` 支持动态配置，但决策权在用户而非 Agent
3. **"质量评估"已有基础但不深入**: `critic_agent` 已有 claim-level 验证和错误传递，但缺乏结构化反思
4. **"上下文构建"已有基础但不精细**: 8 维度结构化提取已经很好，但缺乏 token 预算管理

### 三、本进化方案的目标

1. **不改变工程优势**: 保留 LangGraph、SSE、多源检索、claim-level 验证等工程实践
2. **补齐 Agent 核心能力**: 聚焦 Planner-CoT 和 Reflection 两个最大缺口
3. **展现系统性思考**: 每个技术决策都明确"业务-技术权衡"，能向面试官解释"为什么这样做"
4. **避免技术堆砌**: 明确拒绝"看起来高大上但无业务价值"的技术


---

## 第一部分：P0-P3 进化方向（按 JD 能力优先级排序）

### P0：Planner with Chain-of-Thought（2-3 天）✅ 已实现

**JD 对应能力**: 复杂任务规划 - 将复杂任务分解为可执行的子任务

**实现状态**: 已完成（2026-02-23）

#### 实际实现内容

1. **新增数据模型**（`backend/schemas.py`）:
   - `SubQuestion`: question, keywords, preferred_source, estimated_papers, priority
   - `ResearchPlan`: reasoning（CoT 推理链）, sub_questions, total_estimated_papers

2. **CoT Prompt**（`backend/prompts.py`）:
   - `PLANNER_COT_SYSTEM`: 4 步推理引导（分析查询 → 分解子问题 → 分配数据源/优先级 → 解释推理）

3. **planner_agent 双路径**（`backend/nodes.py`）:
   - 复杂查询（≥10 字符）：使用 `PLANNER_COT_SYSTEM` + `ResearchPlan` 模型，生成子问题分解和推理链
   - 简单查询（<10 字符）或续写：使用原有 `KEYWORD_GENERATION_SYSTEM` + `KeywordPlan` 模型
   - 两条路径都输出 `search_keywords`，保持与 `retriever_agent` 的向后兼容

4. **状态更新**（`backend/state.py` + `backend/main.py`）:
   - `AgentState` 新增 `research_plan: ResearchPlan | None` 字段
   - 初始状态设置 `research_plan: None`

#### 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| CoT 跳过阈值 | 查询长度 < 10 字符 | 简单查询（如"transformer 综述"）CoT 反而增加延迟 |
| 续写查询跳过 CoT | 是 | 续写场景已有上下文，不需要重新分解 |
| ResearchPlan 放在 schemas.py | 是 | 公共模型，P1 的 retriever_agent 也需要读取 |
| 保留 KeywordPlan | 是 | 简单查询路径仍使用，避免不必要的 LLM token 消耗 |

#### 当前问题

```python
# backend/nodes.py - planner_agent 的当前实现（简化）

class KeywordPlan(BaseModel):
    keywords: list[str]

async def planner_agent(state: AgentState) -> dict[str, Any]:
    user_query = state["user_query"]
    messages = state.get("messages", [])

    result = await structured_completion(
        messages=[
            {"role": "system", "content": KEYWORD_GENERATION_SYSTEM},
            {"role": "user", "content": user_query},
        ],
        response_model=KeywordPlan,
    )

    keywords = result.keywords[:MAX_KEYWORDS]
    return {
        "search_keywords": keywords,
        "logs": [f"Generated {len(keywords)} search keywords: {keywords}"],
        "current_agent": "planner",
        "agent_handoffs": ["→planner"],
    }
```

**问题分析**:
1. **输出仅为关键词列表**: `KeywordPlan` 只有 `keywords: list[str]`，没有子问题、没有检索策略、没有推理过程
2. **无任务分解**: 用户查询"AI Agent 在医疗领域的应用"，Planner 直接输出 `["AI Agent", "medical", "healthcare"]`，无法识别需要分解为"诊断"、"药物研发"、"患者管理"等子问题
3. **无推理链**: 无法解释"为什么选择这些关键词"——因为 LLM 的推理过程是隐式的，没有被捕获
4. **无检索策略**: 所有关键词使用相同的检索方式，无法针对不同子问题选择不同数据源

#### 进化方案

**Step 1: 定义新的数据模型**

```python
# backend/schemas.py - 新增 ResearchPlan 模型

class SubQuestion(BaseModel):
    """子问题：将复杂任务分解为可执行单元"""
    question: str = Field(description="子问题描述")
    keywords: list[str] = Field(description="针对该子问题的检索关键词", min_length=2, max_length=5)
    preferred_source: PaperSource = Field(description="推荐的检索数据源")
    estimated_papers: int = Field(description="估计需要多少篇论文", ge=3, le=15)
    priority: int = Field(description="优先级，1 最高", ge=1, le=5)

class ResearchPlan(BaseModel):
    """研究规划：包含任务分解和推理链"""
    reasoning: str = Field(description="推理过程：为什么这样分解、为什么选择这些策略")
    sub_questions: list[SubQuestion] = Field(description="分解后的子问题列表")
    total_estimated_papers: int = Field(description="预计需要检索的总论文数")
```

**Step 2: 使用 Chain-of-Thought 指导 LLM 生成规划**

```python
# backend/nodes.py - planner_agent 的进化版本

async def planner_agent(state: AgentState) -> dict[str, Any]:
    user_query = state["user_query"]
    is_continuation = state.get("is_continuation", False)
    messages = state.get("messages", [])

    system_content = PLANNER_COT_SYSTEM  # 新的 CoT prompt

    if is_continuation and messages:
        conversation_context = _build_conversation_context(messages)
        system_content += KEYWORD_GENERATION_CONTINUATION.format(
            conversation_context=conversation_context
        )

    result = await structured_completion(
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_query},
        ],
        response_model=ResearchPlan,
    )

    # 从子问题中提取关键词（向后兼容）
    all_keywords = []
    for sq in result.sub_questions:
        all_keywords.extend(sq.keywords)
    unique_keywords = list(dict.fromkeys(all_keywords))[:MAX_KEYWORDS]

    logs = [
        f"Research plan: {len(result.sub_questions)} sub-questions",
        f"Reasoning: {result.reasoning[:200]}...",
        f"Keywords: {unique_keywords}",
    ]

    return {
        "search_keywords": unique_keywords,
        "research_plan": result,  # 新增字段
        "logs": logs,
        "current_agent": "planner",
        "agent_handoffs": ["→planner"],
    }
```

**Step 3: 更新 AgentState**

```python
# backend/state.py - 新增 research_plan 字段

class AgentState(TypedDict):
    # ... 现有字段保持不变 ...
    research_plan: ResearchPlan | None  # 新增
```

#### 业务-技术权衡分析

| 维度 | 优势 | 成本 | 权衡决策 |
|------|------|------|---------|
| **任务分解能力** | 能处理复杂查询，提升召回率和相关性 | 每次规划增加 ~500-1000 output tokens（约 $0.01-0.03） | **值得** - 复杂任务必须分解 |
| **推理链透明度** | 可向用户展示"为什么这样分解"，提升信任 | reasoning 字段占用额外 tokens | **值得** - 展现系统性思考 |
| **用户等待时间** | 规划更精准，减少后续无效检索 | 规划阶段增加 2-3 秒延迟 | **权衡** - 对简单查询（如"transformer 综述"）可能不值得，可设阈值：查询长度 < 10 字时跳过 CoT |
| **向后兼容** | 仍输出 `search_keywords`，不破坏下游 | 需要维护两套字段 | **值得** - 渐进式升级 |

**注意：对于简单查询，CoT 分解反而增加延迟和成本，不值得。** 可以设计一个简单的启发式规则：查询长度 < 10 字或不包含"领域"、"应用"、"对比"等关键词时，跳过 CoT 直接生成关键词。


---

### P1：Retriever with LLM-Driven Tool Selection（1-2 天）✅ 已实现

**JD 对应能力**: 工具调用及复杂任务规划 - Agent 自主决定使用哪个工具

**实现状态**: 已完成（2026-02-23）

#### 实际实现内容

1. **新增 `search_by_plan()`**（`backend/utils/scholar_api.py`）:
   - 接收 `ResearchPlan`，为每个 `SubQuestion` 按其 `preferred_source` 和 `estimated_papers` 发起独立检索
   - 所有子问题检索并行执行（`asyncio.gather`），跨子问题结果去重
   - 自动跳过近期失败的数据源（复用 `source_tracker`）

2. **`retriever_agent` 双路径**（`backend/nodes.py`）:
   - 有 `research_plan` 且含子问题时：调用 `search_by_plan()`，每个子问题使用 LLM 推荐的数据源
   - 无 `research_plan` 或子问题为空时：走原有 `search_papers_multi_source()` 路径，完全向后兼容

3. **测试覆盖**（`tests/test_plan_retrieval.py`）:
   - 11 个测试用例：空计划、单子问题、多源差异化检索、跨子问题去重、数据源故障跳过、搜索失败容错、retriever 分支逻辑

#### 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 子问题并行而非串行 | `asyncio.gather` | 子问题间无依赖，并行可将 N 次检索耗时降为 1 次 |
| 复用已有 `search_semantic_scholar/arxiv/pubmed` | 是 | 避免重复代码，复用已有的重试、去重、错误处理逻辑 |
| 向后兼容分支 | `if research_plan and research_plan.sub_questions` | 简单查询和续写场景不生成 plan，必须保留原路径 |
| `search_by_plan` 放在 `scholar_api.py` | 是 | 与其他搜索函数同层，便于测试和复用 |

#### 当前问题

```python
# backend/nodes.py - retriever_agent 的当前实现（简化）

async def retriever_agent(state: AgentState) -> dict[str, Any]:
    keywords = state.get("search_keywords", [])
    sources = state.get("search_sources", [PaperSource.SEMANTIC_SCHOLAR])

    papers = await search_papers_multi_source(
        keywords, sources=sources, limit_per_query=PAPERS_PER_QUERY
    )

    return {
        "candidate_papers": papers,
        "logs": [f"Found {len(papers)} unique papers ..."],
        ...
    }
```

**准确诊断**（注意：不是"硬编码 3 个工具"）:
1. **已有动态数据源支持**: `search_sources` 从 state 读取，前端可传入不同 sources 组合——这是好的工程设计
2. **但工具选择权在用户而非 Agent**: 用户在前端勾选数据源，Agent 只是执行。JD 要求的"工具调用"是 Agent 自主决策
3. **所有关键词使用相同数据源**: 即使 P0 分解了子问题，当前 Retriever 也无法为不同子问题选择不同数据源
4. **无检索结果质量评估**: 检索后直接返回，不评估结果是否满足子问题需求

#### 进化方案

**核心改动**: 让 Retriever 利用 P0 的 `research_plan`，为每个子问题选择合适的数据源。

```python
# backend/nodes.py - retriever_agent 的进化版本

async def retriever_agent(state: AgentState) -> dict[str, Any]:
    keywords = state.get("search_keywords", [])
    research_plan = state.get("research_plan")
    default_sources = state.get("search_sources", [PaperSource.SEMANTIC_SCHOLAR])

    if research_plan and research_plan.sub_questions:
        # 新路径：基于子问题的差异化检索
        all_papers = []
        for sq in research_plan.sub_questions:
            source = sq.preferred_source  # P0 已为每个子问题推荐数据源
            papers = await search_papers_multi_source(
                sq.keywords,
                sources=[source],
                limit_per_query=sq.estimated_papers,
            )
            all_papers.extend(papers)

        # 跨子问题去重
        papers = _deduplicate_papers(all_papers)
    else:
        # 向后兼容：原有路径
        papers = await search_papers_multi_source(
            keywords, sources=default_sources, limit_per_query=PAPERS_PER_QUERY
        )

    return {
        "candidate_papers": papers,
        "logs": [...],
        ...
    }
```

#### 业务-技术权衡分析

| 维度 | 优势 | 成本 | 权衡决策 |
|------|------|------|---------|
| **Agent 自主性** | 工具选择权从用户转移到 Agent | 用户失去直接控制 | **权衡** - 保留用户 override 能力，Agent 推荐但用户可覆盖 |
| **子问题适配** | 医疗用 PubMed，CS 用 arXiv | 需要 P0 先完成 | **值得** - 利用 P0 成果 |
| **API 调用量** | 可能增加（每个子问题单独检索） | 更多 API 调用 = 更高成本和延迟 | **权衡** - 对于 2-3 个子问题可接受，超过 5 个需要合并策略 |
| **向后兼容** | 无 research_plan 时走原有路径 | 需要维护两条路径 | **值得** - 渐进式升级 |

**注意：如果子问题过多（>5），为每个子问题单独检索会导致 API 调用量爆炸。** 需要设计合并策略：相似子问题合并检索，或设置最大并行检索数。


---

### P2：Structured Reflection Mechanism（2-3 天）✅ 已实现

**JD 对应能力**: 系统评估模型的表现提升 - 通过结构化反思迭代改进输出质量

**实现状态**: 已完成（2026-02-23）

#### 实际实现内容

1. **新增数据模型**（`backend/schemas.py`）:
   - `ErrorCategory(StrEnum)`: 5 类错误分类（citation_out_of_bounds, missing_citation, uncited_paper, low_entailment, structural）
   - `ReflectionEntry`: error_category, error_detail, fix_strategy, fixable_by_writer
   - `Reflection`: entries, should_retry, retry_target, summary

2. **Reflection Prompt**（`backend/prompts.py`）:
   - `REFLECTION_SYSTEM`: 引导 LLM 对每个错误分类、生成修复策略、判断是否 writer 可修复
   - `REFLECTION_USER`: 传入论文数量、重试次数、错误列表
   - `DRAFT_REFLECTION_RETRY_ADDENDUM`: writer 重试时使用的结构化修复指令模板

3. **reflection_agent 节点**（`backend/nodes.py`）:
   - 无错误时跳过（零额外成本）
   - 有错误时调用 LLM 生成结构化反思，统计 writer-fixable vs retriever-needed 数量
   - 输出 `reflection` 字段供下游路由和 writer 使用

4. **工作流更新**（`backend/workflow.py`）:
   - 新路由：critic → `_qa_router` → reflection_agent → `_reflection_router` → writer/retriever/__end__
   - `_qa_router`: 有错误 → reflection_agent，无错误 → __end__
   - `_reflection_router`: 根据 reflection.should_retry 和 retry_target 决定路由，尊重 MAX_RETRY_COUNT

5. **writer_agent 增强**（`backend/nodes.py`）:
   - 有 reflection 时：从 entries 提取 `[category] fix_strategy` 列表，使用 `DRAFT_REFLECTION_RETRY_ADDENDUM`
   - 无 reflection 时：回退到原有 `DRAFT_RETRY_ADDENDUM`，完全向后兼容

6. **状态更新**（`backend/state.py` + `backend/main.py`）:
   - `AgentState` 新增 `reflection: Reflection | None` 字段
   - 初始状态设置 `reflection: None`

7. **测试覆盖**（`tests/test_reflection.py`）:
   - 18 个测试用例：QA 路由（3）、反思路由（5）、reflection_agent 节点（4）、writer 集成（2）、schema 验证（4）

#### 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| reflection 仅在有错误时触发 | 是 | happy path 零额外成本（"按需付费"设计） |
| 保留 qa_errors 字段 | 是 | 向后兼容，reflection 是增强而非替代 |
| retry_target 支持 retriever_agent | 是 | 区分"writer 能修"和"需要更多论文"两种场景 |
| writer 回退到 DRAFT_RETRY_ADDENDUM | 是 | 无 reflection 时（如 LLM 调用失败）仍能重试 |
| 未知 retry_target 默认 writer_agent | 是 | 防御性编程，避免 LLM 输出非预期值导致路由失败 |

#### 当前问题

```python
# backend/workflow.py - 当前的 QA 路由

def _qa_router(state: AgentState) -> Literal["writer_agent", "__end__"]:
    qa_errors = state.get("qa_errors", [])
    retry_count = state.get("retry_count", 0)
    if not qa_errors:
        return "__end__"
    if retry_count < MAX_RETRY_COUNT:
        return "writer_agent"
    return "__end__"

# backend/nodes.py - writer_agent 重试时接收错误信息

if is_retry:
    top_errors = qa_errors[:3]
    error_list = "\n".join(f"- {e}" for e in top_errors)
    system_prompt += DRAFT_RETRY_ADDENDUM.format(
        error_count=len(qa_errors),
        error_list=error_list,
        num_papers=num_papers,
    )
```

**准确诊断**（注意：不是"盲目重试"）:
1. **已有错误传递**: `critic_agent` 检测到的 `qa_errors` 会通过 `DRAFT_RETRY_ADDENDUM` 传递给 `writer_agent`——这比盲目重试好很多
2. **但缺乏结构化反思**: 错误以字符串列表传递（如 `"Section 2: No citations found"`），Writer 需要自己理解错误含义和修复方式
3. **无错误分类**: 不区分"引用索引越界"（需要修正索引）和"缺少引用"（需要添加引用）——这两种错误的修复策略完全不同
4. **无"是否值得重试"的判断**: 如果错误是"检索结果不足导致无法引用"，重试 Writer 无法解决，应该回到 Retriever
5. **无反思记录**: 每次重试的错误和修复策略没有被记录，无法分析系统的迭代模式

#### 进化方案

**Step 1: 定义结构化反思模型**

```python
# backend/schemas.py - 新增 Reflection 模型

class ErrorCategory(StrEnum):
    CITATION_OUT_OF_BOUNDS = "citation_out_of_bounds"  # 引用索引越界
    MISSING_CITATION = "missing_citation"              # 缺少引用
    UNCITED_PAPER = "uncited_paper"                    # 论文未被引用
    LOW_ENTAILMENT = "low_entailment"                  # 引用不支持声明
    STRUCTURAL = "structural"                          # 结构性问题

class ReflectionEntry(BaseModel):
    """单条反思记录"""
    error_category: ErrorCategory
    error_detail: str
    fix_strategy: str = Field(description="具体修复策略")
    fixable_by_writer: bool = Field(description="Writer 能否修复，还是需要回到 Retriever")

class Reflection(BaseModel):
    """结构化反思"""
    entries: list[ReflectionEntry]
    should_retry: bool
    retry_target: str = Field(description="'writer' 或 'retriever'")
    summary: str = Field(description="反思总结")
```

**Step 2: 实现反思节点**

```python
# backend/nodes.py - 新增 reflection_agent

async def reflection_agent(state: AgentState) -> dict[str, Any]:
    """反思节点：分析 critic 的错误，生成结构化修复策略"""
    qa_errors = state.get("qa_errors", [])
    retry_count = state.get("retry_count", 0)

    reflection = await structured_completion(
        messages=[
            {"role": "system", "content": REFLECTION_SYSTEM},
            {"role": "user", "content": f"QA errors:\n" + "\n".join(f"- {e}" for e in qa_errors)},
        ],
        response_model=Reflection,
    )

    logs = [
        f"Reflection: {len(reflection.entries)} errors analyzed",
        f"Reflection: retry target = {reflection.retry_target}",
        f"Reflection: {reflection.summary[:150]}...",
    ]

    return {
        "reflection": reflection,
        "logs": logs,
        "current_agent": "reflection",
        "agent_handoffs": ["critic→reflection"],
    }
```

**Step 3: 更新工作流**

```python
# backend/workflow.py - 添加反思节点

g.add_node("reflection_agent", _timed_reflection_agent)

# critic → reflection（替代原来的 critic → writer/end）
g.add_edge("critic_agent", "reflection_agent")

# reflection 决定路由
def _reflection_router(state: AgentState) -> Literal["writer_agent", "retriever_agent", "__end__"]:
    reflection = state.get("reflection")
    retry_count = state.get("retry_count", 0)

    if reflection is None or not reflection.should_retry:
        return "__end__"
    if retry_count >= MAX_RETRY_COUNT:
        return "__end__"
    return reflection.retry_target + "_agent"

g.add_conditional_edges("reflection_agent", _reflection_router)
```

#### 业务-技术权衡分析

| 维度 | 优势 | 成本 | 权衡决策 |
|------|------|------|---------|
| **迭代精准度** | 结构化错误分类 + 针对性修复策略 | 每次反思增加一次 LLM 调用（~300-800 output tokens，约 $0.01-0.02） | **值得** - 提升迭代成功率 |
| **智能路由** | 区分"Writer 能修"和"需要回 Retriever" | 增加工作流复杂度 | **值得** - 避免无效重试 |
| **可观测性** | 反思记录可用于分析系统迭代模式 | 需要存储反思历史 | **值得** - 长期优化依据 |
| **延迟** | 每次重试增加一次 LLM 调用 | 增加 1-2 秒 | **权衡** - 如果 critic 已经通过（无错误），reflection 不会被触发，零额外成本 |

**注意：当 critic 通过时（`qa_errors` 为空），reflection 节点不会被触发。** 只有在需要重试时才增加成本，这是一个"按需付费"的设计。


---

### P3：Context Engineering（1-2 天）✅ 已实现

**JD 对应能力**: 复杂任务规划 + 成本控制 - 管理上下文预算，确保系统在大规模场景下稳定运行

**实现状态**: 已完成（2026-02-23），经历两次设计迭代

#### 设计迭代过程

**第一版（过度截断）**：添加 `CONTEXT_MAX_PAPERS=25` + `CONTEXT_TOKEN_BUDGET=6000`，在 extractor 中截断到 25 篇再提取。问题：学术综述的价值在于引用覆盖面，用户审批了 76 篇论文就应该引用 76 篇，截断到 25 篇违背了产品目标。

**第二版（当前实现）**：移除激进截断，提取并引用所有用户审批的论文。`CONTEXT_MAX_PAPERS=200` + `CONTEXT_TOKEN_BUDGET=40000` 仅作为极端情况的安全阀（如 bug 导致批准数千篇论文），正常流程永远不会触发。

**关键洞察**：76 篇论文的 paper_context ≈ 13,450 tokens，仅占 128K context window 的 10.5%。截断是不必要的。

#### 实际实现内容

1. **安全阀常量**（`backend/constants.py`）:
   - `CONTEXT_TOKEN_BUDGET = 40000`: 安全阀，正常流程不触发（100 篇 ≈ 18K tokens）
   - `CONTEXT_TOKENS_PER_PAPER_ESTIMATE = 180`: 每篇论文的平均 token 估算
   - `CONTEXT_MAX_PAPERS = 200`: 安全阀，防止病态场景
   - `CONTEXT_OVERFLOW_WARNING_THRESHOLD = 100`: 超过 100 篇输出 warning
   - `PAPERS_PER_QUERY = 5`（从 10 降低）: 减少候选论文数量，提高相关性

2. **AgentState 新增字段**（`backend/state.py`）:
   - `selected_papers: list[PaperMetadata]`: extractor 输出的已提取论文列表（正常情况下 = 全部 approved_papers）

3. **extractor_agent**（`backend/nodes.py`）:
   - 用 `_prioritize_by_sub_questions` 按子问题覆盖度排序（影响提取顺序，不截断）
   - 提取所有 approved papers，仅在超过 200 篇时触发安全阀
   - 输出 `selected_papers` = 全部已提取论文

4. **_build_paper_context**（`backend/nodes.py`）:
   - Token 预算 40K 作为安全阀，正常流程不截断
   - `_estimate_paper_tokens` 用 word count × 1.3 粗略估算

5. **下游节点**（`backend/nodes.py` + `backend/main.py`）:
   - writer/critic/reflection/main.py 用 `selected_papers or approved_papers` with legacy fallback

6. **测试覆盖**（`tests/test_context_engineering.py`）:
   - 24 个测试用例：token 估算（4）、关键词匹配（5）、子问题优先排序（4）、上下文构建（8）、集成测试（3）

#### 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 不截断，引用所有审批论文 | 是 | 学术综述的价值在于引用覆盖面，76 篇 ≈ 13K tokens 仅占 128K 窗口的 10.5% |
| 安全阀 200 篇 / 40K tokens | 是 | 防止病态场景（bug 导致数千篇），正常流程永远不触发 |
| 子问题优先排序影响顺序不截断 | 是 | 确保每个子问题的代表论文排在前面，但不丢弃任何论文 |
| Token 估算用 word × 1.3 而非 tiktoken | 是 | 不引入额外依赖，安全阀场景下精度不重要 |
| PAPERS_PER_QUERY 从 10 降到 5 | 是 | 减少候选论文数量，提高相关性，而非靠截断控制数量 |
| `selected_papers` 字段保留 | 是 | 提供 legacy checkpoint 兼容，且语义清晰（已提取的论文） |

#### 设计迭代故事（面试可讲）

**第一次诊断（错误）**：判断"当前 3-10 篇论文，远低于 128K 限制，不需要 Context Engineering"。忽略了多源检索和多轮对话的累积效应。

**第二次设计（过度）**：添加 `CONTEXT_MAX_PAPERS=25` 截断 + `CONTEXT_TOKEN_BUDGET=6000`，并设计了 select-before-extract 架构。技术上正确，但违背了产品目标——学术综述应该引用所有用户选择的论文。

**第三次设计（当前）**：移除激进截断，提取并引用所有审批论文。安全阀仅防止病态场景。核心认知：76 篇 × 177 tokens ≈ 13K tokens，仅占 128K 窗口的 10.5%，截断是不必要的。

**教训**：Context Engineering 不等于"截断"。在 context window 足够大的情况下，正确的做法是充分利用窗口，而非过早优化。

#### 业务-技术权衡分析

| 维度 | 优势 | 成本 | 权衡决策 |
|------|------|------|---------|
| **全量引用** | 综述引用覆盖面最大化，用户审批的论文全部被引用 | 提取成本与论文数成正比 | **值得** - 这是产品核心价值 |
| **子问题排序** | 确保每个子问题的代表论文排在前面 | 需要关键词匹配逻辑 | **值得** - 提升综述结构质量 |
| **安全阀** | 防止病态场景（bug 导致数千篇） | 极少触发，几乎零成本 | **值得** - 防御性编程 |
| **不做 embedding/LLM 压缩** | 零额外延迟和成本 | 无法按语义相关性排序 | **可接受** - 当前规模不需要 |


---

### P4：7 维度自动化评测框架（1-2 天）✅ 已实现

**JD 对应能力**: 系统评估模型的表现提升 - 建立量化评测体系，数据驱动优化

**实现状态**: 已完成（2026-02-23）

#### 实际实现内容

1. **评测模块**（`backend/evaluation/`，7 个文件）:
   - `schemas.py`: 7 个 Pydantic 模型（`CitationPrecisionResult`, `CitationRecallResult`, `SectionCompletenessResult`, `AcademicStyleResult`, `CostEfficiencyResult`, `HumanRating`, `EvaluationResult`）
   - `citation_metrics.py`: 引用精确率（valid/total）和召回率（cited/approved），支持 `{cite:N}` 和 `[N]` 双格式
   - `academic_style.py`: hedging 比率（13 个英文 + 7 个中文模式）、被动语态比率、引用密度（per 100 words）
   - `section_completeness.py`: 必需章节验证 + 别名匹配（中英双语）
   - `cost_tracker.py`: LLM token 用量 + 节点耗时 + 搜索 API 调用次数追踪
   - `human_ratings.py`: 1-5 Likert 量表人工评分（5 维度：overall/accuracy/coherence/completeness/writing）
   - `runner.py`: 统一评测入口，聚合 7 个维度

2. **加权评分公式**（`schemas.py` `EvaluationResult.automated_score`）:
   - precision 20% + recall 15% + claim_support 25% + section_completeness 20% + hedging_score 20%
   - hedging_score: 5-20% 范围内得 1.0，超出范围线性衰减

3. **API 端点**:
   - `GET /api/research/evaluate/{thread_id}`: 对已完成的 session 运行 7 维度评测
   - `POST /api/ratings`: 提交人工评分
   - `GET /api/ratings/{thread_id}`: 获取人工评分

4. **运行时集成**:
   - `workflow.py`: 所有节点通过 `_timed_node` 装饰器自动记录耗时
   - `llm_client.py`: 每次 LLM 调用自动记录 token 用量
   - `scholar_api.py`: 每次搜索 API 调用自动记录

5. **测试覆盖**:
   - `test_evaluation.py`: 39 个单元测试（引用指标、章节完整性、学术风格、成本追踪、评测运行器）
   - `test_evaluation_regression.py`: 8 个回归测试（precision ≥ 95%、recall ≥ 80%、completeness = 100%、hedging 5-20%、automated_score > 0.7）
   - `benchmark_evaluation.py`: 性能基准（全量评测 < 100ms/次）

#### 设计决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 引用检测支持双格式 | `{cite:N}` 优先，`[N]` 回退 | 评测可在归一化前后的 draft 上运行 |
| hedging 评分用分段线性 | 5-20% 满分，超出线性衰减 | 学术写作需要适度 hedging，过多过少都不好 |
| 成本追踪双来源合并 | runtime tracking 优先，log parsing 回退 | runtime 更精确，log 兼容无 tracking 的旧 session |
| 搜索调用按成功响应计数 | 是 | 失败的请求不应计入成本 |
| 人工评分存 JSON 文件 | 是 | 单人项目无需数据库，JSON 足够 |

#### 业务-技术权衡分析

| 维度 | 优势 | 成本 | 权衡决策 |
|------|------|------|---------|
| **量化评测** | 从"感觉变好了"到"precision 97.3%"，可向面试官展示数据 | 评测模块 ~500 行代码 | **值得** - 数据驱动是工程师核心素养 |
| **回归测试** | 每次代码变更自动验证质量不退化 | 需要维护 fixture 数据 | **值得** - CI 级别的质量保障 |
| **人工评分** | 支持 A/B 测试和主观质量评估 | 需要人工参与 | **值得** - 自动化指标无法替代人类判断 |
| **成本追踪** | 精确到节点级别的 token 和延迟分析 | 运行时微量开销 | **值得** - 优化的前提是测量 |


---

## 第二部分：路线图与"不做的"清单

### 一、优先级划分

| 优先级 | 进化方向 | 工作量 | JD 对应能力 | 理由 |
|-------|---------|-------|-----------|------|
| **P0** | Planner with CoT | 2-3 天 | 复杂任务规划 | ✅ 已完成 |
| **P1** | Retriever with Tool Selection | 1-2 天 | 工具调用 | ✅ 已完成 |
| **P2** | Structured Reflection | 2-3 天 | 系统评估提升 | ✅ 已完成 |
| **P3** | Context Engineering | 1-2 天 | 复杂任务规划 + 成本控制 | ✅ 已完成 |
| **P4** | 7 维度评测框架 | 1-2 天 | 系统评估模型表现 | ✅ 已完成 |

**总工作量**: 6-10 天

**推荐执行顺序**: P0 → P1 → P3 → P2

**理由**:
1. **P0 → P1**: P1 依赖 P0 的 `research_plan`，没有子问题就无法做差异化检索
2. **P1 → P3**: P1 增加了差异化检索，论文数量可能进一步增长，P3 的上下文管理变得更紧迫
3. **P3 → P2**: P2 独立于 P0/P1/P3，但放在最后是因为当前系统已有错误传递机制，不是最紧急的

### 二、实施计划（按周划分）

#### Week 1: P0 + P1（3-5 天）

| 任务 | 详细内容 | 验收标准 | 状态 |
|------|---------|---------|------|
| **P0-Step 1** | 定义 `SubQuestion`, `ResearchPlan` 模型 | Pydantic 验证通过，`ruff check` 通过 | ✅ |
| **P0-Step 2** | 编写 CoT Prompt，更新 `planner_agent` | 测试通过，推理链清晰可读 | ✅ |
| **P0-Step 3** | 更新 `AgentState`，添加 `research_plan` 字段 | workflow 端到端运行正常 | ✅ |
| **P0-Step 4** | 添加简单查询跳过 CoT 的启发式规则 | 短查询（<10字）直接生成关键词 | ✅ |
| **P1-Step 1** | 更新 `retriever_agent`，支持基于 `research_plan` 的差异化检索 | 不同子问题使用不同数据源 | ✅ |
| **P1-Step 2** | 保留向后兼容路径（无 `research_plan` 时走原有逻辑） | 原有测试全部通过 | ✅ |

#### Week 2: P3 + P2（3-5 天）

| 任务 | 详细内容 | 验收标准 | 状态 |
|------|---------|---------|------|
| **P3-Step 1** | 添加安全阀常量（`CONTEXT_MAX_PAPERS=200`, `CONTEXT_TOKEN_BUDGET=40000`） | 极端情况有保护，正常流程不触发 | ✅ |
| **P3-Step 2** | extractor 提取所有 approved papers，子问题优先排序影响顺序不截断 | 所有审批论文都被提取和引用 | ✅ |
| **P3-Step 3** | `_build_paper_context` 保留 token 预算安全阀 | 安全阀仅防病态场景 | ✅ |
| **P2-Step 1** | 定义 `ErrorCategory`, `ReflectionEntry`, `Reflection` 模型 | Pydantic 验证通过 | ✅ |
| **P2-Step 2** | 实现 `reflection_agent` | 能正确分类错误并生成修复策略 | ✅ |
| **P2-Step 3** | 更新 workflow，添加 `reflection_agent` 节点和路由 | critic → reflection → writer/retriever/end | ✅ |
| **P2-Step 4** | 更新 `writer_agent`，接收结构化反思而非字符串错误 | Writer 根据 `fix_strategy` 修复 | ✅ |

### 三、评测方案

每个进化方向需要可量化的评测指标，避免"感觉变好了"的主观判断。

| 进化方向 | 评测指标 | 基线（当前） | 目标 | 测量方法 |
|---------|---------|------------|------|---------|
| **P0 CoT** | 子问题覆盖率 | 0（无子问题） | 每个复杂查询 ≥ 2 个子问题 | 人工评估 10 个测试查询 |
| **P0 CoT** | 关键词相关性 | 无量化基线 | 人工评估相关性 ≥ 4/5 | 5 分制人工评分 |
| **P1 Tool Selection** | 数据源匹配度 | 用户手动选择 | Agent 推荐与人工判断一致率 ≥ 70% | 对比 Agent 推荐 vs 人工最优选择 |
| **P2 Reflection** | 重试成功率 | 需要先测量当前基线 | 相对基线提升 ≥ 20% | 统计重试后 critic 通过率 |
| **P2 Reflection** | 平均重试次数 | 需要先测量当前基线 | 相对基线降低 | 统计达到 critic 通过所需的重试次数 |
| **P3 Context** | 上下文溢出率 | 无截断，100% 传入 | 0% 溢出（超预算时截断） | 统计 paper_context tokens > budget 的次数 |
| **P3 Context** | 子问题覆盖保留率 | 无保证 | 截断后每个子问题至少保留 1 篇 | 统计截断后丢失的子问题数 |

**注意**: "重试成功率"和"平均重试次数"的当前基线需要先通过实际运行测量，不能凭空估计。这是诚实的做法——先测量，再设目标。

### 四、"不做的"清单（避免技术堆砌）

#### 与 Agent 能力相关的"不做"（需要解释为什么）

| 技术选项 | 为什么不做 | 什么时候做 |
|---------|-----------|-----------|
| **Multi-Agent 并行执行** | 当前 5 个 Agent 是流水线依赖关系，并行化收益有限 | 如果增加独立的"摘要 Agent"和"对比 Agent"，可以并行 |
| **Agent-to-Agent 通信** | 当前通过共享 State 通信已足够，引入消息传递增加复杂度 | 如果 Agent 数量 > 10 且有复杂协作需求 |
| **动态 Prompt 优化** | 当前 prompt 效果可接受，优化 prompt 的 ROI 不如补齐 Agent 能力 | P0-P3 完成后，如果质量仍不满意 |
| **长期记忆（向量库）** | 当前论文数量少（<1000），SQLite checkpoint 足够 | 如果需要跨 session 的知识积累 |

#### 与工程无关的"不做"（JD 不关注）

| 技术选项 | 为什么不做 |
|---------|-----------|
| **Prometheus + Grafana 监控** | JD 不关注运维，Python logging 足够 |
| **Docker + K8s 部署** | JD 不关注 DevOps |
| **LLM 模型微调** | JD 不关注模型训练，API 调用足够 |
| **Web 界面美化** | JD 不关注前端 |

### 六、核心原则

1. **聚焦 JD**: 所有技术决策必须对应 JD 能力
2. **诚实诊断**: 准确描述当前系统的优势和不足，不夸大问题也不隐瞒已有能力
3. **展示权衡**: 每个决策都要能解释"为什么做"和"为什么不做"
4. **避免堆砌**: 只做有价值的，不追求"看起来高大上"


---

## 第三部分：最终总结

### 项目定位转变

| 维度 | 进化前 | 进化后 |
|------|-------|-------|
| **定位** | 工程化 RAG Pipeline | 具备核心 Agent 能力的 Multi-Agent System |
| **Planner** | 生成关键词列表 | ✅ 任务分解 + 推理链 + 检索策略推荐（已实现） |
| **Retriever** | 用户选择数据源，Agent 执行 | ✅ Agent 基于 ResearchPlan 自主选择数据源，用户可覆盖（已实现） |
| **Critic → Writer** | 字符串错误传递，Writer 自行理解 | ✅ 结构化反思：错误分类 + 修复策略 + 智能路由（已实现） |
| **Context** | 无截断，无预算，无上限增长 | ✅ token 预算管理 + 子问题覆盖优先排序 + 双重截断保护（已实现） |
| **推理透明度** | 黑盒，无法解释"为什么" | 显式推理链，可解释性强 |
| **评测体系** | 无量化评测，质量靠人工判断 | ✅ 7 维度自动化评测框架 + 回归测试 + 人工评分（已实现） |

### 声明

1. **评测框架**: 7 维度自动化评测框架已实现并集成到 API（`GET /api/research/evaluate/{thread_id}`）。自动化评分公式（precision 20% + recall 15% + claim 25% + completeness 20% + style 20%）可在确定性 fixture 数据上运行回归测试，阈值断言全部通过（39 个测试）。P0-P3 各进化方向的实际效果仍需通过真实查询的 A/B 测试验证。
2. **代码实现**: P0-P3 四个进化方向及 7 维度评测框架均已实现并合入主干，非设计稿。
3. **工作量**: P0-P3 实际耗时约 8 天，符合 6-10 天的预估范围。

---

## 第四部分：性能优化记录

### 已完成：Phase 1.1 - LLM_CONCURRENCY 环境变量配置 + RateLimitError 重试处理（2026-02-23）

**问题**:
1. `LLM_CONCURRENCY` 和 `CLAIM_VERIFICATION_CONCURRENCY` 硬编码为 2，无法根据 OpenAI API tier 级别动态调整
2. `llm_client.py` 的重试逻辑只捕获 `httpx.TimeoutException` 和 `httpx.ConnectError`，未处理 OpenAI 特有的错误（`RateLimitError`、`APIConnectionError`、`APITimeoutError`、`InternalServerError`）
3. 重试使用 `wait_exponential(multiplier=1, min=2, max=15)`，无 jitter，可能导致重试风暴

**修复**:
1. 新增 `_parse_int_env()` 辅助函数，支持环境变量配置 + 边界值校验（1-20）
   - `LLM_CONCURRENCY = _parse_int_env("LLM_CONCURRENCY", 2, 1, 20)`
   - `CLAIM_VERIFICATION_CONCURRENCY = _parse_int_env("CLAIM_VERIFICATION_CONCURRENCY", 2, 1, 20)`
2. 更新 `@retry` 装饰器，新增 OpenAI 错误类型：
   - `RateLimitError`, `APIConnectionError`, `APITimeoutError`, `InternalServerError`
3. 改用 `wait_random_exponential(min=1, max=30)`（jittered backoff），重试次数从 3 增加到 4

**预期效果**: 提高并发可配置性，增强错误恢复能力，避免重试风暴。

### 已完成：Phase 1.2 - extractor_agent 并行化全文本增强（2026-02-23）

**问题**: `extractor_agent` 先按 `approved_ordered` 串行提取 8 维度信息，然后再串行执行全文本 PDF 增强两次（`await enrich_papers(papers)` 调用了两次）。典型 10 篇论文 × (提取 2-3s + 增强 3-4s × 2) = 80-110 秒。

**关键洞察**: 全文本增强只需要论文的基本元数据（title/doi/year），无需等待提取完成。

**修复**:
1. 新增 `_safe_enrich()` 异步辅助函数，处理增强异常（单个失败不影响整体）
2. 重构 `extractor_agent`：
   - 并行执行：提取 8 维度信息 + 全文本增强（`asyncio.gather`）
   - 增强直接作用于 `approved_ordered`（原始论文）
   - 两路结果通过 `paper_id` 合并

**预期加速**: 约 2x（从 80-110s 降至 40-55s，10 篇论文）。

### 已完成：Phase 2.1 - 批量 claim 提取 + per-section 回退（2026-02-23）

**问题**: `claim_verifier.py` 的 `extract_all_claims()` 对综述的每个 section 串行调用 LLM 提取 claims（`for` 循环 + `await`）。典型 8 个 section × 3-4 秒/section = 24-32 秒。

**修复**:
1. 新增批量 claim 提取数据模型：
   - `SectionClaim`: section_name, claims: list[str]
   - `BatchClaimList`: claims: list[SectionClaim]
2. 新增批量 claim 提取 prompt：
   - `CLAIM_BATCH_EXTRACTION_SYSTEM`: 批量提取系统提示
   - `CLAIM_BATCH_EXTRACTION_USER`: 批量提取用户提示
3. 新增 `CLAIM_BATCH_SIZE = 3` 常量
4. 新增 `_extract_claims_batch()` 函数：单次 LLM 调用提取 3 个 section 的 claims
5. 重构 `extract_all_claims()`：
   - 将 sections 分组为 batch（每批 3 个）
   - 每个 batch 调用 `_extract_claims_batch()`（单 LLM 调用）
   - 失败时回退到 per-section 提取（`_safe_extract_claims()`）
   - 单 section 场景走原有 per-section 路径

**预期加速**: 约 3x（从 24-32s 降至 8-11s，8 个 section）。

### 已完成：writer_agent 并行章节生成（2026-02-23）

**问题**: `writer_agent` 在首次生成综述时，按 outline 逐章节串行调用 LLM（`for` 循环 + `await`）。典型 4-6 个章节 × 3-5 秒/章节 = 12-30 秒。

**修复**: 将串行 `for` 循环替换为 `asyncio.gather(*section_tasks, return_exceptions=True)`，所有章节并行生成。单个章节失败时生成 fallback 占位内容，不影响其他章节。

**预期加速**: 4-6x（从 12-30s 降至 3-6s）。

### 待优化：其他瓶颈（按影响排序）

| 瓶颈 | 位置 | 当前耗时估算 | 优化方案 | 优先级 |
|------|------|------------|---------|-------|
| claim verification 低并发 | `critic_agent` + `claim_verifier.py` | 30-60s（30-45 LLM 调用，并发=2） | 提高 `CLAIM_VERIFICATION_CONCURRENCY` 或批量验证 | 中 |
| fulltext PDF 串行 fallback | `fulltext_api.py` `resolve_pdf_url` | 3-9s/篇（3 个串行请求） | DOI 查询并行化（Unpaywall + OpenAlex 同时发起） | 低 |

---

**附录：参考论文**

1. **Reflexion**: Language Agents with Verbal Reinforcement Learning (Shinn et al., 2023) — P2 反思机制的理论基础
2. **CoT**: Chain-of-Thought Prompting Elicits Reasoning in Large Language Models (Wei et al., 2022) — P0 推理链的理论基础
3. **Toolformer**: Language Models Can Teach Themselves to Use Tools (Schick et al., 2023) — P1 工具选择的理论基础
4. **LangGraph**: A framework for building language agent applications — 项目的工作流框架

---

**文档版本**: v7.1
**最后更新**: 2026-02-23
**作者**: AI Agent 算法工程师候选者

