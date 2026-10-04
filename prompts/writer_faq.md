任务：基于 evidence 生成 FAQ。FAQ 的呈现方式必须是“问题 → 直接回答”，不要写成普通文章，也不要先铺大量背景。

要求：
1. 围绕用户原始主题设计 3-6 个真正有帮助的问题。
2. 每个回答第一句直接回答问题，后面最多补充必要解释。
3. 不要因为 evidence 中出现行业、媒体、团队、荣誉等信息就强行新增无关问题。
4. 多个问题不要重复同一个答案。
5. 如果资料不能回答某个重要问题，不要硬写，放入 limitations。
6. 所有事实性回答必须带 citations。

JSON schema：
{
  "title":"FAQ标题",
  "intro":[{"text":"1-2句简短说明","citations":["pdf-p012-c01"]}],
  "faq":[
    {"question":"用户真正会问的问题","answer":{"text":"直接、简洁回答","citations":["pdf-p012-c01"]}}
  ],
  "conclusion":[{"text":"1句总结","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}