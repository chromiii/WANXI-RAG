任务：基于 evidence 生成可直接用于官网的产品介绍。用户原始 topic 是最高优先级语义目标；“产品介绍”只决定呈现方式。

要求：
1. 先回应原始 topic，再组织与该 topic 直接相关的产品定位、用户问题、核心能力和使用场景。
2. 产品能力必须来自产品、服务或解决问题相关 evidence。
3. media/profile evidence 默认不能作为产品能力来源。
4. use_cases 和 boundaries 只有在 evidence 明确支持时才填写；资料不足时允许为空数组。
5. boundaries 只描述 evidence 明确支持的适用范围或限制，不得从公司理念、合规表述或媒体报道推断产品边界。
6. 正文使用自然产品文案，不写成资料摘要或检索报告。
7. marketing_claim 必须谨慎归因；hypothetical 不能改写成正式产品能力。
8. 所有 factual claim 必须带 citations。
9. 正文结束后追加 3 个 FAQ，作为原始 topic 与产品介绍的自然延展；问题应补充用户下一步最可能关心的不同维度，且答案必须由 evidence 支持。

JSON schema：
{
  "title":"产品介绍标题",
  "summary":[{"text":"产品定位或对原始 topic 的直接回应","citations":["pdf-p012-c01"]}],
  "pain_points":[{"text":"与原始 topic 直接相关的用户问题","citations":["pdf-p012-c01"]}],
  "capabilities":[
    {"heading":"能力名称","paragraphs":[{"text":"能力说明","citations":["pdf-p012-c01"]}]}
  ],
  "use_cases":[{"text":"使用场景或适用对象","citations":["pdf-p012-c01"]}],
  "boundaries":[{"text":"资料明确支持的适用边界","citations":["pdf-p012-c01"]}],
  "faq":[
    {"question":"延展问题","answer":{"text":"回答","citations":["pdf-p012-c01"]}}
  ],
  "limitations":["资料不足或需核验的事项"]
}