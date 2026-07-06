# MAGA 真人感与多样性生文 Agent 研究笔记

## 研究目标

围绕 MAGA 当前持续推进的真人感、多样性、业务规则边界和真实 `content.generate` 生文链路，调研可借鉴的 Agent / 内容生产 / 品牌语气治理类开源项目。

当前判断：这条线不应该直接做一个“自由写文 Agent”，而应该做一个围绕真实生文流程的质量控制与诊断 harness。

核心目标是：

- 保持真实 `content.generate` 链路，不走 shortcut。
- 一份提示词生成一篇，不做大 prompt 批量生成。
- 严格分层管理 `business_rule`、`selected_keywords`、`examples`、`generation_requirements`。
- 提升真人感，但避免示例高权重导致同质化。
- 提升多样性，但避免业务事实污染全局层。
- 生成后能评估、定位、回放，而不是只看单篇结果。

## 已研究项目 1：TribeAI claude-cowork-brand-voice-plugin

项目地址：

- https://github.com/TribeAI/claude-cowork-brand-voice-plugin

项目定位：

这个项目不是完整的内容生产 SaaS，也不是批量生文平台，而是一个 Claude Cowork 的品牌语气治理插件。它的核心价值在于把分散的品牌素材整理成可执行的品牌语气规范，并在内容生成时做语气约束和质量校验。

它的大体链路是：

```text
真实品牌素材
-> 品牌发现
-> guideline 生成
-> brand voice enforcement
-> QA 检查
```

对应到 MAGA，可以理解为：

```text
真实用户帖子/评论/活动素材
-> 真人表达模式发现
-> 真人感与口气 guideline
-> content.generate 前加载约束
-> 生成后做真人感/多样性/边界 QA
```

## 可借鉴点

### 1. Voice Constant / Tone Flexes

项目把 `voice` 和 `tone` 分开：

- Voice：稳定的品牌人格，不随场景大幅变化。
- Tone：根据渠道、受众、任务场景做变化。

对 MAGA 的启发：

```text
Voice Constant:
  真人表达底色、非广告腔、非分析腔、非过度种草、不是品牌方口吻。

Tone Flex:
  不同帖子场景下的口气变化，例如吐槽、分享、求助、经验复盘、日常碎碎念、轻安利。
```

这能把“真人感”从一个抽象要求，拆成稳定底色和场景口气两层。

适合落在：

```text
selected_keywords / 写作手法 / 说话方式 / 口气层
```

不适合混进：

```text
business_rule 业务事实层
```

### 2. We Are / We Are Not

项目使用成对约束描述品牌表达：

```text
We Are: Confident
We Are Not: Arrogant
```

对 MAGA 的启发：

```text
我们要：像真实用户记录生活
我们不要：像品牌方写产品卖点

我们要：具体生活场景
我们不要：泛泛说效果好、值得买

我们要：自然口语和轻微不完整表达
我们不要：模板化小红书营销腔
```

这个结构很适合表达“禁止什么 / 边界是什么”，也符合 MAGA 当前规则优先写禁止命令的方向。

### 3. Source Ranking

项目对素材来源做分级，例如 authoritative、operational、conversational、contextual、stale 等，并结合 recency、authority、specificity、cross-source consistency 判断可信度。

对 MAGA 的启发：

```text
高权重：
  人工确认过的真实高质量帖子/评论。

中权重：
  运营整理后的表达片段、活动内高质量样本。

低权重：
  自动抽取但未人工确认的语料。

禁入：
  负面污染、召回、医疗风险、分析腔、广告腔、品牌方口吻。

过期：
  旧活动、旧业务规则、旧产品表达方式。
```

这对真人感语料资产治理很有价值。不是所有“真实素材”都应该直接进入 examples，也不是所有 examples 都应该同权重。

### 4. Confidence Scores + Open Questions

项目在 guideline 生成时不会假装所有结论都确定，而是会标注置信度，并把无法判断的问题变成 open questions。

对 MAGA 的启发：

```text
高置信：
  明确禁词、明显广告腔、明显分析腔、明显业务污染。

中置信：
  某类产品出现是否自然，需要抽样验证。

低置信：
  某类痛点表达是否真实，缺少足够样本。
```

这可以用于区分：

```text
立刻改规则
先做抽样验证
需要运营/业务确认
暂时只做告警
```

### 5. QA Agent

项目有专门的 quality assurance agent，用来检查 voice compliance、tone appropriateness、messaging alignment、terminology 等。

对 MAGA 的启发：

生成和审核应该分开。可以设计独立 QA 检查：

```text
真人感
多样性
业务边界
产品出现资格
禁词/风险词
标题/开头重复
隐藏种草感
隐性宝妈视角
示例污染
```

不要让一个生成 prompt 同时负责“写”和“给自己判高分”。

## 不适合直接照搬的地方

这个项目主要是 Claude 插件形态，仓库里以 commands、skills、agents、references 为主，不是完整后端平台。

不建议照搬：

```text
Claude slash command 工作流
自由从 Notion/Drive/Slack 搜素材
直接根据 guideline 产最终文
多 Agent 自由讨论后改写文章
```

应该借鉴：

```text
素材分级
风格规则模板
voice/tone 分层
生成前 guideline 加载
生成后 QA 检查
冲突和不确定点变成 open questions
```

## 对 MAGA 的推荐映射

可以设计一个 `真人表达治理层`，包在真实 `content.generate` 外面，而不是替代它。

```text
1. discover_real_voice
   从真实帖子、评论、活动样本中抽取表达模式。

2. generate_realness_guidelines
   生成：
   - We Are / We Are Not
   - 场景 tone matrix
   - 常用表达
   - 禁止表达
   - 低/中/高置信规则
   - open questions

3. enforce_realness
   生文前加载 guideline，但仍走真实 content.generate。

4. quality_check
   检查真人感、多样性、业务边界、产品出现资格、相似度等。

5. diagnose
   判断问题属于哪一层：
   - business_rule
   - selected_keywords
   - examples
   - generation_requirements
   - 抽样策略
```

## 推荐的 MAGA 架构方向

不是做：

```text
会自由写文的 Agent
```

而是做：

```text
围绕真实 content.generate 的 Content Quality Harness
```

建议结构：

```text
Planner:
  选择 rule / scene / angle / title_shape / texture / route。

ContextBuilder:
  按真实 MAGA 层级组装 business_rule / selected_keywords / examples / generation_requirements。

Generator:
  固定调用真实 content.generate，一次一篇。

Evaluator:
  真人感、多样性、合规、产品出现资格、相似度检查。

Diagnoser:
  判断问题属于哪一层，不乱改业务事实。

Adjuster:
  只调整必要层，最小变量重跑。

Reporter:
  输出批次分布、失败原因、修正建议。
```

## 当前阶段结论

TribeAI 这个项目最值得借的不是插件实现，而是这套思路：

```text
把“风格”从主观感觉，变成可保存、可加载、可校验的 guideline。
```

这正好能补 MAGA 真人感任务里的关键短板：

- 不只靠几个 examples 让模型模仿。
- 不让 examples 变成高权重模板。
- 不把业务事实塞进全局风格层。
- 生完之后能判断是哪一层出了问题。

下一步适合继续研究同类项目：

- 内容生产流水线类项目。
- AI marketing / copywriting 开源系统。
- brand voice + SEO/blog/social workflow。
- LLM eval / prompt regression 项目。
- 人工反馈和语料治理项目。

## 已研究项目 2：d-wwei/great-writer

项目地址：

- https://github.com/d-wwei/great-writer

项目定位：

`great-writer` 是一个面向 AI Agent 的通用写作 skill，不是完整内容生产平台。它把写作拆成多种 mode 和一套固定 pipeline，覆盖技术文章、营销文案、研究报告、小红书笔记、README、技术文档、改写润色、审稿和创意写作。

它的核心不是“多 Agent”，而是：

```text
写作前先研究
-> 找核心
-> 设计结构
-> 起草
-> 审核
-> 去 AI 味打磨
-> 最终检查
```

项目 README 里明确强调，它不是 prompt template，而是一套 6-phase pipeline，用来强迫 Agent 在写之前先思考，并在最后去掉 AI 痕迹。

## 可借鉴点

### 1. 6-phase pipeline：写作前置思考

项目把写作拆成：

```text
Core Logic
-> Structure Design
-> Draft
-> Review
-> Polish
-> Finalize
```

对 MAGA 的启发：

当前 MAGA 生文不能简单变成：

```text
给规则 + 给素材 + 直接生成
```

更好的结构是：

```text
任务目标和内容资格判断
-> 场景/角度/口气选择
-> 真实 content.generate
-> 质量审核
-> 去 AI 味 / 去模板检查
-> 最终验收
```

这和 MAGA 的真实链路不冲突，因为它不要求替代 `content.generate`，只是在生成前后增加控制层。

### 2. Mode routing：先判断内容类型，再加载不同规则

`great-writer` 会根据用户意图选择不同 mode，例如 marketing-copy、xiaohongshu、rewrite、editorial-review 等。

对 MAGA 的启发：

不应该用一套“真人感规则”覆盖所有帖子。可以先做内容类型路由：

```text
经验分享
日常记录
求助/讨论
轻安利
干货整理
避坑复盘
活动相关反馈
```

每种类型加载不同的：

```text
标题形态
开头方式
产品出现资格
表达强度
口气
禁用结构
```

这比单纯增加随机性更稳。多样性不是随机乱跳，而是内容类型、场景、口气、结构的组合空间。

### 3. 小红书 mode 的平台规则

项目的小红书 mode 提出核心原则：

```text
有用 + 真实 + 好看
```

并强调：

```text
第一人称
具体细节
个人经验
诚实说限制
避免学术/企业语气
不要强行网络热词
```

对 MAGA 的启发：

这些规则可以转换成检查项：

```text
是否有具体场景？
是否像个人经历，而不是产品介绍？
是否有过度品牌方口吻？
是否只说“很好用”但没有生活证据？
是否强行套热词？
是否有不自然的姐妹/家人们开头？
```

不过需要注意：项目里的小红书 mode 偏通用平台写作，MAGA 不能照搬它的“种草笔记”公式，否则容易更像营销模板。

### 4. Humanizer：4-pass 去 AI 味

项目的 humanizer 模块把去 AI 味拆成四步：

```text
口语检验
密度与节奏
AI 痕迹清除
反风格检查
```

对 MAGA 最有用的是：

```text
口语检验：
  这句话真实用户会不会这么说？

节奏检查：
  是否连续句长太接近？
  是否段落结构太整齐？

AI 痕迹：
  是否出现“随着...的发展”“值得注意的是”“总而言之”等。

反风格：
  是否在解释而不是呈现场景？
  是否列举过多？
  是否像任何 AI 都能写？
```

这些可以变成自动 evaluator 或半自动 checklist。

### 5. Style Learner：风格指纹

项目的 style-learner 会从参考文本里抽取：

```text
句长
段落长度
正式度
人称
情绪强度
词汇密度
开头方式
转场方式
结尾方式
列表方式
中文口语/书面语
emoji 和网络词使用
```

对 MAGA 的启发：

真人感语料不要只当 examples 使用，而可以先抽成风格指纹：

```text
某类真实用户的句长分布
常见开头
常见弱情绪词
是否爱用反问
是否用 emoji
是否分段很碎
是否有“先吐槽再补充”的结构
```

然后在生成时加载“风格指纹”，而不是直接塞整段示例让模型模仿。

这有助于降低 examples 高权重导致的同质化。

### 6. 机械可检查原则

项目强调很多规则要 mechanically checkable，例如：

```text
不能连续 3 句长度相似
不能出现 blacklist
不能所有章节结构完全对称
每个主要部分要有具体例子或数据
```

对 MAGA 的启发：

真人感和多样性也要尽量转成机械检查：

```text
标题形态重复率
开头结构重复率
高频 n-gram
相似度
禁词
产品出现位置
同一痛点词连续出现次数
同一场景占比
同一句式连续出现
```

主观 judge 可以保留，但不能全靠 judge。

## 不适合直接照搬的地方

### 1. 通用小红书公式不能直接套 MAGA

项目的小红书 mode 里有比较明确的种草结构：

```text
开头 hook
痛点
产品/方案介绍
核心利益点
个人证明
实用 tips
标签
```

这对通用小红书写作有效，但对 MAGA 有风险：

- 容易变成品牌种草。
- 容易让产品出现过早。
- 容易和“产品出现资格”冲突。
- 容易把真人感变成平台模板。

所以只能借检查项和风格拆解，不能直接借完整结构。

### 2. 它是 skill，不是批量生文系统

`great-writer` 主要通过 `SKILL.md` 和 mode/core markdown 文件指导 Agent 写作，不负责：

```text
批次调度
真实业务规则加载
content.generate 调用
样本追踪
相似度评估
失败重跑
资产分层
```

这些仍然需要 MAGA 自己的 harness。

### 3. 它偏单篇精品写作

MAGA 需要的是批量稳定生产。单篇精品写作方法有价值，但不能让每篇都走过重流程，否则成本会很高。

可转化为：

```text
批次级规则：
  用于规划和评估。

单篇轻量检查：
  用于拦截明显 AI 味和同质化。

人工抽样：
  用于高风险规则和低置信问题。
```

## 对 MAGA 的推荐映射

可以把 `great-writer` 的思路拆成三个可落地模块：

### A. Realness Fingerprint Extractor

从真实语料抽：

```text
句长分布
段落长度
常见开头
人称
情绪强度
场景密度
emoji 使用
口语连接词
反问/吐槽/补充结构
禁用模板腔
```

输出到：

```text
selected_keywords / style_profile / texture metadata
```

### B. Humanizer Evaluator

生成后检查：

```text
是否像真人说话
是否出现 AI 黑名单
是否段落太整齐
是否句式太统一
是否解释过多、场景太少
是否泛泛种草
```

### C. Mode Router

根据业务规则和素材，先判断内容类型：

```text
经验分享 / 日常记录 / 求助讨论 / 轻安利 / 避坑 / 干货
```

再选择不同的：

```text
title_shape
opening_shape
product_eligibility
tone
example weight
```

## 当前阶段结论

`great-writer` 对 MAGA 最大的价值是：

```text
把“去 AI 味”和“真人表达”拆成可执行、可检查的写作规则。
```

它不适合作为内容生产底座，但很适合作为：

```text
真人感 evaluator 参考
风格指纹抽取参考
小红书平台表达检查参考
anti-template / anti-AI checklist 参考
```

和上一个 Brand Voice 项目相比：

```text
Brand Voice plugin 更偏品牌语气资产治理。
great-writer 更偏单篇写作质量和去 AI 味机制。
```

两者结合后，对 MAGA 的方向是：

```text
先沉淀真人表达 guideline，
再用 humanizer/evaluator 检查生成结果，
但始终不绕过真实 content.generate 链路。
```

## 已发现候选项目池：待深研

下面这些项目 / 方案是本轮搜索中找到的内容生产、营销、生文相关候选。它们还没有像前两个项目一样完成逐文件拆解，所以这里只记录定位、可能借鉴点和与 MAGA 的初步关系。

### 3. SamurAIGPT/social-post

项目地址：

- https://github.com/SamurAIGPT/social-post

项目定位：

开源 AI 社媒内容生成 SaaS。项目说明里提到它支持 LinkedIn、Twitter/X、Instagram、Facebook、Reddit、LINE 等平台，带平台预览、多 tone 生成、发布意图、Stripe 计费等。

可能借鉴点：

```text
多平台内容参数建模
tone selection
社媒预览 / mockup
发布意图 publish intent
内容生成 SaaS 产品形态
```

对 MAGA 的关系：

```text
更适合看产品形态和多平台内容参数，不是优先解决真人感/同质化。
```

待研究问题：

```text
1. 它如何组织平台差异？
2. tone 是简单枚举，还是有结构化约束？
3. 是否有内容审核、相似度、质量评分？
4. 是否有批量生成和 trace？
```

### 4. n8n：Automate blog creation in brand voice with AI

方案地址：

- https://n8n.io/workflows/2648-automate-blog-creation-in-brand-voice-with-ai/
- 相关 workflow JSON 镜像：https://github.com/enescingoz/awesome-n8n-templates/blob/main/WordPress/Automate%20Blog%20Creation%20in%20Brand%20Voice%20with%20AI.json

方案定位：

一个 n8n workflow template，用已有发布文章作为品牌声音 examples，自动生成符合品牌语气的博客内容。

可能借鉴点：

```text
已有内容 -> brand voice examples -> 新内容生成
workflow 编排
内容获取、分析、生成、发布的自动化链路
```

对 MAGA 的关系：

```text
适合借 workflow 思路；
但它使用历史内容作为 examples 的方式，对 MAGA 有同质化风险。
```

待研究问题：

```text
1. 它如何抽取 brand voice？
2. 是否只是把历史文章塞进 prompt？
3. 有没有质量评估？
4. 有没有避免过度模仿历史文章？
```

### 5. blacktwist/social-media-skills

项目地址：

- https://github.com/blacktwist/social-media-skills

项目定位：

面向 AI Agent 的社媒内容策略、创作、分析 skills，覆盖 text-first 和 visual-first platforms。

可能借鉴点：

```text
社媒上下文采集
平台约束
audience / content pillars / tone preferences
社媒策略和创作拆成多个 skill
```

对 MAGA 的关系：

```text
适合看“社媒内容任务如何拆 skill”；
可能能借到平台约束、受众定位、内容支柱这类结构。
```

待研究问题：

```text
1. skills 如何组织平台、受众、tone？
2. 是否有内容分析和复盘 skill？
3. 是否能映射到 MAGA 的 rule / selected_keywords / examples 分层？
```

### 6. ericosiu/ai-marketing-skills

项目地址：

- https://github.com/ericosiu/ai-marketing-skills

项目定位：

开源 AI marketing skills，覆盖增长实验、sales pipeline、content ops、outbound、SEO、finance automation 等。

可能借鉴点：

```text
营销任务 skill 化
content ops
expert panel 打分
增长实验和内容运营的工作流拆解
```

对 MAGA 的关系：

```text
更偏营销运营系统，不一定直接解决生文真人感；
但可能对 content ops、批量评估、专家面板评分有启发。
```

待研究问题：

```text
1. content ops 具体包含哪些 skill？
2. expert panel 如何评分？
3. 是否有可复用的内容质量评估 rubric？
```

### 7. coreyhaines31/marketingskills

项目地址：

- https://github.com/coreyhaines31/marketingskills
- 官网：https://marketing-skills.com/

项目定位：

面向 Claude Code、Codex、Cursor 等 Agent 的营销任务 skills，覆盖 conversion optimization、copywriting、SEO、analytics、growth engineering。

可能借鉴点：

```text
营销任务技能库
copywriting 框架
SEO / CRO / analytics 任务拆解
适配 Codex 类 coding agent 的 skill 组织方式
```

对 MAGA 的关系：

```text
适合看营销 skill 如何写成可安装、可复用的说明文件；
对 MAGA 的具体价值取决于 copywriting / content skills 是否足够细。
```

待研究问题：

```text
1. 是否有专门的 copywriting / content generation skill？
2. 是否有 voice / audience / offer / proof 的结构化模板？
3. 是否能借鉴为 MAGA 内部 operator-facing skill？
```

## 补充：发现 AI 味之后如何修改

`great-writer` 提供的是修改原则和流程，不是中文营销文案的固定替换表。对 MAGA 更有价值的是把它转成可执行的 rewrite operation。

### 1. 不像人话：直接换成真实口语

判断标准：

```text
这句话真实用户会不会对朋友这么说？
```

如果答案是否定的，不做表层润色，直接改表达方式。

示例：

```text
AI 味：
这款产品在日常育儿场景中提供了较高的便利性。

更自然：
平时带娃已经够乱了，能少操一点心真的很重要。
```

### 2. 解释腔：改成生活场景

不要解释“为什么好”，而是给出一个具体场景，让读者自己感受到。

示例：

```text
AI 味：
这款产品能够缓解家长在育儿过程中的焦虑，让日常喂养更加安心。

更自然：
以前冲完奶还会反复看配料表，现在基本就是按点冲、喝完收拾，心里没那么悬了。
```

### 3. 罗列腔：只保留最强细节

如果一段里同时列很多维度，容易像总结材料。

示例：

```text
AI 味：
从营养、吸收和成长三个方面来看，都比较适合宝宝日常需求。

更自然：
我主要看孩子喝完之后状态稳不稳、肚子舒不舒服。
```

### 4. 空泛种草：补动作、时间、人物、具体处境

空泛表达：

```text
整体体验很好
让我更安心
对宝宝成长有帮助
值得推荐
```

不是完全不能出现，但不能单独出现。需要有生活证据支撑。

改写方向：

```text
抽象评价 -> 具体动作
泛泛安心 -> 为什么安心
产品卖点 -> 用户处境
```

### 5. 句式过齐：打散节奏

检查：

```text
连续句子长度太接近
每段都太完整
段落结构完全对称
开头句式重复
总结句过多
```

改写方向：

```text
长短句交错
允许轻微不完整表达
减少完整总结句
增加生活动作或转折
```

### 6. 模板腔：不要直接重写全文，要定位层级

MAGA 里发现 AI 味后，不建议直接让模型“重写得更真人”。应该先定位是哪一层导致：

```text
解释腔重：
  可能是 selected_keywords 里的写作手法太像总结说明。

句式过齐：
  可能是 title_shape / opening_shape / texture 抽样太集中。

模板腔：
  可能是 examples 权重太高，导致模型模仿整段结构。

品牌方口吻：
  可能是 business_rule 或 generation_requirements 里产品卖点前置。

空泛种草：
  可能是产品出现资格和场景证据不足。
```

建议处理顺序：

```text
1. evaluator 发现问题。
2. diagnoser 判断 likely_layer。
3. adjuster 只改最小必要层。
4. 重新走真实 content.generate。
5. 对比修正前后批次分布。
```

### 7. 可沉淀为固定 rewrite operations

```text
解释 -> 场景
罗列 -> 最强细节
抽象评价 -> 生活动作
品牌卖点 -> 用户处境
完整总结 -> 轻口语补充
整齐段落 -> 长短错落
整段模仿 -> 风格指纹
```

核心结论：

```text
Humanizer 负责发现“哪里不像人”；
Evaluator 负责判断“问题严重不严重”；
Diagnoser 负责判断“问题属于哪一层”；
Adjuster 只做最小变量修正；
Generator 仍然只走真实 content.generate。
```
