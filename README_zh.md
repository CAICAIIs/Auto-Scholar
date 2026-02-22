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

- **5 节点紧凑型工作流**：检索 → 确认 → 精读 → 撰写 → 质检
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

### 语言选项

- **界面语言**：点击语言按钮（中文/English）切换界面语言
- **输出语言**：点击 EN/中 按钮选择综述生成语言

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
| 最大 QA 重试次数 | 3 | 可在 constants.py 配置 |

### 基准测试详情

**SSE 防抖** (`tests/benchmark_sse.py`):
- 原始消息数: 263 tokens
- 防抖后请求数: 21 次
- 压缩比: 12.5x
- 机制: 200ms 时间窗口 + 语义边界检测（。！？.!?\n）

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

`qa_evaluator_node` 对每份综述进行严格校验：

1. **幻觉检测**：确保所有 `cited_paper_ids` 都存在于已确认的论文中
2. **覆盖率检查**：确保所有已确认的论文都被引用
3. **自动重试**：失败时路由回 `draft_node`，并传递错误反馈

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
