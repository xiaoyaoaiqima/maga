# MAGA Worker Executor Protocol

## 当前边界

MAGA 负责业务规则、表达扩散语料、Expert、模型参数、任务状态、审核状态和反馈记录。`maga-worker` 只执行 MAGA 下发的能力调用。

当前对外能力只保留：

- `asset.import`：导入规则/资料资产。
- `content.generate`：文章和评论统一生成。
- `content.rewrite`：违禁词审核或人工反馈后的统一改写。

旧 `xhs.*`、`comment.generate`、单篇 `/content-agent/generation/start` 和自动学习类 capability 已下线。

## Invoke Envelope

`POST /invoke`

```json
{
  "protocol_version": "0.1",
  "run_id": 1,
  "task_id": 1,
  "stage_call_id": "stage-001",
  "capability": "content.generate",
  "executor_hints": {
    "timeout_seconds": 60
  },
  "input": {}
}
```

请求头：

- `X-Maga-Protocol-Version: 0.1`
- `Authorization: Bearer <executor_token>`，当 executor 配置了 token 时必填。

成功响应：

```json
{
  "stage_call_id": "stage-001",
  "status": "succeeded",
  "output": {},
  "stats": {
    "executor": "maga-worker",
    "module": "content-generator",
    "total_latency_ms": 1200
  }
}
```

失败响应仍返回 200，由协议状态表达失败：

```json
{
  "stage_call_id": "stage-001",
  "status": "failed",
  "error_code": "input_invalid",
  "error_message": "unsupported capability: legacy.capability"
}
```

## content.generate

文章和评论都走同一 capability。内容类型由 `content_type` 和 `output_fields` 决定。

评论输出：

```json
{
  "comment": "自然评论正文"
}
```

文章输出：

```json
{
  "title": "标题",
  "body": "正文"
}
```

核心输入由 MAGA 统一组装：

- `content_type`
- `output_fields`
- `business_rule`
- `selected_keywords`
- `expert`
- `model_config`
- `rendered_prompt`

## content.rewrite

审核和改写由 MAGA 控制流程：MAGA 先做确定性违禁词扫描，命中后才调用 `content.rewrite`。worker 不负责自主审核决策。

核心输入：

- `content_type`
- `output_fields`
- `previous_content`
- `forbidden_hits`
- `forbidden_replacements`
- `rewrite_instructions`
- `business_rule`
- `selected_keywords`
- `expert`
- `model_config`
- `rendered_prompt`

输出字段和 `content.generate` 保持一致。

## asset.import

资产导入只返回结构化资产结果，不直接触发生文。正式运营流程优先使用业务规则包导入接口；`asset.import` 保留为 worker 侧导入能力。
