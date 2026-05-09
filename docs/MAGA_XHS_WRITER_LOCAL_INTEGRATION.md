# MAGA x xhs-writer 本地组合草案

## 当前目标

创建 `maga-dev` Hermes profile，用来开发和验证：

MAGA = 营销内容生成工作台 / 控制平面 / 数据资产中心
xhs-writer = 当前默认 Agent 执行层 / worker

## 本地目录映射

| 角色 | 路径 | 说明 |
| --- | --- | --- |
| MAGA 项目 | `/Users/luxifa/maga` | source of truth 的代码库 |
| xhs-writer profile | `/Users/luxifa/.hermes/profiles/xhs-writer` | 当前小红书生文执行器 |
| xhs-writer workspace | `/Users/luxifa/.hermes/profiles/xhs-writer/workspace` | AE、brief、runtime、trace 文件资产 |
| maga-dev profile | `/Users/luxifa/.hermes/profiles/maga-dev` | MAGA x xhs-writer 集成开发 Agent |

## 推荐生产边界

MAGA 不直接调用 xhs-writer 文件系统作为业务数据库。

生产方向应是：

1. MAGA 创建 ContentTask / ContentRun。
2. Hermes xhs-writer worker 通过 MAGA API claim task。
3. MAGA 返回 task snapshot，包括 brief、brand、product、selling points、expert rules、generation strategy、score rubric。
4. xhs-writer worker 运行 GE/AE pipeline。
5. xhs-writer worker 通过 MAGA API 回写 run_event、artifact、score、final content。
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

输入：xhs-writer notes/debug 输出
输出：MAGA run_event/artifact payload

映射重点：

- AE instruct -> run_event(type=ae_instruct)
- Writing Spec -> artifact(type=writing_spec)
- GE draft -> artifact(type=draft)
- AE score -> run_event(type=ae_score)
- Rewrite suggestions -> run_event(type=rewrite_suggestion)
- Final content -> artifact(type=final_content)

## 注意

本地阶段可以读 xhs-writer 文件，但这只是迁移和验证手段。
生产阶段 Hermes 不应直连 MAGA DB，也不应把 xhs-writer workspace 当作 source of truth。
