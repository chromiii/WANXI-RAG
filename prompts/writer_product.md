任务：基于 evidence 生成产品介绍。用户原始 topic 是最高优先级语义目标；“产品介绍”只是呈现形式。

如果 topic 是“万悉科技主要帮助客户解决什么问题？”，整份产品介绍就应围绕这些客户问题以及 Trendee 如何解决它们展开，而不是为了填产品页栏目扩写媒体、团队、荣誉或无关公司信息。

优先顺序：
1. 先直接回应 topic；
2. 只介绍与 topic 直接相关的产品定位/能力；
3. 只在 evidence 明确支持时补充使用场景；
4. boundaries 只允许填写资料明确给出的适用边界/限制，不能把“合规GEO”“公司理念”“媒体报道”推断成产品边界。

规则：
- 产品能力必须来自产品/服务/解决问题相关 evidence。
- media/profile evidence 默认不能作为产品能力来源。
- 如果某个栏目资料不足，允许 pain_points/use_cases/boundaries 为空数组，并将缺失写入 limitations。
- 不要使用同一条弱证据把所有栏目填满。
- marketing_claim 必须归因；hypothetical 不能改写成正式产品能力。
- 所有 factual claim 必须带 citations。

JSON schema：
{
  "title":"产品介绍标题",
  "summary":[{"text":"围绕原始 topic 的产品定位/直接回答","citations":["pdf-p012-c01"]}],
  "pain_points":[{"text":"与原始 topic 直接相关的用户问题","citations":["pdf-p012-c01"]}],
  "capabilities":[
    {"heading":"能力名称","paragraphs":[{"text":"该能力如何对应原始 topic","citations":["pdf-p012-c01"]}]}
  ],
  "use_cases":[{"text":"仅限资料明确支持的使用场景/适用对象","citations":["pdf-p012-c01"]}],
  "boundaries":[{"text":"仅限资料明确支持的产品适用边界","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}
