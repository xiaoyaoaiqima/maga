# 第一次调用失败记录

- 结果：未返回生成内容。
- 失败类型：读取模型响应超过 120 秒，`TimeoutError: The read operation timed out`。
- 处理：允许一次技术性重试；Prompt、模型、temperature、max_tokens 和输出约束保持不变。
- 边界：不是因为内容质量重抽。
