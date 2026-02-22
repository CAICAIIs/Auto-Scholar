# Auto-Scholar 测试指南

本指南帮助你快速测试 Auto-Scholar 的完整功能。

## 环境准备

### 1. 检查环境变量

确保 `.env` 文件配置正确：

```bash
# 查看当前配置
cat .env

# 必须包含 (示例)
LLM_API_KEY=sk-xxx...
LLM_BASE_URL=https://api.openai.com/v1  # 或 DeepSeek/智谱 API
LLM_MODEL=gpt-4o
```

### 2. 启动服务

**终端 1 - 后端:**
```bash
cd /path/to/auto-scholar
uvicorn app.main:app --reload --port 8000
```

看到以下输出表示启动成功：
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     LangGraph workflow initialized
```

**终端 2 - 前端:**
```bash
cd /path/to/auto-scholar/frontend
npm run dev
```

看到以下输出表示启动成功：
```
▲ Next.js 16.x
- Local: http://localhost:3000
```

### 3. 验证服务状态

```bash
# 检查后端健康
curl http://localhost:8000/docs
# 应该返回 Swagger UI HTML

# 检查前端
open http://localhost:3000
# 应该看到 Auto-Scholar 界面
```

---

## 功能测试

### 测试 1: 基础研究流程 (英文)

**步骤:**

1. 打开浏览器访问 `http://localhost:3000`

2. 在输入框输入研究主题：
   ```
   transformer architecture in natural language processing
   ```

3. 点击 "Start" 按钮

4. **观察日志流:**
   - `[system] Starting research: "transformer architecture..."`
   - `[plan_node] Generated 5 search keywords: [...]`
   - `[search_node] Found 30 unique papers across 5 queries`

5. **论文审核弹窗出现:**
   - 查看候选论文列表
   - 默认全选，可取消不相关的论文
   - 建议选择 3-5 篇最相关的论文
   - 点击 "Confirm & Continue"

6. **观察综述生成:**
   - `[read_and_extract_node] Extracted contributions from 3 papers`
   - `[draft_node] Draft complete: 'xxx' with 5 sections`
   - `[qa_evaluator_node] QA passed: all citations verified`

7. **查看结果:**
   - 右侧工作区显示生成的文献综述
   - 鼠标悬停在 [1], [2] 等引用上查看论文详情

**预期结果:** ✅ 生成完整的英文文献综述，包含多个章节和正确的引用

---

### 测试 2: 中文输出

**步骤:**

1. 点击左上角的 "EN" 按钮切换为 "中"（输出语言选择器）

2. 输入研究主题：
   ```
   深度学习在医学影像中的应用
   ```

3. 点击 "开始" 按钮

4. 完成论文审核流程

**预期结果:** ✅ 生成中文文献综述，章节标题和内容均为中文

---

### 测试 3: UI 语言切换

**步骤:**

1. 点击右上角的 "中文" 按钮

2. 观察界面变化：
   - 标题变为 "智能助手控制台"
   - 按钮变为 "开始"
   - 状态变为 "就绪"

3. 再次点击 "English" 切换回英文

**预期结果:** ✅ 界面语言正确切换，不影响输出语言设置

---

### 测试 4: 错误恢复

**步骤:**

1. 输入一个非常模糊的查询：
   ```
   abc
   ```

2. 观察系统行为：
   - 可能找到较少论文
   - 或显示 "No papers found for this query"

3. 重新输入有效查询继续测试

**预期结果:** ✅ 系统优雅处理边缘情况，显示友好错误信息

---

### 测试 5: API 直接调用

**启动研究:**
```bash
curl -X POST http://localhost:8000/api/research/start \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning optimization", "language": "en"}'
```

**预期响应:**
```json
{
  "thread_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "candidate_papers": [
    {
      "paper_id": "xxx",
      "title": "Paper Title",
      "authors": ["Author 1", "Author 2"],
      "abstract": "...",
      "url": "https://...",
      "year": 2024,
      "is_approved": false,
      "core_contribution": null
    }
  ],
  "logs": [
    "Generated 5 search keywords: [...]",
    "Found 25 unique papers across 5 queries"
  ]
}
```

**审核论文:**
```bash
# 使用上一步返回的 thread_id 和 paper_ids
curl -X POST http://localhost:8000/api/research/approve \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "your-thread-id",
    "paper_ids": ["paper-id-1", "paper-id-2", "paper-id-3"]
  }'
```

**预期响应:**
```json
{
  "thread_id": "...",
  "final_draft": {
    "title": "Literature Review: Machine Learning Optimization",
    "sections": [
      {
        "heading": "Introduction",
        "content": "Machine learning optimization... [1] proposed...",
        "cited_paper_ids": ["paper-id-1"]
      }
    ]
  },
  "approved_count": 3,
  "logs": [...]
}
```

---

## 常见问题排查

### 问题 1: "Failed to fetch" 错误

**原因:** 后端未启动或端口不匹配

**解决:**
```bash
# 检查后端是否运行
ps aux | grep uvicorn

# 确认端口 8000
curl http://localhost:8000/docs
```

### 问题 2: 论文搜索返回空

**原因:** Semantic Scholar API 限流或查询太模糊

**解决:**
- 等待几秒后重试
- 使用更具体的学术术语
- 配置 `SEMANTIC_SCHOLAR_API_KEY` 提高限额

### 问题 3: LLM 调用失败

**原因:** API Key 无效或余额不足

**解决:**
```bash
# 测试 API Key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $LLM_API_KEY"
```

### 问题 4: 综述生成卡住

**原因:** 选择论文过多，LLM 处理时间长

**解决:**
- 选择 3-5 篇论文即可
- 查看后端日志了解进度

### 问题 5: 引用验证失败重试

**现象:** 日志显示 "QA failed with X errors (retry 1/3)"

**说明:** 这是正常行为，系统会自动重试最多 3 次

---

## 性能基准

| 操作 | 预期时间 |
|------|---------|
| 关键词生成 | 2-3 秒 |
| 论文搜索 (5 关键词) | 3-5 秒 |
| 贡献提取 (3 篇论文) | 5-10 秒 |
| 综述生成 | 10-20 秒 |
| QA 验证 | 3-5 秒 |
| **总计 (3 篇论文)** | **~30-45 秒** |

---

## 测试检查清单

- [ ] 后端启动成功 (端口 8000)
- [ ] 前端启动成功 (端口 3000)
- [ ] 英文研究流程完整
- [ ] 中文输出正常
- [ ] UI 语言切换正常
- [ ] 论文审核弹窗正常
- [ ] 引用悬浮提示正常
- [ ] 错误情况优雅处理
- [ ] API 直接调用正常

完成以上测试后，Auto-Scholar 即可正常使用！
