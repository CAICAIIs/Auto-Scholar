# Auto-Scholar

AI 驱动的学术文献综述生成器，采用人工监督工作流。

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2+-purple.svg)](https://github.com/langchain-ai/langgraph)
[![Next.js](https://img.shields.io/badge/Next.js-16+-black.svg)](https://nextjs.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## 什么是 Auto-Scholar？

Auto-Scholar 帮助研究人员快速生成结构化的文献综述。输入研究主题，审查候选论文，在几分钟内获得一篇引用规范的学术综述。

**核心特性：**
- **智能论文搜索**：自动生成搜索关键词，从 Semantic Scholar、arXiv 和 PubMed 查找相关论文
- **人工监督**：在论文纳入综述前进行审查和确认
- **防幻觉 QA**：验证所有引用存在且正确引用
- **双语支持**：生成英文或中文综述，界面支持中英文
- **实时进度**：通过实时日志流观察 AI 工作过程

## 核心特性

- **6 节点工作流**：规划 → 检索 → [人工确认] → 精读 → 撰写 → 质检 → 反思
- **防幻觉 QA 自愈机制**：严格的引用校验，自动重试（最多 3 次）
- **Event Queue 防抖引擎**：85-98% 的 SSE 网络请求削减
- **Human-in-the-Loop**：在文献精读前中断工作流，等待人工确认
- **状态持久化**：基于 SQLite 的检查点持久化，支持工作流恢复

## 快速开始

### 前置要求

- Python 3.11+
- uv
- bun
- OpenAI API 密钥（或兼容的 API 端点，如 DeepSeek/智谱）

### 1. 克隆和安装

```bash
git clone https://github.com/CAICAIIs/Auto-Scholar.git
cd Auto-Scholar

# 后端
uv sync --extra dev

# 前端
cd frontend && bun install && cd ..
```

### 2. 配置环境

在项目根目录创建 `.env` 文件：

```env
# 必需
LLM_API_KEY=your-openai-api-key

# 可选 - 用于兼容 API（DeepSeek、智谱等）
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o

# 可选 - 提高 Semantic Scholar 限流阈值
SEMANTIC_SCHOLAR_API_KEY=your-key

# 可选 - 并行操作的 LLM 并发数
# 默认值：2（对免费/低级别 API 密钥安全）
# 推荐值：2-4（免费版），4-8（付费版）
# 较高的值提升性能，但可能触发限流
LLM_CONCURRENCY=2

# 可选 - 声明验证并发数
# 默认值：2（对免费/低级别 API 密钥安全）
# 推荐值：2-4（免费版），4-8（付费版）
CLAIM_VERIFICATION_CONCURRENCY=2

# 可选 - 在时间敏感场景中禁用声明验证
# 默认值：true（保持 97.3% 引用准确率）
# 设置为 "false" 可禁用并减少工作流时间
CLAIM_VERIFICATION_ENABLED=true
```

### 3. 启动服务

**终端 1 - 后端：**
```bash
uv run uvicorn backend.main:app --reload --port 8000
```

**终端 2 - 前端：**
```bash
cd frontend && bun run dev
```

### 4. 打开浏览器

访问 `http://localhost:3000` 开始研究！

## 使用指南

### 步骤 1：输入研究主题

在查询输入框中输入研究主题。示例：
- "transformer architecture in natural language processing"
- "deep learning for medical image analysis"
- "reinforcement learning in robotics"

### 步骤 2：审查候选论文

系统将：
1. 从主题生成 3-5 个搜索关键词
2. 在 Semantic Scholar、arXiv 和 PubMed 搜索相关论文
3. 展示候选论文供你审查

选择要包含在文献综述中的论文。

### 步骤 3：获取综述

确认后，系统将：
1. 提取每篇论文的核心贡献
2. 生成带有规范引用的结构化文献综述
3. 验证所有引用（如发现问题自动重试）

### 智能助手控制台

智能助手控制台通过实时日志流显示工作进度：

- **控制台标题**：显示"控制台"（中文界面）或"Console"（英文界面）
- **折叠/展开**：点击折叠按钮将控制台最小化为侧边栏
- **模型选择**：选择用于生成的 LLM 模型（默认：gpt-4o）
- **语言控制**：统一的语言切换界面：
  - **界面**：切换 [中|EN] 以切换界面语言
  - **综述**：切换 [中|EN] 以选择综述生成语言

**状态保持：**
- 切换界面语言时会保留所有会话数据（threadId、草稿、消息、日志等）
- 使用 sessionStorage 在页面重新加载后保持状态

**自动重新生成：**
- 更改输出语言时，综述会自动以新语言重新生成
- 重新生成期间保持状态，并防止重复请求

## 技术栈

### 后端
- **FastAPI** - 异步 Web 框架
- **LangGraph** - 工作流编排，支持检查点
- **OpenAI** - LLM 用于关键词生成和综述撰写
- **aiohttp** - Semantic Scholar、arXiv 和 PubMed 的异步 HTTP 客户端
- **Pydantic** - 数据验证和序列化
- **tenacity** - API 调用的重试逻辑

### 前端
- **Next.js 16** - React 框架
- **Zustand** - 状态管理
- **next-intl** - 国际化
- **Tailwind CSS** - 样式
- **react-markdown** - 综述渲染
- **Radix UI** - 可访问组件

## 测试

```bash
# 后端编译检查
find backend -name '*.py' -exec python -m py_compile {} +

# 前端类型检查
cd frontend && bun x tsc --noEmit

# 运行测试
uv run pytest tests/ -v
```

## 项目文档

- [文档总览](docs/README.md)
- [系统架构](docs/ARCHITECTURE.md)
- [开发指南](docs/DEVELOPMENT.md)
- [API 参考](docs/API.md)
- [贡献指南](CONTRIBUTING.md)
- [社区行为准则](CODE_OF_CONDUCT.md)
- [安全策略](SECURITY.md)

## 性能指标

| 指标 | 数值 | 验证方法 |
|--------|------|----------|
| 网络请求削减 | 92% | 基准测试：263 tokens → 21 次请求 |
| 引用准确率 | 97.3% | 手动验证 3 个主题共 37 个引用 |
| 典型工作流耗时 | ~45秒 | 3 篇论文端到端 |
| 最大 QA 重试次数 | 3 | 在 workflow.py 中配置 (`MAX_RETRY_COUNT`) |

### 性能目标

| 指标 | 基线 | 目标 | 状态 |
|--------|------|------|------|
| 10 篇论文工作流耗时 | 50-95秒 | 35-65秒 | 已实现 |
| LLM 调用次数（10 篇论文） | ~26-36 | ~20-28 | 已达成 |
| 引用准确率 | 97.3% | ≥97.0% | 保持 |

### 实现总结

第一阶段优化已完成（低风险，中等影响）：
1. **LLM_CONCURRENCY 环境变量**：可选的性能调优，默认安全值
2. **并行全文精读**：10 篇论文节省 10-15 秒

第二阶段优化已完成（中等风险，低-中等影响）：
3. **批量声明提取**：critic agent 节省 3-5 秒

### 性能调优

以下环境变量允许拥有高级别 API 密钥的用户进行性能调优：

| 变量 | 默认值 | 推荐值 | 说明 |
|------|--------|--------|------|
| `LLM_CONCURRENCY` | 2 | 2-4（免费版），4-8（付费版） | 提取阶段的并发 LLM 调用数 |
| `CLAIM_VERIFICATION_CONCURRENCY` | 2 | 2-4（免费版），4-8（付费版） | 并发声明验证调用数 |
| `CLAIM_VERIFICATION_ENABLED` | true | true（推荐），false（时间敏感场景） | 启用/禁用声明验证（启用时保持 97.3% 准确率） |

**提升并发后的预期改进：**
- `LLM_CONCURRENCY=4`：提取时间减少约 50%（25-40秒 → 13-20秒）
- `LLM_CONCURRENCY=4` + 第一阶段第2项 + 第二阶段第1项：10 篇论文工作流 50-95秒 → 35-65秒
- `CLAIM_VERIFICATION_ENABLED=false`：critic_agent 时间减少约 8-20秒（权衡：引用准确率降低）

**注意：**
- 增加并发可能会触发低级别 API 套餐的限流。从默认值开始，逐步增加。
- 禁用声明验证（`CLAIM_VERIFICATION_ENABLED=false`）会减少工作流时间，但可能使引用准确率低于 97.3%。仅在对速度要求高于准确率的时间敏感场景中使用。

### 基准测试和验证工具

**工作流基准测试** (`tests/benchmark_workflow.py`)：
- 端到端性能测量
- 并发对比（基线 vs 优化）
- 各节点耗时分解

**引用验证** (`tests/validate_citations.py`)：
- 引用准确率的回归测试
- 多主题的手动验证
- 支持持续测试的批量验证

**SSE 防抖** (`tests/benchmark_sse.py`)：
- 原始消息数: 263 tokens
- 防抖后请求数: 21 次
- 压缩比: 12.5x
- 机制: 200ms 时间窗口 + 语义边界检测（。！？.!?）+ 换行符

### 基准测试详情

**引用验证** (`tests/validate_citations.py`):
- 验证主题: 3 个（transformer 架构、医学影像、机器人）
- 总引用数: 37
- 正确引用: 36
- 错误类型: 引用索引正确但上下文不匹配（QA 验证存在性，不验证语义相关性）

## 工作原理

### Event Queue 防抖引擎

`StreamingEventQueue` 通过以下机制降低 SSE 网络开销：

1. **时间窗口**：缓冲 200ms 后统一刷新
2. **语义边界**：遇到标点符号（。！？\n）立即刷新

```
无防抖：100 个 Token → 100 次网络请求
有防抖： 100 个 Token → 10-15 次网络请求
```

### QA 自愈机制

`critic_agent` 对每份综述进行严格校验：

1. **幻觉检测**：通过正则匹配 `{cite:N}` 验证所有引用索引在有效范围内
2. **覆盖率检查**：确保所有已确认的论文索引都被引用
3. **自动重试**：失败时经 `reflection_agent` 分析错误，路由回 `writer_agent` 或 `retriever_agent` 重试

## 贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 开源协议

本项目采用 MIT 协议 - 详见 [LICENSE](LICENSE) 文件。

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 工作流编排
- [Semantic Scholar](https://www.semanticscholar.org/) - 学术论文 API
- [arXiv](https://arxiv.org/) - 科学论文预印本服务器
- [PubMed](https://pubmed.ncbi.nlm.nih.gov/) - 生物医学文献数据库
- [FastAPI](https://fastapi.tiangolo.com/) - 异步 Web 框架
- [Next.js](https://nextjs.org/) - React 框架
