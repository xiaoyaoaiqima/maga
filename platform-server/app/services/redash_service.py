"""
Redash 服务层
提供 Redash API 的封装，用于统一数据查询
"""
import json
import asyncio
from typing import Any, Dict, List, Optional
from datetime import datetime
import httpx
from pydantic import BaseModel

from app.core.config import settings
from app.core.logger import logger


class RedashQueryResult(BaseModel):
    """Redash 查询结果"""
    query_id: int
    query_name: str
    data: List[Dict[str, Any]]
    columns: List[Dict[str, str]]
    rows_count: int
    retrieved_at: str


class RedashQuery(BaseModel):
    """Redash 查询定义"""
    id: int
    name: str
    query: str
    data_source_id: int
    description: Optional[str] = None
    is_archived: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class RedashDataSource(BaseModel):
    """Redash 数据源"""
    id: int
    name: str
    type: str
    options: Optional[Dict[str, Any]] = None


class RedashServiceError(Exception):
    """Redash 服务异常"""
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class RedashService:
    """
    Redash 服务类
    提供 Redash API 的完整封装
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 30,
    ):
        self.base_url = (base_url or settings.REDASH_BASE_URL).rstrip('/')
        self.api_key = api_key or settings.REDASH_API_KEY
        self.timeout = timeout or settings.REDASH_REQUEST_TIMEOUT
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def headers(self) -> Dict[str, str]:
        """获取请求头"""
        return {
            'Authorization': f'Key {self.api_key}',
            'Content-Type': 'application/json',
        }

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self.headers,
                timeout=self.timeout,
            )
        return self._client

    async def close(self):
        """关闭客户端连接"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """发送 API 请求"""
        client = await self._get_client()
        try:
            response = await client.request(
                method=method,
                url=endpoint,
                json=json_data,
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Redash API 错误: {e.response.status_code} - {e.response.text}")
            raise RedashServiceError(
                f"Redash API 请求失败: {e.response.text}",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            logger.error(f"Redash 请求异常: {e}")
            raise RedashServiceError(f"Redash 连接失败: {str(e)}")

    # ==================== 数据源管理 ====================

    async def list_data_sources(self) -> List[RedashDataSource]:
        """获取所有数据源"""
        data = await self._request('GET', '/api/data_sources')
        return [RedashDataSource(**ds) for ds in data]

    async def get_data_source(self, data_source_id: int) -> RedashDataSource:
        """获取单个数据源"""
        data = await self._request('GET', f'/api/data_sources/{data_source_id}')
        return RedashDataSource(**data)

    async def create_data_source(
        self,
        name: str,
        ds_type: str,
        options: Dict[str, Any],
    ) -> RedashDataSource:
        """创建数据源"""
        payload = {
            'name': name,
            'type': ds_type,
            'options': options,
        }
        data = await self._request('POST', '/api/data_sources', json_data=payload)
        return RedashDataSource(**data)

    # ==================== 查询管理 ====================

    async def list_queries(
        self,
        page: int = 1,
        page_size: int = 25,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取查询列表"""
        params = {'page': page, 'page_size': page_size}
        if search:
            params['q'] = search
        return await self._request('GET', '/api/queries', params=params)

    async def get_query(self, query_id: int) -> RedashQuery:
        """获取单个查询"""
        data = await self._request('GET', f'/api/queries/{query_id}')
        return RedashQuery(**data)

    async def create_query(
        self,
        name: str,
        query: str,
        data_source_id: int,
        description: str = '',
        options: Optional[Dict] = None,
    ) -> RedashQuery:
        """创建查询"""
        payload = {
            'name': name,
            'query': query,
            'data_source_id': data_source_id,
            'description': description,
            'options': options or {},
        }
        data = await self._request('POST', '/api/queries', json_data=payload)
        logger.info(f"创建 Redash 查询: {name} (ID: {data.get('id')})")
        return RedashQuery(**data)

    async def update_query(
        self,
        query_id: int,
        name: Optional[str] = None,
        query: Optional[str] = None,
        description: Optional[str] = None,
    ) -> RedashQuery:
        """更新查询"""
        payload = {}
        if name:
            payload['name'] = name
        if query:
            payload['query'] = query
        if description is not None:
            payload['description'] = description

        data = await self._request('POST', f'/api/queries/{query_id}', json_data=payload)
        logger.info(f"更新 Redash 查询: {query_id}")
        return RedashQuery(**data)

    async def archive_query(self, query_id: int) -> None:
        """归档（删除）查询"""
        await self._request('DELETE', f'/api/queries/{query_id}')
        logger.info(f"归档 Redash 查询: {query_id}")

    # ==================== 查询执行 ====================

    async def get_query_results(
        self,
        query_id: int,
        use_cache: bool = True,
    ) -> RedashQueryResult:
        """获取查询结果（使用缓存）"""
        data = await self._request('GET', f'/api/queries/{query_id}/results.json')
        query_result = data.get('query_result', {})
        query_data = query_result.get('data', {})

        return RedashQueryResult(
            query_id=query_id,
            query_name=data.get('query', {}).get('name', ''),
            data=query_data.get('rows', []),
            columns=query_data.get('columns', []),
            rows_count=len(query_data.get('rows', [])),
            retrieved_at=query_result.get('retrieved_at', ''),
        )

    async def execute_query(
        self,
        query_id: int,
        parameters: Optional[Dict[str, Any]] = None,
        max_age: int = 0,
    ) -> RedashQueryResult:
        """
        执行查询（支持参数化）
        
        Args:
            query_id: 查询 ID
            parameters: 查询参数
            max_age: 缓存最大年龄（秒），0 表示不使用缓存
            
        Returns:
            查询结果
        """
        payload = {
            'max_age': max_age,
        }
        if parameters:
            payload['parameters'] = parameters

        # 发起查询执行
        response = await self._request(
            'POST',
            f'/api/queries/{query_id}/results',
            json_data=payload,
        )

        # 如果返回了 job，需要轮询等待结果
        if 'job' in response:
            job_id = response['job']['id']
            result = await self._wait_for_job(job_id)
            query_result_id = result.get('query_result_id')
            if query_result_id:
                return await self._get_query_result_by_id(query_result_id, query_id)
            else:
                raise RedashServiceError("查询执行失败：未获取到结果 ID")
        
        # 如果直接返回了结果
        query_result = response.get('query_result', {})
        query_data = query_result.get('data', {})
        
        return RedashQueryResult(
            query_id=query_id,
            query_name='',
            data=query_data.get('rows', []),
            columns=query_data.get('columns', []),
            rows_count=len(query_data.get('rows', [])),
            retrieved_at=query_result.get('retrieved_at', ''),
        )

    async def _wait_for_job(
        self,
        job_id: str,
        max_wait: int = 60,
        poll_interval: float = 1.0,
    ) -> Dict[str, Any]:
        """等待查询作业完成"""
        start_time = datetime.now()
        while True:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > max_wait:
                raise RedashServiceError(f"查询超时：等待 {max_wait} 秒后仍未完成")

            response = await self._request('GET', f'/api/jobs/{job_id}')
            job = response.get('job', {})
            status = job.get('status')

            if status == 3:  # 成功
                return job
            elif status == 4:  # 失败
                error = job.get('error', '未知错误')
                raise RedashServiceError(f"查询执行失败: {error}")
            elif status == 5:  # 取消
                raise RedashServiceError("查询已取消")

            await asyncio.sleep(poll_interval)

    async def _get_query_result_by_id(
        self,
        result_id: int,
        query_id: int,
    ) -> RedashQueryResult:
        """通过结果 ID 获取查询结果"""
        data = await self._request('GET', f'/api/query_results/{result_id}.json')
        query_result = data.get('query_result', {})
        query_data = query_result.get('data', {})

        return RedashQueryResult(
            query_id=query_id,
            query_name='',
            data=query_data.get('rows', []),
            columns=query_data.get('columns', []),
            rows_count=len(query_data.get('rows', [])),
            retrieved_at=query_result.get('retrieved_at', ''),
        )

    # ==================== 批量查询同步 ====================

    async def sync_queries_from_config(
        self,
        queries_config: List[Dict[str, Any]],
        data_source_id: int,
    ) -> List[RedashQuery]:
        """
        从配置同步查询到 Redash
        
        Args:
            queries_config: 查询配置列表
            data_source_id: 数据源 ID
            
        Returns:
            创建/更新的查询列表
        """
        results = []
        
        # 获取现有查询（用于去重）
        existing_queries = await self.list_queries(page_size=200)
        existing_names = {
            q['name']: q['id'] 
            for q in existing_queries.get('results', [])
        }

        for config in queries_config:
            name = config['name']
            query_sql = config['query']
            description = config.get('description', '')

            try:
                if name in existing_names:
                    # 更新已存在的查询
                    query = await self.update_query(
                        query_id=existing_names[name],
                        query=query_sql,
                        description=description,
                    )
                    logger.info(f"更新查询: {name}")
                else:
                    # 创建新查询
                    query = await self.create_query(
                        name=name,
                        query=query_sql,
                        data_source_id=data_source_id,
                        description=description,
                    )
                    logger.info(f"创建查询: {name}")
                
                results.append(query)
            except RedashServiceError as e:
                logger.error(f"同步查询失败 [{name}]: {e.message}")

        return results


# 全局服务实例
_redash_service: Optional[RedashService] = None


def get_redash_service() -> RedashService:
    """获取 Redash 服务实例"""
    global _redash_service
    if _redash_service is None:
        _redash_service = RedashService()
    return _redash_service


async def init_redash_service():
    """初始化 Redash 服务"""
    global _redash_service
    _redash_service = RedashService()
    logger.info("Redash 服务初始化完成")


async def close_redash_service():
    """关闭 Redash 服务"""
    global _redash_service
    if _redash_service:
        await _redash_service.close()
        _redash_service = None
        logger.info("Redash 服务已关闭")
