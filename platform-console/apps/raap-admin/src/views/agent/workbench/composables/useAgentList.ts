import type { AgentListItem } from './useAgentTemplates';

import { computed, ref } from 'vue';

import { logger } from '#/utils/logger';

/**
 * Agent 列表管理 Composable
 */
export function useAgentList() {
  const loading = ref(false);
  const agents = ref<AgentListItem[]>([]);
  const selectedStatus = ref<'active' | 'all' | 'archived' | 'draft'>('all');

  /**
   * 草稿状态的 Agent
   */
  const draftAgents = computed(() =>
    agents.value.filter((a) => a.status === 'draft'),
  );

  /**
   * 运行中的 Agent
   */
  const activeAgents = computed(() =>
    agents.value.filter((a) => a.status === 'active'),
  );

  /**
   * 归档的 Agent
   */
  const archivedAgents = computed(() =>
    agents.value.filter((a) => a.status === 'archived'),
  );

  /**
   * 根据 Tab 筛选的 Agent 列表
   */
  const filteredAgents = computed(() => {
    if (selectedStatus.value === 'all') {
      return agents.value;
    }
    return agents.value.filter((a) => a.status === selectedStatus.value);
  });

  /**
   * 加载 Agent 列表
   * TODO: 调用后端 API
   */
  async function fetchAgents() {
    loading.value = true;
    try {
      // 模拟数据，实际应该调用 API
      // const response = await getAgentListApi();
      // agents.value = response.data;

      // 模拟数据
      agents.value = [
        {
          code: 'article-writer-001',
          name: '生文 Agent',
          description: '高质量文章生成，包含生文、审核、打分',
          status: 'active',
          expertCount: 3,
          lastExecTime: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
          lastExecResult: { total: 100, success: 95, failed: 5 },
          progress: 100,
          createdAt: new Date(
            Date.now() - 7 * 24 * 60 * 60 * 1000,
          ).toISOString(),
        },
        {
          code: 'marketing-copy-001',
          name: '营销文案 Agent',
          description: '营销文案生成，适用于广告、社交媒体',
          status: 'draft',
          expertCount: 2,
          progress: 60,
          createdAt: new Date(
            Date.now() - 1 * 24 * 60 * 60 * 1000,
          ).toISOString(),
        },
      ];
    } catch (error) {
      logger.error('加载 Agent 列表失败:', error);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 删除 Agent
   */
  async function deleteAgent(code: string) {
    try {
      // TODO: 调用后端 API
      // await deleteAgentApi(code);
      agents.value = agents.value.filter((a) => a.code !== code);
    } catch (error) {
      logger.error('删除 Agent 失败:', error);
      throw error;
    }
  }

  /**
   * 归档 Agent
   */
  async function archiveAgent(code: string) {
    try {
      // TODO: 调用后端 API
      // await archiveAgentApi(code);
      const agent = agents.value.find((a) => a.code === code);
      if (agent) {
        agent.status = 'archived';
      }
    } catch (error) {
      logger.error('归档 Agent 失败:', error);
      throw error;
    }
  }

  /**
   * 复制 Agent
   */
  async function duplicateAgent(code: string) {
    try {
      // TODO: 调用后端 API
      // const newAgent = await duplicateAgentApi(code);
      // agents.value.push(newAgent);
    } catch (error) {
      logger.error('复制 Agent 失败:', error);
      throw error;
    }
  }

  /**
   * 设置状态筛选
   */
  function setStatusFilter(status: typeof selectedStatus.value) {
    selectedStatus.value = status;
  }

  return {
    loading,
    agents,
    selectedStatus,
    draftAgents,
    activeAgents,
    archivedAgents,
    filteredAgents,
    fetchAgents,
    deleteAgent,
    archiveAgent,
    duplicateAgent,
    setStatusFilter,
  };
}
