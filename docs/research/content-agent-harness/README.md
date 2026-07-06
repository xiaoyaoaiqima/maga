# MAGA Content Agent Harness 研究索引

这个目录用于沉淀围绕 MAGA 真人感、多样性、生文质量控制的 Agent / 内容生产 / 品牌语气治理项目研究。

当前研究结论：

- MAGA 不应该直接做一个“自由写文 Agent”。
- 更合适的方向是围绕真实 `content.generate` 的质量控制 harness。
- 核心要保护真实链路、一篇一生成、上下文分层、批次可评估、失败可诊断。

## 文件

- `project-research-notes.md`
  - 已研究项目与可借鉴点。
  - 当前包括：
    - `TribeAI/claude-cowork-brand-voice-plugin`
    - `d-wwei/great-writer`
  - 重点覆盖：
    - brand voice / tone 分层
    - 真人表达 guideline
    - source ranking
    - humanizer / evaluator
    - AI 味、解释腔、模板腔检测和修改策略

## 当前项目池状态

已深研：

```text
1. TribeAI/claude-cowork-brand-voice-plugin
   方向：brand voice / guideline / QA。

2. d-wwei/great-writer
   方向：写作 skill / anti-AI-slop / humanizer / style fingerprint。
```

已发现，待深研：

```text
3. SamurAIGPT/social-post
   方向：开源 AI 社媒内容生成 SaaS，多平台 mockup、多 tone、publish intent。

4. n8n Automate blog creation in brand voice with AI
   方向：用历史内容作为 brand voice examples，自动生成博客。

5. blacktwist/social-media-skills
   方向：社媒内容策略、创作、分析的 Agent skills。

6. ericosiu/ai-marketing-skills
   方向：增长实验、内容运营、outbound、SEO、营销自动化 skills。

7. coreyhaines31/marketingskills
   方向：面向 Claude Code / Codex / Cursor 的营销任务 skills，覆盖 copywriting、SEO、CRO、analytics。
```

基础设施类，暂不作为“内容生产解决方案”深研主线：

```text
LangGraph / Microsoft Agent Framework:
  适合借 workflow / state / checkpoint，但不是内容生产项目。

DSPy / DeepEval / Promptfoo / TruLens:
  适合借 prompt optimization / evaluator / regression test，但不是生文业务系统。
```

## 推荐落地方向

建议后续把这条线抽象为：

```text
MAGA Content Quality Harness
```

核心模块：

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
