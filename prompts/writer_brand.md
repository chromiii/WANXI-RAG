任务：基于 evidence 生成品牌介绍。重点回答“这是谁、解决什么问题、核心价值是什么、有哪些能力、服务哪些对象、有哪些可核验的可信信息”。不要写成泛泛 Blog。

只使用与品牌介绍直接相关的 evidence；媒体、荣誉等只可作为 proof points，不能替代品牌价值和能力说明。
所有事实性内容必须使用 claim 对象并附 citations。

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