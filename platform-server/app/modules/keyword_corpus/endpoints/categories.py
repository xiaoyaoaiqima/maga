"""
分类树 API
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionDep, get_db
from app.core.logger import get_logger
from app.services.category_service import CategoryService, LabelService

logger = get_logger()

router = APIRouter(prefix="/categories", tags=["分类管理"])


# ==================== 请求/响应 Schema ====================

class CategoryCreate(BaseModel):
    """创建分类请求"""
    name: str = Field(..., min_length=1, max_length=100, description="分类名称")
    label: Optional[str] = Field(default=None, max_length=50, description="语义化标签（如 大人设、小人设、品牌）")
    parent_id: Optional[str] = Field(default=None, description="父分类 ID（空表示顶级分类）")
    category_type: Optional[str] = Field(default=None, description="分类类型（顶级分类必填）")
    description: Optional[str] = Field(default=None, max_length=500, description="描述")
    icon: Optional[str] = Field(default=None, max_length=50, description="图标")
    color: Optional[str] = Field(default=None, max_length=20, description="颜色")
    labels: Optional[dict[str, list[str]]] = Field(default=None, description="统一标签结构 {product: [...], tag_group_code: [...]}")
    # 兼容旧格式
    tags: Optional[list[str]] = Field(default=None, description="业务标签列表（已弃用，请使用 labels）")
    brands: Optional[list[str]] = Field(default=None, description="品牌标签列表（已弃用，请使用 labels）")
    products: Optional[list[str]] = Field(default=None, description="产品标签列表（已弃用，请使用 labels）")


class CategoryUpdate(BaseModel):
    """更新分类请求"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    label: Optional[str] = Field(default=None, max_length=50, description="语义化标签")
    description: Optional[str] = Field(default=None, max_length=500)
    icon: Optional[str] = Field(default=None, max_length=50)
    color: Optional[str] = Field(default=None, max_length=20)
    sort_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[int] = Field(default=None, ge=0, le=1)
    labels: Optional[dict[str, list[str]]] = Field(default=None, description="统一标签结构 {product: [...], tag_group_code: [...]}")
    # 兼容旧格式
    tags: Optional[list[str]] = Field(default=None, description="业务标签列表（已弃用，请使用 labels）")
    brands: Optional[list[str]] = Field(default=None, description="品牌标签列表（已弃用，请使用 labels）")
    products: Optional[list[str]] = Field(default=None, description="产品标签列表（已弃用，请使用 labels）")


class CategoryBatchImport(BaseModel):
    """批量导入分类和关键词"""
    root_category_id: str = Field(..., description="根分类 ID（如人设分类 ID）")
    items: list[dict] = Field(
        ...,
        description="数据列表 [{categories: ['分类1', '分类2'], keyword: '关键词', corpus: '语料'}, ...]",
    )


class ResponseData(BaseModel):
    """统一响应格式"""
    code: int = 0
    message: str = "success"
    data: Optional[dict | list] = None


# ==================== 分类 API ====================

@router.get("/tree", response_model=ResponseData)
async def get_category_tree(
    db: AsyncSessionDep,
    tenant_code: str = Query(default="default", description="租户编码"),
    category_type: Optional[str] = Query(default=None, description="分类类型筛选"),
    brand_code: Optional[str] = Query(default=None, description="品牌编码（用于 Scope 过滤）"),
    product_name: Optional[str] = Query(default=None, description="产品名称（用于 Scope 过滤）"),
    include_global: bool = Query(default=True, description="是否包含全局语料"),
    is_active: Optional[int] = Query(default=None, description="归档状态筛选：0=归档, 1=启用"),
):
    """
    获取完整分类树

    新增 Scope 过滤参数：
    - brand_code: 品牌编码，用于筛选品牌级和产品级语料
    - product_name: 产品名称，用于筛选产品级语料
    - include_global: 是否包含全局通用语料
    - is_active: 归档状态筛选（0=归档, 1=启用）
    """
    service = CategoryService(db)
    tree = await service.get_tree(
        tenant_code=tenant_code,
        root_category_type=category_type,
        brand_code=brand_code,
        product_name=product_name,
        include_global=include_global,
        is_active=is_active,
    )
    return ResponseData(data=tree)


@router.get("/labels", response_model=ResponseData)
async def get_all_labels(
    db: AsyncSessionDep,
    tenant_code: str = Query(default="default"),
    exclude_keyword: bool = Query(default=True, description="是否排除 KEYWORD 类型"),
):
    """
    获取所有可用的 label 列表

    用于前端展示可绑定的分类类型，如：小人设、场景、表达结构等
    """
    service = LabelService(db)
    labels = await service.get_all_labels(
        tenant_code=tenant_code,
        exclude_keyword=exclude_keyword,
    )
    return ResponseData(data=labels)


@router.get("/sibling-labels", response_model=ResponseData)
async def get_sibling_labels(
    db: AsyncSessionDep,
    parent_id: Optional[str] = Query(default=None, description="父节点 ID（空表示获取顶级节点的 label）"),
    tenant_code: str = Query(default="default"),
):
    """获取同级节点的所有 label（用于新建时参考）"""
    service = CategoryService(db)
    labels = await service.get_sibling_labels(
        parent_id=int(parent_id) if parent_id else None,
        tenant_code=tenant_code,
    )
    return ResponseData(data=labels)


# ==================== 关键词 CRUD API ====================


class KeywordCreate(BaseModel):
    """创建关键词请求"""
    name: str = Field(..., min_length=1, max_length=255, description="关键词名称")
    category_id: str = Field(..., description="所属分类 ID")
    description: Optional[str] = Field(default=None, max_length=500, description="描述")
    properties: Optional[dict] = Field(default=None, description="扩展属性")


class KeywordUpdate(BaseModel):
    """更新关键词请求"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=500)
    properties: Optional[dict] = Field(default=None)
    is_active: Optional[int] = Field(default=None, ge=0, le=1)


@router.get("/keywords", response_model=ResponseData)
async def list_keywords(
    db: AsyncSessionDep,
    category_id: str = Query(..., description="分类 ID"),
    keyword: Optional[str] = Query(default=None, description="关键词搜索"),
    tenant_code: str = Query(default="default"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=500),
):
    """
    获取分类下的关键词列表（分页）

    关键词是 label=KEYWORD 的节点，挂在分类节点下
    """
    service = CategoryService(db)
    items, total = await service.list_keywords(
        category_id=int(category_id),
        keyword=keyword,
        tenant_code=tenant_code,
        page=page,
        page_size=page_size,
    )
    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("/keywords", response_model=ResponseData)
async def create_keyword(
    db: AsyncSessionDep,
    data: KeywordCreate,
    tenant_code: str = Query(default="default"),
):
    """创建关键词"""
    service = CategoryService(db)
    result = await service.create_keyword(
        name=data.name,
        category_id=int(data.category_id),
        description=data.description,
        properties=data.properties,
        tenant_code=tenant_code,
    )
    return ResponseData(data=result, message="关键词创建成功")


@router.get("/{category_id}/children", response_model=ResponseData)
async def get_category_children(
    category_id: str,
    db: AsyncSessionDep,
    tenant_code: str = Query(default="default"),
    include_keywords: bool = Query(default=True, description="是否包含关键词"),
):
    """获取分类的直接子节点"""
    service = CategoryService(db)
    children = await service.get_children(
        parent_id=int(category_id),
        tenant_code=tenant_code,
        include_keywords=include_keywords,
    )
    return ResponseData(data=children)


@router.get("/tenants", response_model=ResponseData)
async def get_all_tenants(
    db: AsyncSessionDep,
):
    """
    获取所有租户列表

    返回所有有数据的租户编码及其节点数量
    """
    service = LabelService(db)
    tenants = await service.get_all_tenants()
    return ResponseData(data=tenants)


@router.get("/{category_id}", response_model=ResponseData)
async def get_category(
    category_id: str,
    db: AsyncSessionDep,
):
    """获取单个分类"""
    service = CategoryService(db)
    category = await service.get_category_by_id(int(category_id))
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    return ResponseData(data=category)


@router.post("", response_model=ResponseData)
async def create_category(
    db: AsyncSessionDep,
    data: CategoryCreate,
    tenant_code: str = Query(default="default"),
):
    """创建分类"""
    service = CategoryService(db)
    
    # label 必填
    if not data.label:
        raise HTTPException(status_code=400, detail="语义标签(label)为必填项")
    
    try:
        category = await service.create_category(
            name=data.name,
            label=data.label,
            parent_id=int(data.parent_id) if data.parent_id else None,
            category_type=data.category_type or data.label,  # category_type 默认使用 label
            description=data.description,
            icon=data.icon,
            color=data.color,
            tenant_code=tenant_code,
            labels=data.labels,
            tags=data.tags,
            brands=data.brands,
            products=data.products,
        )
        return ResponseData(data=category, message="分类创建成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as e:
        # 兜底：并发/竞态下可能绕过预检查，最终由数据库唯一键报错
        raise HTTPException(status_code=409, detail="分类重名冲突：同租户同标签下名称需唯一") from e


@router.put("/{category_id}", response_model=ResponseData)
async def update_category(
    category_id: str,
    data: CategoryUpdate,
    db: AsyncSessionDep,
):
    """更新分类"""
    service = CategoryService(db)
    try:
        category = await service.update_category(
            category_id=int(category_id),
            name=data.name,
            label=data.label,
            description=data.description,
            icon=data.icon,
            color=data.color,
            sort_order=data.sort_order,
            is_active=data.is_active,
            labels=data.labels,
            tags=data.tags,
            brands=data.brands,
            products=data.products,
        )
        if not category:
            raise HTTPException(status_code=404, detail="分类不存在")
        return ResponseData(data=category, message="分类更新成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as e:
        # 兜底：并发更新导致唯一索引冲突（uk_tenant_label_name）
        raise HTTPException(status_code=409, detail="分类重名冲突：同租户同标签下名称需唯一") from e


@router.delete("/{category_id}", response_model=ResponseData)
async def delete_category(
    category_id: str,
    db: AsyncSessionDep,
):
    """删除分类（包含所有子分类和关键词）"""
    service = CategoryService(db)
    try:
        success = await service.delete_category(int(category_id))
        if not success:
            raise HTTPException(status_code=404, detail="分类不存在")
        return ResponseData(message="分类删除成功")
    except IntegrityError as e:
        # 兜底：历史软删除数据可能导致唯一键冲突（uk_edge / uk_tenant_label_name）
        raise HTTPException(status_code=409, detail="删除失败：数据冲突，请重试") from e


class BatchDeleteRequest(BaseModel):
    """批量删除请求"""
    ids: list[str] = Field(..., min_length=1, description="要删除的分类 ID 列表")


@router.post("/batch-delete", response_model=ResponseData)
async def batch_delete_categories(
    data: BatchDeleteRequest,
    db: AsyncSessionDep,
):
    """批量删除分类（包含所有子分类和关键词）"""
    service = CategoryService(db)
    result = await service.batch_delete_categories([int(id) for id in data.ids])
    return ResponseData(
        data=result,
        message=f"删除完成：共删除 {result['total_nodes']} 个节点",
    )


# ==================== 批量导入 API ====================

@router.post("/batch-import", response_model=ResponseData)
async def batch_import_categories(
    db: AsyncSessionDep,
    data: CategoryBatchImport,
    tenant_code: str = Query(default="default"),
):
    """
    批量导入分类和关键词

    数据格式：
    - categories: 分类层级列表 ["分类1", "分类2", ...]
    - keyword: 关键词名称
    - corpus: 语料/描述（可选）
    """
    service = CategoryService(db)
    try:
        result = await service.batch_import_categories(
            root_category_id=int(data.root_category_id),
            items=data.items,
            tenant_code=tenant_code,
        )
        return ResponseData(
            data=result,
            message=f"导入完成：创建 {result['created_categories']} 个分类，{result['created_keywords']} 个关键词",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== 批量导入 V2 API ====================

class ImportItemV2(BaseModel):
    """导入项（V2格式）"""
    path: list[str] = Field(..., min_length=1, description="分类路径")
    corpus: str = Field(default="", description="语料内容")


class BatchImportV2(BaseModel):
    """批量导入请求（V2格式）"""
    parent_node_id: Optional[str] = Field(default=None, description="父节点 ID（空则导入为顶层）")
    items: list[ImportItemV2] = Field(..., min_length=1, description="导入数据列表")


@router.post("/batch-import-v2", response_model=ResponseData)
async def batch_import_v2(
    db: AsyncSessionDep,
    data: BatchImportV2,
    tenant_code: str = Query(default="default"),
):
    """
    批量导入分类和语料（V2版本）

    新格式：
    - path: 分类路径列表 ["层级1", "层级2", ...]
    - corpus: 语料内容（会添加到最后一级分类）

    特点：
    - 自动创建多层级分类结构
    - 同一分类可以有多条语料
    - 支持导入到任意父节点下
    """
    service = CategoryService(db)
    try:
        result = await service.batch_import_v2(
            parent_node_id=int(data.parent_node_id) if data.parent_node_id else None,
            items=[item.model_dump() for item in data.items],
            tenant_code=tenant_code,
        )
        return ResponseData(
            data=result,
            message=f"导入完成：创建 {result['created_nodes']} 个节点，更新 {result['updated_nodes']} 个节点",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== 结构化导入 API ====================


class StructuredCorpusItem(BaseModel):
    """结构化语料项"""
    template_code: str = Field(..., description="模板编码")
    fields: dict[str, str] = Field(..., description="模板字段值")


class StructuredImportItem(BaseModel):
    """结构化导入项"""
    name: str = Field(..., description="节点名称（关键词）")
    corpus: list[StructuredCorpusItem] = Field(..., min_length=1, description="语料列表")


class BatchImportStructured(BaseModel):
    """结构化批量导入请求"""
    parent_node_id: Optional[str] = Field(default=None, description="父节点 ID")
    dimension_type: str = Field(..., description="维度类型（如 persona、scenario）")
    items: list[StructuredImportItem] = Field(..., min_length=1, description="导入数据列表")
    conflict_strategy: str = Field(default="append", description="冲突策略：append/skip/overwrite")
    properties: Optional[dict] = Field(default=None, description="导入节点的属性设置（brands、products、tags）")


@router.post("/batch-import-structured", response_model=ResponseData)
async def batch_import_structured(
    db: AsyncSessionDep,
    data: BatchImportStructured,
    tenant_code: str = Query(default="default"),
):
    """
    结构化批量导入（按维度模板导入）

    新格式：
    - 每个 item 是一个节点（关键词）
    - 每个节点可以有多条结构化语料
    - 语料格式：{template_code, fields: {字段名: 值}}

    特点：
    - 不支持多层级路径，只导入到指定父节点下
    - 语料必须是结构化格式
    - 节点的 label 继承父节点
    """
    service = CategoryService(db)
    try:
        result = await service.batch_import_structured(
            parent_node_id=int(data.parent_node_id) if data.parent_node_id else None,
            dimension_type=data.dimension_type,
            items=[item.model_dump() for item in data.items],
            conflict_strategy=data.conflict_strategy,
            tenant_code=tenant_code,
            properties=data.properties,  # 新设计：直接传 properties
        )
        return ResponseData(
            data=result,
            message=f"导入完成：创建 {result['created_nodes']} 个节点，共 {result['total_corpus']} 条语料",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== 层级导入 API ====================

class HierarchicalCorpusItem(BaseModel):
    """层级导入的语料项"""
    template_code: str = Field(..., description="模板编码")
    fields: dict[str, str] = Field(..., description="模板字段值")


class HierarchicalImportItem(BaseModel):
    """层级导入项"""
    path: list[str] = Field(..., min_length=1, description="层级路径（如 ['一级分类', '二级分类', '三级分类']）")
    name: str = Field(..., description="节点名称（关键词）")
    corpus: HierarchicalCorpusItem = Field(..., description="语料内容")


class BatchImportHierarchical(BaseModel):
    """层级批量导入请求"""
    dimension_type: str = Field(..., description="维度类型/顶级分类标签（如 '违禁词'）")
    items: list[HierarchicalImportItem] = Field(..., min_length=1, description="导入数据列表")
    conflict_strategy: str = Field(default="append", description="冲突策略：append/skip/overwrite")


@router.post("/batch-import-hierarchical", response_model=ResponseData)
async def batch_import_hierarchical(
    db: AsyncSessionDep,
    data: BatchImportHierarchical,
    tenant_code: str = Query(default="default"),
):
    """
    层级批量导入（支持多级分类结构）

    数据格式：
    - path: 层级路径列表 ["一级分类", "二级分类", "三级分类"]
    - name: 节点名称（关键词）
    - corpus: 结构化语料 {template_code, fields}

    特点：
    - 自动创建多层级分类结构（nodes + edges）
    - 相同路径的节点会合并（不重复创建）
    - 语料挂载到最终的叶子节点上
    - 适用于有层级关系的数据导入（如违禁词库、分类体系等）
    """
    service = CategoryService(db)
    try:
        result = await service.batch_import_hierarchical(
            dimension_type=data.dimension_type,
            items=[item.model_dump() for item in data.items],
            conflict_strategy=data.conflict_strategy,
            tenant_code=tenant_code,
        )
        return ResponseData(
            data=result,
            message=f"导入完成：创建 {result['created_nodes']} 个节点，{result['created_edges']} 条关系，{result['total_corpus']} 条语料",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


# ==================== 节点复制 API ====================

class CopyNodeRequest(BaseModel):
    """复制节点请求"""
    source_node_id: str = Field(..., description="源节点 ID")
    target_parent_id: Optional[str] = Field(default=None, description="目标父节点 ID（空则复制为顶层）")


@router.post("/copy", response_model=ResponseData)
async def copy_node(
    db: AsyncSessionDep,
    data: CopyNodeRequest,
    tenant_code: str = Query(default="default"),
):
    """
    复制节点（含子节点和语料）到目标位置

    - 会复制整个子树结构
    - 会复制所有语料
    - 复制后的根节点名称会加上 "_副本" 后缀
    """
    service = CategoryService(db)
    try:
        result = await service.copy_node(
            source_node_id=int(data.source_node_id),
            target_parent_id=int(data.target_parent_id) if data.target_parent_id else None,
            tenant_code=tenant_code,
        )
        return ResponseData(
            data=result,
            message=f"复制成功：共复制 {result['copied_nodes']} 个节点",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


class MoveNodeRequest(BaseModel):
    """移动节点请求"""
    node_id: str = Field(..., description="节点 ID")
    target_parent_id: Optional[str] = Field(default=None, description="目标父节点 ID（空则移为顶层）")
    drop_node_id: Optional[str] = Field(default=None, description="放置的目标节点 ID")
    drop_position: int = Field(default=0, ge=-1, le=1, description="相对于目标节点的位置: -1=上方, 0=内部, 1=下方")


@router.post("/move", response_model=ResponseData)
async def move_node(
    data: MoveNodeRequest,
    db: AsyncSessionDep,
):
    """
    移动节点到新的父节点下

    用于拖拽排序
    """
    service = CategoryService(db)
    try:
        success = await service.move_node(
            node_id=int(data.node_id),
            target_parent_id=int(data.target_parent_id) if data.target_parent_id else None,
            drop_node_id=int(data.drop_node_id) if data.drop_node_id else None,
            drop_position=data.drop_position,
        )
        if not success:
            raise HTTPException(status_code=404, detail="节点不存在")
        return ResponseData(message="移动成功")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except IntegrityError as e:
        raise HTTPException(status_code=409, detail="移动失败：数据冲突，请重试") from e


# ==================== 语料管理 API ====================

class CorpusUpdate(BaseModel):
    """更新语料列表"""
    corpus: list[dict] = Field(..., description="语料列表 [{'text': '内容', 'weight': 1.0}, ...]")


class CorpusItemCreate(BaseModel):
    """添加语料（支持新旧两种格式）"""
    # 旧格式
    text: Optional[str] = Field(default=None, description="语料内容（旧格式，纯文本模式）")
    weight: float = Field(default=1.0, ge=0, description="权重（仅旧格式有效）")
    # 新格式（结构化语料）
    template_code: Optional[str] = Field(default=None, description="模板编码")
    fields: Optional[dict[str, str]] = Field(default=None, description="模板字段值")

    def to_corpus_item(self) -> dict | str:
        """转换为存储格式

        Returns:
            - 如果有 template_code + fields: 返回 {"template_code": "...", "fields": {...}}
            - 如果只有 text: 返回纯文本字符串（直接存储在数组中）
        """
        if self.template_code and self.fields:
            # 新格式：结构化语料
            return {"template_code": self.template_code, "fields": self.fields}
        elif self.text:
            # 纯文本模式：直接返回字符串
            return self.text
        else:
            raise ValueError("必须提供 text 或 template_code + fields")


class CorpusItemUpdate(BaseModel):
    """更新语料（支持新旧两种格式）"""
    # 旧格式
    text: Optional[str] = Field(default=None, description="语料内容（旧格式，纯文本模式）")
    weight: Optional[float] = Field(default=None, ge=0, description="权重（仅旧格式有效）")
    # 新格式（结构化语料）
    template_code: Optional[str] = Field(default=None, description="模板编码")
    fields: Optional[dict[str, str]] = Field(default=None, description="模板字段值")

    def to_corpus_item(self) -> dict | str:
        """转换为存储格式

        Returns:
            - 如果有 template_code + fields: 返回 {"template_code": "...", "fields": {...}}
            - 如果只有 text: 返回纯文本字符串（直接存储在数组中）
        """
        if self.template_code and self.fields:
            # 新格式：结构化语料
            return {"template_code": self.template_code, "fields": self.fields}
        elif self.text:
            # 纯文本模式：直接返回字符串
            return self.text
        else:
            raise ValueError("必须提供 text 或 template_code + fields")


@router.put("/{node_id}/corpus", response_model=ResponseData)
async def update_node_corpus(
    node_id: str,
    data: CorpusUpdate,
    db: AsyncSessionDep,
):
    """更新节点的语料列表（整体替换）"""
    service = CategoryService(db)
    result = await service.update_node_corpus(int(node_id), data.corpus)
    if not result:
        raise HTTPException(status_code=404, detail="节点不存在")
    return ResponseData(data=result, message="语料更新成功")


@router.post("/{node_id}/corpus", response_model=ResponseData)
async def add_corpus_item(
    node_id: str,
    data: CorpusItemCreate,
    db: AsyncSessionDep,
):
    """为节点添加一条语料（支持新旧格式）"""
    service = CategoryService(db)
    try:
        corpus_item = data.to_corpus_item()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await service.add_corpus_item_v2(int(node_id), corpus_item)
    if not result:
        raise HTTPException(status_code=404, detail="节点不存在")
    return ResponseData(data=result, message="语料添加成功")


@router.put("/{node_id}/corpus/{index}", response_model=ResponseData)
async def update_corpus_item_endpoint(
    node_id: str,
    index: int,
    data: CorpusItemUpdate,
    db: AsyncSessionDep,
):
    """更新节点的某条语料（支持新旧格式）"""
    service = CategoryService(db)
    try:
        corpus_item = data.to_corpus_item()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = await service.update_corpus_item_v2(int(node_id), index, corpus_item)
    if not result:
        raise HTTPException(status_code=404, detail="节点或语料不存在")
    return ResponseData(data=result, message="语料更新成功")


@router.delete("/{node_id}/corpus/{index}", response_model=ResponseData)
async def delete_corpus_item(
    node_id: str,
    index: int,
    db: AsyncSessionDep,
):
    """删除节点的某条语料"""
    service = CategoryService(db)
    result = await service.delete_corpus_item(int(node_id), index)
    if not result:
        raise HTTPException(status_code=404, detail="节点或语料不存在")
    return ResponseData(data=result, message="语料删除成功")


@router.put("/keywords/{keyword_id}", response_model=ResponseData)
async def update_keyword(
    keyword_id: str,
    data: KeywordUpdate,
    db: AsyncSessionDep,
):
    """更新关键词"""
    service = CategoryService(db)
    result = await service.update_keyword(
        keyword_id=int(keyword_id),
        name=data.name,
        description=data.description,
        properties=data.properties,
        is_active=data.is_active,
    )
    if not result:
        raise HTTPException(status_code=404, detail="关键词不存在")
    return ResponseData(data=result, message="关键词更新成功")


@router.delete("/keywords/{keyword_id}", response_model=ResponseData)
async def delete_keyword(
    keyword_id: str,
    db: AsyncSessionDep,
):
    """删除关键词（软删除）"""
    service = CategoryService(db)
    success = await service.delete_keyword(keyword_id=int(keyword_id))
    if not success:
        raise HTTPException(status_code=404, detail="关键词不存在")
    return ResponseData(message="关键词删除成功")


class KeywordBatchCreate(BaseModel):
    """批量创建关键词请求"""
    category_id: str
    keywords: list[dict]


@router.post("/keywords/batch", response_model=ResponseData)
async def batch_create_keywords(
    db: AsyncSessionDep,
    data: KeywordBatchCreate,
    tenant_code: str = Query(default="default"),
):
    """批量创建关键词"""
    service = CategoryService(db)
    result = await service.batch_create_keywords(
        category_id=int(data.category_id),
        keywords=data.keywords,
        tenant_code=tenant_code,
    )
    return ResponseData(data=result, message=f"成功创建 {result['created']} 个关键词")


# ==================== Label 语义化查询 API ====================


class BatchGetKeywordsRequest(BaseModel):
    """批量获取 keywords 请求"""
    node_ids: list[str] = Field(..., description="节点 ID 列表")
    include_children: bool = Field(default=False, description="是否包含子节点的 keywords")


@router.get("/by-label/{label}", response_model=ResponseData)
async def get_nodes_by_label(
    label: str,
    db: AsyncSessionDep,
    tenant_code: str = Query(default="default"),
    include_keywords: bool = Query(default=True, description="是否包含 keywords 字段"),
    include_parent_path: bool = Query(default=True, description="是否包含父节点路径"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
):
    """
    按 label 查询所有 Node

    用于 Expert 配置时，获取某个 label（如"小人设"）下的所有节点供勾选
    """
    service = LabelService(db)
    items, total = await service.get_nodes_by_label(
        label=label,
        tenant_code=tenant_code,
        include_keywords=include_keywords,
        include_parent_path=include_parent_path,
        page=page,
        page_size=page_size,
    )
    return ResponseData(data={
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.post("/keywords/batch-get", response_model=ResponseData)
async def batch_get_keywords(
    db: AsyncSessionDep,
    data: BatchGetKeywordsRequest,
    tenant_code: str = Query(default="default"),
):
    """
    批量获取节点的 keywords/corpus

    用于运行时，根据 Expert 配置的 selected_node_ids 获取实际的关键词内容
    返回节点的 name、label、corpus、description
    
    支持多选模式：node_id 可以是逗号分隔的多个 ID，如 "17670796844942514,17670880893908053"
    """
    service = LabelService(db)
    
    # 支持多选模式：逗号分隔的 node_id 需要拆分
    all_node_ids: list[int] = []
    for nid in data.node_ids:
        nid_str = str(nid).strip()
        if "," in nid_str:
            # 多选模式：拆分逗号分隔的 ID
            for single_id in nid_str.split(","):
                single_id = single_id.strip()
                if single_id:
                    all_node_ids.append(int(single_id))
        else:
            # 单选模式
            if nid_str:
                all_node_ids.append(int(nid_str))
    
    result = await service.batch_get_keywords(
        node_ids=all_node_ids,
        include_children=data.include_children,
        tenant_code=tenant_code,
    )
    return ResponseData(data=result)


# ==================== 全量导出/导入 API（用于环境迁移） ====================


class MigrationExportRequest(BaseModel):
    """迁移导出请求"""
    include_archived: bool = Field(default=False, description="是否包含已归档的数据")
    category_types: Optional[list[str]] = Field(default=None, description="要导出的分类类型列表（label值），为空则导出全部")


@router.post("/migration/export", response_model=ResponseData)
async def export_all_data(
    db: AsyncSessionDep,
    data: MigrationExportRequest,
    tenant_code: str = Query(default="default", description="租户编码"),
):
    """
    导出全部数据（用于环境迁移）

    返回数据包含：
    1. 完整分类树（包含节点层级关系和语料数据）
    2. 所有语料模板配置

    支持按分类筛选：通过 category_types 参数指定要导出的分类类型
    """
    service = CategoryService(db)

    # 获取完整分类树（包含语料）
    is_active_filter = None if data.include_archived else 1

    # 如果指定了分类类型，分别获取每个分类的树
    if data.category_types and len(data.category_types) > 0:
        tree = []
        for category_type in data.category_types:
            category_tree = await service.get_tree(
                tenant_code=tenant_code,
                root_category_type=category_type,
                brand_code=None,
                product_name=None,
                include_global=True,
                is_active=is_active_filter,
            )
            tree.extend(category_tree)
    else:
        # 获取所有分类
        tree = await service.get_tree(
            tenant_code=tenant_code,
            root_category_type=None,  # 获取所有维度
            brand_code=None,
            product_name=None,
            include_global=True,
            is_active=is_active_filter,
        )

    # 获取语料模板（如果指定了分类类型，只获取相关模板）
    from app.services.corpus_template_service import CorpusTemplateService
    template_service = CorpusTemplateService(db)

    if data.category_types and len(data.category_types) > 0:
        # 只获取选中的分类类型的模板
        templates = []
        for category_type in data.category_types:
            category_templates = await template_service.get_list(
                tenant_code=tenant_code,
                category_type=category_type
            )
            templates.extend(category_templates)
    else:
        # 获取所有模板
        templates = await template_service.get_list(tenant_code=tenant_code)

    return ResponseData(
        data={
            "tree": tree,
            "templates": [t.model_dump() for t in templates],
            "export_time": None,  # 可选：记录导出时间
            "tenant_code": tenant_code,
        },
        message="导出成功"
    )


class MigrationImportRequest(BaseModel):
    """迁移导入请求"""
    tree: list = Field(..., description="分类树数据")
    templates: list = Field(..., description="语料模板数据")
    conflict_strategy: str = Field(default="skip", description="冲突策略：skip=跳过已存在, overwrite=覆盖已存在")
    skip_templates: bool = Field(default=False, description="是否跳过模板创建（仅导入节点）")


@router.post("/migration/import", response_model=ResponseData)
async def import_all_data(
    db: AsyncSessionDep,
    data: MigrationImportRequest,
    tenant_code: str = Query(default="default", description="租户编码"),
):
    """
    导入全部数据（用于环境迁移）

    流程：
    1. 创建/更新语料模板
    2. 递归创建分类节点（保持层级关系）
    3. 导入语料数据

    冲突策略：
    - skip: 跳过已存在的节点和模板（默认）
    - overwrite: 覆盖已存在的节点和模板
    """
    from app.services.corpus_template_service import CorpusTemplateService
    from app.schemas.corpus_template import CorpusTemplateCreate, CorpusTemplateUpdate

    result = {
        "templates_created": 0,
        "templates_updated": 0,
        "templates_skipped": 0,
        "nodes_created": 0,
        "nodes_updated": 0,
        "nodes_skipped": 0,
        "errors": []
    }

    try:
        # 1. 处理语料模板
        if not data.skip_templates:
            template_service = CorpusTemplateService(db)

            for template_data in data.templates:
                try:
                    template_code = template_data.get("code")
                    if not template_code:
                        continue

                    # 检查模板是否已存在
                    existing = await template_service.get_by_code(template_code)

                    if existing:
                        if data.conflict_strategy == "overwrite":
                            # 更新模板
                            update_data = CorpusTemplateUpdate(
                                name=template_data.get("name"),
                                category_type=template_data.get("category_type"),
                                fields=template_data.get("fields", []),
                                description=template_data.get("description"),
                            )
                            await template_service.update(template_code, update_data)
                            result["templates_updated"] += 1
                        else:
                            result["templates_skipped"] += 1
                    else:
                        # 创建模板
                        create_data = CorpusTemplateCreate(
                            code=template_code,
                            name=template_data.get("name"),
                            category_type=template_data.get("category_type"),
                            fields=template_data.get("fields", []),
                            description=template_data.get("description"),
                            tenant_code=tenant_code,
                        )
                        await template_service.create(create_data)
                        result["templates_created"] += 1

                except Exception as e:
                    result["errors"].append(f"模板创建失败 {template_data.get('code')}: {str(e)}")

        # 2. 递归创建分类节点
        category_service = CategoryService(db)

        # 存储节点ID映射（原始ID -> 新ID），用于处理语料关联
        node_id_map = {}

        async def import_tree_node(node_data: dict, parent_id: int = None):
            """递归导入树节点"""
            try:
                # 检查节点是否已存在
                node_name = node_data.get("name")
                node_label = node_data.get("label")
                category_type = node_data.get("category_type") or node_label
                original_id = node_data.get("id")

                logger.info(f"[导入] 尝试创建节点: name={node_name}, label={node_label}, parent_id={parent_id}")

                # 简化逻辑：直接尝试创建节点，如果已存在则跳过
                try:
                    # 创建节点
                    node_result = await category_service.create_category(
                        name=node_name,
                        label=node_label,
                        category_type=category_type,
                        parent_id=parent_id,
                        description=node_data.get("description"),
                        icon=node_data.get("icon"),
                        color=node_data.get("color"),
                        tenant_code=tenant_code,
                        labels=node_data.get("labels"),
                        tags=node_data.get("tags"),
                        brands=node_data.get("brands"),
                        products=node_data.get("products"),
                    )
                    node_id = node_result["id"]
                    result["nodes_created"] += 1
                    logger.info(f"[导入] 节点创建成功: id={node_id}, name={node_name}")

                    # 保存ID映射
                    if original_id:
                        node_id_map[str(original_id)] = node_id

                except Exception as create_error:
                    # 如果创建失败（可能是因为已存在），记录错误并继续
                    error_msg = str(create_error)
                    logger.warning(f"[导入] 节点创建失败: name={node_name}, error={error_msg}")
                    
                    # 重要：回滚失败的事务，才能继续操作
                    await db.rollback()

                    # 检查是否是唯一键冲突（包括归档节点）
                    if "Duplicate entry" in error_msg or "已存在" in error_msg:
                        # 尝试查找已存在的节点（包括归档的）
                        from sqlalchemy import select as sql_select
                        from app.models.graph import GraphNode as GN

                        existing_stmt = sql_select(GN).where(
                            and_(
                                GN.tenant_code == tenant_code,
                                GN.label == node_label,
                                GN.name == node_name,
                                GN.is_deleted == 0,
                            )
                        )
                        existing_result = await db.execute(existing_stmt)
                        existing_node = existing_result.scalar_one_or_none()

                        if existing_node:
                            if existing_node.is_active == 0:
                                # 节点已归档，恢复它并更新所有字段
                                existing_node.is_active = 1
                                
                                # 重要：清空旧语料，使用导入的新语料
                                # （导入数据代表完整状态，不是增量更新）
                                if existing_node.corpus:
                                    existing_node.corpus = []
                                    from sqlalchemy.orm.attributes import flag_modified
                                    flag_modified(existing_node, "corpus")
                                
                                # 更新基本信息
                                if node_data.get("description"):
                                    existing_node.description = node_data["description"]
                                if node_data.get("icon"):
                                    existing_node.icon = node_data["icon"]
                                if node_data.get("color"):
                                    existing_node.color = node_data["color"]
                                
                                # 合并 properties
                                new_props = node_data.get("properties", {})
                                if new_props:
                                    existing_props = dict(existing_node.properties) if existing_node.properties else {}
                                    existing_props.update(new_props)
                                    existing_node.properties = existing_props
                                
                                await db.commit()
                                node_id = existing_node.id
                                
                                # 保存ID映射（用于子节点关联）
                                if original_id:
                                    node_id_map[str(original_id)] = node_id
                                
                                result["nodes_updated"] += 1
                                logger.info(f"[导入] 恢复已归档节点: id={node_id}, name={node_name}")
                            else:
                                # 节点已启用，根据策略处理
                                if data.conflict_strategy == "skip":
                                    result["nodes_skipped"] += 1
                                    logger.info(f"[导入] 跳过已存在的启用节点: name={node_name} (策略=skip)")
                                    return
                                else:
                                    # overwrite 模式：暂不实现
                                    result["nodes_skipped"] += 1
                                    result["errors"].append(f"节点 '{node_name}' 已存在（覆盖模式未实现）")
                                    return
                        else:
                            # 找不到节点，这是其他错误
                            result["errors"].append(f"节点 '{node_name}' 创建失败: {error_msg}")
                            return
                    else:
                        # 其他类型错误
                        result["errors"].append(f"节点 '{node_name}' 创建失败: {error_msg}")
                        return

                # 导入语料数据
                corpus_list = node_data.get("corpus", [])
                if corpus_list and node_id:
                    for corpus_item in corpus_list:
                        try:
                            # 为节点添加语料（支持新旧格式）
                            await category_service.add_corpus_item_v2(
                                node_id=node_id,
                                corpus_item=corpus_item,
                            )
                        except Exception as e:
                            result["errors"].append(f"语料导入失败（节点 {node_name}）: {str(e)}")

                # 递归处理子节点
                children = node_data.get("children", [])
                if children:
                    for child in children:
                        await import_tree_node(child, node_id)

            except Exception as e:
                result["errors"].append(f"节点导入失败 {node_data.get('name')}: {str(e)}")

        # 开始递归导入
        for root_node in data.tree:
            await import_tree_node(root_node)

        # 重要：确保所有数据写入数据库后再返回
        await db.flush()

        # 构建成功消息
        total_errors = len(result["errors"])
        if total_errors > 0:
            message = f"导入完成，但有 {total_errors} 个错误"
        else:
            message = "导入成功"

        return ResponseData(
            data=result,
            message=message
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}") from e

