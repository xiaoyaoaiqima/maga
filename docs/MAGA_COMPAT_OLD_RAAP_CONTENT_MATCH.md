# MAGA 兼容老 RAAP 文章读取逻辑

## 背景

老 RAAP 的文章主表是 `content`。新 MAGA 如果希望不修改下游服务读取文章逻辑，应把最终可用文章投影到同名 `content` 表，并兼容老 RAAP 的文章匹配接口语义。

当前需要兼容的老 RAAP 下游读取入口是：

```python
@router.post("/match", response_model=ContentMatchResponse, summary="按 agent + user_tags 获取内容")
```

该接口由 `ContentService.match_and_lock_contents()` 调用 `find_matching_contents()` 完成文章筛选与锁定。

## 关键结论

老 RAAP 的 `/match` 读取逻辑不依赖 `distribution_status`。

`distribution_status` 属于另一套内容池库存接口的状态字段，主要服务于 `AVAILABLE -> LOCKED -> CONSUMED` 这类库存领取流程。它不是 `/match` 接口判断文章是否可被下游拿到的条件。

因此，如果新 MAGA 的兼容目标是让老下游通过 `/match` 获取文章，优先保证以下字段符合老逻辑，而不是优先改 `distribution_status`：

- `agent_code` 能匹配请求中的 `agent_id` / `agent_id_list` / `agent_code`
- `context_list` 能被请求中的 `user_tags[].tag_name` 命中
- `is_valid = 1`
- `online_status = "ONLINE"`
- `is_test_case = 0`
- `is_deleted = 0`
- `is_used = 0`
- `is_locked = 0`，或锁已过期

## 老 RAAP `/match` 筛选条件

老 RAAP `find_matching_contents()` 的核心筛选条件是：

```text
Content.agent_code in agent_code_list
Content.is_deleted == 0
Content.is_valid == 1
Content.is_test_case == 0
Content.online_status == "ONLINE"
Content.is_used == 0
Content.is_locked == 0 OR Content.lock_expire_time < now
Content.context_list LIKE each user tag name
```

命中后，如果请求 `is_lock = true`，服务会设置：

```text
is_locked = 1
lock_user_id = request.user_id
lock_time = now
lock_expire_time = now + lock_minutes
```

调用方确认使用文章时，再通过使用接口设置：

```text
is_used = 1
user_id = request.user_id
use_time = now
```

## 老 RAAP 文章生成后的状态流转

老 RAAP 生文任务生成文章时：

```text
distribution_status 默认 PENDING
is_valid 默认 NULL
online_status 默认 OFFLINE
```

审核专家全部通过后：

```text
is_valid = 1
```

前端任务执行详情页点击上线后：

```text
online_status = "ONLINE"
```

此时文章可以被 `/match` 下游读取。`distribution_status` 仍可以是 `PENDING`，不影响 `/match`。

## 新 MAGA 兼容建议

新 MAGA 生成最终文章后，应写入或更新 `content` 表，并至少维护以下字段：

```text
job_id
sub_job_id
content_id
agent_code
title
content
context_list
is_valid
is_test_case
online_status
is_deleted
is_used
is_locked
```

推荐兼容流转：

```text
生成成功：
  is_valid = NULL
  online_status = "OFFLINE"
  is_test_case = 0
  is_deleted = 0
  is_used = 0
  is_locked = 0

审核通过：
  is_valid = 1

运营确认上线，或新 MAGA 自动发布到下游可读状态：
  online_status = "ONLINE"
```

如果后续还要兼容老 RAAP 的内容池 `/acquire` 接口，再单独设计 `distribution_status = "AVAILABLE"` 的上架动作；不要把它和 `/match` 读取逻辑混为一谈。

## 过渡期架构方案

短期可以让新 MAGA 和老 RAAP orchestrator 连接同一个数据库，并共用同一张 `content` 表。这样新 MAGA 只要按老 RAAP 的字段语义写入文章，老 RAAP 已有 `/contents/match` 和 `/contents/use` 就可以继续服务下游，不需要立刻修改下游服务读取逻辑。

该方案适合作为过渡期方案，不建议作为长期架构。长期应逐步让新 MAGA 成为文章生成和读取的唯一 owner。

### 短期职责边界

短期共库时，建议明确如下边界：

```text
新 MAGA：
  负责写入生成产物到 content
  负责设置 title/content/context_list/agent_code/is_valid/online_status 等兼容字段
  不负责锁定和消费文章

老 RAAP：
  继续提供 /contents/match
  继续提供 /contents/use
  负责 is_locked/is_used/lock_user_id/lock_time/lock_expire_time/use_time 等读取侧流转字段
```

新 MAGA 不应主动修改以下字段，除非明确接管 `/match` 和 `/use`：

```text
is_locked
lock_user_id
lock_time
lock_expire_time
is_used
user_id
use_time
```

### 共库写入规则

新 MAGA 写入 `content` 时，应遵循老 RAAP `/match` 可读条件：

```text
content_id: 全局唯一，建议使用 maga_xhs_ 前缀
job_id: MAGA 批次或任务编码
sub_job_id: MAGA 单篇 item/run 标识
agent_code: 必须能匹配下游请求对应 Agent
context_list: 必须包含可被 user_tags 命中的标签/上下文名
title: 最终标题
content: 最终正文
is_valid: 审核通过后为 1
online_status: 运营确认可读后为 ONLINE
is_test_case: 正式文章为 0
is_deleted: 0
is_locked: 初始 0
is_used: 初始 0
distribution_status: 可保持默认 PENDING；/match 不依赖它
```

### 演进路线

推荐分三步演进：

```text
阶段 1：共库兼容
  新 MAGA 写 content
  老 RAAP 继续提供 /match 和 /use
  下游不改读取逻辑

阶段 2：接口迁移
  新 MAGA 实现与老 RAAP 等价的 /contents/match 和 /contents/use
  请求/响应保持兼容
  下游逐步切换调用地址

阶段 3：所有权收敛
  新 MAGA 成为 content 表和文章读取链路 owner
  老 RAAP 退出文章读取链路
  content 表后续 schema 变更由 MAGA 统一管理
```

### 风险与约束

共库方案需要接受以下约束：

- `content` 表结构短期冻结，变更必须同时评估新 MAGA 和老 RAAP。
- 新 MAGA 写入必须保持老 RAAP 字段语义，不新增下游不可理解的必填依赖。
- 老 RAAP 的 `/match` 会修改锁定字段，新 MAGA 不能把这些字段覆盖回初始状态。
- `content_id` 必须全局唯一，避免和老 RAAP 历史文章冲突。
- `agent_code` 和 `context_list` 是 `/match` 命中的关键字段，不能只写标题正文。
