# 自由规划第一次调用失败记录

- 模型返回 10 个 item，但至少一个 `comment` 为空。
- 校验结果：`expected 10 non-empty comments, got 10`。
- 未按内容质量筛选；允许使用相同 Prompt 和参数做一次 schema 重试。
