# RAAP 微服务架构迁移指南

## 📋 概述

本指南详细说明如何将 `rs-koc-platform` 单体应用迁移到 RAAP 微服务架构。核心目标是将 AIGC 工作流拆分为独立服务，并使用 Dapr 进行服务间通信，同时保留 LangGraph 的编排能力。

## 🏗️ 架构设计

### 1. 服务拆分策略

| 原单体组件 | 目标微服务 | 职责 |
|------------|------------|------|
| **Orchestrator** | `raap-service-orchestrator` | **核心编排**：接收请求，定义 Workflow（Expert 组合），协调服务调用，聚合结果。 |
| **GE Agent** | `raap-service-generation-experts` | **内容生成**：管理多个 Generation Expert，处理 LLM 生成任务。每个 Expert 独立管理提示词和生成逻辑。 |
| **BAN Agents** | `raap-service-ag` | **审核**：管理多个审核 Expert (Illegal, Unreasonable, Ineffective)，负责内容合规性检查。 |
| **Critic Agents** | `raap-service-ag` | **评分**：管理多个评分 Expert (Quality, Effectiveness, Brand Fit)，负责内容质量评估。 |
| **KC (关键词与语料)** | `raap-service-keyword-corpus` | **配置中心**：管理 Expert 配置、基础模板、规则片段、卖点库、关键词和语料库。提供 Expert 配置拉取和共享资源获取接口。详见 [KEYWORD_CORPUS_REFACTOR_PLAN.md](../docs/KEYWORD_CORPUS_REFACTOR_PLAN.md) |
| **UM (用户记忆)** | `raap-service-user-memory` | **用户数据**：存储和管理用户历史、偏好、行为数据，支持个性化生成。 |

### 2. 通信架构

平台统一使用 **Dapr** 作为服务网格，内部服务间调用全部采用 **gRPC** 协议。

```
LangGraph Workflow (in Orchestrator)
  │
  ├── [Generation Node] ──(gRPC)──> raap-service-generation-experts
  │
  ├── [BAN Node] ───────(gRPC)──> raap-service-ag
  │
  └── [Critic Node] ────(gRPC)──> raap-service-ag
```

## 🌐 系统宏观架构设计

### 1. 整体架构概述

RAAP 系统采用**微服务架构**，通过 **Dapr** 提供的服务网格机制实现各个微服务间的通信与协调。系统由一个核心编排服务和多个业务子服务组成，每个服务专注于单一功能，确保高内聚和低耦合。

**核心设计原则**:
- ✅ **单一职责**: 每个服务只负责一项核心业务能力
- ✅ **松耦合**: 服务间通过标准化的 gRPC 接口通信
- ✅ **独立部署**: 各服务可独立开发、测试、部署和扩展
- ✅ **容错设计**: 单个服务故障不影响整体系统运行

### 2. 核心服务职责

#### 2.1 Orchestrator（编排服务）

**核心定位**: 系统的"大脑"，负责业务流程管理和服务编排。

**主要职责**:
- 📥 **接收业务请求**: 作为系统唯一入口，接收所有业务请求
- 🔄 **流程编排**: 根据业务场景调度子服务，管理执行顺序和并发策略
- 🔗 **服务协调**: 协调 GE、AG、UM、KC 等服务的调用
- 📊 **结果聚合**: 收集各服务返回结果，聚合后返回给业务层
- ⚡ **性能优化**: 通过异步调用和并发控制提升响应速度

**示例流程**:
```python
async def execute_workflow(self, request):
    # 1. 并发调用用户记忆和关键词服务
    user_context, keywords = await asyncio.gather(
        self.call_um(request.user_id),
        self.call_kc(request.brand_id)
    )
    
    # 2. 基于上下文调用生成服务
    content = await self.call_ge(prompt, user_context, keywords)
    
    # 3. 并发调用审核服务
    ban_result, critic_result = await asyncio.gather(
        self.call_ag_ban(content),
        self.call_ag_critic(content)
    )
    
    # 4. 聚合结果并返回
    return self._aggregate_results(content, ban_result, critic_result)
```

#### 2.2 GE（Generation Experts - 内容生成服务）

**核心定位**: 内容生成引擎，负责所有 AIGC 生成任务。

**主要职责**:
- 🎨 **内容生成**: 根据 Prompt 和上下文生成高质量内容
- 🔍 **语料检索**: 调用 KC 服务获取关键词和语料库数据
- 👤 **个性化生成**: 调用 UM 服务获取用户历史和偏好，生成个性化内容
- 🔁 **自我优化**: 内部可使用 LangGraph 实现"生成-检查-修正"循环
- 📈 **多样性控制**: 确保生成内容的多样性和创新性

**服务依赖**:
- **KC (Keywords & Corpus)**: 获取关键词、语料库、品牌词汇等
- **UM (User Memory)**: 获取用户画像、历史行为、偏好数据

#### 2.3 AG（Alignment & Governance - 对齐与治理服务）

**核心定位**: 内容质量守门员，确保生成内容合规且高质量。

**主要职责**:

**A. BAN 子服务（合规性检查）**:
- 🚫 **Illegal Check**: 检查违法违规内容（政治敏感、暴力、色情等）
- ⚠️ **Unreasonable Check**: 检查不合理内容（逻辑错误、事实错误等）
- ❌ **Ineffective Check**: 检查无效内容（偏离主题、质量低下等）

**B. Critic 子服务（质量评估）**:
- ⭐ **Quality Score**: 评估内容质量（语法、流畅度、逻辑性）
- 🎯 **Effectiveness Score**: 评估内容有效性（是否达成目标）
- 🏷️ **Brand Fit Score**: 评估品牌契合度（是否符合品牌调性）
- 💡 **Innovation Score**: 评估创新性和独特性

**返回结果**:
```python
{
    "ban_result": {
        "is_legal": true,
        "is_reasonable": true,
        "is_effective": true,
        "issues": []  # 如果有问题，详细说明
    },
    "critic_result": {
        "quality_score": 85,
        "effectiveness_score": 90,
        "brand_fit_score": 88,
        "overall_score": 87.7,
        "suggestions": ["可以增加更多数据支撑"]
    }
}
```

#### 2.4 UM（User Memory - 用户记忆服务）

**核心定位**: 用户行为和偏好的存储与分析中心。

**主要职责**:
- 💾 **历史记录**: 存储用户的历史交互、生成内容、反馈数据
- 👥 **用户画像**: 构建用户偏好模型、兴趣标签、行为特征
- 🎯 **个性化推荐**: 为 GE 提供用户偏好数据，支持个性化生成
- 📊 **行为分析**: 分析用户行为模式，优化内容生成策略
- 🔄 **反馈循环**: 收集用户对生成内容的反馈，持续优化

**数据模型示例**:
```python
{
    "user_id": "12345",
    "preferences": {
        "topics": ["科技", "商业", "创新"],
        "style": "专业且易懂",
        "length": "中等长度 (500-800字)"
    },
    "history": [
        {"content_id": "xxx", "rating": 4.5, "timestamp": "..."}
    ],
    "behavioral_features": {
        "active_hours": "09:00-18:00",
        "avg_session_duration": "15min"
    }
}
```

#### 2.5 Keywords-Corpus（关键词与语料库服务）

**服务名**: `raap-service-keyword-corpus`

**核心定位**: Expert 配置中心 + 共享资源管理

**核心设计理念**：
- **去中心化**: 每个服务（GE/AG）管理自己的 Expert，keyword-corpus 只提供配置存储和拉取
- **配置化**: 不同工程师通过配置管理界面创建和管理自己的 Expert
- **版本管理**: 只需管理 Expert 版本，不需要管理提示词版本
- **启动时加载**: 各服务启动时从 keyword-corpus 拉取配置并缓存，运行时不依赖此服务

**主要职责**:
- 📋 **Expert 配置管理**: 存储 Expert 元数据、模板、规则组合、卖点关联
- 📜 **规则片段库**: 存储细粒度的规则（约束、话术、创作规则），可被多个 Expert 复用
- 🏷️ **卖点库**: 存储产品卖点的安全描述，支持根据场景匹配
- 🔑 **关键词库**: 存储品牌关键词、行业术语、热点话题
- 📚 **语料库**: 维护高质量语料库，支持内容生成参考
- 📖 **替换词典**: 存储违禁词和安全替换词的映射关系

**详细设计文档**: 📖 [关键词语料系统设计文档](../docs/KEYWORD_CORPUS_REFACTOR_PLAN.md)

**简化工作流程**:
```
服务启动: GE/AG → keyword-corpus.ListExperts() → GetExpertConfig()
         → 组装完整提示词 → 缓存到内存

运行时: Orchestrator → GE/AG（使用缓存配置）→ LLM 生成

配置更新: 工程师更新配置 → 服务重启 → 重新加载配置
```

#### 2.6 RAAP-Common（公共能力库）

**核心定位**: 基础设施和工具库，为所有服务提供统一的公共能力。

**主要模块**:
- 📝 **统一日志**: 带 Trace ID 的分布式日志，支持全链路追踪
- 🤖 **LLM 工厂**: 统一的模型调用接口，支持一键切换模型
- 🔗 **Dapr 客户端**: 封装服务调用逻辑，统一错误处理
- ⚙️ **配置管理**: 统一的配置和密钥管理
- 📊 **监控工具**: Token 统计、性能监控、成本追踪

### 3. 数据流与工作流

#### 3.1 标准内容生成流程

```
1. [用户请求] 
      ↓
2. [Orchestrator] 解析请求，提取参数
      ↓
3. [并发调用] UM (用户上下文) + KC (关键词/语料)
      ↓
4. [GE] 基于上下文生成内容
      ↓  (GE 内部可能有 LangGraph: 生成 -> 自检 -> 修正)
      ↓
5. [并发调用] AG-BAN (合规检查) + AG-Critic (质量评分)
      ↓
6. [Orchestrator] 聚合结果
      ↓
7. [判断] 
   - 合规 + 高质量 → 返回给用户
   - 不合规 → 拒绝并记录
   - 低质量 → 触发重试（最多 N 次）
      ↓
8. [返回结果] + [更新 UM] (记录用户行为)
```

#### 3.2 服务间调用关系图

```
                 ┌──────────────────────────────┐
                 │   keyword-corpus             │
                 │   (Expert 配置中心)           │
                 │   • Expert 元数据             │
                 │   • 基础模板                  │
                 │   • 规则片段库                │
                 │   • 卖点库                    │
                 │   • 关键词/语料库             │
                 └──────────┬───────────────────┘
                            │ 启动时拉取配置
          ┌─────────────────┼─────────────────┐
          ↓                 ↓                 ↓
    ┌──────────┐      ┌──────────┐     ┌──────────┐
    │    GE    │      │    AG    │     │    UM    │
    │ Experts: │      │ Experts: │     │(用户记忆) │
    │ • gen_1  │      │ • ban_i  │     └──────────┘
    │ • gen_2  │      │ • ban_u  │
    └────┬─────┘      └─────┬────┘
         │                  │
         └────────┬─────────┘
                  ↓ 运行时调用
                    ┌─────────────────┐
                    │   Orchestrator  │ ← 业务请求入口
         │                 │
         │  定义 Workflow:  │
         │  [gen_1,        │
         │   ban_i,        │
         │   ban_u,        │
         │   critic_q]     │
         └─────────────────┘

服务启动流程：
1. GE/AG 启动 → 从 keyword-corpus 拉取 Expert 配置 → 缓存
2. 运行时：Orchestrator → GE/AG（直接调用，使用缓存的配置）

所有服务间通信通过 Dapr gRPC 进行
所有服务共享 raap-common 公共能力库
```

### 4. 高可用性与容错设计

#### 4.1 服务冗余与负载均衡

- **多实例部署**: 关键服务（GE, AG）部署多个副本
- **自动负载均衡**: Dapr 自动进行服务发现和负载分发
- **健康检查**: 定期检查服务健康状态，自动摘除故障实例

#### 4.2 故障隔离与降级

- **熔断机制**: 当下游服务频繁失败时，触发熔断，避免雪崩
- **超时控制**: 为每个服务调用设置合理的超时时间
- **降级策略**: 
  - UM 不可用 → 使用默认用户画像
  - KC 不可用 → 使用缓存的关键词
  - AG 不可用 → 人工审核队列

#### 4.3 重试与补偿

- **智能重试**: 对临时性错误（网络抖动）自动重试，最多 3 次
- **指数退避**: 重试间隔逐步增加，避免服务过载
- **补偿机制**: 对于部分失败的流程，记录状态并支持手动补偿

### 5. 扩展性与灵活性

#### 5.1 水平扩展

- **按需扩展**: 根据负载自动增加服务实例（HPA）
- **独立扩展**: 各服务可根据自身瓶颈独立扩展
  - 高流量场景 → 扩展 GE
  - 审核压力大 → 扩展 AG

#### 5.2 功能扩展

- **插件化设计**: 新增 Agent 类型只需扩展相应服务，不影响其他部分
- **模型可替换**: 通过 raap-common 的 LLM 工厂，轻松切换模型
- **新服务接入**: 通过 Dapr 注册新服务，Orchestrator 即可调用

#### 5.3 版本管理

- **API 版本化**: 通过 `/v1/`, `/v2/` 路径支持多版本并存
- **灰度发布**: 通过流量分配实现新版本的灰度上线
- **向后兼容**: 避免破坏性变更，保证老版本客户端正常工作

### 6. 安全与访问控制

#### 6.1 认证与授权

- **服务认证**: 通过 Dapr 的 mTLS 确保服务间通信安全
- **API 鉴权**: Orchestrator 层实现统一的 API Key / JWT 验证
- **RBAC**: 基于角色的访问控制，不同角色有不同权限

#### 6.2 数据安全

- **数据加密**: 
  - 传输加密: 所有服务间通信使用 TLS
  - 存储加密: 敏感数据（用户行为、API Key）加密存储
- **脱敏处理**: 日志中自动脱敏敏感信息（手机号、身份证等）
- **审计日志**: 记录所有关键操作，支持安全审计和溯源

#### 6.3 防护措施

- **限流控制**: API Gateway 层实现 Rate Limiting
- **请求验证**: 严格的参数校验，防止注入攻击
- **DDoS 防护**: 通过 CDN 和 WAF 防护恶意流量

### 7. 监控与可观测性

#### 7.1 全链路追踪

- **Trace ID**: 每个请求生成唯一 Trace ID，贯穿所有服务
- **链路可视化**: 通过 Jaeger/Zipkin 查看完整调用链
- **性能分析**: 定位慢服务和性能瓶颈

#### 7.2 指标监控

- **业务指标**: 
  - 生成成功率、审核通过率
  - 平均生成时长、P95/P99 延迟
- **系统指标**: CPU、内存、网络、磁盘 I/O
- **成本指标**: Token 消耗、API 调用次数

#### 7.3 告警机制

- **主动告警**: 服务异常、性能下降时自动告警
- **告警分级**: Critical、Warning、Info 三级分类
- **多渠道通知**: 邮件、短信、钉钉/飞书机器人

### 8. 系统优势总结

| 优势维度 | 具体体现 |
|---------|---------|
| **高性能** | 异步并发调用、服务缓存、连接池复用 |
| **高可用** | 多副本部署、健康检查、自动故障转移 |
| **可扩展** | 水平扩展、插件化设计、版本管理 |
| **易维护** | 单一职责、代码复用（raap-common）、标准化接口 |
| **可观测** | 全链路追踪、多维度监控、实时告警 |
| **安全性** | 认证授权、数据加密、审计日志 |

---

## 📦 迁移步骤详解

### 阶段 1: 基础架构准备

#### 1.1 数据库策略
采用**共享数据库**模式，所有服务连接同一个 MySQL 实例，但逻辑上通过表权限隔离。
- `generation-experts`: 读写 `content_library`, 读取 `diversity_report`
- `ag`: 读取 `content_library`, 读写 `badcase`

#### 1.2 Dapr 配置
确保 `values.yaml` 中配置了正确的 `app-id` 和 `app-protocol: grpc`。

### 阶段 2: 服务迁移 (代码实现)

#### 2.1 Generation Experts 服务迁移

**目标**: 将 `ContentGenerateExpert` 逻辑迁移为独立 gRPC 服务。

1.  **定义 Proto**: 在 `proto/generation.proto` 定义生成接口。
2.  **实现 Service**: 创建 `GenerationService` 处理生成逻辑。
3.  **实现 gRPC Server**: 编写 `grpc_server.py` 响应 Dapr 调用。

**代码结构**:
```
raap-service-generation-experts/
├── app/
│   ├── services/
│   │   ├── generation_service.py        # 核心业务逻辑
│   │   └── agents/ge/                   # 原 Agent 代码
│   └── grpc_server.py                   # gRPC 入口
```

#### 2.2 AG (Audit & Grade) 服务迁移

**目标**: 将 BAN 和 Critic Agents 迁移为独立 gRPC 服务。

1.  **定义 Proto**: 在 `proto/ag.proto` 定义 `Check` (BAN) 和 `Evaluate` (Critic) 接口。
2.  **实现 Service**:
    - `BanService`: 路由到对应的 BanExpert (Illegal/Unreasonable/Ineffective)。
    - `CriticService`: 路由到对应的 CriticExpert (Quality/BrandFit/etc)。
3.  **实现 gRPC Server**: 统一处理 BAN 和 Critic 请求。

**代码结构**:
```
raap-service-ag/
├── app/
│   ├── services/
│   │   ├── ban_service.py               # BAN 业务逻辑
│   │   ├── critic_service.py            # Critic 业务逻辑
│   │   └── agents/                      # 原 Agent 代码
│   └── grpc_server.py                   # gRPC 入口
```

#### 2.3 Keywords-Corpus 服务实现

**目标**: 创建 Expert 配置中心，管理所有 Expert 的配置和共享资源。

**详细设计**: 完整的数据库设计、API 定义、服务实现、数据初始化等内容，请查看：

📖 **[关键词语料系统设计文档](../docs/KEYWORD_CORPUS_REFACTOR_PLAN.md)**

**核心要点**：
- 数据库包含 7 张表：experts、expert_configs、rule_fragments、selling_points、keywords、corpus、terminology_dict
- 提供 gRPC API：ListExperts、GetExpertConfig、CreateExpert、UpdateExpert、GetRuleFragments、GetSellingPoints 等
- 支持从 `系统提示词.md` 自动导入规则片段
- 服务启动时一次性加载配置并缓存，运行时不依赖此服务

### 阶段 3: 编排层适配 (Orchestrator)

**架构变更**: 
- **Orchestrator**: 只负责定义 Workflow（Expert 组合）和调度执行，不管理提示词
- **Expert 配置**: 由各服务启动时从 keywords-management 拉取并缓存
- **运行时**: Orchestrator 通过 expert_id 调用对应服务的 Expert

#### 3.1 Orchestrator 实现 (Expert-based Orchestration)

**文件**: `raap-service-orchestrator/app/services/workflow_service.py`

```python
class WorkflowService:
    def __init__(self):
        self.dapr_client = get_dapr_client()
        self.keyword_corpus_client = KeywordCorpusClient()

    async def execute_workflow(self, request):
        """
        执行工作流
        
        Args:
            request: {
                "workflow_key": "xiaohongshu_content_gen",
                "brand_id": 1,
                "params": {
                    "user_persona": "职场妈妈",
                    "problem_type": "成长缓慢",
                    ...
                }
            }
        """
        # 1. 获取 Workflow 配置（定义了 Expert 调用链）
        workflow = await self.get_workflow_config(request.workflow_key)
        # workflow.expert_chain = ["generate_expert_1", "ban_illegal_expert", "ban_unreasonable_expert"]
        
        # 2. 第一步：调用生成 Expert
        gen_result = await self.call_generation_service({
            "expert_id": workflow.expert_chain[0],  # "generate_expert_1"
            "brand_id": request.brand_id,
            "params": request.params
        })
        
        if not gen_result.success:
            return {"status": "failed", "error": gen_result.error}
        
        # 3. 第二步：并发调用审核 Expert
        ban_tasks = [
            self.call_ag_service({
                "expert_id": workflow.expert_chain[1],  # "ban_illegal_expert"
                "content": gen_result.content
            }),
            self.call_ag_service({
                "expert_id": workflow.expert_chain[2],  # "ban_unreasonable_expert"
                "content": gen_result.content
            })
        ]
        ban_results = await asyncio.gather(*ban_tasks)
        
        # 4. 聚合结果并返回
        return {
            "content": gen_result.content,
            "ban_results": ban_results,
            "experts_used": workflow.expert_chain,
            "workflow_version": workflow.version
        }
    
    async def call_generation_service(self, request):
        """调用 GE 服务的指定 Expert"""
        return await self.dapr_client.invoke_method(
            app_id="raap-service-generation-experts",
            method_name="Generate",
            data={
                "expert_id": request["expert_id"],
                "brand_id": request["brand_id"],
                "params": request["params"]
            }
        )
    
    async def call_ag_service(self, request):
        """调用 AG 服务的指定 Expert"""
        return await self.dapr_client.invoke_method(
                app_id="raap-service-ag",
                method_name="Check",
            data={
                "expert_id": request["expert_id"],
                "content": request["content"]
            }
        )
```

#### 3.2 GE/AG 服务启动时加载 Expert 配置

**文件**: `raap-service-generation-experts/app/services/expert_loader.py`

```python
class ExpertLoader:
    """服务启动时从 keyword-corpus 加载 Expert 配置"""
    
    def __init__(self, keyword_corpus_client):
        self.client = keyword_corpus_client
        self.experts_cache = {}
    
    async def load_all_experts(self):
        """加载本服务的所有 Expert（启动时执行一次）"""
        # 1. 获取本服务的所有 Expert
        experts = await self.client.list_experts(service_name="generation")
        
        logger.info(f"Found {len(experts)} experts for service 'generation'")
        
        for expert in experts:
            # 2. 获取每个 Expert 的完整配置
            config = await self.client.get_expert_config(expert.expert_id)
            
            # 3. 组装完整的提示词（仅启动时执行一次）
            assembled_prompt = await self._assemble_prompt(config)
            
            # 4. 缓存到内存
            self.experts_cache[expert.expert_id] = {
                "expert": expert,
                "config": config,
                "system_prompt": assembled_prompt.system_prompt,
                "user_message_template": assembled_prompt.user_message_template,
                "metadata": assembled_prompt.metadata
            }
            
            logger.info(f"✅ Loaded expert: {expert.expert_id} (v{expert.version})")
        
        logger.info(f"✅ Total {len(self.experts_cache)} experts loaded and cached")
    
    async def _assemble_prompt(self, config):
        """组装完整提示词（仅在启动时执行）"""
        # 1. 获取规则片段内容
        rules = await self.client.get_rule_fragments(config.rule_fragments)
        rules_text = "\n\n".join([r.rule_content for r in rules])
        
        # 2. 获取卖点内容
        selling_points = await self.client.get_selling_points(config.selling_points)
        selling_points_text = "\n\n".join([sp.description for sp in selling_points])
        
        # 3. 替换占位符
        system_prompt = config.system_prompt_template.format(
            rules=rules_text,
            selling_points=selling_points_text,
            keywords="{keywords}"  # 运行时动态替换
        )
        
        return AssembledPrompt(
            system_prompt=system_prompt,
            user_message_template=config.user_message_template,
            metadata={"version": config.version}
        )
    
    def get_expert(self, expert_id: str):
        """运行时获取 Expert（从缓存）"""
        expert = self.experts_cache.get(expert_id)
        if not expert:
            raise ValueError(f"Expert {expert_id} not found in cache")
        return expert

# 服务启动时执行
@app.on_event("startup")
async def startup_event():
    keyword_corpus_client = KeywordCorpusClient()
    expert_loader = ExpertLoader(keyword_corpus_client)
    await expert_loader.load_all_experts()
    app.state.expert_loader = expert_loader
```

#### 3.3 Generation Experts 运行时执行

**文件**: `raap-service-generation-experts/app/services/generation_service.py`

运行时使用缓存的 Expert 配置，动态替换占位符后调用 LLM。

```python
class GenerationService:
    def __init__(self, expert_loader, keyword_corpus_client):
        self.expert_loader = expert_loader
        self.keywords_client = keyword_corpus_client
        self.llm_factory = LLMFactory()
    
    async def generate(self, request):
        """
        执行生成任务
        
        Args:
            request: {
                "expert_id": "generate_expert_1",
                "brand_id": 1,
                "params": {
                    "user_persona": "职场妈妈",
                    "problem_type": "成长缓慢",
                    ...
                }
            }
        """
        # 1. 从缓存获取 Expert 配置
        expert = self.expert_loader.get_expert(request.expert_id)
        if not expert:
            raise ValueError(f"Expert {request.expert_id} not found")
        
        # 2. 获取动态数据（关键词）
        keywords = await self.keywords_client.get_keywords(request.brand_id, limit=10)
        keywords_text = "# 品牌关键词\n" + ", ".join([kw.keyword for kw in keywords])
        
        # 3. 替换动态占位符
        system_prompt = expert["system_prompt"].format(keywords=keywords_text)
        user_message = expert["user_message_template"].format(**request.params)
        
        # 4. 调用 LLM 生成
        llm = self.llm_factory.create(model_type="gpt-4")
        result = await llm.ainvoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ])
        
        return {
            "success": True,
            "content": result.content,
            "expert_id": request.expert_id,
            "expert_version": expert["metadata"]["version"],
            "tokens_used": result.usage.total_tokens
        }

# gRPC Server 入口
@app.post("/generate")
async def generate_endpoint(request: GenerateRequest):
    service = GenerationService(
        expert_loader=app.state.expert_loader,
        keyword_corpus_client=app.state.keywords_client
    )
    return await service.generate(request.dict())
```

#### 3.4 （可选）Generation Experts 内部使用 LangGraph

对于需要复杂生成逻辑的 Expert，可以在内部使用 LangGraph 管理 "生成 -> 检查 -> 修正" 循环：

```python
# 这是一个内部的 LangGraph，不对外暴露
workflow = StateGraph(GenerationState)

# 添加节点
workflow.add_node("generate", generate_node)
workflow.add_node("check", check_node)  # 本地检查逻辑
workflow.add_node("refine", refine_node)

# 定义边和循环
workflow.add_edge("generate", "check")
workflow.add_conditional_edges(
    "check",
    should_refine,
    {"refine": "refine", "end": END}
)
workflow.add_edge("refine", "generate")

# 在 GenerationService 中使用
class GenerationService:
    async def generate(self, request):
        expert = self.expert_loader.get_expert(request.expert_id)
        
        # 使用 LangGraph（如果 Expert 配置了复杂流程）
        if expert.get("use_langgraph"):
        app = workflow.compile()
            result = await app.ainvoke({
                "system_prompt": expert["system_prompt"],
                "user_message": user_message
            })
        return result["output"]
        
        # 普通生成（单次调用 LLM）
        return await self.simple_generate(expert, user_message)
```

**架构优势**：
1. **Orchestrator 轻量化**: 只负责 Expert 调度，不管理提示词
2. **服务自治**: 每个服务管理自己的 Expert 和提示词
3. **性能更好**: 启动时加载配置，运行时直接使用缓存
4. **灵活配置**: 通过配置管理界面即可管理 Expert，无需修改代码


### 阶段 4: 公共能力抽离 (raap-common SDK)

#### 4.1 为什么要抽离公共能力？

将公共能力（如日志、LLM 调用、配置加载、Dapr 工具类）抽离是微服务架构中**至关重要**的一步，它能：
- ✅ **避免代码重复**: 每个服务都需要日志、LLM 调用，不应重复实现
- ✅ **保证全链路标准统一**: 统一的日志格式、Trace ID 传递、错误处理
- ✅ **快速切换基础设施**: 当需要从 GPT-4 切换到 Qwen-7B 时，只需修改一处
- ✅ **版本化管理**: 通过 Git Tag 控制基础能力的迭代

**核心原则**: 不建议将这些代码复制粘贴到每个服务中，而是创建一个独立的 Git 仓库，作为依赖库引入。

#### 4.2 raap-common SDK 结构设计

创建独立的 Git 仓库 `raap-common`，作为所有微服务的共享依赖。

**目录结构**:
```
raap-common/
├── setup.py                 # Python 包定义
├── README.md                # 使用文档
├── raap_common/
│   ├── __init__.py
│   ├── logger/              # 1. 统一日志模块
│   │   ├── __init__.py
│   │   ├── core.py          # 日志核心逻辑
│   │   └── handlers.py      # 处理 TraceID 和 JSON 格式
│   ├── llm/                 # 2. 模型调用工厂
│   │   ├── __init__.py
│   │   ├── factory.py       # LangChain/Model 实例工厂
│   │   └── callbacks.py     # 统一 Token 统计与监控回调
│   ├── dapr/                # 3. Dapr 工具类
│   │   ├── __init__.py
│   │   └── client.py        # 封装 DaprClient，增加重试/连接池
│   └── config/              # 4. 统一配置加载
│       ├── __init__.py
│       └── settings.py      # 读取 Env/Dapr Secret
```

#### 4.3 核心模块实现

##### A. 统一日志模块 - **全链路追踪**

在微服务中，日志必须包含 **Trace ID**，否则无法串联 Orchestrator -> Gen -> AG 的请求链路。

**实现方案**:
```python
# raap_common/logger/core.py
import logging
import json
from contextvars import ContextVar

# 用于在异步上下文中存储 trace_id
trace_id_ctx = ContextVar("trace_id", default="-")

class DistributedFormatter(logging.Formatter):
    """分布式日志格式化器，自动注入 Trace ID"""
    def format(self, record):
        log_record = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": os.getenv("SERVICE_NAME", "unknown"),
            "trace_id": trace_id_ctx.get(),  # 自动注入 Trace ID
            "module": record.module,
            "function": record.funcName
        }
        return json.dumps(log_record)

def get_logger(name: str):
    """获取统一配置的 Logger 实例"""
    logger = logging.getLogger(name)
    
    if not logger.handlers:  # 避免重复添加
        handler = logging.StreamHandler()
        handler.setFormatter(DistributedFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    
    return logger

def set_trace_id(trace_id: str):
    """设置当前请求的 Trace ID"""
    trace_id_ctx.set(trace_id)
```

**使用示例**:
```python
from raap_common.logger import get_logger, set_trace_id

logger = get_logger(__name__)

# 在 FastAPI 中间件中提取 Trace ID
@app.middleware("http")
async def trace_middleware(request, call_next):
    # 从 Dapr Header 提取 traceparent
    trace_id = request.headers.get("traceparent", "-")
    set_trace_id(trace_id)
    
    response = await call_next(request)
    return response
```

##### B. LLM 调用工厂 - **统一配置与风控**

不要在每个服务里写 `ChatOpenAI(api_key=...)`。应该通过工厂模式统一管理，便于后续切换模型。

**实现方案**:
```python
# raap_common/llm/factory.py
from langchain_openai import ChatOpenAI
from raap_common.config import settings

class LLMFactory:
    """LLM 实例工厂，统一管理模型配置"""
    
    @staticmethod
    def create(model_type: str = "gpt-4", temperature: float = 0.7):
        """
        统一获取 LLM 实例，自动处理 Key 和 BaseURL
        
        Args:
            model_type: 模型类型 (gpt-4, qwen-7b, etc)
            temperature: 温度参数
        
        Returns:
            ChatOpenAI 实例
        """
        # 1. 统一配置默认参数 (超时、重试)
        common_kwargs = {
            "request_timeout": 60,
            "max_retries": 3,
            "temperature": temperature
        }
        
        # 2. 根据模型类型选择不同配置
        if model_type.startswith("qwen"):
            # 私有化部署模型
            return ChatOpenAI(
                model="qwen2.5-7b",
                openai_api_base="http://vllm-service:8000/v1",
                openai_api_key="EMPTY",
                **common_kwargs
            )
        
        # 3. 使用云端 API (从配置或 Secret 读取)
        api_key = settings.get_secret("openai-key")
        base_url = settings.get("openai-base-url")
        
        return ChatOpenAI(
            model=model_type,
            api_key=api_key,
            base_url=base_url,
            **common_kwargs
        )
```

**核心优势**:
- ✅ **一键切换模型**: 从 GPT-4 切到 Qwen 只需修改一处
- ✅ **统一超时重试**: 避免每个服务单独配置
- ✅ **成本控制**: 可以在工厂层统一添加 Token 计数、限流等逻辑

##### C. Dapr 增强客户端 - **统一调用与错误处理**

封装 gRPC 调用，统一处理异常、序列化、日志记录。

**实现方案**:
```python
# raap_common/dapr/client.py
import json
from typing import Dict, Any
from dapr.clients import DaprClient
from raap_common.logger import get_logger

logger = get_logger(__name__)

class RaapDaprClient:
    """增强版 Dapr 客户端，统一处理序列化和错误"""
    
    def __init__(self):
        self.client = DaprClient()
    
    async def invoke_service(
        self, 
        app_id: str, 
        method: str, 
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        统一的服务调用接口
        
        Args:
            app_id: 目标服务 ID
            method: gRPC 方法名
            data: 请求数据
        
        Returns:
            响应数据 (已反序列化)
        
        Raises:
            Exception: 调用失败时抛出异常
        """
        try:
            # 1. 统一序列化
            req_data = json.dumps(data)
            
            logger.info(f"RPC Call: {app_id}.{method}")
            
            # 2. 统一 gRPC 调用
            resp = await self.client.invoke_method(
                app_id=app_id,
                method_name=method,
                data=req_data,
                content_type="application/json"
            )
            
            # 3. 统一错误处理
            if resp.status_code != 200:
                logger.error(f"RPC Failed: {app_id}.{method}, status={resp.status_code}")
                raise Exception(f"Service {app_id} failed: {resp.text()}")
            
            # 4. 统一反序列化
            return json.loads(resp.data)
            
        except Exception as e:
            # 统一记录 RPC 错误日志
            logger.error(f"RPC Exception: {app_id}.{method} - {str(e)}")
            raise
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.close()
```

##### D. 统一配置加载 - **环境变量 + Dapr Secret**

**实现方案**:
```python
# raap_common/config/settings.py
import os
from typing import Optional

class Settings:
    """统一配置管理，支持环境变量和 Dapr Secret"""
    
    @staticmethod
    def get(key: str, default: Optional[str] = None) -> str:
        """从环境变量读取配置"""
        return os.getenv(key, default)
    
    @staticmethod
    def get_secret(secret_name: str) -> str:
        """
        从 Dapr Secret Store 读取密钥
        TODO: 实现 Dapr Secret API 调用
        """
        # 临时从环境变量读取
        return os.getenv(secret_name.upper().replace("-", "_"))

settings = Settings()
```

#### 4.4 依赖管理与引入

##### 方式一: Git 依赖 (开发阶段推荐)

在每个微服务的 `requirements.txt` 中直接引用 Git 仓库：

```text
# raap-service-orchestrator/requirements.txt
fastapi
dapr
langchain
git+https://github.com/your-org/raap-common.git@v0.1.0#egg=raap-common
```

**优势**: 
- ✅ 快速迭代，不需要发版
- ✅ 可以使用分支或 Tag 控制版本

##### 方式二: 私有 PyPI (生产环境推荐)

如果有 Nexus 或 Artifactory，打包发布后直接安装：

```bash
pip install raap-common==0.1.0
```

#### 4.5 迁移后的服务代码示例

使用 `raap-common` 后，**Generation Service** 代码会变得非常干净：

```python
# raap-service-generation-experts/app/services/generation_service.py
from raap_common.logger import get_logger
from raap_common.llm import LLMFactory
from raap_common.dapr import RaapDaprClient

# 1. 获取统一日志 (自动带 TraceID)
logger = get_logger(__name__)

class GenerationService:
    def __init__(self):
        # 2. 获取统一 LLM (不用管 Key 在哪)
        self.llm = LLMFactory.create(model_type="qwen-7b")
    
    async def generate(self, prompt: str):
        logger.info(f"Start generation for prompt: {prompt[:20]}...")
        
        try:
            result = await self.llm.ainvoke(prompt)
            logger.info("Generation completed successfully")
            return result.content
        except Exception as e:
            logger.error(f"Generation failed: {e}")
            raise
```

**对比原来的代码**:
- ❌ **之前**: 每个服务都要配置日志格式、LLM API Key、Dapr 客户端
- ✅ **现在**: 只需 3 行 import，所有基础能力开箱即用

#### 4.6 实施步骤

1. **创建 raap-common 仓库**
   ```bash
   mkdir raap-common && cd raap-common
   git init
   # 创建上述目录结构和代码
   ```

2. **发布第一个版本**
   ```bash
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. **在各微服务中引入**
   - 修改 `requirements.txt` 添加依赖
   - 重构现有代码，替换为 `raap_common` 的实现

4. **验证效果**
   - 检查日志是否包含统一的 Trace ID
   - 确认 LLM 调用正常工作
   - 测试 Dapr 服务间调用

#### 4.7 长期维护策略

| 场景 | 操作方式 |
|------|----------|
| **日常开发** | 使用最新的 `main` 分支或稳定 Tag |
| **修复 Bug** | 在 `raap-common` 修复，发布新版本，各服务升级依赖 |
| **添加新功能** | 先在 `raap-common` 开发，向后兼容，然后各服务按需使用 |
| **破坏性变更** | 发布新的 Major 版本 (如 v2.0.0)，给各服务预留迁移时间 |

**关键原则**: 
- ✅ **向后兼容**: 避免频繁的 Breaking Changes
- ✅ **语义化版本**: 严格遵循 SemVer (Major.Minor.Patch)
- ✅ **文档先行**: 每次更新都要更新 CHANGELOG 和使用文档

---

### 阶段 5: 部署与验证

#### 5.1 构建与部署
使用统一脚本 `start-k8s.sh` 进行构建和部署：
```bash
./raap-deploy/scripts/start-k8s.sh
```

#### 5.2 验证命令
```bash
# 1. 检查 Pod 状态
kubectl get pods -n raap-dev

# 2. 端口转发 Orchestrator
kubectl port-forward -n raap-dev svc/raap-service-orchestrator 5100:80

# 3. 发送测试请求
curl -X POST http://localhost:5100/api/v1/workflow/execute \
  -H "Content-Type: application/json" \
  -d '{
    "brand_id": 1,
    "activity_id": 100,
    "generation_config": {}
  }'
```

## 📚 常见问题

1.  **gRPC 调用失败**: 检查 Dapr sidecar 日志 (`kubectl logs -c daprd ...`) 和 `app-id` 配置。
2.  **性能问题**: 确保使用了 `DaprClientPool` 复用 gRPC 连接。
3.  **调试**: 使用 `raap-deploy/scripts/verify-dapr-grpc.sh` 进行针对性的 gRPC 连通性测试。
