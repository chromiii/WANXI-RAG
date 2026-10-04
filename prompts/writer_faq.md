任务：基于 evidence 生成 FAQ 页面，不要写成普通长文章。只围绕用户主题挑选最有价值的问题与回答；不要因为 evidence 中出现某个话题就强行新增无关 FAQ。

输出应包含：标题、简短导语、3-8 个 FAQ、简短结语。每个回答应尽量直接回答问题，再补充必要解释。
所有事实性回答都必须使用 claim 对象并附 citations。不得创造客户、数字、技术指标或效果承诺。

JSON schema：
{
  "title":"FAQ标题",
  "intro":[{"text":"简短导语","citations":["pdf-p012-c01"]}],
  "faq":[
    {"question":"问题","answer":{"text":"直接回答","citations":["pdf-p012-c01"]}}
  ],
  "conclusion":[{"text":"简短结语","citations":["pdf-p012-c01"]}],
  "limitations":["资料不足或需核验的事项"]
}