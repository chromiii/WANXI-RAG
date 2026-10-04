# Project 1 — Intent-driven RAG Writing Workflow

## 1. Goal

基于万悉科技品宣 PDF，支持 Blog、FAQ、品牌介绍、产品介绍四类内容生成。系统要求每个事实性主张可回溯到 PDF chunk / 页码，并对无依据数字、案例误用和效果保证进行校验。

## 2. Workflow

```text
User Input
  ↓
Scope Guard
  ├─ meta -> direct system response
  ├─ out_of_scope -> stop
  └─ in_scope / ambiguous -> continue
  ↓
Task Intent Classifier
  ├─ explicit type -> immutable presentation contract
  ├─ auto -> LLM content-type classification
  └─ LLM semantic focus + user goal
  ↓
Query Planner
  ├─ keep original query
  └─ passthrough / rewrite / expand / decompose
  ↓
Hybrid Retrieval
  ├─ Elasticsearch BM25
  └─ BGE-M3 dense kNN
  ↓
Weighted RRF
  ↓
Local Cross-Encoder Reranker
  ↓
Evidence Sufficiency Gate
  ├─ live: LLM judges whether retrieved evidence can answer the core question
  └─ offline: passthrough for deterministic regression only
  ↓
Post-Retrieval Processor
  ├─ evidence metadata / risk flags
  ├─ hard safety filter
  ├─ near-duplicate dedup
  ├─ final Top-N
  └─ context budget
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
  └─ unsupported guarantee guard
  ↓
Markdown + PDF references + workflow trace
```

## 3. Task Intent

Task Intent 只负责“理解任务”，不负责生成检索词。

系统将两个概念分开：

- **Primary Objective**：用户原始 topic，始终保留；
- **Presentation Contract**：Blog / FAQ / 品牌介绍 / 产品介绍；
- **Semantic Focus**：由 LLM 用简短标签概括用户真正关注的语义；
- **User Goal**：由 LLM 用一句话概括用户希望得到的结果；
- **Confidence**：用于调试和可观察性，不直接改变检索排序。

当用户显式指定内容类型时，类型不可被模型覆盖；LLM 只分析 semantic focus / user goal。使用 `auto` 时，LLM 同时决定 content type。离线模式不模拟语义理解，只使用 `generic` focus 和确定性 Blog fallback，以便做 pipeline regression test。

运行时不再使用业务实体、问题关键词或具体客户名做 Intent 分类。

## 4. Query Transformation

Query Planner 独立负责检索前的问题重组。它可以选择：

- **passthrough**：原问题已经适合检索；
- **rewrite**：生成更检索友好的等价表达；
- **expand**：从同一问题的不同语义角度生成额外查询；
- **decompose**：对包含多个独立信息需求的问题生成子查询。

原始 query 永远作为第一个检索通道保留，额外查询最多 3 个。Query Planner 不回答问题，也不补充公司事实。Prompt 不包含真实验收题作为 few-shot 示例，避免对固定 case 过拟合。

## 5. Hybrid Retrieval and Reranking

原始 query 权重 1.0，额外 query 权重 0.7。每个 query 分别执行 BM25 与 BGE-M3 dense retrieval，再由 weighted RRF 合并。

Cross-encoder 使用“原始 topic + Intent Classifier 的 user goal / semantic focus”作为 rerank query；presentation type 不会通过 deterministic retrieval seeds 强行改变召回目标。

## 6. Evidence Sufficiency

固定的“营收 / 融资 / 估值”等缺失事实字段表已经移除。Live 模式在召回后使用独立的 Evidence Sufficiency Judge，只判断当前 evidence 是否足以回答用户核心问题，不生成答案，也不补充外部知识。

如果核心事实缺失，工作流返回 `insufficient_evidence`；offline 模式明确不模拟语义充分性，只用于确定性 pipeline regression。

## 7. Post-Retrieval Processing and Context Construction

Reranker 负责相关性排序；Post-Retrieval Processor 不再二次判断 relevance，也不使用 CORE / SUPPORTING 规则重排。

Processor 按原 reranker 顺序依次执行：

1. **Evidence metadata / risk flags**：标记 `hypothetical`、`marketing_claim`、`metric_claim`、`media_reference`、`profile_reference` 等，不改变排名；
2. **Hard safety filter**：例如用户未询问的“应用设想”不进入 Writer；
3. **Near-duplicate dedup**：使用规范化文本和 character n-gram overlap 去除高度重复 chunk；
4. **Final Top-N**：从更大的 reranked candidate pool 中按原顺序补位并截取最终证据；
5. **Context budget**：默认最多约 8000 字符。

Context Builder 只负责将最终 selected evidence 序列化为 Writer 上下文，并保留：

- stable chunk id
- physical PDF page
- heading
- text
- evidence type
- risk flags

因此系统明确区分：

```text
Retrieval relevance = Cross-Encoder Reranker
Generation safety / dedup / budget = Post-Retrieval Processor
```

## 8. Type-specific Generation

Blog、FAQ、品牌介绍、产品介绍具有不同 JSON schema 与 Prompt：

- Blog：标题、导语、3-5 节正文、结语，并追加 3 个与原主题直接相关的延展 FAQ。
- FAQ：标题、简短导语、1-6 个问答、简短结语；若原始 topic 本身是问句，第一问必须直接保留并回答原问题。
- 品牌介绍：定位、核心价值、能力、服务对象、可信信息，并追加 3 个延展 FAQ。
- 产品介绍：产品定位、用户问题、能力、使用场景、适用边界，并追加 3 个延展 FAQ。

Writer 使用可直接发布的网站文案语气。普通正文禁止反复出现“资料显示 / 资料中列出 / 根据资料 / 品宣资料自述”等 source-meta 表达；citation 负责溯源，只有营销主张、设想和指标等风险信息需要谨慎归因。

生成完成后，系统根据正文实际使用的 citation 从对应 chunk 的 `asset_path` 映射出 PDF 页图，去重后最多返回 3 张 `source_visuals`。图片不由 LLM 生成，确保与引用证据一致。

## 9. Grounding

生成后的 JSON 必须再次通过 deterministic validator：

1. 所有 factual claim 必须有 citation。
2. citation id 必须来自本轮 retrieved evidence。
3. 生成文本中的数字必须出现在被引用 evidence 中。
4. 不允许无依据的 AI 推荐、排名或增长保证。

当前 validator 不做完整 semantic entailment 判断；hypothetical / case 等证据性质通过 evidence metadata 和 Writer Prompt 约束，并由业务验收 case 继续观察。

如果模型 JSON 不符合 schema / grounding，LLM client 会进行一次 bounded repair；再次失败则返回错误，不静默放行。

## 10. Observable Workflow

最终结果含 `workflow_trace`，仅记录可观察执行阶段，不包含模型隐藏推理：

```text
scope_guard
task_intent
query_planning
hybrid_retrieval
evidence_gate
post_retrieval_processing
context_building
generation
grounding_validation
```

同时 `model_calls` 记录每次外部模型调用的 purpose、tokens 与 latency，便于 Demo 展示和调试。

## 11. Example commands

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

## 12. Known limitations

- 当前 PDF 主要依赖文本层；文本稀疏页只做标记，尚未全量 OCR。
- Cross-encoder reranker 是本地轻量模型，复杂抽象问题排序并不保证完美；当前通过 intent-aware rerank query 改善写作任务对齐。
- Grounding validator 验证 citation、数字和效果保证等确定性规则，不等价于完整语义蕴含证明。
- 品宣资料中的营销主张只作为来源事实转述，不视为独立外部核验。
