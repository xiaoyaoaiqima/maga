# Langfuse 提示词模板管理方案

## 一、方案概述

### 1.1 背景
当前项目使用文件系统（JSON/YAML）管理提示词模板，存在以下问题：
- 缺乏版本控制和历史追溯
- 无法进行 A/B 测试和效果对比
- 缺少 LLM 调用的可观测性
- 团队协作困难，难以统一管理
- 无法追踪提示词的实际使用效果

### 1.2 Langfuse 优势
Langfuse 是一个开源的 LLM 应用可观测性和提示词管理平台，提供：
- **提示词版本管理**：支持多版本、标签、环境管理
- **A/B 测试**：对比不同提示词版本的效果
- **可观测性**：自动追踪所有 LLM 调用，记录输入输出、延迟、成本等
- **团队协作**：Web UI 界面，支持多人协作编辑
- **成本追踪**：自动计算每次调用的成本
- **评分与反馈**：支持人工评分和自动评分

### 1.3 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                     应用层 (FastAPI Services)                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │ Generation   │  │   Keyword    │  │ Orchestrator │      │
│  │   Experts    │  │    Corpus    │  │   Service    │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                  │               │
└─────────┼─────────────────┼──────────────────┼──────────────┘
          │                 │                  │
          └─────────────────┼──────────────────┘
                            │
          ┌─────────────────▼──────────────────┐
          │     Langfuse Prompt Manager         │
          │  (统一提示词管理抽象层)              │
          └─────────────────┬──────────────────┘
                            │
          ┌─────────────────┼──────────────────┐
          │                 │                  │
    ┌─────▼─────┐   ┌──────▼──────┐   ┌──────▼──────┐
    │ Langfuse  │   │  本地文件    │   │   数据库    │
    │   API     │   │   缓存      │   │   (可选)    │
    └───────────┘   └─────────────┘   └─────────────┘
```

## 二、技术方案

### 2.1 集成方式选择

**方案 A：完全迁移到 Langfuse（推荐）**
- 所有提示词存储在 Langfuse
- 通过 Langfuse SDK 获取提示词
- 自动追踪所有 LLM 调用
- 支持版本管理和 A/B 测试

**方案 B：混合模式（过渡方案）**
- 保留现有文件系统作为备份
- Langfuse 作为主存储
- 支持从文件系统同步到 Langfuse
- 逐步迁移

**方案 C：仅使用 Langfuse 追踪（最小改动）**
- 提示词仍存储在文件系统
- 使用 Langfuse 仅做调用追踪和监控
- 后续逐步迁移提示词管理

**推荐：方案 A（完全迁移）**，如果选择完全迁移，需要了解 Langfuse 的存储机制（见下方"Langfuse 存储机制"章节）。

### 2.2 核心组件设计

#### 2.2.1 LangfusePromptManager

```python
# rs-koc-platform/app/services/prompt/langfuse_prompt_manager.py

from typing import Dict, Any, List, Optional
from langfuse import Langfuse
from langfuse.decorators import langfuse_context, observe
from langfuse.prompt import PromptClient
import os
from app.common.logger import logger
from agent.prompt_manager import PromptManager, PromptTemplate, PromptType, PromptCategory


class LangfusePromptManager:
    """基于 Langfuse 的提示词管理器"""
    
    def __init__(
        self,
        public_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        host: Optional[str] = None,
        enable_tracing: bool = True
    ):
        """
        初始化 Langfuse 客户端
        
        Args:
            public_key: Langfuse Public Key
            secret_key: Langfuse Secret Key
            host: Langfuse Host URL (默认: https://cloud.langfuse.com)
            enable_tracing: 是否启用调用追踪
        """
        self.public_key = public_key or os.getenv("LANGFUSE_PUBLIC_KEY")
        self.secret_key = secret_key or os.getenv("LANGFUSE_SECRET_KEY")
        self.host = host or os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self.enable_tracing = enable_tracing
        
        if not self.public_key or not self.secret_key:
            logger.warning("Langfuse 密钥未配置，将使用本地文件模式")
            self.client = None
            self.prompt_client = None
        else:
            self.client = Langfuse(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host
            )
            self.prompt_client = PromptClient(
                public_key=self.public_key,
                secret_key=self.secret_key,
                host=self.host
            )
        
        # 本地文件管理器作为备份
        self.local_manager = PromptManager()
        
        # 缓存层（可选：使用 Redis）
        self.cache: Dict[str, Any] = {}
    
    async def get_prompt(
        self,
        prompt_name: str,
        version: Optional[int] = None,
        environment: str = "production",
        labels: Optional[List[str]] = None,
        **variables: Any
    ) -> str:
        """
        获取提示词模板并渲染变量
        
        Args:
            prompt_name: 提示词名称（对应 Langfuse 中的 prompt name）
            version: 提示词版本号（可选，默认使用最新版本）
            environment: 环境（production/staging/development）
            labels: 标签列表（用于 A/B 测试）
            **variables: 模板变量
        
        Returns:
            渲染后的提示词内容
        """
        try:
            # 优先从 Langfuse 获取
            if self.prompt_client:
                prompt = self.prompt_client.get_prompt(
                    name=prompt_name,
                    version=version,
                    environment=environment,
                    labels=labels or []
                )
                rendered = prompt.compile(**variables)
                logger.debug(f"从 Langfuse 获取提示词: {prompt_name}")
                return rendered
        except Exception as e:
            logger.warning(f"从 Langfuse 获取提示词失败: {str(e)}，回退到本地文件")
        
        # 回退到本地文件系统
        local_prompt = self.local_manager.get_prompt(prompt_name)
        if local_prompt:
            return self.local_manager.render_prompt(prompt_name, **variables)
        
        raise ValueError(f"提示词不存在: {prompt_name}")
    
    async def create_prompt(
        self,
        name: str,
        prompt: str,
        type: str = "chat",
        config: Optional[Dict[str, Any]] = None,
        labels: Optional[List[str]] = None,
        environment: str = "production"
    ) -> bool:
        """
        创建或更新提示词到 Langfuse
        
        Args:
            name: 提示词名称
            prompt: 提示词内容（支持变量占位符，如 {{variable}}）
            type: 提示词类型（chat/text）
            config: 提示词配置（temperature, max_tokens 等）
            labels: 标签列表
            environment: 环境
        
        Returns:
            是否创建成功
        """
        if not self.prompt_client:
            logger.warning("Langfuse 未配置，仅保存到本地文件")
            return False
        
        try:
            self.prompt_client.create(
                name=name,
                prompt=prompt,
                type=type,
                config=config or {},
                labels=labels or [],
                environment=environment
            )
            logger.info(f"成功创建提示词到 Langfuse: {name}")
            return True
        except Exception as e:
            logger.error(f"创建提示词到 Langfuse 失败: {str(e)}")
            return False
    
    def sync_local_to_langfuse(self, prompt_id: str) -> bool:
        """
        将本地提示词同步到 Langfuse
        
        Args:
            prompt_id: 本地提示词 ID
        
        Returns:
            是否同步成功
        """
        local_prompt = self.local_manager.get_prompt(prompt_id)
        if not local_prompt:
            return False
        
        # 转换本地格式到 Langfuse 格式
        langfuse_prompt = self._convert_to_langfuse_format(local_prompt)
        
        return self.create_prompt(
            name=prompt_id,
            prompt=langfuse_prompt["prompt"],
            type=langfuse_prompt.get("type", "chat"),
            config=langfuse_prompt.get("config", {}),
            labels=local_prompt.tags,
            environment="production"
        )
    
    def _convert_to_langfuse_format(self, prompt: PromptTemplate) -> Dict[str, Any]:
        """将本地 PromptTemplate 转换为 Langfuse 格式"""
        # 构建 Langfuse 提示词内容
        langfuse_content = {
            "messages": []
        }
        
        if prompt.type == PromptType.SYSTEM:
            langfuse_content["messages"].append({
                "role": "system",
                "content": prompt.content
            })
        else:
            langfuse_content["messages"].append({
                "role": "user",
                "content": prompt.content
            })
        
        # 构建配置
        config = self.local_manager.get_prompt_config(prompt.id)
        langfuse_config = {
            "temperature": config.temperature,
            "max_tokens": config.max_tokens,
            "top_p": config.top_p,
            "frequency_penalty": config.frequency_penalty,
            "presence_penalty": config.presence_penalty
        }
        
        return {
            "prompt": langfuse_content,
            "type": "chat",
            "config": langfuse_config
        }
```

#### 2.2.2 LLM 调用追踪装饰器

```python
# rs-koc-platform/app/services/prompt/langfuse_tracing.py

from langfuse.decorators import langfuse_context, observe
from typing import Dict, Any, Optional
from app.common.logger import logger


@observe(as_type="generation")
async def call_llm_with_tracing(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 1500,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs
) -> str:
    """
    带追踪的 LLM 调用
    
    Args:
        system_prompt: 系统提示词
        user_prompt: 用户提示词
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大 token 数
        metadata: 元数据（用于过滤和分析）
        **kwargs: 其他参数
    
    Returns:
        LLM 返回的文本
    """
    # 设置追踪上下文
    langfuse_context.update_current_trace(
        name="llm_call",
        metadata=metadata or {},
        tags=[model, "generation"]
    )
    
    # 记录输入
    langfuse_context.update_current_observation(
        input={
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
    )
    
    try:
        # 调用实际的 LLM API（使用现有的 AIModelService）
        from app.services.ai_model_service import AIModelService
        
        result = await AIModelService.call_ai_model_with_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            ai_model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
        
        # 记录输出
        langfuse_context.update_current_observation(
            output=result,
            metadata={
                "model": model,
                "temperature": temperature
            }
        )
        
        return result
        
    except Exception as e:
        # 记录错误
        langfuse_context.update_current_observation(
            level="ERROR",
            status_message=str(e)
        )
        logger.error(f"LLM 调用失败: {str(e)}")
        raise
```

#### 2.2.3 集成到现有服务

```python
# rs-koc-platform/app/services/aigc/llm_factory.py (修改)

from app.services.prompt.langfuse_prompt_manager import LangfusePromptManager
from app.services.prompt.langfuse_tracing import call_llm_with_tracing

# 全局 Langfuse 管理器实例
langfuse_prompt_manager = LangfusePromptManager()

class LLMFactory:
    """LangChain多模型工厂（集成 Langfuse）"""
    
    @staticmethod
    async def call_llm(
        config: Dict[str, Any],
        system_prompt: str,
        user_prompt: str,
        prompt_name: Optional[str] = None,  # 新增：提示词名称
        metadata: Optional[Dict[str, Any]] = None  # 新增：元数据
    ) -> str:
        """
        调用LLM模型（带 Langfuse 追踪）
        
        Args:
            config: LLM配置
            system_prompt: 系统提示词（如果 prompt_name 提供，将从 Langfuse 获取）
            user_prompt: 用户提示词
            prompt_name: 提示词名称（可选，如果提供则从 Langfuse 获取）
            metadata: 元数据（用于追踪和分析）
        
        Returns:
            LLM返回的文本
        """
        llm_config = LLMFactory.get_llm_config(config)
        
        # 如果提供了 prompt_name，从 Langfuse 获取提示词
        if prompt_name:
            try:
                # 从 Langfuse 获取系统提示词
                system_prompt = await langfuse_prompt_manager.get_prompt(
                    prompt_name=prompt_name,
                    environment="production",
                    **metadata or {}
                )
            except Exception as e:
                logger.warning(f"从 Langfuse 获取提示词失败: {str(e)}，使用传入的 system_prompt")
        
        # 使用带追踪的调用
        return await call_llm_with_tracing(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=llm_config["model"],
            temperature=llm_config["temperature"],
            max_tokens=llm_config.get("max_tokens", 1500),
            metadata={
                "prompt_name": prompt_name,
                "provider": llm_config["provider"],
                **(metadata or {})
            }
        )
```

## 三、Langfuse 存储机制详解

### 3.1 存储位置

Langfuse 的提示词存储位置取决于部署方式：

#### 3.1.1 Langfuse Cloud（托管服务）

如果使用 Langfuse Cloud（https://cloud.langfuse.com）：
- **存储位置**：提示词存储在 Langfuse 的托管 PostgreSQL 数据库中
- **数据位置**：数据托管在 Langfuse 的云服务器上（AWS/GCP）
- **访问方式**：通过 REST API 和 SDK 访问，无法直接访问数据库
- **数据安全**：数据加密存储，符合 GDPR 标准
- **备份**：Langfuse 负责自动备份和灾难恢复

**优点**：
- 无需维护基础设施
- 自动备份和更新
- 开箱即用

**缺点**：
- 数据存储在第三方服务器
- 需要网络连接
- 可能有数据合规性考虑

#### 3.1.2 自托管 Langfuse（推荐用于生产环境）

如果自托管 Langfuse：
- **存储位置**：提示词存储在**你自己的 PostgreSQL 数据库**中
- **数据库要求**：PostgreSQL 12+（Langfuse 不支持 MySQL）
- **数据控制**：完全控制数据存储位置和访问权限
- **部署方式**：Docker Compose 或 Kubernetes

**数据库表结构**（Langfuse 自动创建）：

```sql
-- 核心表（简化版，实际表结构更复杂）
CREATE TABLE prompts (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    prompt TEXT NOT NULL,  -- JSON 格式存储提示词内容
    type VARCHAR(50),       -- 'chat' 或 'text'
    config JSONB,          -- 模型配置（temperature, max_tokens 等）
    labels TEXT[],         -- 标签数组
    environment VARCHAR(50), -- 'production', 'staging', 'development'
    version INTEGER,       -- 版本号
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    project_id VARCHAR(255),
    UNIQUE(name, version, environment)
);

CREATE TABLE prompt_versions (
    id VARCHAR(255) PRIMARY KEY,
    prompt_id VARCHAR(255) REFERENCES prompts(id),
    version INTEGER,
    prompt TEXT,
    config JSONB,
    labels TEXT[],
    created_at TIMESTAMP
);

-- LLM 调用追踪表
CREATE TABLE traces (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    metadata JSONB,
    created_at TIMESTAMP,
    project_id VARCHAR(255)
);

CREATE TABLE observations (
    id VARCHAR(255) PRIMARY KEY,
    trace_id VARCHAR(255) REFERENCES traces(id),
    type VARCHAR(50),  -- 'GENERATION', 'SPAN', 'EVENT'
    name VARCHAR(255),
    input JSONB,
    output JSONB,
    metadata JSONB,
    model VARCHAR(255),
    usage JSONB,  -- token 使用量
    cost DECIMAL(10, 6),
    latency_ms INTEGER,
    created_at TIMESTAMP
);
```

### 3.2 与现有 MySQL 数据库的关系

**重要说明**：
- Langfuse **必须使用 PostgreSQL**，不支持 MySQL
- 如果项目使用 MySQL，有两种选择：

**选择 1：独立 PostgreSQL 数据库（推荐）**
```
┌─────────────────────────────────────┐
│    你的应用服务 (FastAPI)            │
│  ┌──────────────┐  ┌──────────────┐ │
│  │  MySQL       │  │  PostgreSQL  │ │
│  │  (业务数据)  │  │  (Langfuse)  │ │
│  └──────────────┘  └──────────────┘ │
└─────────────────────────────────────┘
```
- MySQL：存储业务数据（用户、订单、内容等）
- PostgreSQL：仅用于 Langfuse（提示词和追踪数据）
- 两个数据库完全独立，互不影响

**选择 2：迁移到 PostgreSQL（如果业务允许）**
- 将整个项目迁移到 PostgreSQL
- 使用单一数据库存储所有数据
- 需要数据迁移工作

### 3.3 数据持久化

#### 3.3.1 自托管部署的数据持久化

```yaml
# docker-compose.langfuse.yml
version: '3.8'
services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse@postgres:5432/langfuse
      - NEXTAUTH_SECRET=your-secret
      - NEXTAUTH_URL=http://localhost:3000
    depends_on:
      - postgres
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse
      - POSTGRES_DB=langfuse
    volumes:
      # 数据持久化到本地卷
      - langfuse-postgres-data:/var/lib/postgresql/data
    # 或者挂载到主机目录
    # volumes:
    #   - ./langfuse-data:/var/lib/postgresql/data

volumes:
  langfuse-postgres-data:
    driver: local
```

#### 3.3.2 Kubernetes 部署的数据持久化

```yaml
# helm/raap/templates/langfuse-postgresql.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: langfuse-postgresql
  namespace: {{ .Values.global.namespace }}
spec:
  serviceName: langfuse-postgresql
  replicas: 1
  selector:
    matchLabels:
      app: langfuse-postgresql
  template:
    metadata:
      labels:
        app: langfuse-postgresql
    spec:
      containers:
      - name: postgresql
        image: postgres:15
        env:
        - name: POSTGRES_USER
          value: langfuse
        - name: POSTGRES_PASSWORD
          valueFrom:
            secretKeyRef:
              name: langfuse-secret
              key: postgres-password
        - name: POSTGRES_DB
          value: langfuse
        volumeMounts:
        - name: langfuse-postgres-data
          mountPath: /var/lib/postgresql/data
  volumeClaimTemplates:
  - metadata:
      name: langfuse-postgres-data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: standard
      resources:
        requests:
          storage: 50Gi  # 根据数据量调整
```

### 3.4 数据备份策略

#### 3.4.1 自托管备份

```bash
# 备份脚本：backup-langfuse.sh
#!/bin/bash
BACKUP_DIR="/backup/langfuse"
DATE=$(date +%Y%m%d_%H%M%S)
PGPASSWORD=langfuse_password pg_dump -h localhost -U langfuse -d langfuse > "$BACKUP_DIR/langfuse_$DATE.sql"

# 保留最近 30 天的备份
find $BACKUP_DIR -name "langfuse_*.sql" -mtime +30 -delete
```

#### 3.4.2 定期备份（Cron）

```bash
# 添加到 crontab
0 2 * * * /path/to/backup-langfuse.sh
```

### 3.5 数据访问方式

#### 3.5.1 通过 Langfuse API（推荐）

```python
from langfuse import Langfuse
from langfuse.prompt import PromptClient

# 初始化客户端
langfuse = Langfuse(
    public_key="pk-lf-xxx",
    secret_key="sk-lf-xxx",
    host="https://cloud.langfuse.com"  # 或自托管地址
)

# 获取提示词（从 PostgreSQL 读取）
prompt_client = PromptClient(
    public_key="pk-lf-xxx",
    secret_key="sk-lf-xxx",
    host="https://cloud.langfuse.com"
)

prompt = prompt_client.get_prompt(
    name="content_generation_system",
    version=1
)
```

#### 3.5.2 直接访问 PostgreSQL（仅自托管）

```python
import psycopg2
import os

# 连接 PostgreSQL
conn = psycopg2.connect(
    host="localhost",
    database="langfuse",
    user="langfuse",
    password="langfuse_password"
)

cursor = conn.cursor()

# 查询提示词
cursor.execute("""
    SELECT name, prompt, version, labels, environment
    FROM prompts
    WHERE name = %s AND environment = %s
    ORDER BY version DESC
    LIMIT 1
""", ("content_generation_system", "production"))

row = cursor.fetchone()
# row[1] 包含 JSON 格式的提示词内容

cursor.close()
conn.close()
```

**注意**：直接访问数据库不推荐，应该通过 Langfuse API 访问。

### 3.6 数据迁移路径

```
当前状态：文件系统（JSON/YAML）
    ↓
迁移脚本：同步到 Langfuse
    ↓
Langfuse Cloud：托管 PostgreSQL
    OR
自托管 Langfuse：你的 PostgreSQL
    ↓
完全迁移：删除本地文件（可选）
```

### 3.7 存储成本估算

**Langfuse Cloud**：
- 免费版：有限存储
- 付费版：按使用量计费

**自托管 PostgreSQL**：
- 提示词数据：通常很小（< 100MB，除非有大量版本）
- LLM 调用追踪：取决于调用量
  - 每次调用约 1-5KB（输入输出、元数据）
  - 100万次调用 ≈ 1-5GB
- 建议初始存储：10-50GB
- 可根据数据增长扩展

## 四、实施步骤

### 4.1 环境准备

#### 4.1.1 安装依赖

```bash
# 在 rs-koc-platform/requirements.txt 中添加
langfuse>=2.0.0
```

#### 4.1.2 配置环境变量

```bash
# .env 文件或环境变量
LANGFUSE_PUBLIC_KEY=pk-lf-xxx
LANGFUSE_SECRET_KEY=sk-lf-xxx
LANGFUSE_HOST=https://cloud.langfuse.com  # 或自托管地址
LANGFUSE_ENABLE_TRACING=true
```

#### 4.1.3 选择部署方式

**选项 1：使用 Langfuse Cloud（推荐用于快速开始）**
- 注册账号：https://cloud.langfuse.com
- 创建项目，获取 API Keys
- 无需维护基础设施
- **提示词存储在 Langfuse 的托管 PostgreSQL 中**

**选项 2：自托管 Langfuse（推荐用于生产环境）**
- 使用 Docker Compose 或 Kubernetes 部署
- 需要 PostgreSQL 数据库（**必须单独部署，不能使用现有 MySQL**）
- 完全控制数据存储位置
- 适合数据敏感场景

**Docker Compose 部署示例**：

```yaml
# docker-compose.langfuse.yml
version: '3.8'
services:
  langfuse:
    image: langfuse/langfuse:latest
    ports:
      - "3000:3000"
    environment:
      - DATABASE_URL=postgresql://langfuse:langfuse@postgres:5432/langfuse
      - NEXTAUTH_SECRET=your-secret-key-change-in-production
      - NEXTAUTH_URL=http://localhost:3000
      - SALT=your-salt-key
    depends_on:
      - postgres
    restart: unless-stopped
  
  postgres:
    image: postgres:15
    environment:
      - POSTGRES_USER=langfuse
      - POSTGRES_PASSWORD=langfuse
      - POSTGRES_DB=langfuse
    volumes:
      - langfuse-postgres-data:/var/lib/postgresql/data
    restart: unless-stopped
    ports:
      - "5432:5432"  # 可选：用于外部访问

volumes:
  langfuse-postgres-data:
    driver: local
```

**Kubernetes 部署示例**（集成到现有 Helm Chart）：

```yaml
# raap-deploy/helm/raap/templates/langfuse.yaml
{{- if .Values.langfuse.enabled }}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: langfuse
  namespace: {{ .Values.global.namespace }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: langfuse
  template:
    metadata:
      labels:
        app: langfuse
    spec:
      containers:
      - name: langfuse
        image: langfuse/langfuse:latest
        ports:
        - containerPort: 3000
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: langfuse-secret
              key: database-url
        - name: NEXTAUTH_SECRET
          valueFrom:
            secretKeyRef:
              name: langfuse-secret
              key: nextauth-secret
        - name: NEXTAUTH_URL
          value: "http://langfuse.{{ .Values.global.namespace }}.svc.cluster.local:3000"
        resources:
          requests:
            memory: "512Mi"
            cpu: "250m"
          limits:
            memory: "1Gi"
            cpu: "500m"
---
apiVersion: v1
kind: Service
metadata:
  name: langfuse
  namespace: {{ .Values.global.namespace }}
spec:
  selector:
    app: langfuse
  ports:
  - port: 3000
    targetPort: 3000
{{- end }}
```

### 4.2 数据迁移

#### 4.2.1 迁移脚本

```python
# rs-koc-platform/scripts/migrate_prompts_to_langfuse.py

"""
将本地提示词迁移到 Langfuse
"""
import asyncio
from app.services.prompt.langfuse_prompt_manager import LangfusePromptManager
from agent.prompt_manager import prompt_manager
from app.common.logger import logger


async def migrate_all_prompts():
    """迁移所有本地提示词到 Langfuse"""
    langfuse_manager = LangfusePromptManager()
    
    migrated_count = 0
    failed_count = 0
    
    for prompt_id, prompt in prompt_manager.prompts.items():
        try:
            success = langfuse_manager.sync_local_to_langfuse(prompt_id)
            if success:
                migrated_count += 1
                logger.info(f"✓ 迁移成功: {prompt_id}")
            else:
                failed_count += 1
                logger.warning(f"✗ 迁移失败: {prompt_id}")
        except Exception as e:
            failed_count += 1
            logger.error(f"✗ 迁移异常 {prompt_id}: {str(e)}")
    
    logger.info(f"迁移完成: 成功 {migrated_count}, 失败 {failed_count}")


if __name__ == "__main__":
    asyncio.run(migrate_all_prompts())
```

#### 4.2.2 执行迁移

```bash
cd rs-koc-platform
python scripts/migrate_prompts_to_langfuse.py
```

### 4.3 代码集成

#### 4.3.1 修改现有 Agent 调用

```python
# 示例：修改 BaseAgent.call_llm 方法
# rs-koc-platform/app/models/aigc/agents/base.py

async def call_llm(self, system_prompt: str, user_prompt: str) -> str:
    """
    调用LLM模型（集成 Langfuse）
    """
    from app.services.aigc.llm_factory import LLMFactory
    
    # 使用 prompt_id 作为 prompt_name（如果配置了）
    prompt_name = getattr(self.config, 'prompt_name', None)
    metadata = {
        "agent_id": self.config.get("id"),
        "agent_type": self.__class__.__name__,
        "category": self.config.get("category")
    }
    
    return await LLMFactory.call_llm(
        config=self.config,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        prompt_name=prompt_name,  # 新增
        metadata=metadata  # 新增
    )
```

### 4.4 测试验证

#### 4.4.1 单元测试

```python
# rs-koc-platform/test/test_langfuse_prompt_manager.py

import pytest
from app.services.prompt.langfuse_prompt_manager import LangfusePromptManager


@pytest.mark.asyncio
async def test_get_prompt_from_langfuse():
    """测试从 Langfuse 获取提示词"""
    manager = LangfusePromptManager()
    
    # 假设已创建名为 "test_prompt" 的提示词
    prompt = await manager.get_prompt(
        prompt_name="test_prompt",
        variable1="value1",
        variable2="value2"
    )
    
    assert prompt is not None
    assert "value1" in prompt
    assert "value2" in prompt


@pytest.mark.asyncio
async def test_fallback_to_local():
    """测试回退到本地文件"""
    manager = LangfusePromptManager(
        public_key=None,  # 模拟未配置
        secret_key=None
    )
    
    # 应该回退到本地文件
    prompt = await manager.get_prompt(
        prompt_name="unreasonable_review_system",
        content="test content"
    )
    
    assert prompt is not None
```

## 五、使用场景

### 5.1 提示词版本管理

```python
# 创建新版本的提示词
await langfuse_prompt_manager.create_prompt(
    name="content_generation_system",
    prompt="你是一位专业的内容创作者...",
    labels=["v2.0", "improved"],
    environment="production"
)

# 获取特定版本
prompt_v1 = await langfuse_prompt_manager.get_prompt(
    prompt_name="content_generation_system",
    version=1
)

prompt_v2 = await langfuse_prompt_manager.get_prompt(
    prompt_name="content_generation_system",
    version=2
)
```

### 5.2 A/B 测试

```python
# 在 Langfuse UI 中创建两个版本的提示词，分别打上标签 "variant_a" 和 "variant_b"

# 随机选择版本进行测试
import random

variant = random.choice(["variant_a", "variant_b"])
prompt = await langfuse_prompt_manager.get_prompt(
    prompt_name="content_generation_system",
    labels=[variant]
)

# Langfuse 会自动追踪不同版本的效果，可在 UI 中对比
```

### 5.3 环境隔离

```python
# 开发环境
dev_prompt = await langfuse_prompt_manager.get_prompt(
    prompt_name="content_generation_system",
    environment="development"
)

# 生产环境
prod_prompt = await langfuse_prompt_manager.get_prompt(
    prompt_name="content_generation_system",
    environment="production"
)
```

### 5.4 成本追踪

Langfuse 会自动追踪每次调用的：
- Token 使用量（输入/输出）
- 成本（基于模型定价）
- 延迟
- 错误率

可在 Langfuse UI 中查看：
- 每日/每周/每月的成本趋势
- 不同提示词版本的成本对比
- 模型使用分布

## 六、最佳实践

### 6.1 提示词命名规范

```
格式：{service}_{category}_{type}_{version}

示例：
- generation_experts_system_v1
- keyword_corpus_user_v2
- orchestrator_review_system_v1
```

### 6.2 标签使用

- **版本标签**：`v1.0`, `v2.0`, `v2.1`
- **环境标签**：`prod`, `staging`, `dev`
- **测试标签**：`ab_test_a`, `ab_test_b`
- **功能标签**：`content_gen`, `review`, `modification`

### 6.3 元数据规范

```python
metadata = {
    "service": "generation-experts",
    "agent_id": "agent_123",
    "user_id": "user_456",
    "request_id": "req_789",
    "category": "content_generation"
}
```

### 6.4 错误处理

```python
try:
    prompt = await langfuse_prompt_manager.get_prompt(
        prompt_name="content_generation_system"
    )
except ValueError as e:
    # 提示词不存在，使用默认提示词
    logger.warning(f"提示词不存在，使用默认: {str(e)}")
    prompt = default_system_prompt
except Exception as e:
    # 其他错误，回退到本地文件
    logger.error(f"获取提示词失败: {str(e)}")
    prompt = local_manager.render_prompt("content_generation_system")
```

## 七、监控与运维

### 7.1 关键指标

在 Langfuse UI 中监控：
- **提示词使用频率**：哪些提示词使用最多
- **平均延迟**：识别性能瓶颈
- **错误率**：及时发现异常
- **成本趋势**：控制成本
- **A/B 测试效果**：对比不同版本

### 7.2 告警设置

建议设置告警：
- 错误率 > 5%
- 平均延迟 > 10s
- 单日成本超过阈值
- 提示词调用失败

### 7.3 定期审查

- **每周**：审查成本和使用情况
- **每月**：分析 A/B 测试结果，决定是否推广新版本
- **每季度**：清理不再使用的提示词版本

## 八、迁移计划

### 阶段 1：准备阶段（1-2 周）
- [ ] 安装 Langfuse（Cloud 或自托管）
- [ ] 配置环境变量
- [ ] 开发 LangfusePromptManager
- [ ] 编写迁移脚本

### 阶段 2：试点阶段（2-3 周）
- [ ] 选择 2-3 个核心提示词进行迁移
- [ ] 在测试环境验证
- [ ] 收集反馈，优化方案

### 阶段 3：全面迁移（3-4 周）
- [ ] 迁移所有提示词到 Langfuse
- [ ] 更新所有服务代码
- [ ] 启用调用追踪
- [ ] 保留本地文件作为备份

### 阶段 4：优化阶段（持续）
- [ ] 基于数据优化提示词
- [ ] 进行 A/B 测试
- [ ] 建立监控和告警
- [ ] 团队培训

## 九、注意事项

### 9.1 数据库选择

**重要**：Langfuse 必须使用 PostgreSQL，不支持 MySQL。

如果你的项目使用 MySQL：
1. **推荐方案**：部署独立的 PostgreSQL 数据库专门用于 Langfuse
   - MySQL：继续用于业务数据
   - PostgreSQL：仅用于 Langfuse（提示词和追踪数据）
   - 两个数据库完全独立，互不影响

2. **备选方案**：如果业务允许，可以考虑将整个项目迁移到 PostgreSQL
   - 需要数据迁移工作
   - 需要评估迁移成本和风险

1. **数据安全**：
   - 如果使用 Langfuse Cloud，确保不传输敏感数据；或使用自托管版本
   - 自托管时，数据存储在你自己控制的 PostgreSQL 数据库中
   - 建议启用数据库加密和访问控制

2. **数据库要求**：
   - Langfuse **必须使用 PostgreSQL**（12+），不支持 MySQL
   - 如果项目使用 MySQL，需要部署独立的 PostgreSQL 实例
   - 两个数据库可以共存，互不影响

3. **性能影响**：
   - 追踪会增加少量延迟（通常 < 50ms），可在非关键路径禁用
   - 提示词获取通过 API，有网络延迟（本地部署可忽略）

4. **成本控制**：
   - Langfuse Cloud：有免费额度，超出后按使用量收费
   - 自托管：主要是 PostgreSQL 存储成本（通常很小）

5. **数据持久化**：
   - 自托管时，确保 PostgreSQL 数据卷正确配置
   - 建议定期备份数据库
   - 可以使用 Kubernetes PersistentVolume 或 Docker Volume

6. **回滚方案**：
   - 完全迁移前，保留本地文件系统作为备份
   - 支持快速回滚到文件系统模式

7. **团队协作**：
   - 建立提示词修改的审批流程
   - 避免直接在生产环境修改
   - 使用环境隔离（development/staging/production）

## 十、参考资源

- [Langfuse 官方文档](https://langfuse.com/docs)
- [Langfuse Python SDK](https://github.com/langfuse/langfuse-python)
- [Langfuse 自托管指南](https://langfuse.com/docs/deployment/self-host)
- [提示词工程最佳实践](https://langfuse.com/docs/prompts)

---

**最后更新**：2025-01-XX
**维护者**：开发团队
