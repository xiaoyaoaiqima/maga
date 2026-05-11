# MAGA x maga-worker 本地组合草案

## 当前目标

创建并收敛 `maga-worker` Hermes profile，用来开发和验证：

MAGA = 营销内容生成工作台 / 控制平面 / 数据资产中心
maga-worker = 当前默认统一 Agent 执行层 / worker

## 本地目录映射

| 角色 | 路径 | 说明 |
| --- | --- | --- |
| MAGA 项目 | `/Users/luxifa/maga` | source of truth 的代码库 |
| maga-worker profile | `/Users/luxifa/.hermes/profiles/maga-worker` | 前期统一 worker：产文、资产提案、反馈训练、Prompt 优化 |
| xhs-writer profile | `/Users/luxifa/.hermes/profiles/xhs-writer` | 历史小红书生文原型，短期迁入 `maga-worker` 的 `xhs.*` 能力 |
| maga-asset-steward profile | `/Users/luxifa/.hermes/profiles/maga-asset-steward` | 历史资产治理原型，短期迁入 `maga-worker` 的 `asset.*` 能力 |
| maga-dev profile | `/Users/luxifa/.hermes/profiles/maga-dev` | MAGA 集成开发 Agent，不作为生产 worker |

## 推荐生产边界

MAGA 不直接调用 Hermes profile 文件系统作为业务数据库。

前期只部署/管理一个 worker：`maga-worker`。它内部可以承载多组 capability：

- `xhs.*`：实际产文、审核、改写
- `asset.*`：资料清洗、资产变更提案
- `feedback.*`：人工反馈总结、训练建议
- `prompt.*`：Prompt patch / 策略优化建议

生产方向应是：

1. MAGA 创建 ContentTask / ContentRun。
2. Hermes `maga-worker` 通过 MAGA API 或 `/invoke` 协议接收任务。
3. MAGA 返回 task snapshot，包括 brief、brand、product、selling points、expert rules、generation strategy、score rubric。
4. `maga-worker` 根据 capability 运行 GE/AE pipeline、资产提案或反馈训练分析。
5. `maga-worker` 通过 MAGA API 回写 run_event、artifact、score、final content 或 change proposal。
6. MAGA 进入人工审核/发布/评估流程。

## 第一阶段本地 adapter

为了快速验证，可以先做两个本地 adapter：

### 1. task snapshot -> xhs brief

输入：MAGA ContentTask snapshot
输出：`xhs_runtime.py` 可消费的 brief dict 或临时 brief.yaml

映射重点：

- content_task.painpoint -> brief.painpoint
- product.selling_points -> brief.selling_points
- brand.rules -> brand_product_guard corpus/rules
- expert_strategy.required_aes -> brief_type.required_aes
- generation_strategy -> narrative_strategy
- score_rubric -> AE score rubric

### 2. xhs trace -> MAGA events/artifacts

输入：`maga-worker` / 历史 xhs-writer notes/debug 输出
输出：MAGA run_event/artifact payload

映射重点：

- AE instruct -> run_event(type=ae_instruct)
- Writing Spec -> artifact(type=writing_spec)
- GE draft -> artifact(type=draft)
- AE score -> run_event(type=ae_score)
- Rewrite suggestions -> run_event(type=rewrite_suggestion)
- Final content -> artifact(type=final_content)

## 注意

本地阶段可以读历史 xhs-writer / maga-asset-steward 文件，但这只是迁移和验证手段。
生产阶段 Hermes 不应直连 MAGA DB，也不应把任一 profile workspace 当作 source of truth。
