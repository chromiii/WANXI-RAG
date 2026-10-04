任务：基于 evidence 生成可直接用于官网的品牌介绍。重点回答品牌是谁、为何存在、解决什么问题、具备哪些能力、服务哪些对象。

要求：
1. 品牌定位与核心价值优先使用公司定位、愿景和业务价值相关 evidence。
2. 核心能力必须使用能力、产品或服务相关 evidence，不能拿媒体报道替代。
3. 媒体、荣誉、人物资料只可作为 proof_points，不得主导品牌定位。
4. 正文使用自然品牌文案，不写成研究报告或资料摘要。
5. 如果某项资料不足，不要补造；proof_points 可以为空，并写入 limitations。
6. 所有事实性内容必须带 citations。
7. 正文结束后追加 3 个 FAQ，作为当前品牌介绍主题的自然延展，问题应覆盖用户下一步最可能关心的不同信息点，且答案必须有 evidence 支持。

JSON schema：
{
  "title":"品牌介绍标题",
  "positioning":[{"text":"品牌定位","citations":["pdf-p012-c01"]}],
  "value_propositions":[{"text":"核心价值","citations":["pdf-p012-c01"]}],
  "capabilities":[
    {"heading":"核心能力","paragraphs":[{"text":"能力说明","citations":["pdf-p012-c01"]}]}
  ],
  "audiences":[{"text":"服务对象","citations":["pdf-p012-c01"]}],
  "proof_points":[{"text":"可信信息","citations":["pdf-p012-c01"]}],
  "faq":[
    {"question":"延展问题","answer":{"text":"回答","citations":["pdf-p012-c01"]}}
  ],
  "limitations":["资料不足或需核验的事项"]
}