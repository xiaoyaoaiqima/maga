# 旺玥 Rewrite Quality Qwen 稳定性对比

## 实验

- 数据：候选集 15 条，当前状态 candidate。
- 模型：qwen-plus、qwen3-max。
- 每条重复 3 轮，temperature=0，共 90 次调用。
- retry 是 Rewrite Quality 中最接近 watch 的灰区标签。

## 总览

| 模型 | 调用一致率 | unavailable | 稳定 case | 摇摆 case | 稳定偏离候选 | 平均耗时 |
|---|---:|---:|---:|---:|---:|---:|
| qwen-plus | 38/45 (84.4%) | 0 | 14/15 | 1 | 2 | 11.9s |
| qwen3-max | 35/45 (77.8%) | 0 | 14/15 | 1 | 3 | 35.4s |

## 标签摇摆

- qwen-plus WYR-013：候选 reject，三轮 reject / accept / reject。
- qwen3-max WYR-014：候选 accept，三轮 accept / accept / reject。

## 稳定偏离候选

- qwen-plus WYR-007：候选 reject，三轮稳定为 accept。
- qwen-plus WYR-012：候选 retry，三轮稳定为 accept。
- qwen3-max WYR-007：候选 reject，三轮稳定为 accept。
- qwen3-max WYR-012：候选 retry，三轮稳定为 reject。
- qwen3-max WYR-013：候选 reject，三轮稳定为 accept。

## 判读原则

- 同一 case 三轮标签变化：优先归为模型/服务不稳定。
- 三轮稳定但偏离人工候选：优先回看 rubric 是否缺少边界，或候选标签是否需要人工再确认。
- 两模型稳定地在同一 case 偏离：更像共同规则盲区，不应继续靠换模型碰运气。

## 关键 Case 诊断

### WYR-007：共同规则盲区

两模型三轮全部稳定判为 accept，但人工候选是 reject。after 保留了“家里一直喝旺玥”，删除了“每天冲一杯、孩子端着喝得香”。当前 rubric 只笼统要求保留关键事实，没有说明持续冲泡频率和孩子接受度也属于不可无故删除的独立使用事实。

结论：这不是模型随机，优先确认人工是否坚持 reject；若坚持，应把该边界沉淀为 Rewrite Quality 金标和短 rubric，而不是换模型。

### WYR-012：retry 边界不清

after 重复两次“朋友也跟着换了”。qwen-plus 三轮稳定 accept，qwen3-max 三轮稳定 reject，人工候选是 retry。两个模型都看到了同一文本，却分别落到灰区两侧，说明“局部重复可修用 retry”的严重度边界没有写清。

结论：这是 rubric 校准问题。需要人工确认重复事件是否固定标为 retry，再补一条精确金标。

### WYR-013：目标删除与事实损失冲突

after 删除“晚上睡得沉、白天精力旺盛、身高窜了一截”。qwen3-max 三轮稳定 accept；qwen-plus 两次 reject、一次 accept。模型一方面看到 target_issue 是 effect_scope_drift，另一方面又要判断被删除内容是否属于独立正向反馈，当前输入没有标出目标删除范围。

结论：以规则输入歧义为主，同时 qwen-plus 存在一次真实摇摆。仅靠现有 before、after、target_issue 很难稳定区分“正确删除目标问题”和“过度删除其他事实”。

### WYR-014：qwen3-max 单点不稳定

删除“孩子自己冲奶粉”正是 child_self_brewing 的目标修复。qwen-plus 三轮 accept；qwen3-max 前两轮 accept、第三轮却以事实损失 reject。

结论：这是明确的模型不稳定，且 qwen-plus 在该边界更可靠。

## 当前结论

- `qwen-plus`：调用一致率 84.4%，平均约 11.9 秒；15 个 case 中 14 个标签稳定。
- `qwen3-max`：调用一致率 77.8%，平均约 35.4 秒；15 个 case 中 14 个标签稳定。
- 真正标签摇摆各只有 1 个 case，不支持“watch 主要由模型随机导致”的判断。
- 主要问题是三个规则边界：关键使用事实的定义、retry 的严重度、目标删除范围。
- 当前更适合继续用 qwen-plus 做候选 grader，但在人工确认 WYR-007、WYR-012、WYR-013 前，不应据此切生产。
