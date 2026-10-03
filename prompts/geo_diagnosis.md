基于官网 evidence、静态 HTML 检测结果和前置官网分析，评估内容可理解性与可引用性。
既指出已有优点，也指出内容缺口和可能误读的表达。推荐补充直接答案、资料出处、方法边界、可核验案例。
不能仅凭网站内容推断它已被 ChatGPT 等平台收录，也不能给出伪造的实测引用率。
JSON 必须包含：
{"findings":[{"type":"strength|gap|risk","observation":{"text":"基于 evidence 的观察","citations":["web-01-meta"]},
 "recommendation":"建议","priority":"P0|P1|P2","verification":"observed_static_html|inference_to_verify"}],
 "measurement_plan":["用固定问题集、保存模型回答及 URL 引用，前后对照衡量引用覆盖率；记录模型版本和日期"],
 "scope_note":"实际已抓取的页面范围及静态分析限制"}
最多 6 条 finding。建议不是已实现结果。
