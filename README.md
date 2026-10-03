# WANXI-RAG

万悉科技 AI 高级工程师笔试项目。当前仓库只保存代码、Prompt、测试与开发配置；招聘方提供的 PDF、网页运行时快照、解析缓存、向量索引、模型密钥和 Demo 输出均不进入 Git。

## 项目目标

Project 1：读取万悉品宣 PDF，完成页码可追溯的 RAG 写作流程：

```text
PDF -> page-preserving parse -> chunk -> retrieval -> context -> LLM -> grounding -> cited output
```

当前检索实现为 BM25 + character TF-IDF + RRF，属于词法混合检索，不宣称使用 dense embedding。后续可在不改变数据边界的前提下增加 embedding / reranker。

Project 2：基于官网信息实现 Agent Router、依赖调度和多 Agent 协作，包括官网信息分析、GEO 诊断、客户问题生成和内容策略。

## 数据安全边界

Git 中只保存：

- Python 源码
- Prompt
- tests 与 synthetic fixtures
- README / 开发文档
- `.env.example`
- CI / Dev Container 配置

以下内容只在运行时提供，不提交 GitHub：

- 万悉品宣 PDF
- 解析后的 page/chunk cache
- 官网抓取快照
- embedding / FAISS / Chroma / Qdrant 等索引数据
- `.env` 与任何真实 API Key
- Demo 视频与生成结果

默认私有数据目录为 `data/private/`，也可通过 `WANXI_DATA_DIR` 指定其它私有路径。

## 云端开发

创建 Codespace / Codex 工作区后：

```bash
python scripts/setup_dev.py
python -m unittest discover -s tests -v
```

上述步骤不需要真实万悉数据，也不会调用模型 API。

真实数据注入后再运行：

```bash
python -m trendee.cli info
python -m trendee.cli search "GEO 和 SEO 的区别" --source pdf
python -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode offline
python -m trendee.cli serve --host 0.0.0.0 --port 8000
```

## 私有数据准备

默认目录：

```text
data/
  README.md
  private/                 # gitignored
    trendee_brand.pdf
    website_snapshot.json  # 运行时抓取或私下提供
```

也可以在 `.env` 中指定：

```dotenv
WANXI_DATA_DIR=/secure/path/wanxi-data
DEEPSEEK_API_KEY=
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
```

不要提交真实 `.env`。

## 代码结构

```text
trendee/
  documents.py    # PDF / 官网数据读取与抓取
  retrieval.py    # chunk + lexical hybrid retrieval
  grounding.py    # citation / numeric / hallucination guards
  llm.py          # DeepSeek-compatible LLM boundary
  agents.py       # Agent registry, router and dependencies
  service.py      # RAG / multi-agent orchestration
  cli.py          # CLI
prompts/          # 完整 Prompt
tests/            # 不依赖私有数据的 CI 测试
data/README.md    # 运行时数据约定
```


## Elasticsearch 本地检索层

当前本地开发使用 Elasticsearch 作为后续 Hybrid RAG 的检索基础设施。Docker 只监听 `127.0.0.1:9200`，索引数据保存在 Docker named volume `wanxi_rag_es_data`，不会写入 Git 仓库。

启动：

```bash
docker compose up -d elasticsearch
```

检查连接：

```bash
python -m trendee.cli index-info
```

首次创建空 evidence index：

```bash
python -m trendee.cli index-init
```

当前 schema 已定义：

- `content` / `heading`：CJK 文本检索字段，后续走 BM25。
- `embedding`：1024 维 `dense_vector`，为 BGE-M3 等 embedding 预留。
- `modality`：区分 `text`、`image` 等 evidence。
- `page` / `source_sha256`：引用溯源与源文件一致性。
- `asset_path`：仅保存本地私有图片路径，不保存图片本体。
- `metadata`：扩展字段。

此阶段只建立基础设施和 schema，不向 Elasticsearch 写入万悉 PDF、图片、解析缓存或 embedding。

## 当前状态

核心 RAG、Grounding、LLM 边界、Agent Router 与 CLI 已进入仓库。当前清理后的 GitHub 基线刻意不携带任何真实知识库数据，因此完整万悉 Demo 需要在运行环境注入私有 PDF / 官网快照后执行。

详细开发约定见 `docs/DEVELOPMENT.md`。
