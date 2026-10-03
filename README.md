# 万悉科技 AI Agent 笔试作品

## RAG 开发入口

本阶段优先完成 Project 1 RAG。GitHub 仓库作为代码源，已补充 Python 3.12 开发环境、Dev Container/Codespaces 配置、Codex `AGENTS.md` 和离线 CI。
运行 `python scripts/setup_dev.py` 初始化；启动、密钥配置与测试见 [开发环境说明](docs/DEVELOPMENT.md)。
公共仓库不提交招聘方原始 PDF 与演示视频；云端默认使用已验证的页码缓存运行，授权环境中放回原始 PDF 后仍可重新解析并校验 SHA-256。

两个项目共用一个本地工作区。Project 1 从指定品宣 PDF 检索资料，输出带页码引用的内容；Project 2 根据用户问题选择 Agent，通过前置依赖和结果传递完成官网分析、GEO 诊断、候选问题生成与内容策略。

## 当前交付状态

- 已实现 Python 核心代码、本地网页、命令行、完整 Prompt、来源缓存、示例输出、验收测试和离线运行记录视频。
- 提供的 PDF 共 42 页，索引包含 40 个有内容的页面块。官网快照实际包含首页与 `/about` 两页；未把无法提取静态正文的 `/geo-agent` 计入检查范围。
- 随包示例和视频明确使用 `offline` 模式。它执行真实的检索、引用检查和 Agent 调度，输出为确定性的资料整理，**不是 DeepSeek 生成结果**。
- DeepSeek 调用、JSON 修复和校验路径已实现；API 传输与修复行为用明确的模拟接口测试。当前环境没有密钥，**尚未进行真实模型调用、语言质量评估或真实 LLM Router 验收**。
- 本地 HTTP 接口和 JavaScript 语法已验证。当前预览环境限制了浏览器页面访问，网页尚待本机视觉检查。

## 五分钟运行

需要 Python 3.10 或更新版本。先解压项目，在项目根目录执行：

```bash
python -m pip install -r requirements.txt
python -m trendee.cli serve
```

打开 `http://127.0.0.1:8000`。没有密钥时默认进入离线模式。若 `data/trendee_brand.pdf` 存在，会核对源文件 SHA-256；公共云端没有原 PDF 时使用已验证的 `data/brand_pages.json` 页码缓存。离线示例不需要下载模型或向量数据库。

## 配置 DeepSeek 后进行正式模型验收

复制 `.env.example` 为 `.env`，在本机或云端 Secret 中填入自己的密钥：

```dotenv
DEEPSEEK_API_KEY=在安全环境中填写
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_TIMEOUT_SECONDS=90
LLM_MAX_TOKENS=5000
```

真实 `.env` 不进入版本控制；密钥不从网页返回，不进入运行日志。

## 命令行用法

```bash
python -m trendee.cli info
python -m trendee.cli search "GEO 和 SEO 的区别" --source pdf
python -m trendee.cli write "为什么中国出海品牌需要进行 GEO 优化？" --mode offline --output outputs/blog.json
python -m trendee.cli agents "官网表达了什么？" --mode offline
python -m trendee.cli agents "哪些内容适合AI引用，并给出GEO优化建议？" --mode offline
python -m trendee.cli agents "生成客户可能问AI的问题，并给出内容策略和优先级。" --mode offline
python -m unittest discover -s tests -v
```

## Project 1 设计

**解析与切分。** 使用 pypdf 提取文本层，保留从 1 开始的物理页码。材料是幻灯片式品宣，单页通常较短，因此以页为自然边界；长页最多 900 字符，优先在句末或换行切分，页内重叠 100 字符。块不会跨页，章节分隔页不进入检索。稳定 id 如 `pdf-p012-c01` 直接对应原始 PDF。

**检索与上下文。** 中文采用双字片段，英文采用词项。BM25 捕捉稀有词与主题匹配，字符 TF-IDF 余弦补充全文相似度，RRF 融合两路排序；GEO、RAG、出海等术语进行明确的查询展开。默认取 6 块，并限制上下文字符数、去除重复片段。这里的混合检索是两种词法方法，未使用稠密语义 embedding，也未宣称获得语义检索性能。

**生成。** DeepSeek 接收主题、目标读者、内容形式和带 id/页码的证据。正文每个事实段落都须携带引用 id。

**检查。** 校验输出结构、引用 id、引用片段中可支持的数字、已知案例误用和明显的效果保证。错误结果最多请求一次模型修正；仍失败则报告错误，不悄悄换成离线答案。

**拒答。** 未提供营收、融资金额或估值时返回 `insufficient_evidence`。无相关资料不强行生成；伪造案例与覆盖规则的要求返回 `rejected`。

## Project 2 设计

包含官网信息分析、GEO 诊断、客户问题生成、内容策略四类 Agent。规则或 LLM Router 只允许选择固定 Agent 注册表；调度器按依赖拓扑执行，并把真实上游 JSON 传给下游 Agent。

## 云端开发

- `.devcontainer/devcontainer.json`：Python 3.12 云端开发环境。
- `AGENTS.md`：Codex 修改代码时的仓库级约束和验证命令。
- `.github/workflows/ci.yml`：离线测试与 smoke test。
- 公共仓库忽略 `data/trendee_brand.pdf` 和 Demo MP4；云端默认使用页码缓存。
