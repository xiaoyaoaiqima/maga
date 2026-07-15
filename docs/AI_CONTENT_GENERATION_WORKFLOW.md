# AI 内容生成流程：业务规则包驱动

## 核心变化

Demo 主线调整为：

1. 运营拆解并上传业务规则包。
2. 系统按规则包自动规划生成任务，并自动补齐表达扩散语料。
3. `maga-worker` 通过统一 `content.generate` 能力执行生成。
4. MAGA 对生成结果做业务违禁词审核，命中后调用 `content.rewrite` 自然改写，并二次扫描兜底。
5. 运营在批量报告里查看、审核、反馈。

运营不再在生成时手填主题、人群、风格和数量。业务信息以规则包为准，生成策略由系统自动补齐。

## 统一生成链路

文章和评论都走同一套逻辑：

1. 业务规则包提供本次生成需求的业务信息。
2. 系统读取版本化的“表达扩散语料”资产，默认种子包含 `人设`、`生文指令`、`生评论指令`、`扰动规则`、`写作手法`、`格式控制`，但这些不是系统上限。
3. 每个关键词类别下有多个子关键词，每个子关键词挂一组语料。
4. 每次生成时，系统从每个启用类别中自动选择 1 个启用子关键词；后续新增类别只需要在管理页配置。
5. `expert` 使用提示词模版把业务规则和本次选中的表达扩散语料组装成最终 prompt。
6. `expert` 的模型配置决定 provider、model_code、temperature、max_tokens。
7. `maga-worker` 只负责按最终 prompt 生成内容并返回结构化结果。

这里的 `expert` 不是人设，也不是业务规则；它是“提示词模版 + 模型参数配置”。业务规则负责告诉模型写什么，表达扩散语料负责告诉模型怎么写，expert 负责把这些输入组装成最终提示词。

表达扩散语料要保持轻量，尤其是 `人设`、`生文指令`、`生评论指令`、`扰动规则`、`格式控制/评论格式控制` 这些与具体业务事实无关的类别。它们只描述语气、生成动作、随机性和输出形态，不承载产品卖点、活动机制、剧情事实、禁写清单或重业务边界。重业务规则应放在业务规则包或业务规则语料里；可跨业务复用的表达边界放到表达写作规则；必须强约束的底线再放到硬性规则。

表达扩散语料可以维护全局子关键词池，具体业务规则包通过 `keyword_selection` 圈选本次可用子集。例如剧情讨论评论可以从全局 `人设` 池中只圈选 `家庭妈妈`、`经验型妈妈`、`碎碎念妈妈`、`新手妈妈`、`职场妈妈`，生成时只在这个子集里轮换；不要为了单个业务复制一套重表达扩散语料。

## 规则包边界

### 源悦活动评论

源悦活动评论使用业务规则规则包：

- 资产类型：`comment_business_rule_set`
- 默认 `asset_key`：`yuanyue_comment_activity`
- 本地规则来源：`批量生成/业务规则_子关键词导出.csv`
- 历史兼容来源：`源悦种草活动-ai训练规则-业务规则.csv`
- 默认生成主题：`美素佳儿源悦活动评论`
- Demo 默认生成前 10 条规则对应的评论

每行规则保存：

- `业务规则`
- `语料`
- 可选 `评论示例`
- 可选 `评论补充`

生成时每条 item 的计划中带完整业务规则规则、语料、示例和补充。系统再自动选择启用的表达扩散语料，并把最终组装结果写入 `plan_json.unified_generation`，worker 只输出评论正文。

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

妈妈班活动规则包是另一类活动内容规则，不和源悦业务规则混用。

- 妈妈班活动使用妈妈班活动内容规则。
- 源悦活动评论使用业务规则规则。
- 源悦活动生文使用产品使用体验规则。
- 各类规则包分开导入、分开管理、分开生成。
- 文章规则包的生成主题必须来自规则语料中的显式 `活动：` 或当前规则包显示名；禁止回退到其他品牌的历史默认主题。导入后要核对 `content_json.activity_name`、`metadata_json.activity_name` 和生成批次 `product_topic` 三处一致。

## 规则写法原则

规则要轻，示例负责横向扩展。

运营写规则时不需要把所有角度拆成复杂表单，也不要把提示词写成死板大纲。一个规则块只说明这个业务规则在聊什么、语气像什么、边界在哪里；多样性主要靠示例增加，而不是靠堆更多限制。

当生成结果重复时，优先补充更多不同方向的自然示例；不要把规则改成很长的“必须/只能/固定写法”。

### 生文业务规则的语料层级

生文业务规则统一拆成下面六层，六层职责不同，不互相包含：

| 统一名称 | Prompt 中常见标题 | 作用 | 强制性 |
| --- | --- | --- | --- |
| 生文指令 | `任务：` | 说明要生成什么内容类型，例如“小红书妈妈 UGC 正向种草笔记” | 必须执行 |
| 内容方向 | `这篇要写的事：` | 说明本篇具体围绕什么事情展开、产品如何进入、反馈落在哪里 | 必须执行 |
| 内容素材 | `本篇灵感线索：`、`活动素材：` | 给内容方向补充可调用的材料；当前只包含抽象灵感素材和活动素材 | 按素材类型使用 |
| 卖点表达 | `卖点表达：`、`注意：` | 给本篇一条可变化的产品卖点表达；`注意`只约束这条表达怎么使用 | 卖点与注意成对使用 |
| 事实与合规边界 | `硬边界：` | 约束年龄、产品形态、使用动作、量词、禁词和合规事实，防止写错 | 不得违反 |
| 成文要求 | `写法：` | 约束标题、字数、段落、收尾、单篇主线和批量差异等最终成文形态 | 必须遵守 |

`layered_article` 使用这六层时，不再自动加载全局表达扩散语料，也不随机追加人设、帖子说话方式、扰动规则、写作手法或格式控制。六层规则本身就是完整 Prompt；没有填写的可选层直接省略，不用旧系统关键词补齐。

#### 内容素材

`内容素材` 是大框架中可扩展的中间层，目前只保留下面两类：

1. **抽象灵感素材**：给模型一个宽泛联想点，用来打开不同生活入口。它是可选的，可以采用、改造或不用，不能覆盖内容方向。
2. **活动素材**：提供妈妈班、会员活动等文章需要的真实活动信息。活动名称、机制、参与方式、现场信息等业务事实从这里取，不由模型自行补造。

暂不设置 `场景素材`。普通生活场景继续由模型根据内容方向和抽象灵感自然构思，避免把场景提前写死，重新造成模板化。

妈妈班与月子中心规则包采用下面的拆分口径：

- 妈妈班、月子中心是场景分组，不是各自只有一条的业务规则；每个语义去重后的内容方向才是一条业务规则。
- 两个场景的内容方向和活动素材分别维护，不能把待产妈妈、产后妈妈、待产包、新客礼盒、小听粉等素材跨场景随机混用。
- 同一叙事流程只是调整先后顺序，不新增业务规则；顾问邀请、导购邀请、现场看到、群聊看到等浅层参加入口合并成一个方向或作为该方向内部变化。
- 奖品和批批检表达属于活动素材。每篇只从场景对应奖品池抽一条、从批批检池抽一条；奖品只承担现场收获，检测报告才承担品质依据。
- 旧的礼遇活动内容池不接入妈妈班与月子中心规则包，避免把抽奖、积分、集罐礼等其他活动机制混进课堂或月子中心分享场景。

抽象灵感素材应保持低约束，例如：

- 和动物相关
- 和游戏相关
- 和一顿饭相关
- 和家里的一件旧东西相关
- 和一段对话相关
- 和一张照片相关
- 和一个意外的小插曲相关

不要把下面这类已经带有具体写作动作或固定叙事路径的内容放进灵感素材：

- 截图成分表后开始做功课
- 拿清单逐项对比奶粉
- 在妈妈群看到推荐后立即下单
- 去某个具体地点后发现孩子状态变化

这些内容会提前锁死生活入口、产品进入方式或因果关系。确实必须发生的活动事实应放入 `活动素材`；本篇必须如何展开则写入 `内容方向`。

#### 卖点表达

`卖点表达` 是独立于内容方向和内容素材的产品表达层。多样性主要来自多条不同的卖点表达，而不是给同一条卖点配置很多不同后缀。

每条卖点表达通常只配一条 `注意`。这条注意只说明使用该卖点时要守住的局部边界，例如不要照抄专业逻辑、不要解释成分机制或不要作保证性承诺。卖点表达和注意必须作为一组原子数据一起轮换，不能拆开随机组合，也不能把某条卖点的注意套到另一条卖点上。

规则资产中保存多组候选时使用：

```text
【卖点表达槽位】
- 卖点表达：乳铁蛋白含量优秀，提升孩子日常保护力，状态不掉线
  注意：禁止照抄卖点表达的逻辑，普通宝妈不会这么专业，同质化是原罪。
- 卖点表达：添加了免疫球蛋白，给孩子日常保护力多一层支持
  注意：不要解释免疫机制，也不要保证孩子不生病。
```

渲染给模型时只保留本篇抽中的一组：

```text
本篇灵感线索：和朋友相关
卖点表达：乳铁蛋白含量优秀，提升孩子日常保护力，状态不掉线
注意：禁止照抄卖点表达的逻辑，普通宝妈不会这么专业，同质化是原罪。
```

推荐的规则块结构：

```text
任务：写一篇小红书妈妈 UGC 正向种草笔记。

这篇要写的事：
写成妈妈记录最近日常。先自然说到这段时间给孩子换了旺玥，再写孩子最近的日常状态；产品理由和自家反馈都围绕这件事展开。

本篇灵感线索：和孩子最近迷上的一件东西相关

卖点表达：乳铁蛋白含量优秀，提升孩子日常保护力，状态不掉线
注意：禁止照抄卖点表达的逻辑，普通宝妈不会这么专业，同质化是原罪。

活动素材（活动文章按需加入）：
- 会员可以参加集罐活动。
- 达到活动条件后可以兑换礼品。

硬边界：
- 旺玥是 3 岁以上儿童喝的。
- 产品本体使用“罐”作为量词。

写法：
- 标题从正文自然提炼，不超过 20 字。
- 正文只保留一个生活入口、一个产品依据和一个自家反馈。
```

术语边界：

- 文档、页面说明、调试报告和日常沟通使用左侧的统一名称；Prompt 暂时保留右侧标题，避免影响现有规则资产和解析逻辑。
- `生文指令` 只定义任务类型，不负责描述本篇具体写什么。
- `内容方向` 只指 `这篇要写的事`，不包含后面的内容素材、边界或成文要求。
- `内容素材` 目前只包含 `抽象灵感素材` 和 `活动素材`，不要提前扩展场景素材、产品素材等新分类。
- `抽象灵感素材` 是可选材料，不是内容方向的子项，也不能覆盖内容方向；灵感冲突或接入生硬时直接不用。
- `活动素材` 提供可信的活动信息，但不代表每项都必须写进正文；必须出现的活动事实由内容方向明确指定。
- `卖点表达` 不属于内容素材；它负责提供本篇可采用的产品好处表达，是卖点多样性的主要来源。
- `注意` 是当前卖点表达的局部使用边界，不是独立轮换的后缀，也不替代通用的事实与合规边界。
- 同一组里的 `卖点表达` 与 `注意` 必须一起抽取、一起渲染；一般一条卖点只配置一条注意。
- `事实与合规边界` 只放不可写错、不可突破的限制；普通写作建议不要放进这一层。
- `事实与合规边界` 是业务规则块里的文字边界，不等于系统独立执行的 `硬性规则` 审核层。
- `成文要求` 负责最终怎样成文。虽然 Prompt 当前标题仍是 `写法：`，但它不等于“写作手法”，其中的长度、结构和批量差异要求仍然是强约束。
- `成文要求` 也不等于表达扩散语料中的 `写作手法`；前者约束最终交付形态，后者用于提供可轮换的表达方式。
- 不再使用 `主线`、`故事线`、`内容主线`、`元素模块`、`硬边界`、`手法` 作为日常分类名称；需要引用 Prompt 原文时除外。

### 旺玥 V3 六块规则

旺玥 V3 的 `rule_corpus_as_prompt` 规则统一只保留下面六块，不再混入 `主线`、`生活入口槽位`、迁移说明或隐藏 planner 指令：

1. `生文指令：`
2. `内容方向：`
3. `【本篇灵感线索】`
4. `【卖点表达】`
5. `事实与合规边界：`
6. `成文要求：`

资产中的 `【本篇灵感线索】` 可以保存多个抽象候选；`【卖点表达】` 保存多组 `卖点表达 + 注意`。渲染给模型时，两处都只保留本篇抽中的一组，卖点表达与对应注意不得拆开混配。

旺玥卖点按痛点路由：`容易中招 -> 进阶保护力`，`注意力不集中 -> 眼脑双引擎`，`营养不足 / 成长发育需求 / 精力不足 -> 营养丰富`。同属营养丰富的表达还要按具体承接语义细分，避免成长、正餐营养和精力状态互相串线。

旺玥审核口径补充：

- 过去发生的感冒、请假、全勤，以及自家长期使用后的少中招或出勤观察，不自动判 `hard_risk_expression`。真正需要 hard 的是孩子出现当下症状后，马上把旺玥写成临时补救或治疗手段。
- 孩子可以自然表达口味或日常感受，但不能替品牌讲成分、介绍或推荐旺玥，也不能主动给同伴分发、倒奶或邀请别人喝；产品判断和成分依据只能由照护者叙述。
- `小肚子` 本身不是消化效果词。`小肚子鼓鼓的`、裤腰变紧等属于成长体格观察；只有与便便规律、胀气、肚子舒服或消化改善等语义结合时，才命中 `wangyue_digestive_effect_context`。

## 资产配置更新工具

后端提供 `platform-server/scripts/update_asset_config.py` 用于维护 `asset_registry` 里的 JSON 配置字段，避免手写 SQL。默认只做 dry-run；真正写库必须显式加 `--apply`。

查看当前字段：

```bash
cd platform-server
PYTHONPATH=. ../.venv/bin/python scripts/update_asset_config.py \
  --asset-key a2_plot_discussion_comment \
  --field batch_variation_review \
  --show-current
```

预览更新：

```bash
cd platform-server
PYTHONPATH=. ../.venv/bin/python scripts/update_asset_config.py \
  --asset-key a2_plot_discussion_comment \
  --field batch_variation_review \
  --file ../docs/a2_plot_discussion_batch_variation_review.json
```

发布更新：

```bash
cd platform-server
PYTHONPATH=. ../.venv/bin/python scripts/update_asset_config.py \
  --asset-key a2_plot_discussion_comment \
  --field batch_variation_review \
  --file ../docs/a2_plot_discussion_batch_variation_review.json \
  --apply
```

默认发布模式是 `--mode new-version`：归档旧 active 资产，复制一份新 active 版本并写入配置，脚本会在 `.local/asset-config-backups` 保存旧版本备份。只在本地快速试验时使用 `--mode in-place`。

如果只需要修改某一条业务规则语料，使用 `platform-server/scripts/update_comment_business_rule_item.py`，避免手写 SQL 或临时脚本。它支持按 `rule_id`、`source_row_no` 或 `business_rule` 定位 `content_json.items[]` 里的单条规则；默认 dry-run，真正发布需加 `--apply`。

查看当前语料：

```bash
cd platform-server
PYTHONPATH=. ../.venv/bin/python scripts/update_comment_business_rule_item.py \
  --asset-key a2_sentiment_comment_activity \
  --rule-id business_rule_015 \
  --show-current
```

预览单条更新：

```bash
cd platform-server
PYTHONPATH=. ../.venv/bin/python scripts/update_comment_business_rule_item.py \
  --asset-key a2_sentiment_comment_activity \
  --rule-id business_rule_015 \
  --corpus-file /tmp/business_rule_015.txt
```

发布单条更新：

```bash
cd platform-server
PYTHONPATH=. ../.venv/bin/python scripts/update_comment_business_rule_item.py \
  --asset-key a2_sentiment_comment_activity \
  --rule-id business_rule_015 \
  --corpus-file /tmp/business_rule_015.txt \
  --apply
```

## 公开接口

### 业务规则管理页

```text
/#/business-rules
```

运营可以在这里管理多个业务规则包，例如 `源悦-评论` 和 `源悦-生文`。不同生文需求可以使用不同 `asset_key` 单独上传和版本化。

### 导入业务规则规则包

```http
POST /api/v1/assets/imports/comment-business-rule-set
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
  "executor_code": "maga_direct_llm_executor"
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
  "executor_code": "maga_direct_llm_executor"
}
```

`asset_key`、`created_by`、`executor_code` 都是可选字段；`count` 也可选，默认按规则包元数据生成。接口兼容旧字段，但主流程不再依赖运营手填 `product_topic / target_audience / style`。文章和评论都会走同一套 `业务规则包 -> 表达扩散语料 -> expert -> content.generate` 执行模型。

### 表达扩散语料

```http
GET /api/v1/assets/content-generation-keywords?asset_key=default_content_generation_keywords
PUT /api/v1/assets/content-generation-keywords
GET /api/v1/assets/content-generation-keywords/versions
POST /api/v1/assets/content-generation-keywords/rollback
POST /api/v1/assets/content-generation-keywords/preview
POST /api/v1/assets/imports/content-generation-keywords
GET /api/v1/assets/exports/content-generation-keywords
```

表达扩散语料作为 `content_generation_keywords` 资产存储在 `asset_registry`，每次保存生成新的 production 版本，旧版本归档。页面入口：

```text
/#/content-agent/system-prompt-keywords
```

管理页支持新增、编辑、停用关键词类别和子关键词；类别不是固定枚举，默认四类只是种子配置。

运营可以通过 CSV/XLSX 批量导入表达扩散语料，也可以导出当前版本继续编辑。导入导出采用一行一条语料的轻量格式，核心列包括 `类别Code`、`类别名称`、`子关键词Code`、`子关键词名称`、`语料`。页面提供版本列表和回滚能力，回滚会把旧版本复制成新的 production 版本，不直接改写历史版本。

每个关键词类别默认自动轮换选择 1 个启用子关键词；当某次活动需要稳定使用某个方向时，可以把类别的选择模式改为“固定选择”，并指定 `固定子关键词Code`。固定选择只影响该类别，其他类别仍可继续自动轮换。

Prompt 预览用于在保存前查看“业务规则 + 当前页面表达扩散语料配置 + expert 模版”最终组装出的 prompt，帮助运营确认语料是否真的进入了生成上下文。预览时需要额外检查表达扩散语料是否过重：如果 `人设`、`生文指令/生评论指令`、`扰动规则` 或 `格式控制/评论格式控制` 里出现具体产品、活动、剧情、门店、禁写长清单，优先移回业务规则包、业务规则、表达写作规则或硬性规则。

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

审核本身不是让模型自由判断。MAGA 后端先用系统违禁词和业务违禁词做确定性扫描；命中后才把原文、命中词、业务规则、已选表达扩散语料和改写 Expert 渲染后的 prompt 交给 `maga-worker` 执行 `content.rewrite`；改写后再二次扫描，不通过时继续兜底清理或交给人工。

文章批次的审核与改写模式必须分开理解：

- 默认模式：执行审核，并允许命中后进入自动改写。
- `audit_only`：执行确定性违禁词审核和批次相似度观察，保留原文，不调用 `content.rewrite`；命中项标记红线未通过。
- `generate_only`：只看模型原始输出，审核和改写都跳过；历史页必须显示“红线未审核”，不能显示成“红线未通过”。

`a2_momclass_month_center` 默认使用 `audit_only`。运营说“关闭改写”时，不得再映射成 `generate_only`；关闭改写不等于关闭审核。

## 数据承载

文章和评论 Demo 先复用现有批量任务表：

- `ContentBatchJob.product_topic`：`美素佳儿源悦活动评论`
- `ContentBatchJob.product_topic`：文章为 `美素佳儿源悦活动生文`
- `ContentBatchItem.title`：评论存业务规则，文章存生成标题
- `ContentBatchItem.body`：生成正文
- `ContentBatchItem.plan_json.rule_type`：评论为 `business_rule`，文章为 `product_experience`

暂不新增独立评论表。后续如果评论审核、投放、归因需要独立生命周期，再单独建表。

## Worker Capability

统一生成 capability：

```text
content.generate
```

输入来自系统组装后的统一快照：

- `content_type`：`comment` 或 `article`
- `business_rule`：本条业务规则
- `selected_keywords`：每个启用表达扩散类别自动选出的 1 个子关键词及其语料
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
2. 上传文章规则包 `关键词语料/产品使用体验_子关键词导出.csv`，或上传评论规则包 `批量生成/业务规则_子关键词导出.csv`。
3. 查看导入摘要：规则条数、示例数量、默认生成量、风险提示。
4. 点击“按业务规则包生成文章”或“按业务规则生成评论”。
5. 在批量报告中查看每条内容、对应规则和执行 trace。
6. 运营对内容做通过、修改意见、人工编辑保存，或把不希望出现的词加入业务违禁词。

## 回归边界

- 源悦业务规则只走 `comment_business_rule_set`。
- 妈妈班活动规则包继续作为活动内容规则，不被评论生成读取。
- 产品使用体验生文入口走 `/content-agent/batches/start`，主执行链路已经统一到 `content.generate`。
- 旧 `xhs.*` chain、`comment.generate`、单篇 `/generation/start` 已下线；文章和评论统一使用 `content.generate`，审核改写统一使用 `content.rewrite`。
- 对外只讲 MAGA 自动调用 `maga-worker`，不把 Hermes 作为产品概念。
