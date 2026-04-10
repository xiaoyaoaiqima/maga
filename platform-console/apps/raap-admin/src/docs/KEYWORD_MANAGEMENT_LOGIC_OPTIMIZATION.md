# 关键词管理流程 - 逻辑优化方案

**分析时间**: 2025-01-29 **分析范围**: 关键词语料系统全流程 **优化重点**: 操作流程逻辑、批量处理、版本管理、信息展示

---

## 一、当前操作流程分析

### 1.1 典型用户场景

**场景 A：创建新的 Expert 配置**

```
1. 用户进入"分类树管理"页面
2. 创建分类节点（如：品牌 > 电子产品 > Apple）
3. 逐个添加关键词到节点
4. 进入"Expert 配置"页面
5. 创建/编辑 Expert
6. 打开"关键词树选择器"
7. 搜索并绑定节点到变量
```

**痛点**:

- 步骤多，分散在多个页面
- 需要在不同页面之间来回切换
- 容易忘记添加了哪些关键词
- 无法预览绑定效果

---

**场景 B：批量导入关键词**

```
1. 准备 Excel 文件（格式复杂）
2. 进入"文件池管理"
3. 上传文件
4. 等待系统解析
5. 检查解析结果
6. 手动修复错误
7. 确认导入
```

**痛点**:

- Excel 格式要求严格，容易出错
- 解析失败后错误信息不明确
- 无法预览导入效果
- 导入后无法撤销

---

**场景 C：更新现有节点**

```
1. 进入"分类树管理"
2. 找到需要修改的节点
3. 编辑关键词
4. 保存
5. 手动检查哪些 Expert 受影响
```

**痛点**:

- 不知道哪些 Expert 使用了这个节点
- 修改后无法自动通知相关人员
- 无法回滚到历史版本
- 缺少审计日志

---

## 二、核心逻辑痛点

### 2.1 操作流程复杂度 ⭐⭐⭐⭐⭐

**问题描述**:

- 创建 Expert 需要在多个页面间切换
- 分类树创建和关键词添加分离
- 节点绑定和效果预览分离
- 无法在一个页面完成所有操作

**影响**:

- 新手学习成本高
- 容易遗漏步骤
- 操作效率低下
- 用户体验差

---

### 2.2 批量操作功能弱 ⭐⭐⭐⭐⭐

**问题描述**:

- Excel 导入格式复杂（需要包含 ID、父节点 ID、标签、品牌等）
- 无法批量编辑节点属性
- 无法批量复制节点结构
- 导入失败后无法部分恢复
- 缺少导入模板和示例

**影响**:

- 批量导入失败率高
- 手动处理耗时长
- 容易出错
- 重复性工作多

---

### 2.3 版本管理缺失 ⭐⭐⭐⭐

**问题描述**:

- 无法查看节点历史版本
- 无法回滚到之前的版本
- 不知道谁在什么时候修改了什么
- 缺少审计日志
- 无法对比版本差异

**影响**:

- 误操作后无法恢复
- 难以追溯问题根源
- 团队协作困难
- 合规性风险

---

### 2.4 信息展示不足 ⭐⭐⭐⭐

**问题描述**:

- 不知道节点被哪些 Expert 使用
- 缺少使用统计（使用频率、使用时间等）
- 无法查看节点的完整依赖关系
- 缺少节点关联的 Job/Task 信息

**影响**:

- 修改节点前无法评估影响范围
- 容易破坏现有功能
- 缺少数据支持决策
- 难以优化节点结构

---

### 2.5 搜索和定位困难 ⭐⭐⭐

**问题描述**:

- 节点数量多时难以快速定位
- 搜索功能弱（只能搜索名称）
- 无法按使用情况筛选
- 缺少收藏/常用功能
- 无法快速跳转到父节点或子节点

**影响**:

- 节点多时操作效率低
- 容易找不到节点
- 重复创建相同节点
- 浪费时间

---

### 2.6 新旧模式兼容问题 ⭐⭐⭐

**问题描述**:

- 旧 Expert 使用 `variable_mappings`（直接映射标签）
- 新 Expert 使用 `strategy`（策略模式）
- 两种模式并存，维护困难
- 数据迁移工具缺失

**影响**:

- 代码复杂度高
- 容易出错
- 新旧功能不一致
- 迁移成本高

---

## 三、逻辑优化方案

### 3.1 优先级 P0：简化操作流程

#### 方案 A：一站式 Expert 配置向导

**目标**: 在一个页面完成从创建节点到绑定的所有步骤

**实现**:

```typescript
// 新增页面：/expert-config-wizard

步骤 1: 选择或创建分类
  - 显示现有分类树
  - 快速创建新分类
  - 支持拖拽排序

步骤 2: 批量添加关键词
  - Excel 复制粘贴
  - 逐行添加
  - 智能识别标签

步骤 3: 配置 Expert 变量绑定
  - 左侧：节点树
  - 右侧：Expert 变量列表
  - 拖拽绑定

步骤 4: 预览和测试
  - 显示绑定结果
  - 测试生成样例
  - 确认保存
```

**效果**:

- 操作步骤减少 60%
- 页面切换减少 80%
- 新手上手时间减少 50%

---

#### 方案 B：快捷操作面板

**目标**: 在分类树页面直接完成常用操作

**实现**:

```vue
<!-- 分类树页面新增快捷面板 -->

<div class="quick-actions">
  <!-- 快速添加关键词 -->
  <Button @click="showQuickAddModal">
    ➕ 快速添加
  </Button>

  <!-- 批量编辑 -->
  <Button @click="showBatchEditModal">
    ✏️ 批量编辑
  </Button>

  <!-- 查看使用情况 -->
  <Button @click="showUsageModal">
    📊 使用情况
  </Button>

  <!-- 导入导出 -->
  <Button @click="showImportExportModal">
    📥 导入/导出
  </Button>
</div>
```

**效果**:

- 无需切换页面
- 操作步骤减少 40%
- 常用功能一键可达

---

### 3.2 优先级 P0：增强批量操作

#### 方案 A：智能批量导入

**功能**:

1. **支持多种格式**
   - Excel (.xlsx, .xls)
   - CSV
   - JSON
   - 直接复制粘贴（从 Excel/表格）

2. **智能识别**

   ```typescript
   // 示例：用户直接粘贴 Excel 内容
   /*
   Apple      品牌      高端手机品牌
   iPhone     产品      Apple 旗舰手机
   iPad       产品      Apple 平板电脑
   */

   // 系统自动识别：
   // - 第 1 列：节点名称
   // - 第 2 列：标签/分类
   // - 第 3 列：描述
   ```

3. **导入预览**
   - 显示解析结果
   - 标注潜在错误
   - 支持在线编辑
   - 显示统计数据（成功/失败/跳过）

4. **分步导入**

   ```
   步骤 1: 粘贴/上传数据
   步骤 2: 预览和调整
   步骤 3: 确认导入
   步骤 4: 查看结果
   ```

5. **错误处理**
   - 显示详细错误信息
   - 支持部分导入
   - 提供修复建议
   - 保留失败记录供重试

---

#### 方案 B：批量编辑器

**功能**:

1. **表格视图**
   - 类似 Excel 的编辑界面
   - 支持批量选择
   - 支持列拖拽排序
   - 支持冻结列

2. **批量操作**

   ```typescript
   // 批量修改标签
   选中多个节点 → 右键 → 修改标签 → 选择新标签

   // 批量移动节点
   选中多个节点 → 拖拽 → 目标父节点

   // 批量删除
   选中多个节点 → Delete → 确认删除
   ```

3. **查找替换**
   - 查找节点名称
   - 替换关键词
   - 正则表达式支持

4. **验证和检查**
   - 实时验证重复节点
   - 检查循环引用
   - 提示冲突解决

---

### 3.3 优先级 P1：版本管理

#### 方案 A：节点版本控制

**功能**:

1. **版本记录**

   ```typescript
   interface NodeVersion {
     id: string;
     node_id: string;
     version: number;
     changes: {
       field: string;
       old_value: any;
       new_value: any;
     }[];
     created_by: string;
     created_at: string;
     comment?: string; // 修改备注
   }
   ```

2. **版本对比**
   - 显示差异高亮
   - 支持逐字段对比
   - 并排视图

3. **版本回滚**
   - 一键回滚到指定版本
   - 保留当前版本为备份
   - 回滚前确认影响范围

4. **修改备注**
   - 每次修改强制填写备注
   - 备注模板（快速选择）
   - 支持标签分类

---

#### 方案 B：操作审计

**功能**:

1. **审计日志**

   ```typescript
   interface AuditLog {
     id: string;
     action: 'create' | 'update' | 'delete' | 'restore';
     entity_type: 'node' | 'keyword' | 'category';
     entity_id: string;
     entity_name: string;
     changes: Record<string, { old: any; new: any }>;
     user_id: string;
     user_name: string;
     ip_address: string;
     timestamp: string;
   }
   ```

2. **日志查询**
   - 按时间范围筛选
   - 按用户筛选
   - 按操作类型筛选
   - 按实体筛选

3. **日志导出**
   - 导出为 CSV
   - 导出为 JSON
   - 支持定时报告

---

### 3.4 优先级 P1：增强信息展示

#### 方案 A：依赖关系图谱

**功能**:

1. **节点使用情况**

   ```typescript
   interface NodeUsage {
     node_id: string;
     node_name: string;
     // 使用的 Expert 列表
     used_by_experts: Array<{
       expert_id: string;
       expert_name: string;
       variable_name: string;
       last_used_at: string;
     }>;
     // 使用的策略列表
     used_by_strategies: Array<{
       strategy_id: string;
       strategy_name: string;
       dimension_index: number;
     }>;
     // 使用的任务统计
     usage_stats: {
       total_jobs: number;
       last_job_at: string;
       success_rate: number;
     };
   }
   ```

2. **可视化展示**
   - 显示节点依赖树
   - 高亮使用路径
   - 支持缩放和导航

3. **影响分析**
   - 修改前显示影响范围
   - 标注高风险修改
   - 提供回滚方案

---

#### 方案 B：使用统计面板

**功能**:

1. **统计指标**
   - 使用频率（最近 7/30/90 天）
   - 使用趋势图
   - 成功率统计
   - 平均响应时间

2. **热力图**
   - 显示热门节点
   - 显示冷门节点
   - 显示异常节点

3. **智能推荐**
   - 推荐合并相似节点
   - 推荐删除无用节点
   - 推荐优化节点结构

---

### 3.5 优先级 P2：优化搜索体验

#### 方案 A：增强搜索

**功能**:

1. **全文搜索**
   - 搜索节点名称
   - 搜索关键词
   - 搜索描述
   - 搜索标签

2. **高级筛选**

   ```typescript
   // 搜索条件
   interface SearchFilter {
     keyword?: string;
     labels?: string[];
     brands?: string[];
     products?: string[];
     created_at_start?: string;
     created_at_end?: string;
     used_by_expert?: string;
     usage_count_min?: number;
     usage_count_max?: number;
   }
   ```

3. **搜索结果排序**
   - 相关度排序
   - 使用频率排序
   - 创建时间排序
   - 修改时间排序

4. **搜索历史**
   - 保存最近搜索
   - 收藏常用搜索
   - 搜索建议

---

#### 方案 B：快速导航

**功能**:

1. **面包屑导航**

   ```
   首页 > 分类树 > 品牌 > 电子产品 > Apple
   ```

2. **快捷跳转**
   - 跳转到父节点
   - 跳转到子节点
   - 跳转到相关节点

3. **收藏夹**
   - 收藏常用节点
   - 自定义分组
   - 快速访问

4. **最近访问**
   - 显示最近查看的节点
   - 自动清理过期记录

---

### 3.6 优先级 P2：新旧模式兼容

#### 方案 A：统一数据模型

**目标**: 逐步迁移到新模式，同时保持兼容

**实现**:

1. **数据迁移工具**

   ```typescript
   // 自动迁移脚本
   async function migrateOldExpertToStrategy(oldExpert: Expert) {
     // 1. 读取旧的 variable_mappings
     const mappings = oldExpert.variable_mappings;

     // 2. 创建对应的策略
     const strategy = await createStrategyFromMappings(mappings);

     // 3. 更新 Expert
     oldExpert.strategy_id = strategy.id;
     oldExpert.variable_mappings = null; // 标记为已迁移

     // 4. 保存迁移记录
     await logMigration(oldExpert.id, strategy.id);
   }
   ```

2. **兼容层**

   ```typescript
   // 统一访问接口
   function getExpertVariables(expert: Expert) {
     // 优先使用 strategy
     if (expert.strategy_id) {
       return getVariablesFromStrategy(expert.strategy_id);
     }
     // 兼容旧模式
     if (expert.variable_mappings) {
       return expert.variable_mappings;
     }
     return [];
   }
   ```

3. **迁移进度追踪**
   - 显示已迁移/未迁移 Expert
   - 批量迁移工具
   - 迁移验证

---

## 四、实施计划

### 阶段 1：快速见效（1-2 周）

**目标**: 解决最痛的问题，快速提升用户体验

**任务**:

1. ✅ 实现一站式 Expert 配置向导
2. ✅ 实现智能批量导入（支持粘贴）
3. ✅ 实现导入预览和错误提示
4. ✅ 实现快捷操作面板

**预期效果**:

- 操作步骤减少 50%
- 批量导入成功率提升到 95%
- 用户满意度提升 40%

---

### 阶段 2：核心功能（2-4 周）

**目标**: 完善核心功能，建立数据基础

**任务**:

1. 实现节点版本管理
2. 实现依赖关系展示
3. 实现使用统计面板
4. 实现批量编辑器

**预期效果**:

- 支持版本回滚
- 可视化依赖关系
- 数据驱动决策

---

### 阶段 3：高级优化（4-6 周）

**目标**: 全面优化，打造最佳体验

**任务**:

1. 实现增强搜索
2. 实现快速导航
3. 实现智能推荐
4. 完成新旧模式迁移

**预期效果**:

- 搜索速度提升 80%
- 节点查找时间减少 70%
- 系统可维护性提升

---

## 五、技术方案

### 5.1 一站式配置向导

**组件设计**:

```vue
<!-- ExpertConfigWizard.vue -->
<template>
  <div class="wizard-container">
    <!-- 步骤指示器 -->
    <Steps :current="currentStep">
      <Step title="选择分类" />
      <Step title="添加关键词" />
      <Step title="绑定变量" />
      <Step title="预览测试" />
    </Steps>

    <!-- 步骤 1: 分类选择 -->
    <div v-if="currentStep === 0" class="step-content">
      <CategoryTreeSelector v-model="selectedCategory" />
      <Button @click="nextStep">下一步</Button>
    </div>

    <!-- 步骤 2: 关键词添加 -->
    <div v-if="currentStep === 1" class="step-content">
      <QuickKeywordInput v-model="keywords" />
      <Button @click="prevStep">上一步</Button>
      <Button @click="nextStep">下一步</Button>
    </div>

    <!-- 步骤 3: 变量绑定 -->
    <div v-if="currentStep === 2" class="step-content">
      <VariableBindingPanel
        :nodes="nodes"
        :variables="expertVariables"
        v-model="bindings"
      />
      <Button @click="prevStep">上一步</Button>
      <Button @click="nextStep">下一步</Button>
    </div>

    <!-- 步骤 4: 预览测试 -->
    <div v-if="currentStep === 3" class="step-content">
      <PreviewPanel :bindings="bindings" :test-data="sampleData" />
      <Button @click="prevStep">上一步</Button>
      <Button type="primary" @click="handleSave">保存配置</Button>
    </div>
  </div>
</template>
```

---

### 5.2 智能批量导入

**后端 API**:

```python
# raap-service-keyword-corpus/app/api/v1/endpoints/keyword_corpus/batch_import.py

@router.post("/batch-import")
async def batch_import_keywords(
    request: BatchImportRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    批量导入关键词

    支持格式：
    - Excel 文件上传
    - CSV 文件上传
    - JSON 数据
    - 纯文本粘贴（自动识别）
    """
    # 1. 解析输入数据
    parsed_data = await parse_input_data(request.data, request.format)

    # 2. 验证数据
    validation_result = await validate_import_data(parsed_data)

    # 3. 返回预览结果
    if request.preview:
        return {
            "total": len(parsed_data),
            "valid": validation_result.valid_count,
            "invalid": validation_result.invalid_count,
            "errors": validation_result.errors,
            "preview": validation_result.preview
        }

    # 4. 执行导入
    import_result = await execute_import(parsed_data)

    return {
        "success": import_result.success_count,
        "failed": import_result.failed_count,
        "errors": import_result.errors
    }
```

**前端组件**:

```vue
<!-- BatchImportModal.vue -->
<template>
  <Modal v-model:open="visible" title="批量导入关键词" width="800px">
    <Tabs v-model:activeKey="importMode">
      <!-- 粘贴导入 -->
      <TabPane key="paste" tab="粘贴导入">
        <Textarea
          v-model:value="pasteData"
          placeholder="直接粘贴 Excel 内容，例如：
Apple    品牌    高端手机品牌
iPhone   产品    Apple 旗舰手机"
          :rows="10"
        />
      </TabPane>

      <!-- 文件上传 -->
      <TabPane key="file" tab="文件上传">
        <Upload
          :before-upload="handleFileUpload"
          accept=".xlsx,.xls,.csv,.json"
        >
          <Button>点击上传</Button>
        </Upload>
      </TabPane>
    </Tabs>

    <!-- 导入预览 -->
    <div v-if="previewData" class="import-preview">
      <Table
        :columns="previewColumns"
        :data-source="previewData"
        :pagination="{ pageSize: 10 }"
      />
      <div class="preview-summary">
        <Tag color="green">有效: {{ validCount }}</Tag>
        <Tag color="red">无效: {{ invalidCount }}</Tag>
      </div>
    </div>

    <template #footer>
      <Button @click="visible = false">取消</Button>
      <Button v-if="!previewData" @click="handlePreview"> 预览 </Button>
      <Button type="primary" @click="handleImport"> 确认导入 </Button>
    </template>
  </Modal>
</template>
```

---

### 5.3 版本管理

**数据库模型**:

```python
# raap-service-keyword-corpus/app/models/node_version.py

class NodeVersion(Base):
    """节点版本表"""
    __tablename__ = "node_versions"

    id = mapped_column(BigInteger, primary_key=True)
    node_id = mapped_column(
        BigInteger,
        ForeignKey("nodes.id"),
        comment="节点 ID"
    )
    version = mapped_column(
        Integer,
        comment="版本号（递增）"
    )

    # 变更记录（JSON 格式）
    changes = mapped_column(
        JSON,
        comment="""
        变更记录，格式：
        [
            {
                "field": "name",
                "old_value": "旧名称",
                "new_value": "新名称"
            },
            {
                "field": "keywords",
                "old_value": [...],
                "new_value": [...]
            }
        ]
        """
    )

    # 完整数据快照（JSON 格式）
    snapshot = mapped_column(
        JSON,
        comment="节点完整数据快照（用于回滚）"
    )

    # 元数据
    created_by = mapped_column(String(100), comment="创建人")
    created_at = mapped_column(DateTime, comment="创建时间")
    comment = mapped_column(Text, comment="修改备注")

    # 关系
    node = relationship("Node", back_populates="versions")
```

**API 端点**:

```python
@router.get("/nodes/{node_id}/versions")
async def get_node_versions(node_id: int, db: AsyncSession = Depends(get_db)):
    """获取节点版本历史"""
    versions = await db.execute(
        select(NodeVersion)
        .where(NodeVersion.node_id == node_id)
        .order_by(NodeVersion.version.desc())
    )
    return versions.scalars().all()

@router.post("/nodes/{node_id}/rollback/{version}")
async def rollback_node(
    node_id: int,
    version: int,
    db: AsyncSession = Depends(get_db)
):
    """回滚节点到指定版本"""
    # 1. 获取目标版本快照
    target_version = await get_node_version(node_id, version, db)

    # 2. 创建当前版本备份
    await create_version_snapshot(node_id, db)

    # 3. 恢复快照数据
    await restore_snapshot(node_id, target_version.snapshot, db)

    # 4. 记录回滚操作
    await log_rollback_action(node_id, version, db)

    return {"success": True}
```

---

## 六、成功指标

### 6.1 用户体验指标

- **操作步骤减少**: 50%↓
- **页面切换减少**: 80%↓
- **新手上手时间**: 50%↓
- **批量导入成功率**: 95%↑
- **用户满意度**: 40%↑

### 6.2 效率指标

- **节点查找时间**: 70%↓
- **批量操作时间**: 60%↓
- **搜索响应时间**: 80%↓
- **错误率**: 30%↓

### 6.3 数据质量指标

- **重复节点减少**: 40%↓
- **无用节点清理**: 20%↓
- **节点结构优化**: 提升 30%

---

## 七、风险评估

### 7.1 技术风险

| 风险             | 影响 | 概率 | 缓解措施            |
| ---------------- | ---- | ---- | ------------------- |
| 版本管理性能问题 | 高   | 中   | 使用快照 + 增量存储 |
| 批量导入数据损坏 | 高   | 低   | 预览 + 验证 + 备份  |
| 依赖关系计算复杂 | 中   | 高   | 异步计算 + 缓存     |

### 7.2 业务风险

| 风险           | 影响 | 概率 | 缓解措施            |
| -------------- | ---- | ---- | ------------------- |
| 用户学习成本   | 中   | 低   | 向导 + 帮助文档     |
| 数据迁移失败   | 高   | 低   | 灰度发布 + 回滚方案 |
| 旧模式兼容问题 | 高   | 中   | 兼容层 + 自动迁移   |

---

## 八、总结

本优化方案从 **6 个核心维度** 提出了 **12 个具体方案**，涵盖了：

1. ✅ **简化操作流程** - 一站式向导 + 快捷操作
2. ✅ **增强批量操作** - 智能导入 + 批量编辑
3. ✅ **版本管理** - 版本控制 + 审计日志
4. ✅ **信息展示** - 依赖关系 + 使用统计
5. ✅ **搜索体验** - 全文搜索 + 快速导航
6. ✅ **新旧兼容** - 统一模型 + 数据迁移

**实施优先级**:

- **P0（立即实施）**: 操作流程简化 + 批量操作增强
- **P1（近期规划）**: 版本管理 + 信息展示
- **P2（长期优化）**: 搜索优化 + 新旧迁移

**预期效果**:

- 操作效率提升 **60%**
- 用户满意度提升 **40%**
- 维护成本降低 **30%**

---

**生成时间**: 2025-01-29 **版本**: v1.0.0
