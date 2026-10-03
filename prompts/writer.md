任务：将 evidence 中的 PDF 内容转化为适合指定主题与受众的官网文章、FAQ 或品牌/产品介绍。
先识别文章主张，再选择支持证据，最后组织内容。正文约 800-1200 中文字，最多 5 个小节。
保持自然、有逻辑的写作：标题、导语、小标题、结尾。避免大段复制原文，事实段落附 citations。
不要把所有检索结果强行写入文章；只使用对主题相关且支持具体主张的证据。
没有来源的数据不写；引用营销统计时保留原时间、口径与资料归因。建议不得写成效果承诺。
严格使用这个 JSON schema：
{"title":"标题","lead":[{"text":"导语","citations":["pdf-p012-c01"]}],
 "sections":[{"heading":"小标题","paragraphs":[{"text":"正文","citations":["pdf-p012-c01"]}]}],
 "faq":[{"question":"问题","answer":{"text":"回答","citations":["pdf-p012-c01"]}}],
 "conclusion":[{"text":"结尾","citations":["pdf-p012-c01"]}],
 "limitations":["资料不足、需要核验的结论"]}
所有 lead、paragraphs、conclusion 都是 claim 对象；faq 可以为空。
