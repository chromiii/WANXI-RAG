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



## PDF ingestion

将招聘方提供的 PDF 放入私有运行目录：

```text
data/private/trendee_brand.pdf
```

然后执行：

```bash
python -m trendee.cli ingest
```

该命令只在本地处理 PDF，不调用外部模型或 API。它会生成：

```text
data/private/
  trendee_brand.pdf
  evidence_staging.jsonl
  ingestion_manifest.json
  assets/
    pages/
      p001.png
      p002.png
      ...
```

`evidence_staging.jsonl` 当前包含 `text` 和 `page_image` 两类 evidence。对 PPT/宣传册式 PDF，默认将整页渲染结果作为视觉资产，因为页面通常由文本、矢量图形和小图标共同组成；单独抽取 PDF 内嵌 raster image 往往只得到 logo/icon 等碎片。

`page_image` 目前使用页标题与整页文本作为可检索代理文本，完整页面 PNG 用于后续引用预览和视觉证据展示。OCR、embedding、Elasticsearch bulk indexing 属于后续阶段；内嵌图片抽取默认关闭。

可先检查 `ingestion_manifest.json` 中的页数、文本 evidence 数和 `page_image_evidence_count`，再继续建立向量索引。


## Evidence normalization

原始 PDF block 只用于 staging，不直接进入向量库。完成 `ingest` 后执行：

```bash
python -m trendee.cli normalize
```

该步骤会：

- 删除重复页眉/页脚和明显无意义短块；
- 只在同一个物理页内合并相邻文本；
- 默认目标约 700 字符、单 chunk 上限 1000 字符；
- 生成稳定引用 ID，如 `pdf-p018-c01`；
- 将每个文本 chunk 的 `asset_path` 绑定到对应的完整页面 PNG；
- 标记文本过少的页面，留给后续 OCR 补充。

输出：

```text
data/private/
  evidence_normalized.jsonl      # 机器读取 / 后续 Elasticsearch
  evidence_normalized.md         # 人工检查 / VS Code Markdown 预览
  normalization_manifest.json
```

`evidence_normalized.md` 按 PDF 页组织，每页展示标题、对应完整页面 PNG 和规范化后的 chunks。Markdown 文件使用 UTF-8 BOM，方便 Windows PowerShell / Notepad / VS Code 直接查看；JSONL 保持标准 UTF-8 作为机器数据源。

如果在 Windows PowerShell 5.1 中直接查看 JSONL，请显式指定 UTF-8：

```powershell
Get-Content data\private\evidence_normalized.jsonl -Encoding UTF8 -TotalCount 3
```

完整页面 PNG 是引用预览资产，不作为重复正文文档与文本 chunk 竞争 Top-K。正常页面通过文本召回后直接带出整页视觉证据；文本稀疏页面后续再使用 OCR 增强。


## Dense embedding + Hybrid retrieval

规范化完成后，安装可选的本地 ML 依赖：

```powershell
py -m pip install -r requirements-ml.txt
```

首次运行会下载本地 embedding 模型 `BAAI/bge-m3`。模型下载完成后，PDF 文本在本机推理，不调用托管 embedding API。

确保 Elasticsearch 已启动：

```powershell
docker compose up -d elasticsearch
```

然后把 `evidence_normalized.jsonl` 本地向量化并写入 Elasticsearch：

```powershell
py -m trendee.cli index-build
```

该命令会：

- 使用 `heading + content` 生成 1024 维 dense embedding；
- 默认按 batch=8 本地计算；
- 同一 PDF source 重建时先删除旧 chunks，避免脏数据；
- embedding 直接写入 Elasticsearch，不额外保存向量文件；
- 保留 page / asset_path / bbox 等引用信息。

检查索引：

```powershell
py -m trendee.cli index-info
```

测试真正的 Hybrid Search：

```powershell
py -m trendee.cli hybrid-search "GEO 原生网站有哪些核心能力？"
```

检索流程为：

```text
query
  ├─ Elasticsearch BM25
  └─ BGE-M3 query embedding -> Elasticsearch kNN
                 ↓
           Python RRF fusion
                 ↓
        optional cross-encoder
                 ↓
              Top-K
```

RRF 在应用层实现，因此不依赖 Elasticsearch 的高级付费检索特性。返回的每个文本 chunk 都保留对应 PDF 页码与完整页面 PNG 的 `asset_path`。

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
