任务：基于 evidence 生成官网 Blog。先围绕主题确定 3-5 个核心主张，再只使用真正支持这些主张的 evidence；不要为了覆盖 Top-K 而强行写入无关材料。

输出必须是结构完整的 Blog：标题、导语、3-5 个小节、可选 FAQ、结语。正文约 800-1200 中文字。
每个事实性段落都使用 claim 对象并附 citations。建议可以写，但必须和资料事实区分；不要创造客户、数字、技术指标或结果承诺。
与主题无关的客户、媒体、团队、荣誉或“应用设想”不要为了使用 evidence 而写入正文；含“设想”的材料只能作为设想描述，绝不能改写成已合作/已交付案例。

JSON schema：
{
  "title":"标题",
  "lead":[{"text":"导语","citations":["pdf-p012-c01"]}],
  "sections":[
    {"heading":"小标题","paragraphs":[{"text":"正文","citations":["pdf-p012-c01"]}]}
  ],
  "faq":[
    {"question":"可选问题","answer":{"text":"回答","citations":["pdf-p012-c01"]}}
  ],
  "conclusion":[{"text":"结语","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}