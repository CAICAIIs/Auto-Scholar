# [Proposal 3] AI Runtime Layer - Revised Design (Application-First Approach)

> **Author**: Sisyphus (AI Analysis)
> **Status**: Phase 1 Implemented
> **Based on**: Issue #2 discussion with source code analysis of Dify, OpenHands, and Haystack

---

## TL;DR

为 Auto-Scholar 设计一个**应用级的 AI Runtime 层**，参考 OpenHands 架构而非 Dify 平台级架构：

- **Phase 1（核心）**：Task-aware 路由 + Fallback + 模型能力检测 ✅ **已实现**
- **Phase 2（扩展）**：外部配置 YAML + 流式输出 + 成本追踪
- **Phase 3（高级）**：Embedding Provider + 多模态支持 + 智能 Router 模式

**核心原则**：
1. 基于现有 `llm_client.py` 增量扩展，避免过度设计
2. 参考 OpenHands 应用级架构（~120KB，12 文件），而非 Dify 平台级架构（50+ providers）
3. 渐进式发展，根据实际需求按需添加抽象
4. 与 LangGraph 节点模式无缝集成

---

## 一、为什么需要 AI Runtime（修正）

### 1.1 当前项目状态

Auto-Scholar 是一个基于 LangGraph 的学术文献综述生成器：

```
planner_agent → retriever_agent → extractor_agent → writer_agent → critic_agent
```

**已有基础设施**：

| 功能 | 状态 | 位置 |
|------|------|------|
| ModelProvider 枚举 | ✅ | schemas.py |
| ModelConfig schema | ✅ | schemas.py |
| resolve_model() | ✅ | llm_client.py |
| /api/models 端点 | ✅ | main.py |
| Cost tracking | ✅ | evaluation/cost_tracker.py |
| SSE Streaming | ✅ | event_queue.py |

### 1.2 当前问题

| 问题 | 影响 | 优先级 |
|------|------|--------|
| 所有任务用同一模型 | 成本高 | 🔴 高 |
| 无 Task-aware 路由 | 无法按任务特性选择最优模型 | 🔴 高 |
| 无 Fallback 机制 | 单点故障风险 | 🟡 中 |
| 无模型能力检测 | 缺少智能决策依据 | 🟡 中 |
| 配置分散在环境变量 | 不易管理复杂场景 | 🟢 低 |
| 缺少流式输出接口 | 无法实时显示生成内容 | 🟡 中 |


#### 2.2 成本追踪增强
扩展 `backend/evaluation/cost_tracker.py`，按 TaskType 统计成本：
```python
# 新增函数
def record_llm_usage_by_task(
    prompt_tokens: int,
    completion_tokens: int,
    model: str,
    task_type: TaskType | None = None,
):
    # ... 现有实现 ...
```
SSE 新增事件类型：
```python
{event: "cost_update", task_type: "extraction", cost: 0.045}
```

#### 2.3 Provider 层（可选，模型数量 >5 时）
当支持的 provider 超过 3-4 个时，考虑引入 Provider 层：
```
backend/llm/providers/
├── __init__.py
├── base.py            # BaseProvider 抽象类
├── openai.py         # OpenAI 实现
├── anthropic.py      # Anthropic 实现
└── deepseek.py       # DeepSeek 实现
```
**何时需要**：当发现每个 provider 的特殊逻辑超过 100 行时。

#### 2.4 前端适配
扩展 ModelSelector 支持显示 fallback 模型列表和成本统计：
```typescript
// ModelSelector 组件新增字段
interface ModelConfigWithRouting extends ModelConfig {
  isFallback?: boolean;
  taskType?: string;
}
```

### Phase 3: 高级层（明确需求后再做）

#### 3.1 Embedding Provider
当确定要做 RAG（基于用户论文库的问答）时实现：
```python
# backend/llm/providers/embedding.py
class EmbeddingProvider(BaseProvider):
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """生成文本向量"""
```
集成到 LLM 调用中，支持 hybrid retrieval（向量检索 + 关键词检索）。

#### 3.2 多模态支持
支持分析论文中的图表、公式、表格：
```python
# 模型能力扩展
class ModelCapability(StrEnum):
    # ... 现有能力 ...
    OCR = "ocr"              # 图表 OCR
    TABLE_EXTRACTION = "table_extraction"  # 表格提取
```

#### 3.3 智能 Router 模式
参考 OpenHands 的 `RouterLLM` 基类，根据输入内容动态选择模型：
```python
# backend/llm/router/
├── __init__.py
├── base.py
└── content_aware.py   # 根据输入内容选模型
```

#### 3.4 Prompt 管理系统（可选）
如果需要支持用户自定义 prompts：
```
backend/prompts/
├── user/
│   ├── planning.yaml
│   ├── extraction.yaml
│   ├── writing.yaml
│   └── qa.yaml
└── __init__.py  # 加载覆盖系统 prompts
```

---

## 五、与原 Proposal 的对比

| 设计元素 | 原 Proposal | 修订版 | 原因 |
|---------|-----------|--------|------|
| 目录结构 | `backend/ai/` 20+ 文件 | `backend/llm/` 4-8 文件 | 原版是平台级设计，修订版是应用级设计 |
| Gateway 类 | 单例 `LLMGateway` | 函数式 API (`structured_completion`) | 原版增加了复杂度，修订版保持简单 |
| 配置方式 | YAML + 多路径搜索 + 环境变量替换 | 简单 YAML 或环境变量 | 原版过度复杂，修订版按需添加 |
| Tool Registry | 完整 Tool 系统 | 不做（节点不是 ReAct agent） | Auto-Scholar 当前不需要 |
| 中间件系统 | Pre/Post/Hook 中间件 | 不做（用装饰器就够了） | 原版过度设计 |
| Embedding | Phase 1 就做 | Phase 3（明确需求后） | 原版过早添加 |
| Prompt Registry | Phase 1 就做 | Phase 3（可选） | 原版过早添加 |
| 缓存层 | Phase 1 内存缓存 | 不做（缓存命中率极低） | 原版考虑不周 |
| 参考对象 | Dify（平台级） | OpenHands（应用级） | 修正后的参考更匹配 Auto-Scholar 定位 |

---

## 六、总结

本 Proposal 基于对 Dify、OpenHands、Haystack 的源码分析，提出了一个**应用级的、渐进式的 AI Runtime 层设计方案**：

### 核心改进
1. **参考对象正确**：参考 OpenHands（应用级，~120KB）而非 Dify（平台级，50+ providers）
2. **设计原则务实**：在现有 `llm_client.py` 上增量扩展，不推倒重来
3. **抽象深度适度**：`backend/llm/` 4-8 个文件，提供类型、路由、能力检测

### Phase 划分
- **Phase 1（核心，~3-5 天）**：Task-aware 路由 + Fallback + 模型能力检测 ✅ **已实现**
- **Phase 2（扩展，~1 周）**：外部配置 YAML + 流式输出 + 成本追踪
- **Phase 3（高级，按需）**：Embedding Provider + 多模态支持 + 智能 Router 模式

### Phase 1 实现详情

**新增文件**（`backend/llm/` 目录，3 个文件）：

| 文件 | 职责 |
|------|------|
| `backend/llm/__init__.py` | 包导出 |
| `backend/llm/task_types.py` | `TaskType` 枚举（5 种任务类型）+ `TaskRequirement` 数据类（硬约束 + 软偏好） |
| `backend/llm/router.py` | `select_model()` 两阶段路由（硬过滤 + 软评分）+ `get_fallback_chain()` 有序候选链 |

**修改文件**：

| 文件 | 变更 |
|------|------|
| `backend/schemas.py` | `ModelConfig` 新增 6 个能力字段：`max_context_tokens`、`supports_long_context`、`cost_tier`、`reasoning_score`、`creativity_score`、`latency_score` |
| `backend/utils/llm_client.py` | `_infer_capabilities()` 按 provider/model 推断能力；`structured_completion()` 新增 `task_type` 参数 |
| `backend/nodes.py` | 所有 `structured_completion()` 调用传入对应 `task_type` |
| `backend/utils/claim_verifier.py` | 所有 `structured_completion()` 调用传入 `task_type="qa"` |

**设计决策**：
1. 不引入 LiteLLM：只需 2-3 个 provider，直接用 `AsyncOpenAI` + 不同 `base_url` 覆盖
2. 路由两阶段：硬约束过滤（structured_output、long_context、cost_tier）→ 软偏好评分（reasoning、creativity、latency、cost bonus）
3. 完全向后兼容：不传 `task_type` 时走原有默认路径
4. 能力推断：按 provider + model name 自动推断，无需手动配置

**测试覆盖**：43 个新测试（task_types 10 + capabilities 11 + router 22），全部通过

### 预期收益
- **成本降低**：planner/extractor/critic 用 mini 模型，预计节省 40-60% 成本
- **可靠性提升**：Fallback 机制避免单点故障
- **可扩展性**：渐进式发展，按需添加功能
- **与 LangGraph 协作**：保持函数式 API，节点调用方式不变

---

**文件创建时间**：2026-02-25  
**Phase 1 实现时间**：2026-02-25  
**状态**：Phase 1 已实现，Phase 2-3 待评审

