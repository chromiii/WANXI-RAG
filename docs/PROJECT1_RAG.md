# Project 1 — Intent-driven RAG Writing Workflow

## 1. Goal

基于万悉科技品宣 PDF，支持 Blog、FAQ、品牌介绍、产品介绍四类内容生成。系统要求每个事实性主张可回溯到 PDF chunk / 页码，并对无依据数字、案例误用和效果保证进行校验。

## 2. Workflow

```text
User Input
  ↓
Task Intent Parser
  ├─ explicit type -> direct route
  ├─ clear wording -> rule route
  └─ ambiguous + live -> DeepSeek intent classification
  ↓
Query Planner
  ├─ keep original query
  └─ optional 1-3 retrieval rewrites
  ↓
Hybrid Retrieval
  ├─ Elasticsearch BM25
  └─ BGE-M3 dense kNN
  ↓
Weighted RRF
  ↓
Local Cross-Encoder Reranker
  ↓
Context Builder
  ↓
Type-specific Writer
  ├─ Blog
  ├─ FAQ
  ├─ Brand Introduction
  └─ Product Introduction
  ↓
Grounding Validator
  ├─ citation IDs
  ├─ numeric guard
  ├─ unsupported client-case guard
  └─ unsupported guarantee guard
  ↓
Markdown + PDF references + workflow trace
```

## 3. Task Intent

Task Intent 和 Retrieval Intent 分开：

- Task Intent 回答“用户要生成什么内容”，决定 Writer schema。
- Query Planner 回答“为了完成这个任务应该检索什么”，只扩展召回，不改变最终用户意图。

若用户显式指定 `--type FAQ`，不会额外调用意图模型；若使用 `--type auto`，先用规则识别，只有 live 模式下的模糊输入才调用 DeepSeek。

## 4. Retrieval

原始 query 权重 1.0，rewrite query 权重 0.7。每个 query 分别执行 BM25 与 BGE-M3 dense retrieval，再由 weighted RRF 合并。Cross-encoder 最终始终使用原始 query 对候选文档重新评分，避免 query rewrite 偏离用户真正意图。

## 5. Context Construction

只把最终 Top-K evidence 加入 generation context，并保留：

- stable chunk id
- physical PDF page
- heading
- text
- page image asset path

Writer 被明确要求只使用真正支持当前主题的 evidence，不要求覆盖全部 Top-K。

## 6. Type-specific Generation

Blog、FAQ、品牌介绍、产品介绍具有不同 JSON schema 与 Prompt：

- Blog：标题、导语、3-5 节正文、可选 FAQ、结语。
- FAQ：标题、简短导语、3-8 个问答、简短结语；不允许退化成普通文章 sections。
- 品牌介绍：定位、核心价值、能力、服务对象、可信信息。
- 产品介绍：产品定位、用户问题、能力、使用场景、适用边界。

## 7. Grounding

生成后的 JSON 必须再次通过 deterministic validator：

1. 所有 factual claim 必须有 citation。
2. citation id 必须来自本轮 retrieved evidence。
3. 生成文本中的数字必须出现在被引用 evidence 中。
4. “招商银行应用设想”不得改写成已交付客户案例。
5. 不允许无依据的 AI 推荐、排名或增长保证。

如果模型 JSON 不符合 schema / grounding，LLM client 会进行一次 bounded repair；再次失败则返回错误，不静默放行。

## 8. Observable Workflow

最终结果含 `workflow_trace`，仅记录可观察执行阶段，不包含模型隐藏推理：

```text
task_intent
query_planning
hybrid_retrieval
context_building
generation
grounding_validation
```

同时 `model_calls` 记录每次外部模型调用的 purpose、tokens 与 latency，便于 Demo 展示和调试。

## 9. Example commands

自动识别内容类型：

```powershell
py -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode live
```

显式指定：

```powershell
py -m trendee.cli write "万悉科技主要帮助客户解决什么问题？" --mode live --type FAQ
py -m trendee.cli write "请介绍万悉科技" --mode live --type 品牌介绍
py -m trendee.cli write "介绍万悉科技的 GEO 产品能力" --mode live --type 产品介绍
```

检索调试：

```powershell
py -m trendee.cli rag-search "万悉科技主要帮助客户解决什么问题？" --mode live
py -m trendee.cli hybrid-search "万悉科技主要帮助客户解决什么问题？" --no-rerank
```

## 10. Known limitations

- 当前 PDF 主要依赖文本层；文本稀疏页只做标记，尚未全量 OCR。
- Cross-encoder reranker 是本地轻量模型，复杂抽象问题排序并不保证完美。
- Grounding validator 验证 citation/数字/已知误用规则，不等价于完整语义蕴含证明。
- 品宣资料中的营销主张只作为来源事实转述，不视为独立外部核验。
