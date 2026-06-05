# AI 内容生成流程：业务规则包驱动

## 核心变化

Demo 主线调整为：

1. 运营拆解并上传业务规则包。
2. 系统按规则包自动规划生成任务，并自动补齐系统提示词关键词。
3. `maga-worker` 通过统一 `content.generate` 能力执行生成。
4. MAGA 对生成结果做业务违禁词审核，命中后调用 `content.rewrite` 自然改写，并二次扫描兜底。
5. 运营在批量报告里查看、审核、反馈。

运营不再在生成时手填主题、人群、风格和数量。业务信息以规则包为准，生成策略由系统自动补齐。

## 统一生成链路

文章和评论都走同一套逻辑：

1. 业务规则包提供本次生成需求的业务信息。
2. 系统读取版本化的“系统提示词关键词”资产，默认种子包含 `人设`、`生文指令`、`生评论指令`、`扰动规则`、`写作手法`、`格式控制`，但这些不是系统上限。
3. 每个关键词类别下有多个子关键词，每个子关键词挂一组语料。
4. 每次生成时，系统从每个启用类别中自动选择 1 个启用子关键词；后续新增类别只需要在管理页配置。
5. `expert` 使用提示词模版把业务规则和本次选中的关键词语料组装成最终 prompt。
6. `expert` 的模型配置决定 provider、model_code、temperature、max_tokens。
7. `maga-worker` 只负责按最终 prompt 生成内容并返回结构化结果。

这里的 `expert` 不是人设，也不是业务规则；它是“提示词模版 + 模型参数配置”。业务规则负责告诉模型写什么，系统提示词关键词负责告诉模型怎么写，expert 负责把这些输入组装成最终提示词。

## 规则包边界

### 源悦活动评论

源悦活动评论使用评论切角规则包：

- 资产类型：`comment_angle_rule_set`
- 默认 `asset_key`：`yuanyue_comment_activity`
- 本地规则来源：`批量生成/评论切角_子关键词导出.csv`
- 历史兼容来源：`源悦种草活动-ai训练规则-评论切角.csv`
- 默认生成主题：`美素佳儿源悦活动评论`
- Demo 默认生成前 10 条规则对应的评论

每行规则保存：

- `评论切角`
- `语料`
- 可选 `评论示例`
- 可选 `评论补充`

生成时每条 item 的计划中带完整切角规则、语料、示例和补充。系统再自动选择启用的系统提示词关键词，并把最终组装结果写入 `plan_json.unified_generation`，worker 只输出评论正文。

### 源悦活动生文

源悦活动生文使用产品使用体验规则包：

- 资产类型：`product_experience_rule_set`
- 默认 `asset_key`：`yuanyue_product_experience`
- 本地规则来源：`关键词语料/产品使用体验_子关键词导出.csv`

每行规则保存：

- `产品使用体验`
- `语料`

系统会从 `产品使用体验` 中拆出月龄、使用时间和体验主题，用于后续生文规划。

### 妈妈班活动

妈妈班活动规则包是另一类活动内容规则，不和源悦评论切角混用。

- 妈妈班活动使用妈妈班活动内容规则。
- 源悦活动评论使用评论切角规则。
- 源悦活动生文使用产品使用体验规则。
- 各类规则包分开导入、分开管理、分开生成。

## 规则写法原则

规则要轻，示例负责横向扩展。

运营写规则时不需要把所有角度拆成复杂表单，也不要把提示词写成死板大纲。一个规则块只说明这个切角在聊什么、语气像什么、边界在哪里；多样性主要靠示例增加，而不是靠堆更多限制。

当生成结果重复时，优先补充更多不同方向的自然示例；不要把规则改成很长的“必须/只能/固定写法”。

## 公开接口

### 业务规则管理页

```text
/#/business-rules
```

运营可以在这里管理多个业务规则包，例如 `源悦-评论` 和 `源悦-生文`。不同生文需求可以使用不同 `asset_key` 单独上传和版本化。

### 导入评论切角规则包

```http
POST /api/v1/assets/imports/comment-angle-rule-set
```

请求：

- `multipart/form-data`
- `file`：`.csv` 或 `.xlsx`
- `asset_key`：可选，默认 `yuanyue_comment_activity`
- `created_by`：可选

响应摘要包含：

- 规则条数
- 示例数量
- 默认生成量
- 风险提示

### 导入产品使用体验规则包

```http
POST /api/v1/assets/imports/product-experience-rule-set
```

请求：

- `multipart/form-data`
- `file`：`.csv` 或 `.xlsx`
- `asset_key`：可选，默认 `yuanyue_product_experience`
- `display_name`：可选，默认 `源悦-生文（产品使用体验）`
- `created_by`：可选

响应摘要包含：

- 规则条数
- 示例数量
- 默认生成量
- 风险提示

### 启动评论批量生成

```http
POST /api/v1/content-agent/comment-batches/start
```

请求只需要：

```json
{
  "asset_key": "yuanyue_comment_activity",
  "created_by": "ops",
  "executor_code": "hermes_maga_worker"
}
```

`asset_key`、`created_by`、`executor_code` 都是可选字段。接口不接收运营手填的 `product_topic`、`target_audience`、`style`、`count`。

### 启动文章批量生成

文章批量生成接口：

```http
POST /api/v1/content-agent/batches/start
```

请求只需要：

```json
{
  "asset_key": "yuanyue_product_experience",
  "created_by": "ops",
  "executor_code": "hermes_maga_worker"
}
```

`asset_key`、`created_by`、`executor_code` 都是可选字段；`count` 也可选，默认按规则包元数据生成。接口兼容旧字段，但主流程不再依赖运营手填 `product_topic / target_audience / style`。文章和评论都会走同一套 `业务规则包 -> 系统提示词关键词 -> expert -> content.generate` 执行模型。

### 系统提示词关键词

```http
GET /api/v1/assets/content-generation-keywords?asset_key=default_content_generation_keywords
PUT /api/v1/assets/content-generation-keywords
GET /api/v1/assets/content-generation-keywords/versions
POST /api/v1/assets/content-generation-keywords/rollback
POST /api/v1/assets/content-generation-keywords/preview
POST /api/v1/assets/imports/content-generation-keywords
GET /api/v1/assets/exports/content-generation-keywords
```

系统提示词关键词作为 `content_generation_keywords` 资产存储在 `asset_registry`，每次保存生成新的 production 版本，旧版本归档。页面入口：

```text
/#/content-agent/system-prompt-keywords
```

管理页支持新增、编辑、停用关键词类别和子关键词；类别不是固定枚举，默认四类只是种子配置。

运营可以通过 CSV/XLSX 批量导入系统提示词关键词，也可以导出当前版本继续编辑。导入导出采用一行一条语料的轻量格式，核心列包括 `类别Code`、`类别名称`、`子关键词Code`、`子关键词名称`、`语料`。页面提供版本列表和回滚能力，回滚会把旧版本复制成新的 production 版本，不直接改写历史版本。

每个关键词类别默认自动轮换选择 1 个启用子关键词；当某次活动需要稳定使用某个方向时，可以把类别的选择模式改为“固定选择”，并指定 `固定子关键词Code`。固定选择只影响该类别，其他类别仍可继续自动轮换。

Prompt 预览用于在保存前查看“业务规则 + 当前页面关键词配置 + expert 模版”最终组装出的 prompt，帮助运营确认语料是否真的进入了生成上下文。

## 生文 Expert 管理

新链路里的 Expert 不再等同于旧 RAAP 的 Agent/Job 编排节点，而是一次模型执行的配置单元：

- Prompt 模板
- 模型参数：`provider_code`、`model_code`、`temperature`、`max_tokens`、`system_prompt`
- 执行能力：`content.generate` 或 `content.rewrite`

页面入口：

```text
/#/content-agent/experts
```

默认包含三个配置：

- `article_generator_v1`：文章生成，能力为 `content.generate`
- `comment_generator_v1`：评论生成，能力为 `content.generate`
- `content_rewrite_v1`：审核改写，能力为 `content.rewrite`

审核本身不是让模型自由判断。MAGA 后端先用系统违禁词和业务违禁词做确定性扫描；命中后才把原文、命中词、业务规则、已选系统关键词和改写 Expert 渲染后的 prompt 交给 `maga-worker` 执行 `content.rewrite`；改写后再二次扫描，不通过时继续兜底清理或交给人工。

## 数据承载

文章和评论 Demo 先复用现有批量任务表：

- `ContentBatchJob.product_topic`：`美素佳儿源悦活动评论`
- `ContentBatchJob.product_topic`：文章为 `美素佳儿源悦活动生文`
- `ContentBatchItem.title`：评论存评论切角，文章存生成标题
- `ContentBatchItem.body`：生成正文
- `ContentBatchItem.plan_json.rule_type`：评论为 `comment_angle`，文章为 `product_experience`

暂不新增独立评论表。后续如果评论审核、投放、归因需要独立生命周期，再单独建表。

## Worker Capability

统一生成 capability：

```text
content.generate
```

输入来自系统组装后的统一快照：

- `content_type`：`comment` 或 `article`
- `business_rule`：本条业务规则
- `selected_keywords`：每个启用关键词类别自动选出的 1 个子关键词及其语料
- `expert`：提示词模版和模型参数配置快照
- `rendered_prompt`：最终给模型的 prompt
- `output_fields`：评论为 `["comment"]`，文章为 `["title", "body"]`

评论输出为：

```json
{
  "comment": "..."
}
```

文章输出为：

```json
{
  "title": "...",
  "body": "..."
}
```

本地 fake runtime 会优先用规则示例稳定返回，方便 Demo 和测试；真实 runtime 使用 `rendered_prompt`、模型配置和输出字段生成内容。

统一改写 capability：

```text
content.rewrite
```

它只负责按 MAGA 提供的原文、命中词和改写指令做自然改写。违禁词列表维护、命中判断、是否通过、二次扫描和兜底清理都留在 MAGA 后端，不塞进首轮生文 prompt。

## Demo 流程

1. 打开内容生成工作台。
2. 上传文章规则包 `关键词语料/产品使用体验_子关键词导出.csv`，或上传评论规则包 `批量生成/评论切角_子关键词导出.csv`。
3. 查看导入摘要：规则条数、示例数量、默认生成量、风险提示。
4. 点击“按业务规则包生成文章”或“按评论切角生成评论”。
5. 在批量报告中查看每条内容、对应规则和执行 trace。
6. 运营对内容做通过、修改意见、人工编辑保存，或把不希望出现的词加入业务违禁词。

## 回归边界

- 源悦评论切角只走 `comment_angle_rule_set`。
- 妈妈班活动规则包继续作为活动内容规则，不被评论生成读取。
- 产品使用体验生文入口走 `/content-agent/batches/start`，主执行链路已经统一到 `content.generate`。
- 旧 `xhs.*` chain、`comment.generate`、单篇 `/generation/start` 已下线；文章和评论统一使用 `content.generate`，审核改写统一使用 `content.rewrite`。
- 对外只讲 MAGA 自动调用 `maga-worker`，不把 Hermes 作为产品概念。
