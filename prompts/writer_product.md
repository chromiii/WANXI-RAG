任务：基于 evidence 生成产品介绍。重点回答“产品解决什么用户问题、核心能力是什么、适合哪些场景、边界在哪里”。不要把公司荣誉或媒体报道当成产品能力。

所有事实性内容必须使用 claim 对象并附 citations；未提供的功能、输入输出、价格、效果指标不得补造。

JSON schema：
{
  "title":"产品介绍标题",
  "summary":[{"text":"产品定位","citations":["pdf-p012-c01"]}],
  "pain_points":[{"text":"用户问题","citations":["pdf-p012-c01"]}],
  "capabilities":[
    {"heading":"能力名称","paragraphs":[{"text":"能力说明","citations":["pdf-p012-c01"]}]}
  ],
  "use_cases":[{"text":"使用场景","citations":["pdf-p012-c01"]}],
  "boundaries":[{"text":"适用边界","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}