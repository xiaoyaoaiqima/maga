<script setup lang="ts">
import type { JobApi } from '#/api/core/job';

import { ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import {
  Button,
  Descriptions,
  DescriptionsItem,
  Modal,
  Spin,
  Tag,
} from 'ant-design-vue';

import { getExpertConfigApi } from '#/api/core/job';

interface Props {
  open?: boolean;
  expertCode?: null | string;
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  expertCode: null,
});

const emit = defineEmits<{
  (e: 'update:open', value: boolean): void;
}>();

const router = useRouter();
const loading = ref(false);
const expertDetail = ref<JobApi.ExpertConfigBrief | null>(null);

async function fetchExpertDetail() {
  if (!props.expertCode) return;

  loading.value = true;
  try {
    expertDetail.value = await getExpertConfigApi(props.expertCode);
  } catch (error) {
    console.error('获取 Expert 详情失败:', error);
    expertDetail.value = null;
  } finally {
    loading.value = false;
  }
}

function handleClose() {
  emit('update:open', false);
}

function goToEdit() {
  if (!props.expertCode) return;

  // 跳转到 Expert 编辑页
  router.push({
    path: '/config/expert-edit',
    query: { code: props.expertCode },
  });

  handleClose();
}

// 监听弹窗打开和 expertCode 变化
watch(
  () => [props.open, props.expertCode],
  ([open, code]) => {
    if (open && code) {
      fetchExpertDetail();
    } else {
      expertDetail.value = null;
    }
  },
  { immediate: true },
);
</script>

<template>
  <Modal
    :open="open"
    :title="`Expert 详情: ${expertCode || ''}`"
    :width="700"
    :footer="null"
    @cancel="handleClose"
  >
    <Spin :spinning="loading">
      <div v-if="expertDetail" class="expert-detail-content">
        <Descriptions :column="1" bordered size="small">
          <DescriptionsItem label="Expert 编码">
            <code>{{ expertDetail.expert_config_code }}</code>
          </DescriptionsItem>

          <DescriptionsItem label="Expert 名称">
            {{ expertDetail.expert_config_name }}
          </DescriptionsItem>

          <DescriptionsItem label="描述">
            {{ expertDetail.description || '-' }}
          </DescriptionsItem>

          <DescriptionsItem label="Expert 类型">
            <Tag v-if="expertDetail.expert_type" color="purple">
              {{ expertDetail.expert_type }}
            </Tag>
            <span v-else>-</span>
          </DescriptionsItem>

          <DescriptionsItem label="Expert 应用">
            <code v-if="expertDetail.expert_app">{{
              expertDetail.expert_app
            }}</code>
            <span v-else>-</span>
          </DescriptionsItem>

          <DescriptionsItem label="Expert 服务">
            <code v-if="expertDetail.expert_service">{{
              expertDetail.expert_service
            }}</code>
            <span v-else>-</span>
          </DescriptionsItem>

          <DescriptionsItem label="Expert 函数">
            <code v-if="expertDetail.expert_func">{{
              expertDetail.expert_func
            }}</code>
            <span v-else>-</span>
          </DescriptionsItem>

          <DescriptionsItem label="模型">
            <Tag v-if="expertDetail.model_code" color="cyan">
              {{ expertDetail.model_code }}
            </Tag>
            <span v-else>-</span>
          </DescriptionsItem>

          <DescriptionsItem label="启用状态">
            <Tag :color="expertDetail.enabled ? 'success' : 'default'">
              {{ expertDetail.enabled ? '已启用' : '已禁用' }}
            </Tag>
          </DescriptionsItem>

          <DescriptionsItem label="Prompt 模板" :span="1">
            <div v-if="expertDetail.prompt_template" class="prompt-template">
              <pre>{{ expertDetail.prompt_template }}</pre>
            </div>
            <span v-else>-</span>
          </DescriptionsItem>

          <DescriptionsItem
            v-if="
              expertDetail.plugin_config &&
              expertDetail.plugin_config.length > 0
            "
            label="Plugin 配置"
            :span="1"
          >
            <div class="plugin-config-list">
              <div
                v-for="(plugin, idx) in expertDetail.plugin_config"
                :key="idx"
                class="plugin-config-item"
              >
                <div class="plugin-header">
                  <Tag color="blue" size="small">Plugin {{ idx + 1 }}</Tag>
                  <code class="plugin-code">{{ plugin.plugin_code }}</code>
                </div>
                <div
                  v-if="
                    plugin.variable_mapping &&
                    Object.keys(plugin.variable_mapping).length > 0
                  "
                  class="variable-mapping"
                >
                  <div
                    v-for="[varName, contextNames] in Object.entries(
                      plugin.variable_mapping,
                    )"
                    :key="varName"
                    class="variable-item"
                  >
                    <span class="variable-name">{{ varName }}:</span>
                    <span class="variable-value">
                      <template v-if="Array.isArray(contextNames)">
                        {{ contextNames.join(', ') }}
                      </template>
                      <template v-else>
                        {{ contextNames }}
                      </template>
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </DescriptionsItem>
        </Descriptions>

        <div class="modal-footer">
          <Button @click="goToEdit" type="primary"> ✏️ 去编辑 </Button>
          <Button @click="handleClose">关闭</Button>
        </div>
      </div>
      <div v-else-if="!loading" class="empty-detail">暂无 Expert 详情</div>
    </Spin>
  </Modal>
</template>

<style scoped>
.expert-detail-content {
  padding: 8px 0;
}

.expert-detail-content :deep(.ant-descriptions-item-label) {
  width: 120px;
  font-weight: 500;
}

.expert-detail-content code {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

.prompt-template {
  padding: 12px;
  overflow-x: auto;
  background: hsl(var(--muted) / 30%);
  border-radius: 6px;
}

.prompt-template pre {
  margin: 0;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-all;
  white-space: pre-wrap;
}

.plugin-config-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.plugin-config-item {
  padding: 12px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.plugin-header {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}

.plugin-code {
  padding: 2px 6px;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  background: hsl(var(--muted));
  border-radius: 4px;
}

.variable-mapping {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-left: 12px;
}

.variable-item {
  display: flex;
  gap: 8px;
  font-size: 13px;
}

.variable-name {
  min-width: 100px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
}

.variable-value {
  flex: 1;
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 12px;
  color: hsl(var(--foreground));
}

.modal-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding-top: 16px;
  margin-top: 20px;
  border-top: 1px solid hsl(var(--border));
}

.empty-detail {
  padding: 40px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}
</style>
