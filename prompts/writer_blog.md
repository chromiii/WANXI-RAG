任务：基于 evidence 生成官网 Blog。围绕用户原始主题形成完整论证，不要把文章写成公司资料摘抄或能力清单。

要求：
1. 标题、导语、3-5 个正文小节和结语必须共同服务于原始主题。
2. 正文优先解释主题本身，再使用与主题直接相关的公司事实、能力或方法支撑论点。
3. 每个事实性段落使用 claim 对象并附 citations。
4. 不得为了覆盖 Top-K 而强行写入无关客户、媒体、团队、荣誉或设想。
5. 正文结束后追加 3 个 FAQ，作为原始主题的自然延展；三个问题应分别补充不同角度，不重复正文标题，也不引入 evidence 不支持的新话题。
6. 正文约 800-1200 中文字，FAQ 不计入正文长度。

JSON schema：
{
  "title":"标题",
  "lead":[{"text":"导语","citations":["pdf-p012-c01"]}],
  "sections":[
    {"heading":"小标题","paragraphs":[{"text":"正文","citations":["pdf-p012-c01"]}]}
  ],
  "conclusion":[{"text":"结语","citations":["pdf-p012-c01"]}],
  "faq":[
    {"question":"延展问题","answer":{"text":"回答","citations":["pdf-p012-c01"]}}
  ],
  "limitations":["资料不足或需核验的事项"]
}