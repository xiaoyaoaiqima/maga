<script setup lang="ts">
import type { JobApi, JobVariantApi } from '#/api/core/job';

import { computed, onMounted, ref, watch } from 'vue';

import {
  Alert,
  Button,
  Card,
  Divider,
  Drawer,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Textarea,
} from 'ant-design-vue';

import {
  getAgentApi,
  getAgentSimpleListApi,
  getTenantSimpleListApi,
} from '#/api/core/business';
import {
  createJobVariantApi,
  deleteJobVariantApi,
  disableJobVariantApi,
  getExpertConfigApi,
  getJobVariantListApi,
  updateJobVariantApi,
} from '#/api/core/job';

type VariantRow = JobVariantApi.JobVariant;

const loading = ref(false);
const dataSource = ref<VariantRow[]>([]);

const tenantOptions = ref<Array<{ label: string; value: number }>>([]);
const agentOptions = ref<Array<{ label: string; value: string }>>([]);

const filters = ref({
  tenant_id: undefined as number | undefined,
  agent_code: undefined as string | undefined,
  enabled: true as boolean,
  keyword: '',
});

const drawerOpen = ref(false);
const editingVariantId = ref<null | string>(null);
const isEdit = computed(() => !!editingVariantId.value);

const editorForm = ref({
  tenant_id: undefined as number | undefined,
  agent_code: undefined as string | undefined,
  variant_name: '',
  tags: [] as string[],
  enabled: true,
  remark: '',
  expert_config_code_list: [] as string[],
  expert_param_config_text: '{\n  \n}\n',
});

type ExpertMeta = {
  code: string;
  model: null | string;
  name: string;
  plugin_config: JobApi.ExpertPluginConfigItem[];
  type: string;
};

type VariableCatalogEntry = {
  options: string[];
  plugin_codes: string[];
  variable_name: string;
};

const paramEditorOpen = ref(false);
const expertMetaLoading = ref(false);
const expertMetaMap = ref<Record<string, ExpertMeta>>({});
// 可视化编辑器：每个 Expert 的“变量 → 已选 context_name”（临时态，关闭弹窗即丢）
const visualSelections = ref<
  Record<string, Record<string, string | undefined>>
>({});

const columns = [
  {
    title: '名称',
    dataIndex: 'variant_name',
    key: 'variant_name',
    width: 200,
    ellipsis: true,
  },
  { title: '标签', dataIndex: 'tags', key: 'tags', width: 180 },
  { title: '租户', dataIndex: 'tenant_id', key: 'tenant_id', width: 90 },
  {
    title: 'Agent',
    dataIndex: 'agent_code',
    key: 'agent_code',
    width: 160,
    ellipsis: true,
  },
  { title: '状态', dataIndex: 'enabled', key: 'enabled', width: 80 },
  {
    title: '更新时间',
    dataIndex: 'update_time',
    key: 'update_time',
    width: 150,
  },
  {
    title: '操作',
    dataIndex: 'action',
    key: 'action',
    width: 300,
    fixed: true,
  },
];

async function fetchTenants() {
  const data = await getTenantSimpleListApi();
  tenantOptions.value = data.map((x) => ({
    label: `${x.tenant_name} (${x.tenant_code})`,
    value: x.id,
  }));
}

async function fetchAgents(tenantId: number) {
  const agents = await getAgentSimpleListApi(tenantId);
  agentOptions.value = agents.map((x) => ({
    label: `${x.agent_name} (${x.agent_code})`,
    value: x.agent_code,
  }));
}

async function loadList() {
  loading.value = true;
  try {
    const list = await getJobVariantListApi({
      tenant_id: filters.value.tenant_id,
      agent_code: filters.value.agent_code,
      enabled: filters.value.enabled,
      keyword: filters.value.keyword?.trim() || undefined,
      limit: 200,
      skip: 0,
    });
    dataSource.value = list || [];
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(`加载方案库失败${detail ? `：${detail}` : ''}`);
  } finally {
    loading.value = false;
  }
}

function openCreateDrawer() {
  editingVariantId.value = null;
  editorForm.value = {
    tenant_id: filters.value.tenant_id,
    agent_code: filters.value.agent_code,
    variant_name: '',
    tags: [],
    enabled: true,
    remark: '',
    expert_config_code_list: [],
    expert_param_config_text: '{\n  \n}\n',
  };
  drawerOpen.value = true;
}

function openEditDrawer(row: VariantRow) {
  editingVariantId.value = row.variant_id;
  editorForm.value = {
    tenant_id: (row.tenant_id ?? undefined) as any,
    agent_code: (row.agent_code ?? undefined) as any,
    variant_name: row.variant_name,
    tags: row.tags || [],
    enabled: !!row.enabled,
    remark: row.remark || '',
    expert_config_code_list: row.expert_config_code_list || [],
    expert_param_config_text: JSON.stringify(
      row.expert_param_config || {},
      null,
      2,
    ),
  };
  drawerOpen.value = true;
}

function closeDrawer() {
  drawerOpen.value = false;
}

function formatJson() {
  try {
    const obj = JSON.parse(editorForm.value.expert_param_config_text || '{}');
    editorForm.value.expert_param_config_text = JSON.stringify(obj, null, 2);
    message.success('已格式化');
  } catch (error: any) {
    message.error(`JSON 解析失败：${error?.message || ''}`);
  }
}

async function fillExpertConfigListFromAgent() {
  const agentCode = editorForm.value.agent_code;
  if (!agentCode) {
    editorForm.value.expert_config_code_list = [];
    return;
  }
  try {
    const agent = await getAgentApi(agentCode);
    editorForm.value.expert_config_code_list =
      agent.expert_config_code_list || [];
  } catch {
    editorForm.value.expert_config_code_list = [];
  }
}

function normalizeContextOptions(v: string | string[]): string[] {
  if (Array.isArray(v)) return v.filter((x): x is string => !!x);
  return v ? [v] : [];
}

const selectedExperts = computed(() => {
  return editorForm.value.expert_config_code_list.map((code, index) => {
    const meta = expertMetaMap.value[code];
    return {
      order: index + 1,
      code,
      name: meta?.name || code,
      type: meta?.type || '-',
      model: meta?.model || '-',
      plugin_config: meta?.plugin_config || [],
    };
  });
});

const expertVariableCatalog = computed<Record<string, VariableCatalogEntry[]>>(
  () => {
    const result: Record<string, VariableCatalogEntry[]> = {};

    for (const expert of selectedExperts.value) {
      const pluginConfig = expert.plugin_config || [];

      // varName -> { sets: Set<string>[], plugin_codes: Set<string> }
      const occurrences: Record<
        string,
        { plugin_codes: Set<string>; sets: Array<Set<string>> }
      > = {};

      for (const pluginItem of pluginConfig) {
        const pluginCode = pluginItem?.plugin_code;
        if (!pluginCode) continue;

        const mapping = pluginItem?.variable_mapping || {};
        for (const [variableName, rawOptions] of Object.entries(mapping)) {
          const opts = normalizeContextOptions(rawOptions as any);
          if (opts.length === 0) continue;

          if (!occurrences[variableName]) {
            occurrences[variableName] = {
              sets: [],
              plugin_codes: new Set<string>(),
            };
          }
          occurrences[variableName]!.sets.push(new Set(opts));
          occurrences[variableName]!.plugin_codes.add(pluginCode);
        }
      }

      const catalog: VariableCatalogEntry[] = [];
      for (const [variableName, entry] of Object.entries(occurrences)) {
        const sets = entry.sets;
        if (sets.length === 0) continue;

        let intersection = new Set<string>(sets[0]);
        for (let i = 1; i < sets.length; i++) {
          const nextSet = sets[i]!;
          intersection = new Set(
            [...intersection].filter((x) => nextSet.has(x)),
          );
        }

        catalog.push({
          variable_name: variableName,
          options: [...intersection].toSorted(),
          plugin_codes: [...entry.plugin_codes].toSorted(),
        });
      }

      result[expert.code] = catalog.toSorted((a, b) =>
        a.variable_name.localeCompare(b.variable_name),
      );
    }

    return result;
  },
);

const emptyIntersectionWarnings = computed(() => {
  const warnings: Array<{ expert_code: string; variable_name: string }> = [];
  for (const expert of selectedExperts.value) {
    const list = expertVariableCatalog.value[expert.code] || [];
    for (const v of list) {
      if (v.options.length === 0) {
        warnings.push({
          expert_code: expert.code,
          variable_name: v.variable_name,
        });
      }
    }
  }
  return warnings;
});

async function ensureExpertMetasLoaded() {
  const codes = editorForm.value.expert_config_code_list || [];
  const missing = codes.filter((c) => !!c && !expertMetaMap.value[c]);
  if (missing.length === 0) return;

  expertMetaLoading.value = true;
  try {
    const results = await Promise.all(
      missing.map(async (code) => {
        try {
          const cfg = await getExpertConfigApi(code);
          return { code, cfg } as const;
        } catch {
          return { code, cfg: null } as const;
        }
      }),
    );
    const next = { ...expertMetaMap.value };
    for (const r of results) {
      if (!r.cfg) continue;
      next[r.code] = {
        code: r.code,
        name: r.cfg.expert_config_name || r.code,
        type: r.cfg.expert_type || '-',
        model: r.cfg.model_code ?? null,
        plugin_config: r.cfg.plugin_config || [],
      };
    }
    expertMetaMap.value = next;
  } finally {
    expertMetaLoading.value = false;
  }
}

function initVisualSelections() {
  const next: Record<string, Record<string, string | undefined>> = {};
  let parsed: any = {};
  try {
    parsed = JSON.parse(editorForm.value.expert_param_config_text || '{}');
  } catch {
    parsed = {};
    message.warning(
      '当前 expert_param_config JSON 不合法，已以空配置打开可视化编辑',
    );
  }

  for (const expert of selectedExperts.value) {
    next[expert.code] = {};
    const saved = parsed?.[expert.code];
    if (Array.isArray(saved)) {
      for (const pluginItem of saved) {
        const mapping = pluginItem?.variable_mapping || {};
        for (const [variableName, contextName] of Object.entries(mapping)) {
          if (typeof contextName === 'string' && contextName) {
            next[expert.code]![variableName] = contextName;
          }
        }
      }
    }
  }
  visualSelections.value = next;
}

function setVisualSelection(
  expertCode: string,
  variableName: string,
  v: null | string | undefined,
) {
  if (!visualSelections.value[expertCode]) {
    visualSelections.value[expertCode] = {};
  }
  if (!v) {
    delete visualSelections.value[expertCode]![variableName];
    return;
  }
  visualSelections.value[expertCode]![variableName] = v;
}

async function openParamEditor() {
  if (!editorForm.value.agent_code) {
    message.warning('请先选择 Agent');
    return;
  }
  if (editorForm.value.expert_config_code_list.length === 0) {
    message.warning('当前 Agent 未加载 Expert 编排，请先选择 Agent');
    return;
  }
  await ensureExpertMetasLoaded();
  initVisualSelections();
  paramEditorOpen.value = true;
}

function closeParamEditor() {
  paramEditorOpen.value = false;
}

function resetParamEditor() {
  for (const expertCode of Object.keys(visualSelections.value)) {
    visualSelections.value[expertCode] = {};
  }
}

function saveParamEditorToJson() {
  const nextExpertParamConfig: Record<
    string,
    JobApi.PluginConfigSnapshotItem[]
  > = {};

  for (const expert of selectedExperts.value) {
    const pluginConfig = expert.plugin_config || [];
    if (pluginConfig.length === 0) continue;

    const picked = visualSelections.value[expert.code] || {};
    const snapshot: JobApi.PluginConfigSnapshotItem[] = [];

    for (const pluginItem of pluginConfig) {
      const pluginCode = pluginItem?.plugin_code;
      if (!pluginCode) continue;

      const mapping = pluginItem?.variable_mapping || {};
      const pickedMapping: Record<string, string> = {};
      for (const variableName of Object.keys(mapping)) {
        const v = picked[variableName];
        if (typeof v === 'string' && v) {
          pickedMapping[variableName] = v;
        }
      }

      if (Object.keys(pickedMapping).length > 0) {
        snapshot.push({
          plugin_code: pluginCode,
          variable_mapping: pickedMapping,
        });
      }
    }

    if (snapshot.length > 0) {
      nextExpertParamConfig[expert.code] = snapshot;
    }
  }

  editorForm.value.expert_param_config_text = JSON.stringify(
    nextExpertParamConfig,
    null,
    2,
  );
  message.success(
    '已生成 expert_param_config JSON（未选择的变量仍按随机处理）',
  );
  closeParamEditor();
}

async function handleSubmit() {
  try {
    const expertParamConfig = JSON.parse(
      editorForm.value.expert_param_config_text || '{}',
    );

    if (!editorForm.value.variant_name.trim()) {
      message.warning('请输入方案名称');
      return;
    }
    if (!editorForm.value.agent_code) {
      message.warning('请选择 Agent（用于限定该方案可复用的编排）');
      return;
    }

    if (isEdit.value) {
      await updateJobVariantApi(editingVariantId.value!, {
        tenant_id: editorForm.value.tenant_id,
        agent_code: editorForm.value.agent_code,
        variant_name: editorForm.value.variant_name.trim(),
        tags: editorForm.value.tags,
        enabled: editorForm.value.enabled,
        remark: editorForm.value.remark || undefined,
        expert_config_code_list: editorForm.value.expert_config_code_list,
        expert_param_config: expertParamConfig,
      });
      message.success('更新成功');
    } else {
      await createJobVariantApi({
        tenant_id: editorForm.value.tenant_id,
        agent_code: editorForm.value.agent_code,
        variant_name: editorForm.value.variant_name.trim(),
        tags: editorForm.value.tags,
        enabled: editorForm.value.enabled,
        remark: editorForm.value.remark || undefined,
        expert_config_code_list: editorForm.value.expert_config_code_list,
        expert_param_config: expertParamConfig,
      });
      message.success('创建成功');
    }
    closeDrawer();
    await loadList();
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(
      `${isEdit.value ? '更新失败' : '创建失败'}${detail ? `：${detail}` : ''}`,
    );
  }
}

async function handleDisable(row: VariantRow) {
  try {
    await disableJobVariantApi(row.variant_id);
    message.success('已禁用');
    await loadList();
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(`禁用失败${detail ? `：${detail}` : ''}`);
  }
}

async function handleDelete(row: VariantRow) {
  try {
    await deleteJobVariantApi(row.variant_id);
    message.success('删除成功');
    await loadList();
  } catch (error: any) {
    const detail =
      error?.response?.data?.detail ??
      error?.response?.data?.message ??
      error?.message ??
      '';
    message.error(`删除失败${detail ? `：${detail}` : ''}`);
  }
}

watch(
  () => filters.value.tenant_id,
  async (tenantId) => {
    agentOptions.value = [];
    filters.value.agent_code = undefined;
    if (tenantId) {
      await fetchAgents(tenantId);
    }
  },
);

watch(
  () => editorForm.value.tenant_id,
  async (tenantId) => {
    agentOptions.value = [];
    editorForm.value.agent_code = undefined;
    editorForm.value.expert_config_code_list = [];
    if (tenantId) {
      await fetchAgents(tenantId);
    }
  },
);

watch(
  () => editorForm.value.agent_code,
  async () => {
    await fillExpertConfigListFromAgent();
  },
);

onMounted(async () => {
  await fetchTenants();
  await loadList();
});
</script>

<template>
  <div class="variant-library-page">
    <Card :bordered="false" :loading="loading" title="方案库（Variant）">
      <Alert
        class="alert-info"
        type="info"
        show-icon
        message="说明"
        description="Variant 用于沉淀可复用的组合模板（expert_param_config），可在创建任务时直接选择并分配占比。"
      />

      <div class="toolbar">
        <Space>
          <Select
            v-model:value="filters.tenant_id"
            :options="tenantOptions"
            allow-clear
            placeholder="筛选租户"
            style="width: 260px"
            show-search
          />
          <Select
            v-model:value="filters.agent_code"
            :options="agentOptions"
            allow-clear
            placeholder="筛选 Agent"
            style="width: 260px"
            show-search
          />
          <Select
            v-model:value="filters.enabled"
            :options="[
              { label: '仅启用', value: true },
              { label: '仅禁用', value: false },
            ]"
            style="width: 120px"
          />
          <Input
            v-model:value="filters.keyword"
            placeholder="名称/备注关键字"
            style="width: 220px"
            allow-clear
          />
          <Button @click="loadList">查询</Button>
        </Space>

        <Space>
          <Button type="primary" @click="openCreateDrawer">+ 新建方案</Button>
        </Space>
      </div>

      <Table
        :data-source="dataSource"
        :columns="columns"
        :pagination="false"
        row-key="variant_id"
        size="middle"
        :scroll="{ x: 1200 }"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'tags'">
            <Space wrap>
              <Tag v-for="t in record.tags" :key="t" color="blue">{{ t }}</Tag>
              <span
                v-if="(record.tags?.length ?? 0) === 0"
                class="text-muted-foreground"
                >-</span
              >
            </Space>
          </template>
          <template v-else-if="column.key === 'enabled'">
            <Tag :color="record.enabled ? 'green' : 'red'">
              {{ record.enabled ? '启用' : '禁用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button type="link" @click="openEditDrawer(record)">编辑</Button>
              <Popconfirm
                title="确认禁用该方案？禁用后将不会出现在 Job 创建页的方案库选择列表。"
                ok-text="禁用"
                cancel-text="取消"
                @confirm="handleDisable(record)"
              >
                <Button type="link" danger :disabled="!record.enabled">
                  禁用
                </Button>
              </Popconfirm>
              <Divider type="vertical" />
              <Popconfirm
                title="确认删除该方案？删除后不可恢复。"
                ok-text="删除"
                cancel-text="取消"
                @confirm="handleDelete(record)"
              >
                <Button type="link" danger>删除</Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>

      <Drawer
        :open="drawerOpen"
        :title="isEdit ? '编辑方案' : '新建方案'"
        width="780"
        @close="closeDrawer"
      >
        <Form layout="vertical">
          <FormItem label="租户（可选）">
            <Select
              v-model:value="editorForm.tenant_id"
              :options="tenantOptions"
              allow-clear
              placeholder="NULL 表示全局共享"
              show-search
              :get-popup-container="(trigger) => trigger.parentElement"
            />
          </FormItem>
          <FormItem label="Agent（必选）">
            <Select
              v-model:value="editorForm.agent_code"
              :options="agentOptions"
              placeholder="请选择 Agent"
              show-search
              :get-popup-container="(trigger) => trigger.parentElement"
            />
            <div class="form-tip">
              💡 该方案会绑定 Agent，用于保证 expert_config_code_list
              与参数结构可复用。
            </div>
          </FormItem>
          <FormItem label="方案名称（必填）">
            <Input
              v-model:value="editorForm.variant_name"
              :maxlength="255"
              show-count
            />
          </FormItem>
          <FormItem label="标签">
            <Select
              v-model:value="editorForm.tags"
              mode="tags"
              placeholder="输入后回车添加"
              style="width: 100%"
              show-search
              :filter-option="true"
              :get-popup-container="(trigger) => trigger.parentElement"
            />
          </FormItem>
          <FormItem label="启用状态">
            <Switch v-model:checked="editorForm.enabled" />
            <span class="switch-label">{{
              editorForm.enabled ? '启用' : '禁用'
            }}</span>
          </FormItem>
          <FormItem label="Expert 编排顺序（快照）">
            <Space wrap>
              <Tag
                v-for="c in editorForm.expert_config_code_list"
                :key="c"
                color="purple"
              >
                {{ c }}
              </Tag>
              <span
                v-if="editorForm.expert_config_code_list.length === 0"
                class="text-muted-foreground"
              >
                未加载（请选择 Agent）
              </span>
            </Space>
          </FormItem>
          <FormItem label="expert_param_config（JSON）">
            <div class="json-toolbar">
              <Space>
                <Button @click="openParamEditor">… 可视化配置</Button>
                <Button @click="formatJson">格式化</Button>
              </Space>
            </div>
            <Textarea
              v-model:value="editorForm.expert_param_config_text"
              :rows="16"
              placeholder="请输入 JSON：{ expert_code: [{ plugin_code, variable_mapping }] }"
            />
            <div class="form-tip">
              💡 变量值必须是 context_name（与 Job 创建页“组合变量配置”一致）。
            </div>
          </FormItem>
          <FormItem label="备注">
            <Textarea
              v-model:value="editorForm.remark"
              :rows="3"
              :maxlength="255"
              show-count
            />
          </FormItem>

          <div class="drawer-footer">
            <Space>
              <Button @click="closeDrawer">取消</Button>
              <Button type="primary" @click="handleSubmit">
                {{ isEdit ? '保存' : '创建' }}
              </Button>
            </Space>
          </div>
        </Form>
      </Drawer>

      <Modal
        v-model:open="paramEditorOpen"
        title="expert_param_config 可视化配置"
        :width="920"
        ok-text="生成 JSON 并保存"
        cancel-text="取消"
        :ok-button-props="{ loading: expertMetaLoading }"
        @ok="saveParamEditorToJson"
        @cancel="closeParamEditor"
      >
        <Alert
          class="alert-info"
          type="info"
          show-icon
          message="说明"
          description="这里配置的是“Variant 的变量选择”。未选择的变量将保持随机；生成后会回填到下方 JSON 文本框，仍可手动微调。"
        />

        <Alert
          v-if="emptyIntersectionWarnings.length > 0"
          class="alert-warning"
          message="存在无交集变量"
          :description="`以下变量在同名跨多个 plugin 时候选值交集为空：${emptyIntersectionWarnings
            .slice(0, 8)
            .map((x) => `${x.expert_code}.${x.variable_name}`)
            .join(
              '、',
            )}${emptyIntersectionWarnings.length > 8 ? '…' : ''}。该变量将无法随机/无法选择，请检查 Expert 的 plugin_config.variable_mapping 配置。`"
          show-icon
          type="warning"
        />

        <div class="param-editor-toolbar">
          <Space>
            <Button @click="resetParamEditor">清空选择（回到随机）</Button>
          </Space>
          <Space>
            <Tag v-if="expertMetaLoading" color="blue">
              Expert 元数据加载中…
            </Tag>
            <Tag color="purple">{{ selectedExperts.length }} 个 Expert</Tag>
          </Space>
        </div>

        <Divider style="margin: 12px 0" />

        <div class="param-editor">
          <div
            v-for="expert in selectedExperts"
            :key="expert.code"
            class="expert-card"
          >
            <div class="expert-card-header">
              <div class="expert-title">
                <span class="expert-name"
                  >{{ expert.order }}. {{ expert.name }}</span
                >
                <Tag color="blue">{{ expert.code }}</Tag>
              </div>
              <div class="expert-meta text-muted-foreground">
                <span>{{ expert.type }}</span>
                <span v-if="expert.model && expert.model !== '-'">
                  · {{ expert.model }}</span
                >
              </div>
            </div>

            <Divider style="margin: 10px 0" />

            <div
              v-if="(expertVariableCatalog[expert.code]?.length ?? 0) === 0"
              class="empty-flow"
            >
              <span class="text-muted-foreground">
                该 Expert 未配置变量（plugin_config 为空或无
                variable_mapping）。
              </span>
            </div>

            <div v-else class="vars">
              <div
                v-for="v in expertVariableCatalog[expert.code]"
                :key="`${expert.code}-${v.variable_name}`"
                class="var-row"
              >
                <div class="var-name">
                  <span class="var-key">{{ v.variable_name }}</span>
                  <Tag v-if="v.plugin_codes.length > 1" color="purple">
                    跨 {{ v.plugin_codes.length }} 个 plugin
                  </Tag>
                  <Tag v-if="v.options.length === 0" color="red">无交集</Tag>
                </div>

                <div class="var-select">
                  <Select
                    :value="visualSelections[expert.code]?.[v.variable_name]"
                    :options="v.options.map((x) => ({ label: x, value: x }))"
                    :disabled="v.options.length === 0"
                    allow-clear
                    placeholder="不选=随机"
                    style="width: 520px"
                    @update:value="
                      (val) =>
                        setVisualSelection(
                          expert.code,
                          v.variable_name,
                          val as any,
                        )
                    "
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </Modal>
    </Card>
  </div>
</template>

<style scoped>
.variant-library-page {
  padding: 16px;
}

.alert-info {
  margin-bottom: 16px;
}

.alert-warning {
  margin-bottom: 12px;
}

.toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.form-tip {
  margin-top: 6px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.json-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
  margin-top: 16px;
  border-top: 1px solid hsl(var(--border));
}

.switch-label {
  margin-left: 8px;
  color: hsl(var(--muted-foreground));
}

.param-editor-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
}

.param-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 64vh;
  padding-right: 4px;
  overflow: auto;
}

.param-editor .expert-card {
  padding: 12px;
  cursor: default;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.param-editor .expert-card-header {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.param-editor .expert-title {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
}

.param-editor .expert-name {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.param-editor .expert-meta {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.param-editor .vars {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.param-editor .var-row {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.param-editor .var-name {
  display: flex;
  gap: 8px;
  align-items: center;
  min-width: 240px;
}

.param-editor .var-key {
  font-family: 'SF Mono', Monaco, Inconsolata, monospace;
  font-size: 13px;
  color: hsl(var(--foreground));
}

.empty-flow {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px 0;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
</style>
