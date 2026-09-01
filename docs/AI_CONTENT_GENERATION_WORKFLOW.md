# AI 内容生成流程：业务规则包驱动

## 核心变化

Demo 主线调整为：

1. 运营拆解并上传业务规则包。
2. 系统按规则包自动规划生成任务，并自动补齐表达扩散语料。
3. direct LLM executor 通过统一 `content.generate` 能力执行生成。
4. MAGA 对生成结果做确定性审核；是否允许进入 `content.rewrite` 由资产策略决定。旺玥 production 不调用模型改写，只有显式 experimental 才运行改写实验。
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
7. direct LLM executor 只负责按最终 prompt 生成内容并返回结构化结果。

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

生成时每条 item 的计划中带完整业务规则规则、语料、示例和补充。系统再自动选择启用的表达扩散语料，并把最终组装结果写入 `plan_json.unified_generation`，direct LLM executor 只输出评论正文。

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

运营导入的槽位语料是原始业务资产。导入和组装时必须逐条保留原文，不得为了缩短 Prompt、统一语气或方便路由而压缩、概括、润色或改写。可以另行标记疑似冲突、事实错误和损坏语料，但未经运营确认不得静默修改；确认删除的问题语料可以移出候选池，问题记录与原始文件仍需可追溯。

a2礼遇默认按老客分享处理。认可表达根据本篇抽中的原始素材，自然承接活动、每批检测、长期购买背景或实际使用感受；生成要求不再强制单一活动了解途径，也不再用“信息了解后认可 / 老客使用感受”限制正文能否出现老客背景或产品体验。已经领到小听、老客回归礼、会员权益或完成确定性集罐兑换可以写；只拦截自称已经抽中或拿到旅游基金、金手链、夏凉被等抽奖奖品。“肚子”和“失败”不做词面禁用或替换；“没闹过肚子”“转过别的牌子失败”等上下文正常表达直接放行，只有明确形成 a2、a2至初或活动的负面经历时才由语义审核处理。“囤了好几罐”不写进生文 Prompt，机器审核按上下文处理：普通购买或老客回馈语境放行，只有与活动前库存参加集罐、扫码累计或兑换发生关联时才硬拦；明确是活动期间或看到活动后购买的罐子放行。标题生成时要求少于19字；审核允许20字，只有超过20字才直接淘汰。

a2礼遇已知规则的小改动默认走快速路径：定位已知文件、最小修改、运行 1 个聚焦测试，然后直接返回结果。除非运营明确要求回测、对比或发布验证，否则不扫描历史 `outputs`、不重建 Review 或随机完整 Prompt，也不重新生成文章批次。

a2礼遇排查正文新增活动机制时，不能只对照活动内容槽位。必须检查该篇完整 `rendered_prompt`、实际 system prompt 和所有槽位中目标词的出现位置；如果目标词只出现在“禁止 A、B、C”式负向枚举里，应优先判断为 Prompt 反向提示污染。修复时删除具体禁用概念的枚举，改写为正向用途或抽象边界，例如“罐底码只用于查询检测或溯源信息”“活动机制只使用本篇素材明确提供的内容”，具体错误继续由后链路审核拦截。

快速路径同时限制上下文加载：

- 用户已给出精确语料、文件或资产位置和明确修改时，直接定位修改；精确删除、替换不属于语料改写或松绑任务，不额外启用语料 Skill。
- 已导入 MAGA 的 a2 业务规则以 `asset_registry` 中的当前资产为运行真相。调整已导入语料时只从当前 candidate 创建新版本；除非用户明确要求修改或重新导入源文件，不读取、不同步、不修改 Downloads 下的原始 CSV 和历史导出副本。
- 当前请求和可见证据已足以确定操作时，跳过历史 Memory 和 rollout 查询；只在结论依赖旧决策、旧路径或仍有歧义时做定向检索。
- 需要遵循错误恢复协议时，先用 `rg` 定位相关 G-code 或关键词及附近段落；除非要修改该协议的整体结构，不读取整份文档。
- 执行顺序固定为：一次定向定位 → 一次最小修改 → 一个聚焦验证 → 返回结果。文档记录不阻塞核心修改交付。

### a2礼遇外部 CSV 快速审核流程

运营交付一份最终 CSV 并要求审核时，默认只审核这一个最终文件。Downloads 下的原始语料、历史输出、旧审核报告和过往批次均不进入本轮输入，除非运营明确要求做版本对比或追溯源语料。

固定流程：

1. 读取最终 CSV 一次，确认表头、文章数和分类比例。后续问题行号始终使用该 CSV 的真实行号，包含表头行。
2. 一次运行当前 production 资产和确定性 guard，生成候选命中清单。默认不逐篇调用外部 LLM，不读取或错误使用本机 API key。
3. 人工只复核命中项和必要的边界样本，排除“想抽到”“听说别人抽到”“不用报名”“不踩雷”等上下文误报；不再次通读或扫描全部历史文章。
4. 输出分为 `明确拦截 / 轻修或待确认 / 批次级观察`。不同类别可能重叠，不能把各项数量直接相加成问题文章总数。
5. 默认直接返回简短结论和真实行号。只有运营明确要求 Markdown、CSV 或修复版时才生成额外交付文件；未要求时不修改原 CSV，也不制作长报告。
6. 运营纠正单条边界后，只更新对应 production 规则或 guard、补一个聚焦测试，并重新判断受该规则影响的命中项；不得重新扫描历史 `outputs`、重建整份 Review 或重跑完整批次。

速度约束：批量审核不得边审核边临时搭建一套新扫描系统。已存在的 production guard 是默认入口；发现规则缺口时先完成当前候选复核，再把缺口作为独立的小规则修改处理。

已封装为可复用服务 `a2_reiyu_csv_audit_service.py`，并提供无外部 API 的命令行入口：

```bash
cd /Users/luxifa/maga/platform-server
python scripts/audit_a2_reiyu_csv.py /path/to/input.csv --output /path/to/audit.csv --concurrency 10
```

输出 CSV 保留原始列，追加真实 `CSV行号`、审核结论、审核档位、问题码、原因、命中片段和改写标记；同时生成 `.summary.json`统计。正式模式先执行标题长度、文本表层、每批检测、旧罐资格和上下文禁词 Guard，再使用与生文后审核相同的 `a2_reiyu_business_usability_v1` 金标 Judge 并行审核。禁词资产、模型路由、Provider 端点和密钥均从数据库当前配置读取，不读取本机临时 API Key。`--deterministic-only` 仅用于调试，不能作为正式 CSV 审核结果。

生成和审核保持为两个独立任务，但调用同一套 Guard 和金标 Judge。a2礼遇通过批次生成接口运行时，未显式指定 `postprocess_mode` 的请求会先按 `generate_only` 完成生成，随后把原批次投递到独立审核任务；生成请求不等待审核。审核任务默认 10 并发，依次执行标题、文本表层、每批检测、旧罐资格、当前数据库禁词资产和 `a2_reiyu_business_usability_v1` 金标 Judge，结果写回原 `content_batch_item.quality_json`。任务状态记录在 `content_batch_job.strategy_json.a2_reiyu_audit`；同一批次的 queued/running/completed 状态不重复投递，审核链路异常时文章进入 `watch` 且 `hard_pass=false`。服务启动时会重新投递遗留的 queued/running 任务，并通过数据库行锁保证同一批次只有一个审核执行者。显式 `generate_only` 仍表示只生成、不自动投递审核。

### 生文业务规则的五段框架

生文业务规则统一拆成下面五段，职责不同，不互相重复：

| 统一名称 | Prompt 中常见标题 | 作用 | 强制性 |
| --- | --- | --- | --- |
| 生文指令 | `生文指令：` | 说明要生成什么内容类型，例如“小红书妈妈 UGC 正向种草笔记” | 必须执行 |
| 内容方向 | `内容方向：` | 说明本篇具体围绕什么事情展开、产品如何进入、反馈落在哪里 | 必须执行 |
| 本篇素材 | `本篇素材：` | 放本篇已选中的灵感线索、用户痛点、产品卖点、品牌/产品事实或活动信息 | 按素材类型使用 |
| 写法 | `写法：` | 说明如何表达，例如生活动作切入、产品浓度、单篇只展开一个反馈 | 必须遵守 |
| 生成要求 | `生成要求：` | 约束标题、字数、输出格式以及不可突破的事实与合规边界 | 不得违反 |

`layered_article` 使用这五段时，不再自动加载全局表达扩散语料，也不随机追加人设、帖子说话方式、扰动规则、写作手法或格式控制。五段规则本身就是完整 Prompt；没有填写的可选层直接省略，不用旧系统关键词补齐。

#### 内容素材

运营侧字段名使用 `生文素材`；运行时 Prompt 显示 `本篇素材`。素材池可以保存多条候选，但运行时只注入本篇已选中的内容。

1. **灵感线索**：给模型一个宽泛联想点，用来打开不同生活入口。它不能覆盖内容方向。
2. **用户痛点**：说明妈妈为什么会关注这件事，不单独扩写成焦虑小作文。
3. **产品卖点或卖点痛点表达**：提供本篇已抽中的一条产品表达，不要求完整介绍所有卖点。
4. **品牌/产品事实**：只能按审核后的原意使用，不由模型自行补造。
5. **活动信息**：提供妈妈班、会员活动等真实活动机制、参与方式、现场信息或权益。

暂不设置 `场景素材`。普通生活场景继续由模型根据内容方向和抽象灵感自然构思，避免把场景提前写死，重新造成模板化。

妈妈班与月子中心规则包采用下面的拆分口径：

- 妈妈班、月子中心是场景分组，不是各自只有一条的业务规则；每个语义去重后的内容方向才是一条业务规则。
- 两个场景的内容方向和生文素材分别维护，不能把待产妈妈、产后妈妈、待产包、新客礼盒、小听粉等素材跨场景随机混用。
- 同一叙事流程只是调整先后顺序，不新增业务规则；顾问邀请、导购邀请、现场看到、群聊看到等浅层参加入口合并成一个方向或作为该方向内部变化。
- 奖品和批批检表达属于本篇素材中的活动信息。每篇只从场景对应奖品池抽一条、从批批检池抽一条；奖品只承担现场收获，检测报告才承担品质依据。
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

这些内容会提前锁死生活入口、产品进入方式或因果关系。确实必须发生的事实应放入 `生文素材` 并标明类型；本篇必须如何展开则写入 `内容方向`。

#### 卖点痛点表达

`卖点痛点表达` 是本篇素材中的一种组合素材。卖点与痛点不拆成两个 Prompt 槽位，而是以 `selling_painpoint_group` 作为一个完整组合进行路由。

旺玥当前的卖点痛点表达来源于 `旺玥卖点表达_导入_卖点加痛点.csv`，资产顶层按原始行保存 `selling_painpoint_group + expression`。每条业务规则只引用一个 `selling_painpoint_group`，不再在规则 `corpus` 中复制整组表达。其他品牌从旧 RAAP 或旧语料迁移时也沿用这一结构：组合负责路由，原始多样表达负责本篇实际措辞，不能把多条来源表达压成一条抽象卖点说明。

结构化存储示例：

```json
{
  "selling_painpoint_expressions": [
    {
      "selling_painpoint_group": "进阶保护力+容易中招",
      "expression": "我选奶粉时会优先看乳铁蛋白，旺玥还有免疫球蛋白，更加分。",
      "source_row_no": 58
    }
  ]
}
```

渲染给模型时只保留本篇抽中的一条表达，不渲染组合组名，也不额外渲染独立痛点：

```text
本篇素材：
- 灵感线索：和朋友相关
- 卖点痛点表达：我选奶粉时会优先看乳铁蛋白，旺玥还有免疫球蛋白，更加分。
```

推荐的规则块结构：

```text
生文指令：
写一篇小红书妈妈 UGC 正向种草笔记。

内容方向：
妈妈记录下最近日常，家里一直喝旺玥。具体怎么写，用一个瞬间、前后对比、从哪里说起都由模型自行构思；结合本篇素材自行发挥。

本篇素材：
- 灵感线索：和孩子最近迷上的一件东西相关
- 卖点痛点表达：我选奶粉时会优先看乳铁蛋白，旺玥还有免疫球蛋白，更加分。
- 活动信息：会员可以参加集罐活动，达到条件后可以兑换礼品。

写法：
- 标题从正文自然提炼。
- 正文只保留一个生活入口、一个产品依据和一个自家反馈。

生成要求：
- 旺玥是 3 岁以上儿童喝的。
- 产品本体使用“罐”作为量词。
- 标题从正文自然提炼，不超过 20 字。
- 正文 120-180 字，只输出 title 和 body。
```

术语边界：

- `生文指令` 只定义任务类型，不负责描述本篇具体写什么。
- `内容方向` 不包含后面的本篇素材、写法或生成要求。旺玥内容方向只保留帖子类型、最低产品关系和开放写作姿态，不预埋具体表达句。
- `抽象灵感素材` 是可选材料，不是内容方向的子项，也不能覆盖内容方向；灵感冲突或接入生硬时直接不用。
- 旺玥规则可以在灵感槽位中使用内部值 `不使用灵感线索`。该值只参与轮换，选中时渲染器会整块留空，不会把这句话或“本篇灵感线索”等元指令展示给模型。
- 旺玥规则可以按卖点表达 `source_row_no` 配置 `inspiration_none_source_row_nos` 和 `inspiration_clue_by_source_row_no`。运行时先抽卖点痛点表达：命中无灵感行号时，表示该表达在当前帖子类型里已经自带完整经历、具体结果或强效果，不再抽取灵感；命中精确映射时，只使用该条兼容灵感；其余表达才按规则灵感池轮换。配置属于“业务规则 × 卖点表达”，不能写成表达池的全局属性；同一表达在其他帖子类型中仍可使用自己的兼容灵感。没有安全匹配时应留空，不回退到全局灵感。
- 旺玥保护力规则不使用 `和游戏相关`、`和周末在家的一件小事相关`。这两类线索在对照批次中重复把正文带向游戏时长、绘本、拼图或专注力，属于灵感与保护力卖点不匹配，不应归因到卖点表达。
- `活动信息` 提供可信的活动事实，但不代表每项都必须写进正文；必须出现的活动事实由内容方向明确指定。
- `卖点痛点表达` 属于本篇素材；它以卖点与痛点的组合为路由单位，运行时只注入本篇抽中的一条表达。
- `selling_painpoint_group` 只用于资产路由，不作为独立痛点文字渲染给模型。
- 卖点痛点表达做冗余治理时，“表达变体保留”表示原句继续作为可抽取表达使用，只归并语义关系，不自动清洗、改写或拆成残句；只有确认属于纯重复的整句才从候选池删除。
- 旧语料迁移时，先逐条保留来源中的可用卖点表达，再按“卖点父类 + 痛点”归组。业务规则 CSV 使用 `卖点痛点组合` 引用组名；运行时从资产顶层表达池抽一条进入 `本篇素材 / 卖点痛点表达`。不得为了缩短 Prompt，把一组多样表达改写成单条概括句。
- 莼悦旧 RAAP 导出中 `人设+沟通策略+卖点` 的原始卖点表达已经业务确认：原文里的强因果、成分和产品事实都可以直接用于生文，不按通用风险话术主动降调。确定性审核只拦模型在本篇原文之外新增的认证、成分、数字、周期、作用机制、具体孩子变化或其他可核验效果；不能因为原文本身力度强就判错或改弱。
- 莼悦的可核验产品事实只准使用本篇卖点痛点原文，允许自然转述，也允许拆开穿插渠道、时间、地点、动作和心情；不得改变原文中的认证、成分、数字、周期、作用机制、具体孩子变化或明确因果，也不得新增这些事实。不再要求整条原文全部、按顺序逐字覆盖，也不再给“家里正在喝/正在选莼悦”特殊通行证。像“现在喝着挺安稳”这类抽象、不可量化的使用感受可以自然外扩；UGC 标题也允许在原文事实基础上增加“焦虑终结者”“让敏敏宝宝安心”这类主观效果判断和强种草表达。机器验收保留完整原句和片段命中指标用于调试，但不再把逐字命中作为正式通过条件；事实含义是否被改变由业务人工判断，确定性审核继续拦截原文外新增的可核验产品事实。
- 莼悦允许“别的品牌介绍里从没这样说过”这类不点名竞品、不新增具体认证/成分/效果的自然比较感受。只有点名竞品并新增具体可核验对比事实，或出现明确贬损时，才按竞品事实或风险问题处理。
- 莼悦内容审核不强制正文必须完成“最终选择/购买莼悦”的闭环。只要帖子自然建立了与莼悦的产品关系，停在被推荐、了解到、记下来或继续关注都可以，不因缺少明确下单或选择动作判 watch / fail。
- 莼悦不得把本篇卖点原文写成罐身、包装、标签、说明或配料表上的文字。信息来源不再由全局生成要求枚举，而是在 `生文素材` 的 `【信息来源素材】` 槽位中按篇抽取：可以给具体渠道短标签、给抽象来源，也可以抽中“正文不写来源”。来源选项只写点位或短动作，不写成半成品句子；“抽象来源”这类说明只留在元数据，不渲染给模型。Prompt 不再额外解释来源槽的使用规则。
- 从真人池整理卖点或痛点素材时，必须区分 `真人原句` 与 `基于真人原句的业务化候选`。只有能在本地来源中逐字检索并追溯到 `note_id/comment_id` 或文件行的内容才能标为真人原句；任何删改、拼接、概括或品牌替换后的文本都必须明确标为派生候选，不能称为直接抽取的真人内容。
- 真人表达进入候选池时默认优先保留原句，不为了补齐业务逻辑、降低 watch 或显得更规范而主动润色。只有原句命中已确认的硬边界，或用户明确给出改法时才做最小修改；不好改的原句宁可不采用，也不要硬改成失去真人感的安全话术。
- 卖点表达试跑出现内容漂移时，必须分别核对本篇抽中的卖点表达、灵感线索和内容方向，不能用整篇结果直接否定卖点。若多个卖点在同一灵感线索下稳定漂向同类场景或效果，应优先处理灵感线索；只有问题随卖点表达稳定复现时，才归因到卖点表达本身。
- 偏用户分享、家庭体验或评论口吻的表达，允许在 `selling_painpoint_group` 后增加 `-ugc`，例如 `进阶保护力+容易中招-ugc`。基础组规则会同时抽取基础组与同名 `-ugc` 子组；规则若明确引用 `-ugc`，则只抽取 UGC 表达。组名后缀只负责路由和识别，不修改表达原文，也不渲染给模型。
- 单条表达后续可以按实际调优需要增加自己的局部字段，当前导入阶段不统一附加内容治理边界。
- `写法` 只放如何表达，不放禁词清单或产品事实。
- `生成要求` 负责标题、长度、输出格式和不可突破的事实与合规边界；完整禁词仍优先放确定性审核层。
- 不再使用 `主线`、`故事线`、`内容主线`、`元素模块`、`硬边界`、`手法` 作为日常分类名称；需要引用 Prompt 原文时除外。

### 旺玥 V3 五段规则

旺玥 V3 的旧资产继续保留原有区块，渲染时统一归一成五段框架。卖点痛点表达结构化存储并在运行时进入 `本篇素材`：

1. `生文指令：`
2. `内容方向：`
3. `本篇素材：`，其中包括抽中的灵感线索和卖点痛点表达
4. `写法：`
5. `生成要求：`

资产中的旧标记 `【本篇灵感线索】` 仍可保存多个抽象候选，渲染时只抽一条并输出为 `本篇素材 / 灵感线索`。卖点痛点表达统一保存在顶层 `selling_painpoint_expressions`，规则项通过 `selling_painpoint_group` 引用；渲染时同样只注入本篇抽中的一条表达。

组合组名直接沿用来源 CSV 第一列，例如 `进阶保护力+容易中招`、`营养丰富+成长发育需求`。卖点和痛点不再拆字段维护。

旺玥业务规则展示名称统一使用：

```text
V3M-{编号}｜{selling_painpoint_group}｜{post_type}
```

例如 `V3M-01｜进阶保护力+容易中招｜使用反馈`。`rule_id` 仍是稳定标识；展示名称不再维护 `日常营养`、`成长营养`、`眼脑营养`、`精力状态` 或季节词等中间别名。

旺玥审核口径补充：

- 不展开感冒、咳嗽、传染、发烧、医院、请假或同伴生病等具体疾病、就医和请假场景；不区分当前或过去语境。抽象的“容易中招 / 少中招 / 保护力 / 状态稳”可以保留，但不能写成临时补救、治疗或防病保证。
- 孩子可以自然表达口味或日常感受，但不能替品牌讲成分、介绍或推荐旺玥，也不能主动给同伴分发、倒奶或邀请别人喝；产品判断和成分依据只能由照护者叙述。
- 旺玥自家长期使用中的消化吸收体验允许正常表达，例如便便规律、胀气少、小肚子舒服，以及积食或排便状态的前后变化，不触发专属审核或自动改写。医生、治疗、保证有效等医疗化表达，以及正式硬违禁词，仍按各自规则处理。
- 中文正文里用独立 `ta/Ta/TA` 指代人物属于确定性流畅性问题，代码硬审直接拦截并要求局部改成“他”“她”或“孩子”；不要依赖 LLM Judge 临场识别。
- `post_type` 只用于生成多样化和批量分布，不作为单篇硬验收条件。`复购/长期使用` 没有写满两周、补货或明确复购，只要正文已有真实使用、孩子接受或自家反馈，仍应 pass；只有完全停留在未来打算、没有实际使用时才可判类型不成立。

### 旺玥 V3 正式审核链路

旺玥 V3 默认策略是 `production`。正式链只做确定性修复、客观硬阻断和本地观察，不调用 `content.rewrite`，也不在每篇生产内容上同步运行四个 Focused Judge：

```text
确定性禁词替换与代码硬审
→ 标题/正文客观格式检查
→ AI Flavor、相似度等本地 watch 信号
→ 直接入池或硬阻断
```

- Production 自动修复只保留可机械验证的表面处理：去掉 JSON/Markdown/`标题：` 外壳，以及精确替换 `🍼 → 空`、`宝宝 → 孩子`、`宝妈 → 家长`、`体质 → 体格`、`脾胃 → 肚肚状态`。
- Production 硬阻断包括：3 岁以下与旺玥使用相关、孩子自己冲泡/舀粉/倒奶、奶瓶/干粉入口/即饮/盒装/便携小包等错误产品形态、孩子主动要奶/推荐/分发、疾病医疗场景、现实时间阶段、错误品牌或数字、明显残句与推理泄露。
- 标题 production 只做格式清理，并对空标题或加权超过 20 字直接阻断；不再依据“营销感、自然度、重复度、标题句式”等主观规则重造标题。emoji 保留，长度计算时按 2 字计。
- 正文 `120-180` 只用于引导生成，不复刻成审核区间。旺玥审核只要求正文非空且小于 250 字；达到或超过 250 字时直接阻断，不自动改写。
- AI Flavor 可以本地检测并落盘，但不影响 production hard pass；mouth phrase budget 在 production 整步跳过，不逐篇开会话，也不自动改写。
- `unnatural_collocation` 和正文 `instruction_leak` 都不再进入 production 模型改写。明显格式外壳可机械清理；正文指令泄露、病句和语义断裂交人工或实验层。
- 时间逻辑、产品出现资格、ingredient/benefit mismatch、故事逻辑、卖点承接、标题自然度、营销密度、口癖预算、post type 与 scene motive 等全部属于 Experimental / Shadow。
- 代码硬审失败后不允许 LLM 改写把文章重新放行。
- 其他业务暂时继续使用原产品体验审核链路。

需要修复的旺玥文章不在生产任务内同步改写。正式流程先通过 `business-usability-review` 把 Focused Review 未通过的文章留在 `hold_out`，再由独立后链路调用：

```text
POST /api/v1/content-agent/batches/{batch_id}/wangyue-deferred-repair
```

该入口只选择已有正式审核结果、`can_auto_pool != true` 且未被代码硬审阻断的文章。每篇最多调用一次局部改写，随后重新执行确定性硬审和全部 Focused Judge；只有完整复审通过才回写并恢复入池，否则原文继续留在 `hold_out`。批次的 `production` 配置不会被改成 `experimental`，改写前后正文及两次审核结果记录在 `wangyue_deferred_repair_history`。

需要跑实验链时，必须显式设置：

```json
{"wangyue_rewrite_policy":"experimental"}
```

Experimental 才运行 Temporal Logic / Claim-Public Disease / Content Fit / Fluency、Rewrite Quality Validator 和历史 `content.rewrite`，单个目标最多尝试 2 次，候选不因一次 Judge 通过就自动视为业务可用。

分层依据不是“这个问题看起来能改”，而是历史一次改写是否稳定、改动是否只落在局部、以及改后能否用确定性规则验收。历史旺玥链路中，Phrase Guard 和 AI Flavor 首轮改写仍约有两成到四成不通过；批次 787/788 的原始生成只需约 11-12 秒，但 6/4 次后置改写把总阶段跨度拉到约 49/58 秒。涉及故事主线、产品角色、时间线、卖点承接或事实取舍的问题，应回到 planner、业务规则或语料层处理，不能靠生成后连续洗稿补救。

## 资产配置更新工具

单条旺玥卖点痛点表达使用版本化接口更新，不直接改生产表：

```text
PATCH /api/v1/assets/article-business-rule-sets/{asset_key}/selling-painpoint-expressions/{source_row_no}
```

请求同时提供 `expected_expression` 和新 `expression`。服务会校验旧值、归档当前 production 版本并创建新版本，metadata 记录修改前后内容和基础资产版本，避免语料调试依赖一次性脚本。

全量替换卖点表达池使用 CSV 导入接口，保留基础组与 `-ugc` 分组：

```text
POST /api/v1/assets/imports/article-selling-painpoint-expressions
```

上传字段为 `卖点表达,语料`；允许文件开头包含 `#` 注释行。导入会完整替换当前 expression pool，并创建新的 production 资产版本。

需要同时调整单条文章业务规则的内容方向和卖点路由时，使用：

```text
PATCH /api/v1/assets/article-business-rule-sets/{asset_key}/rules/{rule_id}
```

接口支持在同一个 production 版本中更新 `corpus` 与 `selling_painpoint_group`，并通过 `expected_corpus`、`expected_selling_painpoint_group` 防止覆盖其他人的新修改。

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

`asset_key`、`created_by`、`executor_code`、`count` 都是可选字段。评论接口不接收运营手填的 `product_topic`、`target_audience`、`style`。

需要“先超采样、再从同一批次择优交付”时，可以显式传入候选数量和交付选择配置：

```json
{
  "asset_key": "a2_sentiment_comment_activity",
  "rule_ids": ["a2_direct_01", "a2_direct_43"],
  "count": 180,
  "concurrency": 10,
  "comment_prompt_slots": {
    "本条表达路径": [
      "从渠道或地点起句，不用固定时间词。",
      "直接说事实，结尾自然问一句。",
      "省略主语，像评论区顺手接话。"
    ]
  },
  "comment_batch_variation_review": {
    "enabled": true,
    "affects_hard_pass": false,
    "opening_prefix_frequency": {"prefix_chars": 3, "max_count": 5},
    "opening_clause_frequency": {"max_count": 2}
  },
  "comment_delivery_selection": {
    "enabled": true,
    "target_count": 105,
    "max_similarity": 0.45,
    "opening_prefix_frequency": {"prefix_chars": 3, "max_count": 5},
    "opening_first_char_frequency": {"max_count": 35},
    "opening_clause_frequency": {"max_count": 2},
    "min_bulk_refill_count": 30,
    "max_bulk_refill_count": 100,
    "bulk_refill_multiplier": 3
  }
}
```

- 评论候选数量 `count` 最大为 `300`；一条候选仍然对应一次独立生成调用。
- `affects_hard_pass=false` 表示批次同质化只作为交付选择信号，不覆盖单条业务审核结果。
- `comment_delivery_selection` 只从单条业务通过项里执行完全去重、开头配额和相似度择优，不修改正文。
- 如果交付选择不足目标数，报告会返回 `delivery_shortfall_count` 和 `suggested_bulk_refill_count`；按建议数量整批补量，不做零碎追数。

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

审核本身不是让模型自由判断。MAGA 后端先用系统违禁词和业务违禁词做确定性扫描；允许改写的资产才把原文、命中词、业务规则、已选表达扩散语料和改写 Expert 渲染后的 prompt 交给 direct LLM executor 执行 `content.rewrite`。旺玥 production 命中后只做精确替换或直接阻断，不进入该模型链。

文章批次的审核与改写模式必须分开理解：

- 默认模式：执行审核；是否允许自动改写由资产策略决定。旺玥默认 `production`，模型改写预算为 0。
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

## Direct LLM Capability

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

### 旺玥回归分层

截至 2026-07-22，`python -m pytest -q -k wangyue` 选择 251 个 pytest case，完整运行约 3-4 秒。用例本身不是历史“跑得很慢”的主因；原先的主要问题是 `test_content_batch_execution_service.py` 创建异步 SQLite engine 后没有统一 dispose，导致 pytest 已输出总结但进程仍挂尾。该文件现在用自动 fixture 回收每个测试创建的 engine。

- Smoke：Focused Judge、aggregator 和 gold 契约，用于规则文案或 gold 调整后的快速检查。
- 旺玥 PR gate：`python -m pytest -q -k wangyue`，覆盖 production 与 experimental 路由，但不调用实时 LLM。
- 后端全量：`python -m pytest -q`。
- Release-only：candidate holdout、历史模型 A/B 和改写稳定性快照；这些不是默认 pytest 实时用例，不应混进每次 PR 回归。

当前 251 条里确有维护层面的重复：部分 Judge Prompt 逐字断言与 gold/rubric 语义重复，且 production/experimental 集成用例仍在同一大文件中。但它们不会造成模型调用，当前优先保留覆盖；后续若再拆文件，应按“纯函数/确定性 production”与“async experimental integration”拆，而不是直接删业务边界。

- 源悦业务规则只走 `comment_business_rule_set`。
- 妈妈班活动规则包继续作为活动内容规则，不被评论生成读取。
- 产品使用体验生文入口走 `/content-agent/batches/start`，主执行链路已经统一到 `content.generate`。
- 旧 `xhs.*` chain、`comment.generate`、单篇 `/generation/start` 已下线；文章和评论统一使用 `content.generate`，审核改写统一使用 `content.rewrite`。
- 对外只讲 MAGA 自动调用 direct LLM executor，不把 direct LLM executor 作为产品概念。
