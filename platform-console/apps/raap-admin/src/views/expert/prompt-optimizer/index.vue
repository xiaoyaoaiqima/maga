<script setup lang="ts">
import type { PromptOptimizerApi } from '#/api/core/prompt-optimizer';

import { computed, reactive, ref } from 'vue';

import { Page } from '@vben/common-ui';

import {
  CheckOutlined,
  CopyOutlined,
  PlayCircleOutlined,
  SaveOutlined,
} from '@ant-design/icons-vue';
import {
  Alert,
  Button,
  Empty,
  Input,
  message,
  Select,
  Space,
  Spin,
  Tag,
  Textarea,
} from 'ant-design-vue';

import {
  applyPromptPatchesApi,
  createPromptOptimizerRunApi,
  updatePromptPatchApi,
} from '#/api/core/prompt-optimizer';

defineOptions({ name: 'ExpertPromptOptimizer' });

const modeOptions = [
  { label: '局部修补', value: 'local_patch' },
  { label: '全局整理', value: 'global_refactor' },
  { label: '审核优化', value: 'critic_patch' },
  { label: '批量归因', value: 'batch_patch' },
];

const form = reactive({
  mode: 'global_refactor' as PromptOptimizerApi.OptimizerMode,
  prompt_name: '提示词优化工作台草稿',
  prompt_content: '',
  problem_text: '',
  generated_title: '',
  generated_content: '',
  model: '',
  base_url: '',
  temperature: 0.2,
  max_tokens: 8000,
});

const running = ref(false);
const saving = ref(false);
const runResult = ref<PromptOptimizerApi.Run | null>(null);

const needsGeneratedContent = computed(() =>
  ['batch_patch', 'critic_patch', 'local_patch'].includes(form.mode),
);

const parsedOutput = computed(() => runResult.value?.parsed_output ?? null);
const patches = computed(() => runResult.value?.patches ?? []);
const acceptedPatchIds = computed(() =>
  patches.value
    .filter((patch) => ['accepted', 'edited'].includes(patch.status))
    .map((patch) => patch.id),
);

async function copyText(text?: null | string) {
  if (!text) return;
  await navigator.clipboard.writeText(text);
  message.success('已复制');
}

async function runOptimizer() {
  if (!form.prompt_content.trim()) {
    message.warning('请先输入提示词');
    return;
  }
  if (!form.problem_text.trim()) {
    message.warning('请先输入人类意见或问题描述');
    return;
  }

  running.value = true;
  runResult.value = null;
  try {
    const result = await createPromptOptimizerRunApi({
      mode: form.mode,
      prompt_name: form.prompt_name,
      prompt_content: form.prompt_content,
      problem_text: form.problem_text,
      generated_title: form.generated_title || undefined,
      generated_content: form.generated_content || undefined,
      model: form.model || undefined,
      base_url: form.base_url || undefined,
      temperature: form.temperature,
      max_tokens: form.max_tokens,
      json_mode: true,
    });
    runResult.value = result;
    if (result.status === 'succeeded') {
      message.success('优化完成');
    } else {
      message.error(result.error_message || '优化失败');
    }
  } catch (error: any) {
    message.error(error?.message || '优化请求失败');
  } finally {
    running.value = false;
  }
}

async function setPatchStatus(
  patch: PromptOptimizerApi.Patch,
  status: PromptOptimizerApi.Patch['status'],
) {
  const updated = await updatePromptPatchApi(patch.id, { status });
  Object.assign(patch, updated);
}

async function saveVersion() {
  if (!runResult.value) return;
  if (acceptedPatchIds.value.length === 0) {
    message.warning('请先接受至少一条 patch');
    return;
  }

  saving.value = true;
  try {
    const result = await applyPromptPatchesApi(runResult.value.id, {
      patch_ids: acceptedPatchIds.value,
      change_summary: '从提示词优化工作台保存新版本',
      save_version: true,
    });
    if (result.conflicts.length > 0) {
      message.warning(`保存完成，但有 ${result.conflicts.length} 条 patch 需要人工处理`);
    } else {
      message.success(`已保存为版本 ${result.new_version?.version_no ?? ''}`);
    }
  } catch (error: any) {
    message.error(error?.message || '保存版本失败');
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Page
    description="用结构化 patches 管理提示词的局部修补、全局整理和审核规则优化。"
    title="提示词优化工作台"
  >
    <div class="prompt-optimizer">
      <section class="panel input-panel">
        <div class="panel-header">
          <div>
            <h2>输入</h2>
            <p>选择模式后粘贴 prompt 和问题描述。</p>
          </div>
          <Button type="primary" :loading="running" @click="runOptimizer">
            <template #icon>
              <PlayCircleOutlined />
            </template>
            运行
          </Button>
        </div>

        <div class="field-grid">
          <label>
            <span>优化模式</span>
            <Select
              v-model:value="form.mode"
              :options="modeOptions"
              class="full"
            />
          </label>
          <label>
            <span>草稿名称</span>
            <Input v-model:value="form.prompt_name" />
          </label>
        </div>

        <label class="stacked">
          <span>原始提示词</span>
          <Textarea
            v-model:value="form.prompt_content"
            :rows="14"
            placeholder="粘贴需要优化的 prompt"
          />
        </label>

        <label class="stacked">
          <span>人类意见 / 审查问题</span>
          <Textarea
            v-model:value="form.problem_text"
            :rows="5"
            placeholder="例如：提示词太冗长，有重复矛盾规则；或某篇内容缺少推荐动作"
          />
        </label>

        <div v-if="needsGeneratedContent" class="generated-fields">
          <label class="stacked">
            <span>生成标题</span>
            <Input v-model:value="form.generated_title" />
          </label>
          <label class="stacked">
            <span>生成内容 / 被审核内容</span>
            <Textarea
              v-model:value="form.generated_content"
              :rows="6"
              placeholder="局部修补、审核优化、批量归因模式建议提供样例内容"
            />
          </label>
        </div>

        <div class="field-grid">
          <label>
            <span>模型</span>
            <Input v-model:value="form.model" placeholder="默认读取后端环境变量" />
          </label>
          <label>
            <span>Base URL</span>
            <Input
              v-model:value="form.base_url"
              placeholder="默认读取后端环境变量"
            />
          </label>
        </div>
      </section>

      <section class="panel result-panel">
        <div class="panel-header">
          <div>
            <h2>结果</h2>
            <p>先审阅 patch，再保存为新版本。</p>
          </div>
          <Space>
            <Button :disabled="!runResult" @click="copyText(runResult?.raw_output)">
              <template #icon>
                <CopyOutlined />
              </template>
              原始输出
            </Button>
            <Button
              type="primary"
              :disabled="acceptedPatchIds.length === 0"
              :loading="saving"
              @click="saveVersion"
            >
              <template #icon>
                <SaveOutlined />
              </template>
              保存版本
            </Button>
          </Space>
        </div>

        <Spin :spinning="running">
          <Empty v-if="!runResult" description="暂无优化结果" />

          <template v-else>
            <Alert
              v-if="runResult.status === 'failed'"
              type="error"
              show-icon
              :message="runResult.error_message || '优化失败'"
            />

            <div v-if="parsedOutput" class="summary">
              <div>
                <span>问题诊断</span>
                <p>{{ parsedOutput.prompt_issue || '-' }}</p>
              </div>
              <div>
                <span>修改建议</span>
                <p>{{ parsedOutput.modify_suggestion || '-' }}</p>
              </div>
              <div v-if="parsedOutput.risk_notes">
                <span>风险提示</span>
                <p>{{ parsedOutput.risk_notes }}</p>
              </div>
            </div>

            <div class="patch-list">
              <div
                v-for="patch in patches"
                :key="patch.id"
                class="patch-item"
              >
                <div class="patch-title">
                  <Space>
                    <Tag color="blue">#{{ patch.patch_index }}</Tag>
                    <Tag>{{ patch.operation }}</Tag>
                    <Tag :color="patch.status === 'accepted' ? 'green' : undefined">
                      {{ patch.status }}
                    </Tag>
                  </Space>
                  <Space>
                    <Button size="small" @click="setPatchStatus(patch, 'rejected')">
                      拒绝
                    </Button>
                    <Button
                      size="small"
                      type="primary"
                      @click="setPatchStatus(patch, 'accepted')"
                    >
                      <template #icon>
                        <CheckOutlined />
                      </template>
                      接受
                    </Button>
                  </Space>
                </div>
                <div class="patch-body">
                  <div>
                    <span>old_text</span>
                    <pre>{{ patch.old_text }}</pre>
                  </div>
                  <div>
                    <span>new_text</span>
                    <pre>{{ patch.new_text || '' }}</pre>
                  </div>
                </div>
                <p class="reason">{{ patch.reason }}</p>
              </div>
            </div>
          </template>
        </Spin>
      </section>
    </div>
  </Page>
</template>

<style scoped>
.prompt-optimizer {
  display: grid;
  grid-template-columns: minmax(420px, 0.95fr) minmax(520px, 1.05fr);
  gap: 16px;
  align-items: start;
}

.panel {
  min-width: 0;
  padding: 16px;
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.panel-header {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 16px;
}

.panel-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.panel-header p {
  margin: 4px 0 0;
  color: hsl(var(--muted-foreground));
}

.field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

label,
.stacked {
  display: grid;
  gap: 6px;
}

label span,
.summary span,
.patch-body span {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.full {
  width: 100%;
}

.stacked {
  margin-bottom: 12px;
}

.generated-fields {
  padding-top: 4px;
}

.summary {
  display: grid;
  gap: 10px;
  margin-bottom: 16px;
}

.summary p {
  margin: 4px 0 0;
  line-height: 1.7;
}

.patch-list {
  display: grid;
  gap: 12px;
}

.patch-item {
  padding: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.patch-title {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.patch-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

pre {
  min-height: 92px;
  max-height: 220px;
  padding: 10px;
  margin: 4px 0 0;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  background: hsl(var(--muted));
  border-radius: 6px;
}

.reason {
  margin: 10px 0 0;
  color: hsl(var(--muted-foreground));
}

@media (max-width: 1100px) {
  .prompt-optimizer,
  .field-grid,
  .patch-body {
    grid-template-columns: 1fr;
  }
}
</style>
