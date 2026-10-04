任务：基于 evidence 生成产品介绍。最终内容必须像“产品页/产品说明”，而不是公司新闻、媒体报道或泛泛品牌文章。

优先回答：
1. 产品是什么 / 产品定位；
2. 它解决什么用户问题；
3. 核心能力是什么；
4. 适合什么使用场景 / 服务对象；
5. 有哪些资料未覆盖的边界。

规则：
- 产品能力必须来自 evidence，不得从公司理念、媒体报道或团队介绍反推产品功能。
- 如果某个栏目资料不足，允许该数组为空，并把缺失信息写入 limitations；不要用同一条弱证据把所有栏目填满。
- marketing_claim 必须归因；hypothetical 不能改写成正式产品能力。
- 产品介绍应突出“能力 → 场景 → 价值”，避免重复公司介绍。

JSON schema：
{
  "title":"产品介绍标题",
  "summary":[{"text":"产品定位","citations":["pdf-p012-c01"]}],
  "pain_points":[{"text":"产品解决的用户问题","citations":["pdf-p012-c01"]}],
  "capabilities":[
    {"heading":"能力名称","paragraphs":[{"text":"能力说明","citations":["pdf-p012-c01"]}]}
  ],
  "use_cases":[{"text":"使用场景/适用对象","citations":["pdf-p012-c01"]}],
  "boundaries":[{"text":"资料明确说明的适用边界","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}