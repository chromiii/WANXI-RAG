# WANXI-RAG

![CI](https://github.com/chromiii/WANXI-RAG/actions/workflows/ci.yml/badge.svg)

万悉科技 AI 高级工程师笔试 · Project 1。

这是一个面向官网内容生成的 evidence-backed RAG 系统：读取招聘方提供的品宣 PDF，完成页码可追溯的解析、混合检索、问题重组、证据充分性判断、结构化写作和引用校验。

> 仓库只保存代码、Prompt、测试和文档。招聘方 PDF、解析结果、Embedding、Elasticsearch 数据、API Key、运行日志和 Demo 输出均保持在本地私有运行环境中。

## What it does

系统支持四类输出：

- Blog
- FAQ
- 品牌介绍
- 产品介绍

核心链路：

~~~text
PDF
→ PyMuPDF page-preserving ingest
→ Normalize / stable chunk IDs
→ LLM Intent Classifier
→ Query Transformation
→ Elasticsearch BM25 + BGE-M3
→ weighted RRF
→ local Cross-Encoder reranker
→ Evidence Sufficiency Gate
→ Post-Retrieval dedup / safety / context budget
→ Type-specific Writer
→ Grounding Validator
→ cited content + physical PDF page
~~~

## Assignment mapping

| 笔试要求 | 本项目实现 |
| --- | --- |
| PDF 读取、解析、切分 | PyMuPDF 文本块 + 整页 PNG；同物理页内 normalize；稳定 chunk ID |
| 检索与上下文 | BM25 + BGE-M3 dense retrieval + weighted RRF + cross-encoder rerank |
| Prompt / 内容生成 | Intent、Query Planner、Evidence Sufficiency、四类 Writer 独立 Prompt |
| 防幻觉与引用 | citation closure、数字检查、效果保证 guard、Evidence Sufficiency、hypothetical metadata |
| Demo / 工程落地 | CLI、Local Debug Studio、单元测试、真实 PDF live acceptance evaluator |

## Key design decisions

- **Original query is preserved.** Query rewrite 只能扩展召回，不能替代用户原问题。
- **Intent ≠ Query Rewrite.** Intent 只理解用户目标；Query Planner 单独决定 passthrough / rewrite / expand / decompose。
- **Presentation Contract is separate from semantic goal.** 用户显式选择 FAQ/产品介绍时，格式不能覆盖原始语义目标。
- **Retrieval relevance belongs to the reranker.** Post-Retrieval 不再通过产品类型关键词重新做 relevance ranking。
- **Missing facts stop before writing.** Live 模式使用通用 Evidence Sufficiency Judge，而不是维护“营收/融资/估值”等字段黑名单。
- **Grounding is explicit but bounded.** Validator 检查 citation ID、数字和高风险保证类表述，但不声称证明完整 semantic entailment。
- **Private data stays local.** PDF、页图、normalized evidence、向量索引、密钥和运行日志不进入 Git。

## Quick start

完整安装说明见 docs/INSTALL.md。

Windows PowerShell 快速流程：

~~~powershell
git clone https://github.com/chromiii/WANXI-RAG.git
cd WANXI-RAG

py scripts\setup_dev.py --with-ml
.\.venv\Scripts\Activate.ps1

Copy-Item .env.example .env
# 在 .env 中填写 DEEPSEEK_API_KEY

docker compose up -d elasticsearch

# 将授权 PDF 放到 data/private/trendee_brand.pdf
py -m trendee.cli prepare
py -m trendee.cli index-build

py scripts\eval_project1.py --mode live --require-pdf-artifacts
py -m trendee.cli serve
~~~

浏览器打开：

~~~text
http://127.0.0.1:8000
~~~

## Code-only review

没有招聘方 PDF、没有 API Key，也可以验证代码基线：

~~~powershell
py scripts\setup_dev.py
~~~

或手动：

~~~powershell
py -m pip install -r requirements.lock
py -m unittest discover -s tests -v
py -m compileall -q trendee
~~~

CI 使用同一类 code-only 检查，不读取私有知识库。

## Live acceptance

真实 PDF + DeepSeek 的完整验收：

~~~powershell
py scripts\eval_project1.py --mode live --require-pdf-artifacts
~~~

单 case：

~~~powershell
py scripts\eval_project1.py --mode live --case official_blog
py scripts\eval_project1.py --mode live --case hypothetical_bank_scenario
~~~

验收 case 的唯一来源：

~~~text
eval/project1_cases.json
~~~

CLI demo、Web 快速案例和 acceptance evaluator 共用该 catalog，避免三处重复 hardcoding。

## Local Debug Studio

启动：

~~~powershell
py -m trendee.cli serve
~~~

页面可观察：

- Intent 的 content type / semantic focus / user goal / confidence
- Query Plan 与 original / expanded queries
- BM25 / dense / RRF / reranker 召回线索
- Evidence Sufficiency
- Post-Retrieval 状态
- 最终 Writer JSON / Markdown
- citation → chunk → PDF physical page
- Grounding 结果
- model call token / latency metadata
- 本地 JSONL run log

## Repository layout

~~~text
WANXI-RAG/
├─ trendee/
│  ├─ ingestion/          # PDF ingest + normalization
│  ├─ search/             # ES / embedding / RRF / reranker
│  ├─ rag/                # scope / intent / evidence gate / writer workflow
│  ├─ grounding.py        # citation / numeric / guarantee guards
│  ├─ llm.py              # DeepSeek-compatible model boundary
│  ├─ server.py           # local Debug Studio API
│  └─ cli.py
├─ prompts/               # model prompts
├─ eval/
│  └─ project1_cases.json # single acceptance/demo case catalog
├─ scripts/
│  ├─ setup_dev.py
│  └─ eval_project1.py
├─ tests/                 # code-only regression suite
├─ web/                   # local Debug Studio
├─ docs/
│  ├─ INSTALL.md
│  ├─ DEMO.md
│  ├─ PROJECT1_RAG.md
│  ├─ PROJECT1_TESTING.md
│  └─ DEVELOPMENT.md
├─ docker-compose.yml
├─ requirements.lock
└─ requirements-ml.txt
~~~

## Runtime data

默认私有目录：

~~~text
data/private/
├─ trendee_brand.pdf
├─ evidence_staging.jsonl
├─ evidence_normalized.jsonl
├─ ingestion_manifest.json
├─ normalization_manifest.json
├─ assets/pages/
├─ eval/
└─ logs/
~~~

也可以通过 WANXI_DATA_DIR 指向其他私有路径。

## Models and infrastructure

| Component | Default |
| --- | --- |
| LLM | DeepSeek-compatible API |
| Dense embedding | BAAI/bge-m3 |
| Cross-encoder | BAAI/bge-reranker-base |
| Search store | Elasticsearch 9.5.4 |
| PDF parser | PyMuPDF |
| Web demo | Python stdlib HTTP server + vanilla JS |

Embedding 和 reranker 均在本地运行；PDF 文本不会被发送到托管 embedding API。

## Tests

~~~powershell
py -m unittest discover -s tests -v
py -m unittest discover -s tests -p "test_project1_*.py" -v
~~~

测试覆盖包括：

- Intent / explicit presentation contract
- Query transformation contract
- PDF page preservation / boilerplate / chunk boundary
- Hybrid retrieval primitives
- Evidence Sufficiency
- hypothetical evidence handling
- dedup / context budget
- Writer schema
- citation closure / numeric hallucination / unsupported guarantee
- source visual provenance

详细说明见 docs/PROJECT1_TESTING.md。

## Security & privacy

不要提交：

- .env / API Key
- 招聘方 PDF
- normalized evidence
- page renders
- embeddings / Elasticsearch volume
- website runtime snapshot
- evaluation reports
- Demo 视频

.gitignore 已覆盖这些运行时数据。完整边界见 data/README.md 与 docs/DEVELOPMENT.md。

## Known limitations

- 当前主要依赖 PDF 文本层；文本稀疏页会被标记，但没有实现全量 OCR/视觉模型补全。
- Cross-encoder 只能提高候选排序质量，不保证复杂问题始终获得完美 Top-K。
- Evidence Sufficiency 使用 LLM 做语义判断，因此属于 bounded model judgment，不是形式证明。
- Grounding Validator 验证确定性约束，但不等价于完整 NLI / semantic entailment 系统。
- 品宣材料中的营销性表述只作为来源事实转述，不代表独立第三方核验。

## More docs

- 安装与从零运行：docs/INSTALL.md
- Demo / 录屏脚本：docs/DEMO.md
- RAG 设计：docs/PROJECT1_RAG.md
- 测试与验收：docs/PROJECT1_TESTING.md
- 开发与数据边界：docs/DEVELOPMENT.md
