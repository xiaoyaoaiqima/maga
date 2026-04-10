## 一、系统整体概述

编排调度中心（Raap Orchestration Center）负责对「文章生成 / 打分等 expert 服务」进行统一编排、调度与全链路数据记录，核心目标包括：

- **统一配置**：通过后台配置 `expert_config`，详细定义每个 expert 的模型、插件、prompt 等配置；然后通过配置 `job`，抽象出一类业务任务（例如"财经日报生成任务"），选择需要参与的 expert 配置。
- **统一调度**：将 `job` 拆解为多个 `expert_task`（定时任务 / 常驻任务），通过调度器（如 Prefect / APScheduler / crond 等）执行。
- **统一执行链路**：每次实际生成一篇文章对应一个 `sub_job`，并通过 `job_id / sub_job_id / content_id` 贯穿整个执行流程。
- **统一记录**：通过内容表、expert 业务结果表、expert 标准指标表 + 统一 utils 方法，完整记录每次 expert 调用的业务结果与技术指标。

> **全局约定**：  
> - `job_id` / `sub_job_id` / `content_id` **均为工具生成的全局唯一字符串**（如 UUID / 雪花 ID），不使用自增主键作为业务 ID。  
> - 可以在部分表中保留自增 `id` 作为技术主键，但**所有业务串联都使用 job_id/sub_job_id/content_id**。

---

## 二、核心概念与主线 ID

- **expert_config**：expert 的详细配置，包括模型、插件配置、prompt_template 等，在创建 job 前需要预先配置好。
- **job**：一类业务任务的抽象配置（如"财经日报生成任务"），通过选择已配置的 `expert_config_code` 列表来定义流程，不直接执行。
- **expert_task**：具体的调度任务（crond job），`job` 部署后按 `expert_config` 维度拆分，每个 `expert_config_code` 生成一条 `expert_task`。
- **sub_job**：一次"文章生产流程"的实例，最终产出一篇文章；整个多 expert 协同处理围绕同一个 `sub_job_id` 展开。
- **content**：某篇文章的内容实体（正文 + 上下文信息）。
- **plugin / plugin_context / plugin_config**：用于描述上下文拼装、工具调用等插件体系。
- **expert_business_result**：记录各 expert 的业务语义结果（文章内容、打分结果、修改建议等），包含本次执行使用的 prompt 和 plugin_config 快照。
- **expert_metrics**：记录各 expert 调用的标准技术指标（耗时、tokens、请求响应快照等）。

> **主线 ID 设计：**
> - `job_id`：标识某个编排任务模板，例如"某日报生成任务"。
> - `sub_job_id`：标识一次完整的"生成一篇文章"的过程。
> - `content_id`：标识某一篇具体文章内容，可与 `sub_job_id` 同值或独立生成，但类型与生成方式需全局统一。
>
> 任何时候只要拿到一个 `content_id`，就可以通过各表的关联字段，追踪该内容的完整生命周期。

---

## 三、数据模型设计

### 3.1 插件相关表：`plugin` 与 `plugin_context`

> **说明**：以下是插件系统基础表结构（来自既有设计），编排调度中心通过 `expert_config.plugin_config` 对它们进行编排与引用。

**`plugin` 表（插件管理表）示例结构：**

```sql
CREATE TABLE `plugin` (
  `id`             INT NOT NULL AUTO_INCREMENT COMMENT 'Primary Key',
  `plugin_code`    VARCHAR(255) DEFAULT NULL COMMENT '插件的code',
  `plugin_name`    VARCHAR(255) DEFAULT NULL COMMENT '插件的名称',
  `plugin_type`    VARCHAR(255) DEFAULT NULL COMMENT '插件的类型，用于区分：上下文拼接、工具调用等',
  `variable_list`  JSON COMMENT 'context_template 中的变量列表',
  `context_template` TEXT COMMENT '该插件的内容模板（待插入上下文），最终成为提示词的一部分',
  `enabled`        TINYINT(1) DEFAULT NULL COMMENT '是否激活',
  `create_time`    DATETIME DEFAULT NULL COMMENT 'Create Time',
  `update_time`    DATETIME DEFAULT NULL COMMENT 'Update Time',
  `created_by`     VARCHAR(255) DEFAULT NULL COMMENT 'Created By',
  `updated_by`     VARCHAR(255) DEFAULT NULL COMMENT 'Updated By',
  `is_deleted`     INT DEFAULT NULL COMMENT 'Is Deleted',
  `remark`         TEXT DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_plugin_code` (`plugin_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='插件管理表';
```
样例如下：
id	plugin_code	plugin_name	plugin_type	variable_list	context_template	enabled	create_time	update_time	created_by	updated_by	is_deleted
1	aaa	人设插件	context	["user"]	请你以{{user}}的身份：	1	2025/12/4 6:30	2025/12/4 6:30			0
2	bbb	品牌插件	context	["brand_tone", "brand_slogan"]	这个品牌的调性是`{{brand_tone}}` & `{{brand_slogan}}`	1	2025/12/4 6:30	2025/12/4 6:30			0
3		腾讯云文本审核	tool	["param_1", "param_2"]	"{
     ""param_1"": {{param_1}},
     ""param_2"": {{param_2}},
}"	1	2025/12/4 6:30	2025/12/4 6:30			0										

**`plugin_context` 表（插件上下文表）示例结构：**

```sql
CREATE TABLE `plugin_context` (
  `id`              INT NOT NULL AUTO_INCREMENT COMMENT 'Primary Key',
  `variable_name`   VARCHAR(255) DEFAULT NULL COMMENT '变量名（与 plugin.variable_list 中某一项对应）',
  `context_name`    VARCHAR(255) DEFAULT NULL COMMENT '替换上下文变量名（用于在 plugin_config 中引用）',
  `context`         TEXT COMMENT '替换上下文变量的解释/详细内容',
  `default_keywords` JSON DEFAULT NULL COMMENT '默认关键词',
  `default_corpus`  JSON DEFAULT NULL COMMENT '默认语料',
  `create_time`     DATETIME DEFAULT NULL COMMENT 'Create Time',
  `update_time`     DATETIME DEFAULT NULL COMMENT 'Update Time',
  `created_by`      VARCHAR(255) DEFAULT NULL COMMENT 'Created By',
  `updated_by`      VARCHAR(255) DEFAULT NULL COMMENT 'Updated By',
  `is_deleted`      INT DEFAULT NULL COMMENT 'Is Deleted',
  `remark`          TEXT DEFAULT NULL COMMENT '备注',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
  COMMENT='插件上下文表';
```
样例如下：
id	variable_name	context_name	context	default_keywords	default_corpus	create_time	update_time	created_by	updated_by	is_deleted							
1	user	家庭CEO	家庭CEO，掌握家庭财务大权，一把抓														
2	user	斜杠妈妈	带娃+副业双管齐下														
3	brand_tone	品牌调性	科学严谨														
4	brand_slogan	品牌口号	健康才是无上美																												


---

### 3.2 `plugin_config` 配置结构

**作用**：`plugin_config` 字段用于关联 `plugin` 与 `plugin_context`，指定某个 plugin 中某个变量使用哪些 `context_name` 进行渲染。该配置存储在 `expert_config.plugin_config` 字段中。

**结构示例：**

```json
  {
    "plugin_code_1": {
      "variable_name_1": ["context_name_1", "context_name_2"]
    },
    "plugin_code_2": {
      "variable_name_2": ["context_name_3", "context_name_4"],
      "variable_name_3": "context_name_5"
    }
  }
```

**字段含义：**

- **plugin_code_x**：对应 `plugin.plugin_code`。
- **variable_name_n**：对应 `plugin_context.variable_name`。
- **value**：
  - 为字符串时：指定唯一一个 `context_name`；
  - 为数组时：指定一组候选 `context_name`，**运行时可随机选择一个 / 按策略选择一个**。

**运行时处理逻辑（概念）：**

1. 解析 `plugin_config`，逐个 plugin / variable 处理，首先根据plugin_code获取对应的plugin，查看它的plugin_type是否为context，是则进行下一步。
2. 根据 `variable_name + context_name` 去 `plugin_context` 中查询上下文内容、默认关键词和默认语料。
3. 将选中的上下文内容渲染进 `plugin.context_template` 中，形成完整的上下文片段。
4. 将所有 plugin 渲染结果拼接 / 组合，形成最终的 `prompt_template`，存储在 `expert_config.prompt_template` 中。

---

### 3.3 `expert_config` 表：expert 配置表

**职责**：详细记录每个 expert 的配置信息，包括唯一的 expert_config_code、名称、expert_type、expert_service、expert_func、插件配置、模型相关配置、prompt_template 等。在创建 job 前，需要预先配置好所有要用到的 expert_config。

**关键点：**

- `expert_config_code` 为表唯一字符串，用于标识该配置，**不要求与 expert 方法名一致**。多个不同的 expert_config 可以使用同一个 expert 方法（通过 `expert_service` 和 `expert_func` 指定）。
- `expert_app` 指定 Dapr app ID（如 `"raap-service-ag"`），用于通过 Dapr 调用目标服务。
- `expert_service` 指定 service 名称（如 `"critic.CriticService"`）。
- `expert_func` 指定 gRPC method 名称（如 `"ReviewBan"`）。
- `plugin_config` 用于关联 `plugin` 与 `plugin_context`，指定插件变量使用的 context_name。
- `prompt_template` 是所有 plugin 渲染结果拼接 / 组合后的最终 prompt 模板。
- `model_config` 包含模型编码、模型参数（temperature、max_tokens 等）等配置。

**建议表结构：**

```sql
CREATE TABLE `expert_config` (
  `id`               BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',
  
  `expert_config_code`  VARCHAR(64) NOT NULL COMMENT 'expert_config 配置 code',
  `expert_config_name`  VARCHAR(255) NOT NULL COMMENT 'expert_config 名称',
  `expert_type`      VARCHAR(64) NOT NULL COMMENT '业务类型：GENERATION/SCORE/REWRITE/... 等',
  `expert_service`  VARCHAR(255) NOT NULL COMMENT 'expert的service（对应实际expert方法所在的服务）',
  `expert_func`  VARCHAR(255) NOT NULL COMMENT 'expert的function（对应实际expert方法）',
  `description`      TEXT COMMENT 'expert 配置描述',
  
  `model_code`       VARCHAR(255) COMMENT '使用的模型编码',
  `model_config`     JSON COMMENT '模型参数配置，例：{"temperature":0.7,"max_tokens":2048}',
  
  `plugin_config`    JSON COMMENT '插件配置 json，关联 plugin 和 plugin_context',
  `prompt_template`  TEXT COMMENT 'prompt 模板（所有 plugin 渲染结果拼接后的最终模板）',
  
  `invoke_target`    VARCHAR(255) NOT NULL COMMENT '调用目标字符串，如 generation_expert.run',
  
  `enabled`          TINYINT(1) DEFAULT 1 COMMENT '是否可用',
  `create_time`      DATETIME,
  `update_time`      DATETIME,
  `created_by`       VARCHAR(255),
  `updated_by`       VARCHAR(255),
  `is_deleted`       TINYINT(1) DEFAULT 0,
  `remark`           TEXT,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_expert_config_code` (`expert_config_code`)
) COMMENT='expert 配置表';
```

**配置示例：**

假设有两个"财经日报生成 expert"配置，都使用同一个 expert 方法，但配置不同：

**配置1：**
- `expert_config_code`: `"finance_daily_gen_v1"`
- `expert_config_name`: `"财经日报生成专家（版本1）"`
- `expert_type`: `"GENERATION"`
- `expert_service`: `"raap-service-generation-experts"`
- `expert_func`: `"article_generation_expert"`
- `model_code`: `"gpt-4o-mini"`
- `model_config`: `{"temperature": 0.7, "max_tokens": 2048}`
- `plugin_config`: 
  ```json
  {
    "aaa": {
      "user": ["家庭CEO", "斜杠妈妈"]
    },
    "bbb": {
      "brand_tone": ["品牌调性"],
      "brand_slogan": ["品牌口号"]
    }
  }
  ```
- `prompt_template`: `"请你以{{user}}的身份：\n这个品牌的调性是`{{brand_tone}}` & `{{brand_slogan}}`\n\n请生成一篇财经日报文章。"`
- `invoke_target`: `"article_generation_expert.run"`

**配置2（使用相同的 expert 方法，但配置不同）：**
- `expert_config_code`: `"finance_daily_gen_v2"`
- `expert_config_name`: `"财经日报生成专家（版本2）"`
- `expert_type`: `"GENERATION"`
- `expert_service`: `"raap-service-generation-experts"` （与配置1相同）
- `expert_func`: `"article_generation_expert"` （与配置1相同）
- `model_code`: `"gpt-4"`
- `model_config`: `{"temperature": 0.9, "max_tokens": 4096}`
- `plugin_config`: 
  ```json
  {
    "aaa": {
      "user": ["专业投资者"]
    }
  }
  ```
- `prompt_template`: `"请你以{{user}}的身份：\n\n请生成一篇深度财经分析文章。"`
- `invoke_target`: `"article_generation_expert.run"`

---

### 3.4 `job` 表：编排任务配置表

**职责**：由后台运营 / 研发配置，用来抽象一个完整的"文章生产业务流程"，通过选择已配置的 `expert_config_code` 列表来定义流程顺序。
- `id` 为技术主键（自增 BIGINT），`job_id` 为全局唯一字符串（工具生成），使用 UNIQUE KEY 约束。
- **重要**：创建 job 前，需要先配置好所有要用到的 `expert_config`。

**建议表结构：**

```sql
CREATE TABLE `job` (
  `id`                   BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',
  `job_id`      VARCHAR(64) NOT NULL COMMENT '全局唯一 job_id（工具生成）',
  `job_name`    VARCHAR(255) NOT NULL COMMENT '任务名称',
  `description` TEXT COMMENT '任务描述',

  `expert_config_code_list` JSON NOT NULL COMMENT '参与的 expert_config.expert_config_code 列表（顺序即流程顺序）',
  `article_count`     INT  COMMENT '本次job目标生产文章篇数',

  `status`      VARCHAR(32) NOT NULL DEFAULT 'NOT_DEPLOYED'
                COMMENT '任务状态：NOT_DEPLOYED/DEPLOYED/PAUSED/COMPLETED',
  `enabled`     TINYINT(1) DEFAULT 1 COMMENT '是否可用',

  `create_time` DATETIME,
  `update_time` DATETIME,
  `created_by`  VARCHAR(255),
  `updated_by`  VARCHAR(255),
  `is_deleted`  TINYINT(1) DEFAULT 0,
  `remark`      TEXT,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_job_id` (`job_id`)
) COMMENT='编排任务配置表';
```

**示例：**

- `expert_config_code_list`: `["finance_daily_gen_v1", "article_score_v1"]`
  - 表示该 job 先执行 `finance_daily_gen_v1`（生成文章），再执行 `article_score_v1`（打分）。

---

### 3.5 `expert_task` 表：expert 定时任务（crond job 表）

**职责**：描述每个 expert_config 对应的一条调度任务记录，由 `job` 在部署时根据 `job.expert_config_code_list` 拆分生成；该表更新时，调度服务需同步更新系统中的定时任务。

**关键点：**

- `expert_config_code` 关联到 `expert_config.expert_config_code`，通过该 expert_config_code 可以获取完整的 expert 配置信息（模型、插件、prompt_template、expert_app、expert_service、expert_func 等）。
- 不再存储 `model_code`、`plugin_config`、`expert_config` 等字段，这些信息都从 `expert_config` 表中获取。
- 调用 expert 时，使用 `expert_app`、`expert_service` 和 `expert_func` 通过 Dapr gRPC 调用目标服务。

**典型场景：**

- **文章生成 expert**：一般是按 cron 指定时间运行一次或多次，完成一次运行后可认为该任务实例"已完成"。
- **打分 / 监控 expert**：往往为常驻周期性任务，会按 cron 周期执行，长期处于"正常"状态。

**建议表结构：**

```sql
CREATE TABLE `expert_task` (
  `id`               BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',

  `job_id`           VARCHAR(64) NOT NULL COMMENT '对应 job.job_id',
  `expert_config_code` VARCHAR(64) NOT NULL COMMENT '对应 expert_config.expert_config_code',

  `cron_expression`  VARCHAR(255) NOT NULL COMMENT 'cron 表达式',
  `misfire_policy`   TINYINT NOT NULL DEFAULT 1 COMMENT '计划执行错误策略：1立即执行 2执行一次 3放弃执行',
  `concurrent`       TINYINT NOT NULL DEFAULT 0 COMMENT '是否并发执行：0允许 1禁止',

  `status`           TINYINT NOT NULL DEFAULT 0 COMMENT '0待执行 1执行中 2暂停 3完成（一次性任务）',

  `create_time`      DATETIME,
  `update_time`      DATETIME,
  `created_by`       VARCHAR(255),
  `updated_by`       VARCHAR(255),
  `is_deleted`       TINYINT(1) DEFAULT 0,
  `remark`           TEXT,
  PRIMARY KEY (`id`),
  KEY `idx_job_id` (`job_id`),
  KEY `idx_expert_config_code` (`expert_config_code`)
) COMMENT='expert 调度任务表（crond job）';
```

---

### 3.6 `sub_job` 表：一次文章生产流程实例

**职责**：描述一次完整的"生成一篇文章"的流程实例。由**文章生成 expert** 创建，后续打分、修正等 expert 会基于同一个 `sub_job_id` 进行处理。

**关键点修正：**

- 字段 **`expert_list`**：记录本次子任务需要执行的 `expert_config.expert_config_code` 列表（可以来源于 `job.expert_config_code_list`，也可以针对该子任务做适当裁剪）。
-  **`expert_complete_list`**：记录已经完成执行的 `expert_config.expert_config_code` 列表。
- 不再存储 `generation_expert_id`、`generation_model_code`、`plugin_config_snapshot`、`prompt` 等字段，这些信息存储在 `expert_business_result` 表中。
- `status` 仅保留：`RUNNING / FAILED / COMPLETED`。
  - 当 `expert_complete_list` 中的 expert_config_code 与 `expert_list` 完全一致时，将 `status` 置为 `COMPLETED`，表示本次子任务整体流程已走完。

**建议表结构：**

```sql
CREATE TABLE `sub_job` (
  `id`                   BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',

  `job_id`               VARCHAR(64) NOT NULL COMMENT 'job_id（全局唯一）',
  `sub_job_id`           VARCHAR(64) NOT NULL COMMENT 'sub_job_id（全局唯一）',
  `content_id`           VARCHAR(64) NOT NULL COMMENT 'content_id（全局唯一）',

  `expert_list`          JSON NOT NULL COMMENT '本次 sub_job 需要执行的 expert_config.expert_config_code 列表（顺序）',
  `expert_complete_list` JSON COMMENT '已经完成执行的 expert_config.expert_config_code 列表',

  `status`               VARCHAR(32) NOT NULL DEFAULT 'RUNNING'
                         COMMENT 'RUNNING/FAILED/COMPLETED',
  `error_message`        TEXT COMMENT '整体失败原因（如有）',

  `create_time`          DATETIME,
  `update_time`          DATETIME,
  `created_by`           VARCHAR(255),
  `updated_by`           VARCHAR(255),

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_sub_job_id` (`sub_job_id`),
  KEY `idx_job_id` (`job_id`),
  KEY `idx_content_id` (`content_id`)
) COMMENT='一次文章生产流程的子任务表';
```

**状态流转示意：**

- `RUNNING`：正在执行中（有未完成的 expert）。
- `FAILED`：出现致命错误，无法继续（例如生成失败且不再重试）。
- `COMPLETED`：
  - 正常含义：**流程执行完成**，`expert_complete_list` 与 `expert_list` 一致。
  - 也可拓展为“中途人工终止”的场景，但需要在 `remark` 或额外字段中区分“正常完成/中途取消”。

---

### 3.6 `content` 表：文章内容表

**职责**：记录文章内容本身（正文、上下文信息等）。  
**关键点修正**：不再使用 `version` 字段；如后续 expert 对文章进行修改，直接更新 `content` 字段即可，修改记录通过 `expert_business_result` 表体现。

**建议表结构：**

```sql
CREATE TABLE `content` (
  `id`           BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',

  `job_id`       VARCHAR(64) NOT NULL,
  `sub_job_id`   VARCHAR(64) NOT NULL,
  `content_id`   VARCHAR(64) NOT NULL COMMENT '文章内容 id（全局唯一）',

  `prompt`       TEXT COMMENT '本内容对应的 prompt（可与 sub_job.prompt 一致或后续更新）',
  `context_list` JSON COMMENT '生成该内容时使用的 context_name 数组列表（来自 plugin_context.context_name）',
  `title`        VARCHAR(255) COMMENT '标题',
  `content`      LONGTEXT COMMENT '文章正文内容',
  `is_valid`     TINYINT(1) DEFAULT NULL COMMENT '是否当前有效（0不可用 1可用 null待定）',
  `is_test_case` TINYINT(1) DEFAULT 1 COMMENT '是否为测试用例（0不是 1是）',

  `create_time`  DATETIME,
  `update_time`  DATETIME,
  `created_by`   VARCHAR(255),
  `updated_by`   VARCHAR(255),

  PRIMARY KEY (`id`),
  KEY `idx_job_sub_content` (`job_id`, `sub_job_id`, `content_id`)
) COMMENT='文章内容表';
```

如需未来支持“版本回溯”，推荐增加一张 `content_history` 表，将过往版本归档，而不在主表中加 `version` 字段。

---

### 3.7 `expert_business_result` 表：expert 业务返回结果记录表

**职责**：记录每次 expert 执行的业务语义结果（例如生成的文章结构、打分结果、修改意见等），用于业务分析与追踪。同时记录本次执行使用的 prompt 和 plugin_config 快照。

**必带字段**：`job_id`、`sub_job_id`、`content_id`。

**关键点：**

- `expert_config_code` 关联到 `expert_config.expert_config_code`。
- `expert_config_name` 对应 `expert_config.expert_config_name`。
- `plugin_config_snapshot` 记录本次执行实际使用的插件配置快照（以防后续 expert_config 修改）。
- `prompt` 记录本次执行使用的最终 prompt（包含插件渲染后的上下文）。

**建议表结构：**

```sql
CREATE TABLE `expert_business_result` (
  `id`              BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',

  `job_id`          VARCHAR(64) NOT NULL,
  `sub_job_id`      VARCHAR(64) NOT NULL,
  `content_id`      VARCHAR(64) NOT NULL,

  `expert_task_id`   BIGINT NOT NULL COMMENT '对应 expert_task.id',
  `expert_config_code` VARCHAR(64) NOT NULL COMMENT '对应 expert_config.expert_config_code',
  `expert_config_name` VARCHAR(255) NOT NULL COMMENT '对应 expert_config.expert_config_name',

  `business_type`   VARCHAR(64) NOT NULL COMMENT '业务类型：GENERATION/SCORE/REWRITE/... 等',

  `plugin_config_snapshot` JSON COMMENT '本次执行实际使用的插件配置快照（以防后续 expert_config 修改）',
  `prompt`          TEXT COMMENT '本次执行使用的最终 prompt（包含插件渲染后的上下文）',

  `business_result` JSON NOT NULL COMMENT 'expert 业务返回整体 json，结构按 business_type 约定',

  `status`          VARCHAR(32) NOT NULL DEFAULT 'SUCCESS'
                    COMMENT 'SUCCESS/FAILED/PARTIAL',
  `error_message`   TEXT COMMENT '失败原因（如有）',

  `create_time`     DATETIME,

  PRIMARY KEY (`id`),
  KEY `idx_job_sub_content` (`job_id`, `sub_job_id`, `content_id`)
) COMMENT='expert 业务返回结果记录表';
```

**典型示例：**

- **文章生成 expert（GENERATION）**：

  ```json
  {
    "type": "GENERATION",
    "title": "今日宏观经济简报",
    "article": "......",
    "outline": ["一、宏观概述", "二、市场表现"],
    "tags": ["宏观", "股市"]
  }
  ```

- **打分 expert（SCORE）**：

  ```json
  {
    "type": "SCORE",
    "score": 4.5,
    "reason": "逻辑清晰，但部分数据引用较旧",
    "dimension_scores": {
      "logic": 5,
      "data_freshness": 4
    }
  }
  ```

如后续有“文章修改 expert”，可以在 `business_type` 中新增 `REWRITE`，并在 `business_result` 中记录修改前后差异等信息。

---

### 3.8 `expert_metrics` 表：expert 标准返回记录表（技术指标）

**职责**：记录每次 expert 调用的标准技术指标，用于性能分析、成本核算与问题排查。

**必带字段**：`job_id`、`sub_job_id`、`content_id`。

**关键点：**

- `expert_config_code` 关联到 `expert_config.expert_config_code`。
- `expert_config_name` 对应 `expert_config.expert_config_name`。

**建议表结构：**

```sql
CREATE TABLE `expert_metrics` (
  `id`              BIGINT NOT NULL AUTO_INCREMENT COMMENT '技术主键',

  `job_id`          VARCHAR(64) NOT NULL,
  `sub_job_id`      VARCHAR(64) NOT NULL,
  `content_id`      VARCHAR(64) NOT NULL,

  `expert_task_id`   BIGINT NOT NULL,
  `expert_config_code` VARCHAR(64) NOT NULL COMMENT '对应 expert_config.expert_config_code',
  `expert_config_name` VARCHAR(255) NOT NULL COMMENT '对应 expert_config.expert_config_name',

  `start_time`      DATETIME NOT NULL,
  `end_time`        DATETIME NOT NULL,
  `duration_ms`     BIGINT NOT NULL COMMENT '执行耗时（毫秒）',

  `request_tokens`  INT COMMENT '请求 tokens（LLM 类 expert）',
  `response_tokens` INT COMMENT '响应 tokens',
  `total_tokens`    INT COMMENT '总 tokens',
  `model_code`      VARCHAR(255) COMMENT '模型编码',

  `raw_request`     JSON COMMENT '请求报文快照（可做脱敏及字段裁剪）',
  `raw_response`    JSON COMMENT '响应报文快照（可做字段裁剪）',

  `create_time`     DATETIME,

  PRIMARY KEY (`id`),
  KEY `idx_job_sub_content` (`job_id`, `sub_job_id`, `content_id`)
) COMMENT='expert 标准指标记录表';
```

---

## 四、编排与调度执行流程

### 4.1 expert_config 配置流程

在创建 job 之前，需要先配置好所有要用到的 `expert_config`。

- **步骤 1：配置 expert_config**
  - 后台页面填写：
    - `expert_config_name`、`expert_type`、`description`；
    - `expert_app`：指定 Dapr app ID（如 `"raap-service-generation-experts"`）；
    - `expert_service`：指定 gRPC service 名称（如 `"content_generation.ContentGenerationService"`）；
    - `expert_func`：指定 gRPC method 名称（如 `"Generate"`）；
    - `model_code`、`model_config`（模型参数，如 temperature、max_tokens 等）；
    - `plugin_config`：选择要使用的插件，并为每个插件的变量指定 context_name（可以是单个值或候选数组）；
    - `prompt_template`：所有 plugin 渲染结果拼接后的最终 prompt 模板。
  - 系统生成唯一的 `expert_config_code`，写入 `expert_config` 表。
  - **注意**：
    - `prompt_template` 可以通过系统自动生成，即根据 `plugin_config` 配置，从 `plugin` 和 `plugin_context` 表中获取模板和上下文，渲染后拼接生成。
    - 多个不同的 `expert_config` 可以使用同一个 `expert_service` 和 `expert_func`，只需要 `expert_config_code` 不同即可。

- **步骤 2：验证 expert_config**
  - 确保 `plugin_config` 中引用的 `plugin_code` 和 `context_name` 都存在且有效。
  - 确保 `prompt_template` 格式正确。
  - 确保 `expert_service` 和 `expert_func` 指向的服务和方法存在。

### 4.2 job 配置与部署流程

- **步骤 1：创建 job**
  - 后台页面填写：
    - `job_name`、`description`；
    - `expert_config_code_list`：从已配置的 `expert_config` 中选择，例如 `["finance_daily_gen_v1", "article_score_v1"]`。
  - 系统生成全局唯一的 `job_id`，写入 `job` 表，`status` = `NOT_DEPLOYED`。

- **步骤 2：部署 job**
  - 管理员在后台点击"部署"：
    - 读取 `job.expert_config_code_list`；
    - 按每个 `expert_config_code` 生成对应的 `expert_task`：
      - 设置 `job_id`、`expert_config_code`；
      - 从 `expert_config` 表中获取 `expert_app`、`expert_service` 和 `expert_func`，用于后续调用 expert 服务；
      - 配置 `cron_expression`、`misfire_policy`、`concurrent` 等调度参数。
    - 将 `expert_task` 注册到实际调度系统。
    - 将 `job.status` 更新为 `DEPLOYED` 或 `RUNNING`。

- **步骤 3：运行与控制**
  - 对某些 expert 需要暂停 / 仅停止文章生成：
    - 更新对应 `expert_task.status = 1`（暂停），或更新 `job.status = COMPLETED`。
    - 调度服务监听到 `expert_task`/`job` 变化后，更新实际定时任务。

---

### 4.3 一次文章生产链路（以 sub_job 为中心）

以"文章生成 expert + 打分 expert"为例：

- **阶段 1：文章生成 expert 触发**
  1. 调度器按 `expert_task(cron_expression)` 触发文章生成 expert。
  2. 系统生成：
     - 全局唯一 `sub_job_id`；
     - 全局唯一 `content_id`；
  3. 创建 `sub_job` 记录：
     - `job_id` = 对应 job；
     - `sub_job_id` / `content_id`；
     - `expert_list` 来自 `job.expert_config_code_list` 或根据策略裁剪（存储 expert_config_code 数组）；
     - `expert_complete_list` 初始为空；
     - `status` = `RUNNING`。
  4. 获取 expert_config 配置：
     - 根据 `expert_task.expert_config_code` 从 `expert_config` 表中获取完整配置（expert_service、expert_func、模型、插件、prompt_template 等）。
     - 运行时处理 `plugin_config`：
       - 如果某个变量的值是数组，按策略（随机、轮询等）选择一个具体的 `context_name`。
       - 根据选中的 `context_name` 从 `plugin_context` 表中获取上下文内容。
       - 将上下文内容渲染进 `plugin.context_template`，拼接所有 plugin 片段，生成最终的 `prompt`。
  5. 调用文章生成 expert 接口：
     - 根据 `expert_config.expert_service` 和 `expert_config.expert_func` 确定调用的服务和方法。
     - 入参包含 `job_id`、`sub_job_id`、`content_id`、`expert_task_id`、`expert_config_code` 及从 `expert_config` 获取的配置信息（模型、prompt 等）。
     - expert 返回文章内容及相关结构化信息（见后文）。
  6. 处理返回：
     - 写入 `content` 表（正文 + `context_list` + `prompt`）。
     - 写入 `expert_business_result`（`business_type=GENERATION`）：
       - 记录 `expert_config_code`、`expert_config_name`；
       - 记录 `plugin_config_snapshot`（本次实际使用的插件配置快照）；
       - 记录 `prompt`（本次使用的最终 prompt）。
     - 写入 `expert_metrics`（时延、tokens 等，记录 `expert_config_code`、`expert_config_name`）。
     - 将该生成 expert 的 `expert_config_code` 加入 `sub_job.expert_complete_list`。

- **阶段 2：打分 expert 触发**
  1. 调度器按 `expert_task(cron_expression)` 触发打分 expert。
  2. 系统查询需要打分的 `sub_job`/`content` 列表（例如筛选"已生成但未打分"的内容）。
  3. 对每条内容：
     - 获取对应的 `expert_config` 配置。
     - 调用打分 expert 接口，入参携带统一 ID 及必要上下文。
     - 解析返回结果：
       - 写入 `expert_business_result`（`business_type=SCORE`）：
         - 记录 `expert_config_code`、`expert_config_name`；
         - 记录 `plugin_config_snapshot`、`prompt`。
       - 写入 `expert_metrics`（记录 `expert_config_code`、`expert_config_name`）。
       - 将该打分 expert 的 `expert_config_code` 加入 `sub_job.expert_complete_list`。
  4. 当 `set(expert_complete_list) == set(expert_list)`：
     - 将 `sub_job.status` 更新为 `COMPLETED`（表示该子任务执行流程已全部完成）。

- **阶段 3：异常与失败处理**
  - 如果某 expert 执行失败：
    - 在 `expert_business_result` 中记录 `status=FAILED`、`error_message`。
    - 在 `expert_metrics` 中仍记录本次调用指标（如有）。
    - 可按策略选择：
      - 重试；
      - 标记 `sub_job.status = FAILED` 并终止后续 expert；
      - 进入人工干预流程。

---

## 五、expert 调用接口设计

### 5.1 通用入参结构

> **入参核心思想**：以 `job_id / sub_job_id / content_id` 为主线，通过 `expert_config_code` 获取完整的 expert 配置（包括 expert_service、expert_func、模型、插件、prompt_template 等），并在运行时将 `plugin_config` 中的变量值确定为一个具体的 `context_name`，渲染生成最终的 prompt。根据 `expert_service` 和 `expert_func` 确定实际调用的服务和方法。

**建议接口示例：**

- 路由：根据 `expert_config.expert_service` 和 `expert_config.expert_func` 确定调用的服务和方法，例如：
  - 如果 `expert_service` 为 `"raap-service-generation-experts"`，`expert_func` 为 `"article_generation_expert"`，则调用该服务的对应方法。
  - 或者使用统一的路由：`POST /api/experts/{expert_config_code}/invoke`（编排中心内部根据 expert_config 信息路由到对应服务）

**请求体示例：**

```json
{
  "job_id": "job-xxx",
  "sub_job_id": "sub-xxx",
  "content_id": "content-xxx",
  "expert_task_id": 123,
  "expert_config_code": "finance_daily_gen_v1",
  "expert_app": "raap-service-ag",
  "expert_service": "critic.CriticService",
  "expert_func": "ReviewBan",
  "content": "**********",
  "prompt": "请你以家庭CEO的身份：\n这个品牌的调性是`科学严谨` & `健康才是无上美`\n\n请生成一篇财经日报文章。",
  "model_code": "gpt-4o-mini",
  "model_config": {
    "temperature": 0.7,
    "max_tokens": 2048
  }
}
```

**说明：**

- `expert_config_code`：用于从 `expert_config` 表中获取完整配置。
- `expert_service`、`expert_func`：从 `expert_config` 表中获取，用于确定实际调用的服务和方法。
- `prompt`：编排中心根据 `expert_config.plugin_config` 和 `expert_config.prompt_template` 渲染生成的最终 prompt。
- `model_code`、`model_config`：从 `expert_config` 表中获取，也可在请求中覆盖。
- 编排中心在调用前会：
  1. 根据 `expert_config_code` 获取 `expert_config` 配置（包括 `expert_service`、`expert_func`）。
  2. 处理 `plugin_config`：如果某变量的值是数组，按策略选择一个具体的 `context_name`。
  3. 根据选中的 `context_name` 从 `plugin_context` 获取上下文，渲染进 `plugin.context_template`。
  4. 将所有 plugin 片段拼接，生成最终的 `prompt`。
  5. 根据 `expert_service` 和 `expert_func` 确定调用的服务和方法，发起实际调用。

---

### 5.2 生文 expert 返回结构示例

```json
{
  "status": "SUCCESS",
  "job_id": "job-xxx",
  "sub_job_id": "sub-xxx",
  "content_id": "content-xxx",

  "business_result": {
    "type": "GENERATION",
    "title": "今日行业观察",
    "article": "......",
    "outline": ["段1", "段2"],
    "tags": ["医疗", "政策"]
  },
  "metrics": {
    "start_time": "2025-12-04T10:00:00Z",
    "end_time": "2025-12-04T10:00:03Z",
    "duration_ms": 3200,
    "request_tokens": 800,
    "response_tokens": 1200,
    "total_tokens": 2000,
    "model_code": "gpt-4o-mini"
  }
}
```

编排中心在拿到返回结果后，统一：

- 写入 `content` 表（`content`、`prompt`、`context_list` 等）。
- 写入 `expert_business_result`（`business_type=GENERATION`）：
  - 记录 `expert_config_code`、`expert_config_name`；
  - 记录 `plugin_config_snapshot`（本次实际使用的插件配置快照）；
  - 记录 `prompt`（本次使用的最终 prompt）。
- 写入 `expert_metrics`（记录 `expert_config_code`、`expert_config_name`）。
- 更新 `sub_job.expert_complete_list`，将该 `expert_config_code` 加入列表，检查是否可将 `sub_job.status` 置为 `COMPLETED`。

---

### 5.3 打分 expert 返回结构示例

```json
{
  "status": "SUCCESS",
  "job_id": "job-xxx",
  "sub_job_id": "sub-xxx",
  "content_id": "content-xxx",

  "business_result": {
    "type": "SCORE",
    "score": 4.2,
    "reason": "主题清晰，部分数据佐证不足",
    "dimension_scores": {
      "logic": 4.5,
      "data": 3.8
    }
  },
  "metrics": {
    "start_time": "2025-12-04T11:00:00Z",
    "end_time": "2025-12-04T11:00:01Z",
    "duration_ms": 1500,
    "request_tokens": 300,
    "response_tokens": 200,
    "total_tokens": 500,
    "model_code": "gpt-4o-mini"
  }
}
```

编排中心同样通过统一 utils 方法进行持久化和日志记录。

---

## 六、插件与上下文拼装流程

该流程在编排中心调用 expert 前执行，用于根据 `expert_config.plugin_config` 和 `expert_config.prompt_template` 生成最终的 prompt。

- **步骤 1：获取 expert_config 配置**
  - 根据 `expert_config_code` 从 `expert_config` 表中获取：
    - `expert_service`、`expert_func`：expert 服务和方法信息。
    - `plugin_config`：插件配置 JSON。
    - `prompt_template`：prompt 模板（所有 plugin 渲染结果拼接后的模板）。
    - `model_code`、`model_config`：模型配置信息。

- **步骤 2：解析 plugin_config**
  - 遍历每个 `plugin_code`：
    - 遍历其下的 `variable_name` → 取出对应的 `value`（字符串或数组）。
    - 若为数组，则按策略（随机、轮询、按权重等）选择一个具体的 `context_name`。
    - 记录最终选择的 `context_name`，用于后续生成 `plugin_config_snapshot`。

- **步骤 3：查找 plugin_context**
  - 根据 `(plugin_code, variable_name, context_name)` 从 `plugin_context` 中拿到：
    - `context`：具体的上下文文本；
    - `default_keywords`：可用于扩展 prompt；
    - `default_corpus`：可选，用于 few-shot 示例等。

- **步骤 4：渲染 plugin.context_template**
  - 根据 `plugin_code` 从 `plugin` 表中获取 `context_template`。
  - 使用上述 `context` / `default_keywords` / `default_corpus` 等信息，替换 `context_template` 里的变量占位符。
  - 得到最终的 plugin 片段文本。

- **步骤 5：拼装 expert prompt**
  - 将所有 plugin 片段按顺序拼接，形成完整的上下文部分。
  - 将上下文部分与 `expert_config.prompt_template` 组合，生成最终的 `prompt`。
  - 该 `prompt` 将：
    - 传递给 expert 接口调用；
    - 写入 `expert_business_result.prompt`（记录本次执行使用的 prompt）；
    - 写入 `content.prompt`（如果是生成类 expert）。

- **步骤 6：记录 context_list 和 plugin_config_snapshot**
  - 将实际选中的 `context_name` 列表写入 `content.context_list`，确保后续可复盘「是哪些上下文驱动了当前文章」。
  - 将本次实际使用的 `plugin_config`（变量值已确定为一个具体的 `context_name`）写入 `expert_business_result.plugin_config_snapshot`。

---

## 七、统一 utils 设计（记录结果 / 指标 / 日志）

围绕「调用 expert 接口的输入输出」，设计三类统一 utils 方法。

### 7.1 记录 expert 业务返回结果的 utils

**函数职责**：将每次 expert 的业务结果写入 `expert_business_result`，同时记录本次执行使用的 prompt 和 plugin_config 快照。

**示例函数签名（伪代码）：**

```python
def save_expert_business_result(
    job_id: str,
    sub_job_id: str,
    content_id: str,
    expert_task_id: int,
    expert_config_code: str,
    expert_config_name: str,
    business_type: str,
    business_result: dict,
    plugin_config_snapshot: dict | None = None,
    prompt: str | None = None,
    status: str = "SUCCESS",
    error_message: str | None = None,
) -> None:
    ...
```

### 7.2 记录 expert 标准指标的 utils

**函数职责**：计算并写入 `expert_metrics`，方便后续做性能与成本分析。

```python
from datetime import datetime

def save_expert_metrics(
    job_id: str,
    sub_job_id: str,
    content_id: str,
    expert_task_id: int,
    expert_config_code: str,
    expert_config_name: str,
    model_code: str,
    start_time: datetime,
    end_time: datetime,
    request_tokens: int | None,
    response_tokens: int | None,
    raw_request: dict | None,
    raw_response: dict | None,
) -> None:
    ...
```

内部统一计算：

- `duration_ms = (end_time - start_time).total_seconds() * 1000`
- `total_tokens = (request_tokens or 0) + (response_tokens or 0)`

### 7.3 日志打印 utils

**函数职责**：统一日志格式，把关键 ID 和 expert 信息都打出来，方便全链路跟踪。

```python
def log_expert_call(
    level: str,
    job_id: str,
    sub_job_id: str,
    content_id: str,
    expert_config_code: str,
    expert_config_name: str,
    message: str,
    extra: dict | None = None,
) -> None:
    ...
```

日志中统一包含：

- `job_id` / `sub_job_id` / `content_id`；
- `expert_config_code` / `expert_config_name`；
- 关键信息（message + extra 序列化）。

---

## 八、以 content_id 追踪文章全生命周期

基于以上表结构和统一 ID 设计，可以通过一个 `content_id` 回溯整篇文章的生命周期：

- 在 **`content`**：
  - 获取当前文章正文、生成时的 `prompt`、`context_list` 以及是否有效。
- 在 **`sub_job`**：
  - 获取本次文章生产流程的整体状态（RUNNING/FAILED/COMPLETED）、参与的 `expert_config_code` 列表、已完成的 `expert_config_code` 情况及错误信息。
- 在 **`expert_business_result`**：
  - 查看所有 expert 在该 content 上的业务语义结果（生文、打分、修改、审核等）的详细记录。
  - 查看每次执行使用的 `expert_config_code`、`prompt`、`plugin_config_snapshot`。
- 在 **`expert_metrics`**：
  - 查看每次 expert 调用的耗时、tokens 消耗、模型信息和请求响应快照。
  - 查看每次执行使用的 `expert_config_code`。
- 结合 **`expert_task`**、**`expert_config`** 与 **`job`**：
  - 通过 `expert_config_code` 回溯到 `expert_config`，获取完整的 expert 配置信息（expert_service、expert_func、模型、插件、prompt_template 等）。
  - 回溯该文章属于哪个上层业务任务、处于什么调度策略、是在哪个 cron 表达式下被触发。
  - 了解实际调用的 expert 服务和方法。

这保证了：

- **可观察性**：可以清晰地从业务视角和技术视角理解每篇文章的产生原因与过程。
- **可审计性**：满足内部合规 / 审计需求。
- **可优化性**：基于 `expert_metrics` 和业务结果数据，可以迭代调优 expert 配置与 prompt 策略。

---

## 九、扩展与优化建议

- **新增 expert 类型**：
  - 只需在 `business_type` 中新增类型（如 SUMMARY、REWRITE、CLASSIFY 等），不需要改动表结构。
  - 对应的业务返回结构在文档中额外约定即可。

- **策略引擎**：
  - 可基于 `expert_business_result`（打分、标签等）设计自动化策略：
    - 例如分数低于阈值自动触发 rewrite expert；  
    - 多个打分 expert 投票决定是否发布。

- **多租户 / 多业务线**：
  - 如需支持多租户，可在关键表（`job`、`expert_task`、`sub_job`、`content` 等）中增加 `tenant_id` / `biz_line` 字段。

- **链路可视化**：
  - 后台可以基于 `job_id` 和 `sub_job_id` 构建流程拓扑，展示每个 expert 的执行时间、结果和耗时。

整体上，本技术文档定义了：

- **数据模型**：plugin / plugin_context / expert_config / job / expert_task / sub_job / content / expert_business_result / expert_metrics；
- **ID 策略**：expert_config_code / job_id / sub_job_id / content_id 全局唯一并贯穿全链路；
- **配置与调度流程**：从 expert_config 配置 → job 配置（选择 expert_config_code_list）→ expert_task 部署 → sub_job 实例 → expert 调用；
- **统一 utils**：对 expert 调用的业务结果、标准指标与日志进行统一封装和落库，记录 expert_config_code、prompt、plugin_config_snapshot 等关键信息。

在此基础上，可以进一步落地到具体实现（FastAPI 接口、SQLAlchemy ORM 模型、Prefect Flow 定义等），作为下一阶段的工程任务。


