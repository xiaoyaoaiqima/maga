<script setup lang="ts">
import type { SelectProps } from 'ant-design-vue';
import type { Dayjs } from 'dayjs';

import type { AgentApi } from '#/api/core/business';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { ClearOutlined } from '@ant-design/icons-vue';
import {
  Button,
  DatePicker,
  message,
  Modal,
  Pagination,
  Select,
  Switch,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAgentListApi } from '#/api/core/business';
import { checkCanModifyApi } from '#/api/core/publish';
import { requestClient } from '#/api/request';
import { use_page_persistence } from '#/utils/page_persistence';

const { RangePicker } = DatePicker;

interface ExpertProfile {
  corpus_version: string;
  property: string;
  rejected_count: string;
  rlaif_count: string;
  rlhf_check_count: string;
  manual_alignment_accuracy: string;
  tuning_rounds: string;
  type: string;
  model_code: string;
}

interface ExpertItem {
  id: string;
  name: string;
  code: string;
  expert_type: string;
  profile: ExpertProfile;
  related_agents: string[];
  status: boolean;
  statusText?: string;
  isDefault?: boolean;
  expanded?: boolean;
}

interface FilterState {
  agent_code: string[];
}

type PersistedCalibrationPageState = {
  applied_filters: FilterState;
  current_page: number;
  filters: FilterState;
};

interface ExpertConfigResponse {
  id: number;
  expert_config_code: string;
  expert_config_name: string;
  expert_type: string;
  enabled: boolean;
  model_code?: string;
}

const PAGE_SIZE = 10;
const MAX_VISIBLE_AGENTS = 2;
const router = useRouter();
const allExperts = ref<ExpertItem[]>([]);
const currentPage = ref(1);

const dateRange = ref<[Dayjs, Dayjs] | undefined>(undefined);
const ranges: Record<string, [Dayjs, Dayjs]> = {
  最近7天: [dayjs().subtract(6, 'day'), dayjs()] as [Dayjs, Dayjs],
  最近30天: [dayjs().subtract(29, 'day'), dayjs()] as [Dayjs, Dayjs],
};
const filters = ref<FilterState>({
  agent_code: [],
});
const appliedFilters = ref<FilterState>({
  agent_code: [],
});
const agentOptions = ref<NonNullable<SelectProps['options']>>([
  { label: '法律专家', value: 'legal_expert' },
  { label: '平台不合规专家', value: 'platform_noncompliance_expert' },
  { label: '品牌不合规专家', value: 'brand_noncompliance_expert' },
]);
const loading = ref(false);
const filterOption: SelectProps['filterOption'] = (input, option) =>
  (option?.label ?? '').toString().toLowerCase().includes(input.toLowerCase());

// 页面状态持久化（初始化时自动执行状态恢复）
const page_persistence = use_page_persistence<PersistedCalibrationPageState>({
  storage_key: 'raap_admin.expert.calibration.persist.v1',
  version: 1,
  get_state: () => ({
    filters: { ...filters.value },
    applied_filters: { ...appliedFilters.value },
    current_page: currentPage.value,
  }),
  apply_state: (persisted) => {
    filters.value = { ...persisted.filters };
    appliedFilters.value = { ...persisted.applied_filters };
    currentPage.value = persisted.current_page || 1;
  },
});

// 启动自动持久化：监听状态变化并自动保存到 localStorage
page_persistence.start_auto_persist();

const filteredExperts = computed(() => {
  if (appliedFilters.value.agent_code.length === 0) {
    return allExperts.value;
  }
  return allExperts.value.filter((expert) =>
    appliedFilters.value.agent_code.includes(expert.code),
  );
});

const totalExperts = computed(() => filteredExperts.value.length);

const pagedExperts = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE;
  return filteredExperts.value.slice(start, start + PAGE_SIZE);
});

// 生成多样化的 Expert 档案数据
const generateRandomProfile = (index: number): ExpertProfile => {
  // 使用索引作为随机种子,确保同一个 expert 每次显示数据一致
  const seed = index * 137;

  // 语料版本 (最近3个月的版本)
  const versionDates = [
    'v2025.01.15',
    'v2025.01.22',
    'v2025.02.05',
    'v2025.02.18',
    'v2025.03.01',
    'v2025.03.12',
    'v2025.03.25',
    'v2025.04.08',
    'v2025.04.20',
    'v2025.05.02',
  ];
  const corpus_version = versionDates[seed % versionDates.length];

  // 人工对齐精准率 (85% - 98%)
  const accuracyBase = 85 + (seed % 14);
  const accuracyDecimal = (seed % 10) / 10;
  const manual_alignment_accuracy = `${(accuracyBase + accuracyDecimal).toFixed(1)}%`;

  // RLAIF 打分次数 (500 - 15000)
  const rlaifBase = 500 + ((seed * 37) % 14_500);
  const rlaif_count = `${rlaifBase.toLocaleString()}次`;

  // RLHF 抽检次数 (50 - 2000,约为 RLAIF 的 5-15%)
  const rlhfBase = Math.round(rlaifBase * (0.05 + (seed % 10) / 100));
  const rlhf_check_count = `${rlhfBase.toLocaleString()}次`;

  // 驳回次数 (5 - 200,约为 RLHF 的 5-15%)
  const rejectedBase = Math.round(rlhfBase * (0.05 + ((seed * 2) % 10) / 100));
  const rejected_count = `${rejectedBase.toLocaleString()}次`;

  // 调优轮数 (3 - 25)
  const tuning_rounds = `${3 + (seed % 23)}次`;

  return {
    corpus_version,
    manual_alignment_accuracy,
    property: '', // 会在外部设置
    rejected_count,
    rlaif_count,
    rlhf_check_count,
    tuning_rounds,
    type: '',
    model_code: '',
  };
};

const resolveExpertPropertyLabel = (expertType?: string) => {
  if (expertType === 'BAN') return '0/1评分类';
  if (expertType === 'CRITIC') return '1-100评分类';
  if (expertType === 'GENERATION') return '生文类';
  if (expertType) return 'else类';
  return 'else类';
};

const buildExpertAgentMap = (
  agents: AgentApi.Agent[],
): Record<string, string[]> => {
  const map: Record<string, Set<string>> = {};
  agents.forEach((agent) => {
    const expertCodes = agent.expert_config_code_list ?? [];
    expertCodes.forEach((code) => {
      if (!map[code]) {
        map[code] = new Set<string>();
      }
      if (agent.agent_name) {
        map[code].add(agent.agent_name);
      }
    });
  });

  const result: Record<string, string[]> = {};
  Object.entries(map).forEach(([code, names]) => {
    result[code] = [...names];
  });
  return result;
};

const fetchExperts = async () => {
  loading.value = true;
  try {
    const [expertResponse, agentResponse] = await Promise.all([
      requestClient.get<ExpertConfigResponse[]>('/v1/expert-configs', {
        params: {
          skip: 0,
          limit: 1000,
        },
      }),
      getAgentListApi({ page: 1, page_size: 100 }),
    ]);
    const items = expertResponse ?? [];
    const agentItems = agentResponse?.items ?? [];
    const expertAgentMap = buildExpertAgentMap(agentItems);
    allExperts.value = items.map((item, index) => {
      const isDefault = index < 2; // 前两个模拟为默认
      let statusText = '';
      if (isDefault) {
        statusText = '默认启用';
      } else {
        statusText = item.enabled ? '已启用' : '已禁用';
      }

      const profile = generateRandomProfile(index);
      profile.property = resolveExpertPropertyLabel(item.expert_type);
      profile.type = isDefault ? '默认' : '非默认';
      profile.model_code = item.model_code || '-';

      return {
        id: String(item.id),
        name: item.expert_config_name || item.expert_config_code,
        code: item.expert_config_code,
        expert_type: item.expert_type,
        profile,
        related_agents: expertAgentMap[item.expert_config_code] ?? [],
        status: item.enabled,
        statusText,
        isDefault,
      };
    });
    agentOptions.value = items.map((item) => ({
      label: item.expert_config_name || item.expert_config_code,
      value: item.expert_config_code,
    }));
  } catch (error) {
    console.error('获取 ExpertConfig 列表失败:', error);
    message.error('获取 ExpertConfig 列表失败');
  } finally {
    loading.value = false;
  }
};

const handleAction = (name: string, action: string) => {
  message.info(`正在前往【${name}】的${action}界面...`);
};

const handleGoGenerate = () => {
  router.push({ path: '/job/create' });
};

const handleCalibration = (expert: ExpertItem) => {
  router.push({
    path: '/analysis/article-pool',
    query: {
      expert_config_code: expert.code,
      expert_config_name: expert.name,
    },
  });
};

const handleTuning = (expert: ExpertItem) => {
  router.push({
    path: '/expert/debug',
    query: {
      expert_config_code: expert.code,
    },
  });
};

const handleEditExpert = (expert: ExpertItem) => {
  router.push({
    path: '/config/expert-edit',
    query: { code: expert.code },
  });
};

const handleToggleStatus = async (expert: ExpertItem) => {
  if (expert.isDefault) return;

  const newStatus = !expert.status;
  try {
    await requestClient.put(`/v1/expert-configs/${expert.id}`, {
      enabled: newStatus,
    });
    expert.status = newStatus;
    expert.statusText = newStatus ? '已启用' : '已禁用';
    message.success(`${expert.name}已${newStatus ? '启用' : '禁用'}`);
  } catch (error) {
    console.error('更新专家状态失败:', error);
    message.error('更新Expert状态失败');
  }
};

const handleSearch = () => {
  appliedFilters.value = {
    agent_code: [...filters.value.agent_code],
  };
  currentPage.value = 1;
  message.success('已应用筛选条件');
};

const handleReset = () => {
  dateRange.value = undefined;
  filters.value.agent_code = [];
  appliedFilters.value = {
    agent_code: [],
  };
  currentPage.value = 1;
  message.info('已重置筛选条件');
};

const handlePageChange = (page: number) => {
  currentPage.value = page;
};

const toggleAgentExpansion = (expert: ExpertItem) => {
  expert.expanded = !expert.expanded;
};

const handleDelete = async (expert: ExpertItem) => {
  // 检查上线状态
  try {
    const checkResult = await checkCanModifyApi('ExpertConfig', expert.code);

    if (!checkResult.allowed) {
      if (checkResult.action === 'reject') {
        // 已上线，直接拒绝删除
        message.error(checkResult.reason || '该配置已上线，不可删除');
        return;
      } else if (checkResult.action === 'confirm') {
        // 有引用关系，需要确认
        Modal.confirm({
          title: '确认删除',
          content: `${checkResult.reason}\n\n是否继续删除？`,
          okText: '继续删除',
          cancelText: '取消',
          okButtonProps: { danger: true },
          onOk: async () => {
            await proceedDelete(expert);
          },
        });
        return;
      }
    }
  } catch (error) {
    console.error('检查删除权限失败:', error);
  }

  // 允许删除
  Modal.confirm({
    title: '确认删除',
    content: `确定要删除 Expert "${expert.name}" 吗？`,
    okText: '确定',
    cancelText: '取消',
    okButtonProps: { danger: true },
    onOk: async () => {
      await proceedDelete(expert);
    },
  });
};

const proceedDelete = async (expert: ExpertItem) => {
  try {
    await requestClient.delete(`/v1/expert-configs/${expert.id}`);
    message.success('删除成功');
    fetchExperts();
  } catch {
    message.error('删除失败');
  }
};

onMounted(async () => {
  // 先恢复持久化的状态
  await page_persistence.restore();
  // 再拉取数据
  await fetchExperts();
});
</script>

<template>
  <div class="calibration-page">
    <!-- 顶部标题 + 筛选条（与 AI可视化 一致） -->
    <div class="filter-bar">
      <div class="filter-title">
        <span class="title-text">Expert管理</span>
      </div>
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">时间筛选</span>
          <RangePicker v-model:value="dateRange" :ranges="ranges" />
        </div>
        <div class="filter-item">
          <span class="filter-label">Expert筛选</span>
          <Select
            v-model:value="filters.agent_code"
            :filter-option="filterOption"
            :max-tag-count="2"
            :max-tag-text-length="8"
            :options="agentOptions"
            allow-clear
            class="agent-filter-select"
            mode="multiple"
            placeholder="所有Expert"
            show-search
          />
        </div>
        <div class="filter-actions">
          <Button :loading="loading" type="primary" @click="handleSearch">
            确认筛选
          </Button>
          <Button :disabled="loading" @click="handleReset">
            <template #icon>
              <ClearOutlined />
            </template>
            重置筛选
          </Button>
        </div>
      </div>
    </div>

    <div class="calibration-content">
      <!-- 表头区域 (四列独立色块，使用 Grid 布局确保对齐) -->
      <div class="grid-container table-header table-grid">
        <div class="header-item table-cell">Expert名称</div>
        <div class="header-item table-cell">Expert档案</div>
        <div class="header-item table-cell">关联Agent</div>
        <div class="header-item item-status table-cell">状态</div>
        <div class="header-item table-cell">操作区域</div>
      </div>

      <div v-if="loading" class="expert-loading">加载中...</div>
      <div v-else>
        <!-- 列表内容 -->
        <div class="expert-list">
          <div
            v-for="expert in pagedExperts"
            :key="expert.id"
            class="grid-container expert-row table-grid"
            :class="{ 'row-disabled': !expert.status }"
          >
            <!-- A. 专家名称列 (蓝色方块) -->
            <div class="col-name table-cell">
              <div class="name-box">
                {{ expert.name }}
              </div>
            </div>

            <!-- B. 专家档案列 (多行文本) -->
            <div class="col-profile table-cell">
              <div class="profile-details">
                <div class="profile-line">
                  <span class="label">类型：</span>
                  <span class="value highlight-blue">{{
                    expert.profile.type
                  }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">属性：</span>
                  <span class="value">{{ expert.profile.property }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">模型：</span>
                  <span class="value">{{ expert.profile.model_code }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">(RLAIF) 已参与打分次数：</span>
                  <span class="value bold-value">{{
                    expert.profile.rlaif_count
                  }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">(RLHF) 人工抽检次数：</span>
                  <span class="value bold-value">{{
                    expert.profile.rlhf_check_count
                  }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">被人工驳回次数：</span>
                  <span class="value bold-value">{{
                    expert.profile.rejected_count
                  }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">RLHF后调优轮数：</span>
                  <span class="value bold-value">{{
                    expert.profile.tuning_rounds
                  }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">已人工对齐精准率：</span>
                  <span class="value bold-value">{{
                    expert.profile.manual_alignment_accuracy
                  }}</span>
                </div>
                <div class="profile-line">
                  <span class="label">依赖语料版本号：</span>
                  <span class="value">{{ expert.profile.corpus_version }}</span>
                </div>
              </div>
            </div>

            <!-- C. 关联 Agent 列 -->
            <div class="col-related table-cell">
              <div class="related-agents">
                <span
                  v-if="expert.related_agents.length === 0"
                  class="related-empty"
                  >-</span
                >
                <div v-else class="related-list">
                  <div class="related-items-wrapper">
                    <div
                      v-for="agentName in expert.expanded
                        ? expert.related_agents
                        : expert.related_agents.slice(0, MAX_VISIBLE_AGENTS)"
                      :key="agentName"
                      class="related-badge"
                    >
                      {{ agentName }}
                    </div>
                    <button
                      v-if="expert.related_agents.length > MAX_VISIBLE_AGENTS"
                      class="related-expand-btn"
                      type="button"
                      @click="toggleAgentExpansion(expert)"
                    >
                      <span v-if="!expert.expanded" class="expand-text">
                        +{{ expert.related_agents.length - MAX_VISIBLE_AGENTS }}
                      </span>
                      <span
                        v-else
                        class="expand-icon"
                        :class="{ 'expand-icon-rotated': expert.expanded }"
                      >
                        ▼
                      </span>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- C. 状态列 (Switch) -->
            <div class="col-status table-cell">
              <div class="status-wrapper">
                <Switch
                  :checked="expert.status"
                  :disabled="expert.isDefault"
                  class="custom-switch"
                  :class="{ 'switch-default': expert.isDefault }"
                  @change="handleToggleStatus(expert)"
                />
                <div
                  class="status-text"
                  :class="{
                    'text-blue': expert.status && !expert.isDefault,
                    'text-default-enabled': expert.isDefault,
                    'text-muted': !expert.status && !expert.isDefault,
                  }"
                >
                  {{ expert.statusText }}
                </div>
              </div>
            </div>

            <!-- D. 操作区域列 (文字链接) -->
            <div class="col-action table-cell">
              <div class="action-layout">
                <button
                  class="action-link action-link-vertical"
                  type="button"
                  @click="handleGoGenerate()"
                >
                  去生文
                </button>
                <button
                  class="action-link action-link-vertical"
                  type="button"
                  @click="handleCalibration(expert)"
                >
                  去校准
                </button>
                <button
                  class="action-link action-link-vertical"
                  type="button"
                  @click="handleTuning(expert)"
                >
                  去调参
                </button>
                <button
                  class="action-link action-link-vertical"
                  type="button"
                  @click="handleEditExpert(expert)"
                >
                  编辑
                </button>
                <button
                  class="action-link-danger action-link-vertical"
                  type="button"
                  @click="handleDelete(expert)"
                >
                  删除
                </button>
                <button
                  class="action-link-weak action-link-vertical"
                  type="button"
                  @click="handleAction(expert.name, '合成Agent')"
                >
                  去合成Agent
                </button>
              </div>
            </div>
          </div>
        </div>

        <div class="pagination-wrapper">
          <Pagination
            :current="currentPage"
            :page-size="PAGE_SIZE"
            :total="totalExperts"
            :show-size-changer="false"
            @change="handlePageChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.calibration-page {
  width: 100%;
  min-height: 100%;
  padding: 12px 24px 32px;
  font-family:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue',
    Arial, 'Noto Sans', sans-serif;
  background-color: transparent;
}

/* 顶部标题 + 筛选区域（与 AI 可视化一致） */
.filter-bar {
  position: sticky;
  top: 0;
  z-index: 10;
  padding: 12px 24px 16px;
  margin: -12px -24px 24px;
  background: hsl(var(--background) / 92%);
  border-bottom: 1px solid hsl(var(--border));
  box-shadow:
    0 12px 24px hsl(var(--background) / 30%),
    0 1px 0 hsl(var(--border));
  backdrop-filter: blur(8px);
}

.filter-title {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 12px;
}

.title-text {
  font-size: 18px;
  font-weight: 700;
  color: transparent;
  background-image: linear-gradient(
    90deg,
    hsl(var(--primary)),
    hsl(var(--success))
  );
  background-clip: text;
}

.update-time {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}

.filter-item {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
}

.filter-label {
  font-weight: 500;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.filter-actions {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  margin-left: auto;
}

.agent-filter-select {
  width: 320px;
}

.agent-filter-select :deep(.ant-select-selector) {
  flex-wrap: nowrap !important;
  height: auto !important;
  min-height: 32px !important;
  max-height: 32px !important;
  overflow: hidden !important;
}

.agent-filter-select :deep(.ant-select-selection-overflow) {
  flex-wrap: nowrap !important;
  overflow: hidden !important;
}

.agent-filter-select :deep(.ant-select-selection-overflow-item) {
  flex-shrink: 0;
}

.agent-filter-select :deep(.ant-select-selection-item) {
  max-width: 140px;
}

.calibration-content {
  max-width: 1400px;
  margin: 0 auto;
}

.expert-loading {
  padding: 24px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

/* 强制 Grid 布局，严格定义五列宽度 */
.grid-container {
  display: grid !important;

  /* 专家名称(220px) | 专家档案(1fr) | 关联Agent(220px) | 状态(120px) | 操作区域(320px) */
  grid-template-columns: 220px 1fr 220px 120px 320px !important;
  gap: 0 !important;
  align-items: center;
}

/* 表头样式 */
.table-header {
  margin-bottom: 24px;
  overflow: hidden;
  border-radius: 8px;
  box-shadow:
    inset 0 0 0 1px hsl(var(--border)),
    0 4px 12px hsl(var(--background) / 20%);
}

.dark .table-header {
  box-shadow:
    inset 0 0 0 1px hsl(var(--border)),
    0 4px 12px hsl(var(--background-deep) / 20%);
}

.header-item {
  padding: 10px 0;
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--primary-foreground));
  text-align: center;
  background: hsl(var(--primary));
  border-radius: 0;
  box-shadow: none;
}

.dark .header-item {
  color: hsl(var(--foreground));
  background: #000;
}

.header-item.item-status {
  background: hsl(var(--primary) / 90%);
}

.dark .header-item.item-status {
  background: hsl(var(--card));
}

/* 列表行样式 */
.expert-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.expert-row {
  align-items: stretch;
  padding: 0;
  overflow: hidden;
  background: hsl(var(--card));
  border-radius: 12px;
  box-shadow:
    0 2px 8px hsl(var(--background-deep) / 15%),
    0 0 0 1px hsl(var(--border));
  transition:
    box-shadow 0.3s cubic-bezier(0.25, 0.8, 0.25, 1),
    transform 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
}

.col-name {
  display: flex;
  align-items: center;
  justify-content: center;
}

.col-profile {
  display: flex;
  align-items: center;
}

.col-related {
  display: flex;
  align-items: center;
  justify-content: center;
}

.expert-row .table-cell {
  position: relative;
  display: flex;
  align-items: center;
  padding: 16px;
}

.expert-row .table-cell::after {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 1px;
  content: '';
  background: hsl(var(--border));
}

.expert-row .table-cell:last-child::after {
  display: none;
}

.expert-row .table-cell > * {
  width: 100%;
}

.expert-row:hover {
  box-shadow:
    0 15px 20px -12px rgb(0 0 0 / 10%),
    0 0 15px 5px rgb(0 0 0 / 5%);
  transform: translateY(-2px);
}

/* A. 专家名称 - 蓝色胶囊 */
.name-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 180px;
  height: 60px;
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 8%);
  border-radius: 12px;
  box-shadow: inset 0 0 0 1px hsl(var(--primary) / 15%);
}

.related-agents {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  color: hsl(var(--foreground));
  text-align: center;
  overflow-wrap: anywhere;
}

.related-list {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
}

.related-items-wrapper {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.related-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 180px;
  min-height: 36px;
  padding: 6px 10px;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--success));
  text-align: center;
  overflow-wrap: anywhere;
  background: hsl(var(--success) / 12%);
  border-radius: 10px;
  box-shadow: inset 0 0 0 1px hsl(var(--success) / 20%);
}

.related-expand-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 180px;
  min-height: 32px;
  padding: 4px 8px;
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--primary));
  cursor: pointer;
  background: hsl(var(--primary) / 8%);
  border: 1px solid hsl(var(--primary) / 30%);
  border-radius: 8px;
  transition: all 0.2s ease;
}

.related-expand-btn:hover {
  background: hsl(var(--primary) / 15%);
  border-color: hsl(var(--primary) / 50%);
}

.expand-text {
  font-size: 14px;
  font-weight: 600;
}

.expand-icon {
  font-size: 12px;
  transition: transform 0.3s ease;
}

.expand-icon-rotated {
  transform: rotate(180deg);
}

.related-empty {
  color: hsl(var(--muted-foreground));
}

.row-disabled .related-agents {
  color: hsl(var(--muted-foreground));
}

.row-disabled .name-box {
  color: hsl(var(--muted-foreground));
  background-color: hsl(var(--muted));
  box-shadow: none;
}

/* B. 专家档案 - 文本列表 */
.profile-details {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  padding: 0;
}

.profile-line {
  display: flex;
  font-size: 14px;
  line-height: 1.8;
}

.profile-line .label {
  flex-shrink: 0;
  width: 170px;
  color: hsl(var(--muted-foreground));
}

.profile-line .value {
  font-weight: 400;
  color: hsl(var(--foreground));
}

.highlight-blue {
  font-weight: 500;
  color: hsl(var(--primary)) !important;
}

.bold-value {
  font-weight: 600;
  color: hsl(var(--foreground));
}

/* C. 状态 - Switch */
.col-status {
  display: flex;
  align-items: center;
  justify-content: center;
}

.status-wrapper {
  text-align: center;
}

.status-text {
  margin-top: 10px;
  font-size: 13px;
  font-weight: 500;
}

.text-blue {
  color: hsl(var(--primary));
}

.text-default-enabled {
  color: hsl(var(--primary) / 45%);
}

.text-muted {
  color: hsl(var(--muted-foreground));
}

.custom-switch {
  transform: scale(1.1);
}

:deep(.switch-default.ant-switch-checked.ant-switch-disabled) {
  background-color: hsl(var(--primary) / 45%) !important;
}

:deep(
  .switch-default.ant-switch-checked.ant-switch-disabled .ant-switch-inner
) {
  opacity: 0.6;
}

/* D. 操作区域 - 纵向布局 */
.action-layout {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
  width: 100%;
}

.col-action {
  display: flex;
  align-items: center;
  justify-content: center;
}

.action-link,
.action-link-weak {
  width: 100%;
  padding: 2px 0;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--primary));
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  background: none;
  border: none;
  transition: opacity 0.2s ease;
}

.action-link-vertical {
  display: block;
  width: 100%;
}

.action-link:hover,
.action-link-weak:hover {
  text-decoration: underline;
  opacity: 0.7;
}

.action-link-weak {
  color: hsl(var(--muted-foreground) / 70%);
}

.action-link-danger {
  width: 100%;
  padding: 2px 0;
  font-size: 14px;
  font-weight: 500;
  color: hsl(var(--destructive));
  text-align: center;
  text-decoration: none;
  cursor: pointer;
  background: none;
  border: none;
  transition: opacity 0.2s ease;
}

.action-link-danger:hover {
  text-decoration: underline;
  opacity: 0.7;
}

.pagination-wrapper {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

/* 整体状态淡化 */
.row-disabled .col-profile,
.row-disabled .action-link {
  opacity: 0.4;
}

/* 强制去除 Vben 或 Ant Design 的干扰 */
:deep(.ant-switch-disabled) {
  opacity: 0.8 !important;
}
</style>
