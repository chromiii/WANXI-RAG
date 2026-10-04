任务：基于 evidence 生成 FAQ。用户原始 topic 是主问题，FAQ 只是呈现方式，不得改变问题本身。

要求：
1. 如果 topic 本身是一个明确问题，第一条 FAQ 的 question 必须与原始 topic 相同或仅做标点级规范化；answer 必须直接回答这个原问题。
2. 其余 FAQ 只能作为原问题的自然子问题/补充问题，不能把主题扩散到无关行业、媒体、团队、荣誉等信息。
3. 每个回答第一句先给结论，后面最多补充必要解释。
4. 多个 FAQ 不要重复同一个答案。
5. 如果资料不足以支持某个子问题，不要硬写，写入 limitations。
6. 所有事实性回答必须带 citations。

JSON schema：
{
  "title":"FAQ标题",
  "intro":[{"text":"1-2句简短说明","citations":["pdf-p012-c01"]}],
  "faq":[
    {"question":"第一问优先使用原始 topic","answer":{"text":"直接回答","citations":["pdf-p012-c01"]}}
  ],
  "conclusion":[{"text":"1句总结","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}
