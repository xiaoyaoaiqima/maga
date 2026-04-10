"""
Agent service - Agent 产品服务
"""
import time
from typing import Optional, List, Tuple

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.agent import Agent
from app.models.tenant import Tenant
from app.services.expert_config_service import ExpertConfigService
from app.schemas.agent import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentFilters,
    AgentSimpleItem,
    AgentListRequest,
    AgentListResponseData,
    AgentCopyRequest,
    AgentTagResponse,
    AgentTagUpdate,
    AgentInfoUpdate,
)
from app.core.logger import logger


class AgentService:
    """Agent 产品服务"""
    
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _agent_name_exists(self, agent_name: str, exclude_code: Optional[str] = None) -> bool:
        conditions = [Agent.agent_name == agent_name]
        if exclude_code:
            conditions.append(Agent.agent_code != exclude_code)
        stmt = select(Agent.id).where(and_(*conditions)).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def _ensure_agent_name_unique(self, agent_name: str, exclude_code: Optional[str] = None) -> None:
        if await self._agent_name_exists(agent_name, exclude_code=exclude_code):
            raise ValueError(f"Agent 名称 '{agent_name}' 已存在")

    async def _build_unique_agent_name(self, base_name: str) -> str:
        timestamp = int(time.time() * 1000)
        suffix = f" 复制 {timestamp}"
        max_length = 255
        trimmed_base = base_name[: max_length - len(suffix)]
        candidate = f"{trimmed_base}{suffix}"
        if not await self._agent_name_exists(candidate):
            return candidate
        for index in range(1, 6):
            suffix = f" 复制{index} {timestamp}"
            trimmed_base = base_name[: max_length - len(suffix)]
            candidate = f"{trimmed_base}{suffix}"
            if not await self._agent_name_exists(candidate):
                return candidate
        suffix = f" 复制 {time.time_ns()}"
        trimmed_base = base_name[: max_length - len(suffix)]
        return f"{trimmed_base}{suffix}"

    async def agent_name_exists(self, agent_name: str, exclude_code: Optional[str] = None) -> bool:
        return await self._agent_name_exists(agent_name, exclude_code=exclude_code)
    
    async def create_agent(self, data: AgentCreate, created_by: Optional[str] = None) -> AgentResponse:
        """
        创建 Agent
        
        Args:
            data: Agent 创建数据
            created_by: 创建人
        
        Returns:
            创建的 Agent
        
        Raises:
            ValueError: Agent 编码已存在 / 租户不存在
        """
        # 检查 Agent 编码是否已存在
        stmt = select(Agent).where(
            and_(
                Agent.agent_code == data.agent_code,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise ValueError(f"Agent 编码 '{data.agent_code}' 已存在")
        
        await self._ensure_agent_name_unique(data.agent_name)

        # 如果指定了租户，检查租户是否存在
        tenant_name = None
        if data.tenant_id:
            tenant_stmt = select(Tenant).where(
                and_(
                    Tenant.id == data.tenant_id,
                    Tenant.is_deleted == 0
                )
            )
            tenant_result = await self.db.execute(tenant_stmt)
            tenant = tenant_result.scalar_one_or_none()
            
            if not tenant:
                raise ValueError(f"租户 ID '{data.tenant_id}' 不存在")
            tenant_name = tenant.tenant_name

        # zero_score_invalid_expert_codes 校验（可选）
        if data.zero_score_invalid_expert_codes is not None:
            expert_list = set(data.expert_config_code_list or [])
            for code in data.zero_score_invalid_expert_codes:
                if code not in expert_list:
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 中包含未在 expert_config_code_list 内的 expert: {code}"
                    )
            # 不允许包含 GENERATION expert
            expert_config_service = ExpertConfigService(self.db)
            for code in data.zero_score_invalid_expert_codes:
                expert_config = await expert_config_service.get_by_code(code)
                if not expert_config:
                    raise ValueError(f"ExpertConfig with code {code} not found")
                if not expert_config.enabled:
                    raise ValueError(f"ExpertConfig with code {code} is not enabled")
                if expert_config.expert_type.upper() == "GENERATION":
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 不允许包含 GENERATION expert: {code}"
                    )
        
        # 创建 Agent
        agent = Agent(
            agent_code=data.agent_code,
            agent_name=data.agent_name,
            agent_type=data.agent_type,
            expert_config_code_list=data.expert_config_code_list,
            zero_score_invalid_expert_codes=data.zero_score_invalid_expert_codes,
            default_model_code=data.default_model_code,
            default_config=data.default_config,
            description=data.description,
            input_schema=data.input_schema,
            output_schema=data.output_schema,
            tenant_id=data.tenant_id,
            rate_limit=data.rate_limit,
            remark=data.remark,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(agent)
        await self.db.commit()
        await self.db.refresh(agent)
        
        logger.info(f"创建 Agent 成功: {agent.agent_code}")
        
        response = AgentResponse.model_validate(agent)
        response.tenant_name = tenant_name
        return response
    
    async def get_agent(self, agent_id: int) -> Optional[AgentResponse]:
        """
        获取 Agent 详情（按 ID）
        
        Args:
            agent_id: Agent ID
        
        Returns:
            Agent 详情，不存在返回 None
        """
        stmt = select(Agent, Tenant.tenant_name).join(
            Tenant, Agent.tenant_id == Tenant.id, isouter=True
        ).where(
            and_(
                Agent.id == agent_id,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        row = result.one_or_none()
        
        if not row:
            return None
        
        agent, tenant_name = row
        response = AgentResponse.model_validate(agent)
        response.tenant_name = tenant_name
        return response
    
    async def get_agent_by_code(self, agent_code: str) -> Optional[AgentResponse]:
        """
        获取 Agent 详情（按编码）
        
        Args:
            agent_code: Agent 编码
        
        Returns:
            Agent 详情，不存在返回 None
        """
        stmt = select(Agent, Tenant.tenant_name).join(
            Tenant, Agent.tenant_id == Tenant.id, isouter=True
        ).where(
            and_(
                Agent.agent_code == agent_code,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        row = result.one_or_none()
        
        if not row:
            return None
        
        agent, tenant_name = row
        response = AgentResponse.model_validate(agent)
        response.tenant_name = tenant_name
        return response
    
    async def list_agents(self, filters: AgentFilters) -> Tuple[int, List[AgentResponse]]:
        """
        获取 Agent 列表
        
        Args:
            filters: 查询过滤条件
        
        Returns:
            (总数, Agent 列表)
        """
        # 构建查询条件
        conditions = [Agent.is_deleted == 0]
        
        if filters.agent_code:
            conditions.append(Agent.agent_code.like(f"%{filters.agent_code}%"))
        if filters.agent_name:
            conditions.append(Agent.agent_name.like(f"%{filters.agent_name}%"))
        if filters.agent_type:
            conditions.append(Agent.agent_type == filters.agent_type)
        if filters.tenant_id is not None:
            # 包含指定租户的 Agent 和全局共享的 Agent
            conditions.append(
                or_(
                    Agent.tenant_id == filters.tenant_id,
                    Agent.tenant_id.is_(None)
                )
            )
        
        # 查询总数
        count_stmt = select(func.count()).select_from(Agent).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 查询列表（包含租户名称和编码）
        stmt = (
            select(Agent, Tenant.tenant_name, Tenant.tenant_code)
            .join(Tenant, Agent.tenant_id == Tenant.id, isouter=True)
            .where(and_(*conditions))
            .order_by(Agent.create_time.desc())
            .offset((filters.page - 1) * filters.page_size)
            .limit(filters.page_size)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        items = []
        for agent, tenant_name, tenant_code in rows:
            response = AgentResponse.model_validate(agent)
            response.tenant_name = tenant_name
            response.tenant_code = tenant_code
            items.append(response)
        
        return total, items
    
    async def update_agent(
        self, 
        agent_code: str, 
        data: AgentUpdate,
        updated_by: Optional[str] = None
    ) -> Optional[AgentResponse]:
        """
        更新 Agent
        
        Args:
            agent_code: Agent 编码
            data: 更新数据
            updated_by: 更新人
        
        Returns:
            更新后的 Agent，不存在返回 None
        """
        stmt = select(Agent).where(
            and_(
                Agent.agent_code == agent_code,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return None

        update_data = data.model_dump(exclude_unset=True)

        # 预计算 merged expert list / zero score list 用于校验
        merged_expert_list = (
            update_data.get("expert_config_code_list")
            if "expert_config_code_list" in update_data
            else (agent.expert_config_code_list or [])
        )
        merged_zero_score_list = (
            update_data.get("zero_score_invalid_expert_codes")
            if "zero_score_invalid_expert_codes" in update_data
            else agent.zero_score_invalid_expert_codes
        )

        # zero_score_invalid_expert_codes 校验（None 表示兼容旧逻辑；[]/list 表示新逻辑）
        if merged_zero_score_list is not None:
            expert_set = set(merged_expert_list or [])
            for code in merged_zero_score_list:
                if code not in expert_set:
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 中包含未在 expert_config_code_list 内的 expert: {code}"
                    )
            expert_config_service = ExpertConfigService(self.db)
            for code in merged_zero_score_list:
                expert_config = await expert_config_service.get_by_code(code)
                if not expert_config:
                    raise ValueError(f"ExpertConfig with code {code} not found")
                if not expert_config.enabled:
                    raise ValueError(f"ExpertConfig with code {code} is not enabled")
                if expert_config.expert_type.upper() == "GENERATION":
                    raise ValueError(
                        f"zero_score_invalid_expert_codes 不允许包含 GENERATION expert: {code}"
                    )
        
        if "agent_name" in update_data and update_data["agent_name"] is not None:
            if update_data["agent_name"] != agent.agent_name:
                await self._ensure_agent_name_unique(update_data["agent_name"], exclude_code=agent_code)

        # 更新字段
        for key, value in update_data.items():
            setattr(agent, key, value)

        # 更新操作者信息（用于界面显示"创建者"）
        agent.updated_by = updated_by
        if updated_by:
            agent.created_by = updated_by

        await self.db.commit()
        await self.db.refresh(agent)
        
        logger.info(f"更新 Agent 成功: {agent.agent_code}")
        
        # 获取租户名称
        tenant_name = None
        if agent.tenant_id:
            tenant_stmt = select(Tenant.tenant_name).where(Tenant.id == agent.tenant_id)
            tenant_result = await self.db.execute(tenant_stmt)
            tenant_name = tenant_result.scalar_one_or_none()
        
        response = AgentResponse.model_validate(agent)
        response.tenant_name = tenant_name
        return response
    
    async def delete_agent(self, agent_code: str, deleted_by: Optional[str] = None) -> bool:
        """
        删除 Agent（软删除）
        
        Args:
            agent_code: Agent 编码
            deleted_by: 删除人
        
        Returns:
            是否删除成功
        """
        stmt = select(Agent).where(
            and_(
                Agent.agent_code == agent_code,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            return False
        
        agent.is_deleted = 1
        agent.updated_by = deleted_by
        
        await self.db.commit()
        
        logger.info(f"删除 Agent 成功: {agent.agent_code}")
        return True
    
    async def list_simple(self, tenant_id: Optional[int] = None) -> List[AgentSimpleItem]:
        """
        获取简单 Agent 列表（用于下拉框）
        
        Args:
            tenant_id: 可选，按租户过滤（会包含全局共享的 Agent）
        
        Returns:
            简单 Agent 列表
        """
        conditions = [
            Agent.is_deleted == 0,
            Agent.enabled == 1,
        ]
        
        if tenant_id is not None:
            # 包含指定租户的 Agent 和全局共享的 Agent
            conditions.append(
                or_(
                    Agent.tenant_id == tenant_id,
                    Agent.tenant_id.is_(None)
                )
            )
        
        stmt = (
            select(Agent)
            .where(and_(*conditions))
            .order_by(Agent.agent_name)
        )
        result = await self.db.execute(stmt)
        agents = result.scalars().all()
        
        return [AgentSimpleItem.model_validate(a) for a in agents]

    async def get_agent_list(self, request: AgentListRequest) -> AgentListResponseData:
        """
        获取 Agent 列表（支持筛选）
        
        Args:
            request: 列表请求参数
            
        Returns:
            AgentListResponseData: Agent 列表响应
        """
        # 构建查询条件
        conditions = [Agent.is_deleted == 0, Agent.publish_status == 'PUBLISHED']
        
        if request.agent_code:
            conditions.append(Agent.agent_code.like(f"%{request.agent_code}%"))
        if request.agent_name:
            conditions.append(Agent.agent_name.like(f"%{request.agent_name}%"))
        if request.agent_type:
            conditions.append(Agent.agent_type == request.agent_type)
        if request.remark:
            conditions.append(Agent.remark.like(f"%{request.remark}%"))
        if request.enabled is not None:
            conditions.append(Agent.enabled == (1 if request.enabled else 0))
        
        # 计算分页参数
        skip = (request.page - 1) * request.page_size
        limit = request.page_size
        
        # 查询总数
        count_stmt = select(func.count()).select_from(Agent).where(and_(*conditions))
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0
        
        # 计算总页数
        total_pages = (total + request.page_size - 1) // request.page_size if total > 0 else 0
        
        # 查询列表（包含租户名称）
        stmt = (
            select(Agent, Tenant.tenant_name)
            .join(Tenant, Agent.tenant_id == Tenant.id, isouter=True)
            .where(and_(*conditions))
            .order_by(Agent.create_time.desc())
            .offset(skip)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = result.all()
        
        items = []
        for agent, tenant_name in rows:
            response = AgentResponse.model_validate(agent)
            response.tenant_name = tenant_name
            items.append(response)
        
        return AgentListResponseData(
            page=request.page,
            page_size=request.page_size,
            total=total,
            total_pages=total_pages,
            items=items
        )

    async def copy_agent(
        self,
        request: AgentCopyRequest,
        created_by: str = "system"
    ) -> AgentResponse:
        """
        复制 Agent（创建新的 Agent）
        
        Args:
            request: 复制请求参数
            created_by: 创建者
            
        Returns:
            AgentResponse: 新创建的 Agent 响应
            
        Raises:
            ValueError: 如果原 Agent 不存在
        """
        # 1. 获取原 Agent
        stmt = select(Agent).where(
            and_(
                Agent.id == request.agent_id,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        original_agent = result.scalar_one_or_none()
        
        if not original_agent:
            raise ValueError(f"Agent 不存在: agent_id={request.agent_id}")
        
        # 2. 生成新的 agent_code（添加时间戳后缀）
        timestamp = int(time.time() * 1000)
        original_agent_code = original_agent.agent_code.split("_copy_")[0]
        new_agent_code = f"{original_agent_code}_copy_{timestamp}"
        new_agent_name = await self._build_unique_agent_name(original_agent.agent_name)
        
        # 3. 创建新的 Agent
        new_agent = Agent(
            agent_code=new_agent_code,
            agent_name=new_agent_name,
            agent_type=original_agent.agent_type,
            expert_config_code_list=original_agent.expert_config_code_list,
            zero_score_invalid_expert_codes=original_agent.zero_score_invalid_expert_codes,
            default_model_code=original_agent.default_model_code,
            default_config=original_agent.default_config,
            description=original_agent.description,
            input_schema=original_agent.input_schema,
            output_schema=original_agent.output_schema,
            tenant_id=original_agent.tenant_id,
            rate_limit=original_agent.rate_limit,
            remark=original_agent.remark,
            tags_config=original_agent.tags_config,
            enabled=original_agent.enabled,
            publish_status=original_agent.publish_status,
            publish_time=original_agent.publish_time,
            publish_by=created_by,
            created_by=created_by,
            updated_by=created_by,
        )
        self.db.add(new_agent)
        await self.db.commit()
        await self.db.refresh(new_agent)
        
        logger.info(f"成功复制 Agent: original_code={original_agent.agent_code}, new_code={new_agent_code}")
        
        # 4. 获取租户名称
        tenant_name = None
        if new_agent.tenant_id:
            tenant_stmt = select(Tenant.tenant_name).where(Tenant.id == new_agent.tenant_id)
            tenant_result = await self.db.execute(tenant_stmt)
            tenant_name = tenant_result.scalar_one_or_none()
        
        response = AgentResponse.model_validate(new_agent)
        response.tenant_name = tenant_name
        return response

    async def get_agent_tags(self, agent_id: int) -> AgentTagResponse:
        """
        获取 Agent 的标签配置（品牌标签、产品标签、活动标签）
        
        Args:
            agent_id: Agent id
            
        Returns:
            AgentTagResponse: 标签响应
            
        Raises:
            ValueError: 如果 Agent 不存在
        """
        stmt = select(Agent).where(
            and_(
                Agent.id == agent_id,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise ValueError(f"Agent 不存在: agent_id={agent_id}")
        
        # 从 tags_config 中提取三个标签列表
        tags_config = agent.tags_config or {}
        return AgentTagResponse(
            brand_tag_list=tags_config.get("brand_tag_list"),
            product_tag_list=tags_config.get("product_tag_list"),
            activity_tag_list=tags_config.get("activity_tag_list")
        )

    async def update_agent_tags(
        self,
        agent_id: int,
        request: AgentTagUpdate,
        updated_by: str = "system"
    ) -> AgentTagResponse:
        """
        更新 Agent 的标签配置（品牌标签、产品标签、活动标签）
        
        Args:
            agent_id: Agent 编码
            request: 标签更新请求
            updated_by: 更新者
            
        Returns:
            AgentTagResponse: 更新后的标签响应
            
        Raises:
            ValueError: 如果 Agent 不存在
        """
        stmt = select(Agent).where(
            and_(
                Agent.id == agent_id,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise ValueError(f"Agent 不存在: agent_id={agent_id}")
        
        # 获取现有的 tags_config 或初始化为空字典
        # 注意：JSON 字段的 dict 原地修改，SQLAlchemy 默认可能无法检测变更
        # 这里强制创建新对象，配合 flag_modified 确保一定会 UPDATE
        tags_config = dict(agent.tags_config or {})
        
        # 更新标签（只更新传入的字段）
        if request.brand_tag_list is not None:
            tags_config["brand_tag_list"] = request.brand_tag_list
        if request.product_tag_list is not None:
            tags_config["product_tag_list"] = request.product_tag_list
        if request.activity_tag_list is not None:
            tags_config["activity_tag_list"] = request.activity_tag_list
        
        agent.tags_config = tags_config

        # 更新操作者信息（用于界面显示"创建者"）
        agent.updated_by = updated_by
        if updated_by:
            agent.created_by = updated_by

        # 显式标记 JSON 字段已修改，确保 SQLAlchemy 检测到变化
        flag_modified(agent, "tags_config")

        await self.db.commit()
        await self.db.refresh(agent)
        
        logger.info(f"更新 Agent 标签成功: agent_id={agent_id}")
        
        return AgentTagResponse(
            brand_tag_list=tags_config.get("brand_tag_list"),
            product_tag_list=tags_config.get("product_tag_list"),
            activity_tag_list=tags_config.get("activity_tag_list")
        )

    async def update_agent_info(
        self,
        agent_id: int,
        request: AgentInfoUpdate,
        updated_by: str = "system"
    ) -> AgentResponse:
        """
        更新 Agent 信息（名称和备注）
        
        Args:
            agent_id: Agent 编码
            request: 更新请求
            updated_by: 更新者
            
        Returns:
            AgentResponse: 更新后的 Agent 响应
            
        Raises:
            ValueError: 如果 Agent 不存在
        """
        stmt = select(Agent).where(
            and_(
                Agent.id == agent_id,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise ValueError(f"Agent 不存在: agent_id={agent_id}")
        
        # 更新字段
        if request.agent_name is not None:
            if request.agent_name != agent.agent_name:
                await self._ensure_agent_name_unique(request.agent_name, exclude_code=agent.agent_code)
            agent.agent_name = request.agent_name
        if request.remark is not None:
            agent.remark = request.remark

        # 更新操作者信息（用于界面显示"创建者"）
        agent.updated_by = updated_by
        if updated_by:
            agent.created_by = updated_by

        await self.db.commit()
        await self.db.refresh(agent)
        
        logger.info(f"更新 Agent 信息成功: agent_id={agent_id}")
        
        # 获取租户名称
        tenant_name = None
        if agent.tenant_id:
            tenant_stmt = select(Tenant.tenant_name).where(Tenant.id == agent.tenant_id)
            tenant_result = await self.db.execute(tenant_stmt)
            tenant_name = tenant_result.scalar_one_or_none()
        
        response = AgentResponse.model_validate(agent)
        response.tenant_name = tenant_name
        return response

    async def soft_delete_agent(self, agent_id: int, deleted_by: str = "system") -> bool:
        """
        删除 Agent（软删除）
        
        Args:
            agent_id: Agent 编码
            deleted_by: 删除人
            
        Returns:
            是否删除成功
            
        Raises:
            ValueError: 如果 Agent 不存在
        """
        stmt = select(Agent).where(
            and_(
                Agent.id == agent_id,
                Agent.is_deleted == 0
            )
        )
        result = await self.db.execute(stmt)
        agent = result.scalar_one_or_none()
        
        if not agent:
            raise ValueError(f"Agent 不存在: agent_id={agent_id}")
        
        agent.is_deleted = 1
        agent.updated_by = deleted_by
        
        await self.db.commit()
        
        logger.info(f"删除 Agent 成功: agent_id={agent_id}")
        return True
