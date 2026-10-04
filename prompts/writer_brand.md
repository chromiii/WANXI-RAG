任务：基于 evidence 生成品牌介绍。最终内容必须像“公司/品牌介绍页”，重点回答品牌是谁、为何存在、解决什么问题、具备哪些能力、服务哪些对象。

要求：
1. 品牌定位与核心价值优先使用公司定位/愿景类 evidence。
2. 核心能力必须使用能力/产品/服务相关 evidence，不能拿媒体报道替代。
3. 媒体、荣誉、人物资料只能进入 proof_points，不得主导品牌定位。
4. 如果某项资料不足，不要补造；proof_points 可以为空，并写入 limitations。
5. 所有事实性内容必须带 citations。

JSON schema：
{
  "title":"品牌介绍标题",
  "positioning":[{"text":"品牌定位","citations":["pdf-p012-c01"]}],
  "value_propositions":[{"text":"核心价值","citations":["pdf-p012-c01"]}],
  "capabilities":[
    {"heading":"核心能力","paragraphs":[{"text":"能力说明","citations":["pdf-p012-c01"]}]}
  ],
  "audiences":[{"text":"服务对象","citations":["pdf-p012-c01"]}],
  "proof_points":[{"text":"可核验的可信信息","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}