import { computed, ref } from 'vue';

import { getAgentListApi } from '#/api/core/business';
import { logger } from '#/utils/logger';

/**
 * Agent 模板类型定义（复用现有 Agent）
 */
export interface AgentTemplate {
  /** Agent 编码（作为模板 ID） */
  id: string;
  /** Agent 名称 */
  name: string;
  /** Agent 描述 */
  description: string;
  /** Agent 类型（作为分类） */
  agentType:
    | 'BATCH_GENERATION'
    | 'REALTIME_CHAT'
    | 'REPORT_ANALYSIS'
    | 'REVIEW_IMAGE';
  /** Expert 配置列表 */
  expertConfigCodeList: string[];
  /** 所属租户 */
  tenantName?: string;
  /** 默认模型 */
  defaultModelCode?: string;
  /** 备注 */
  remark?: string;
}

/**
 * Agent 类型配置映射
 */
export const AGENT_TYPE_CONFIG: Record<
  string,
  { color: string; icon: string; label: string }
> = {
  BATCH_GENERATION: { label: '批量文章生成', color: 'blue', icon: '📝' },
  REVIEW_IMAGE: { label: '图片审核', color: 'red', icon: '🔍' },
  REALTIME_CHAT: { label: '实时对话', color: 'green', icon: '💬' },
  REPORT_ANALYSIS: { label: '报告分析', color: 'purple', icon: '📊' },
};

/**
 * Agent 模板管理 Composable
 * 直接使用现有 Agent 数据作为模板
 */
export function useAgentTemplates() {
  const selectedTemplate = ref<AgentTemplate | null>(null);
  const selectedCategory = ref<string>('all');
  const loading = ref(false);
  const templates = ref<AgentTemplate[]>([]);

  /**
   * 加载 Agent 列表作为模板
   */
  async function fetchTemplates() {
    loading.value = true;
    try {
      const response = await getAgentListApi({ page: 1, page_size: 100 });
      // 将 Agent 数据转换为模板格式
      templates.value = (response.items || []).map((agent) => ({
        id: agent.agent_code,
        name: agent.agent_name,
        description: agent.description || agent.remark || '',
        agentType: agent.agent_type,
        expertConfigCodeList: agent.expert_config_code_list || [],
        tenantName: agent.tenant_name,
        defaultModelCode: agent.default_model_code,
        remark: agent.remark,
      }));
      // 同步更新筛选后的模板列表
      updateFilteredTemplates();
    } catch (error) {
      logger.error('加载 Agent 模板失败:', error);
      templates.value = [];
      filteredTemplates.value = [];
    } finally {
      loading.value = false;
    }
  }

  /**
   * 根据分类筛选模板（使用 computed 自动响应变化）
   */
  const filteredTemplates = computed<AgentTemplate[]>(() => {
    if (selectedCategory.value === 'all') {
      return templates.value;
    }
    return templates.value.filter(
      (t) => t.agentType === selectedCategory.value,
    );
  });

  /**
   * 设置分类筛选
   */
  function setCategory(category: string) {
    selectedCategory.value = category;
  }

  /**
   * 选择模板
   */
  function selectTemplate(template: AgentTemplate) {
    selectedTemplate.value = template;
  }

  /**
   * 重置选择
   */
  function resetSelection() {
    selectedTemplate.value = null;
  }

  /**
   * 获取模板分类列表（基于 Agent 类型）
   */
  function getCategories(): Array<{
    icon: string;
    key: string;
    label: string;
  }> {
    return [
      { key: 'all', label: '全部', icon: 'AppstoreOutlined' },
      {
        key: 'BATCH_GENERATION',
        label: AGENT_TYPE_CONFIG.BATCH_GENERATION.label,
        icon: 'FileTextOutlined',
      },
      {
        key: 'REVIEW_IMAGE',
        label: AGENT_TYPE_CONFIG.REVIEW_IMAGE.label,
        icon: 'EyeOutlined',
      },
      {
        key: 'REALTIME_CHAT',
        label: AGENT_TYPE_CONFIG.REALTIME_CHAT.label,
        icon: 'MessageOutlined',
      },
      {
        key: 'REPORT_ANALYSIS',
        label: AGENT_TYPE_CONFIG.REPORT_ANALYSIS.label,
        icon: 'AnalysisOutlined',
      },
    ];
  }

  /**
   * 获取 Agent 类型的显示信息
   */
  function getAgentTypeInfo(agentType: string) {
    return (
      AGENT_TYPE_CONFIG[agentType] || {
        label: agentType,
        color: 'default',
        icon: '📦',
      }
    );
  }

  return {
    selectedTemplate,
    selectedCategory,
    filteredTemplates,
    loading,
    templates,
    setCategory,
    selectTemplate,
    resetSelection,
    getCategories,
    getAgentTypeInfo,
    fetchTemplates,
  };
}
