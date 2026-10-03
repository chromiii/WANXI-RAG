读取前置官网分析和 GEO 诊断。若问题生成已执行，引用其候选问题。把发现转为可执行内容任务。
优先级按事实可信度风险、用户意图覆盖与实施成本排序，不能虚构搜索流量、转化率或预计收益。
JSON：{"actions":[{"priority":"P0|P1|P2","content_type":"FAQ|Blog|产品页|案例页|方法页",
 "topic":"内容题目","target_question":"对应用户问题",
 "reason":{"text":"为什么要做，基于官网证据及前置诊断","citations":["web-01-b001-c01"]},
 "acceptance_criteria":"可检查的内容完成标准","measurement":"上线后如何验证，非效果保证"}],
 "scope_note":"建议基于已抓取页面，需补充实际用户数据验证"}。
最多 5 个任务，必须含具体验收标准，不要只写“多写博客”。
