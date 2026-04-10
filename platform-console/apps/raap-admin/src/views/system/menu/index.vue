<script setup lang="ts">
import { computed, h, onMounted, reactive, ref, watch } from 'vue';

import { IconPicker } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Menu as AMenu,
  MenuItem as AMenuItem,
  Button,
  Card,
  Dropdown,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Modal,
  Popconfirm,
  Radio,
  RadioGroup,
  Space,
  Switch,
  Table,
  Tag,
  TreeSelect,
} from 'ant-design-vue';

import { requestClient } from '#/api/request';

interface Menu {
  id: string;
  parent_id: string;
  menu_name: string;
  menu_type: string; // M=目录, C=菜单, F=按钮
  path: null | string;
  component: null | string;
  icon: null | string;
  perm_code: null | string;
  sort_order: number;
  visible: number;
  status: number;
  created_at: string;
  updated_at: string;
  children?: Menu[];
}

interface TreeMenuItem {
  id: string;
  parent_id: string;
  menu_name: string;
  menu_type: string;
  path: null | string;
  component: null | string;
  icon: null | string;
  perm_code: null | string;
  sort_order: number;
  visible: number;
  children: TreeMenuItem[];
}

const loading = ref(false);
const dataSource = ref<TreeMenuItem[]>([]);
const flatMenuList = ref<Menu[]>([]);
const modalVisible = ref(false);
const editingMenu = ref<Menu | null>(null);
const isSubmitting = ref(false);
const formRef = ref();

const formState = reactive({
  parent_id: '0',
  menu_name: '',
  menu_type: 'M',
  path: '',
  component: '',
  icon: '',
  perm_code: '',
  sort_order: 0,
  visible: 1,
  status: 1,
});

const columns = [
  { title: '菜单名称', dataIndex: 'menu_name', key: 'menu_name', width: 200 },
  {
    title: '图标',
    dataIndex: 'icon',
    key: 'icon',
    width: 60,
    align: 'center' as const,
  },
  {
    title: '图标代码',
    dataIndex: 'icon',
    key: 'icon_code',
    width: 180,
    ellipsis: true,
  },
  { title: '类型', dataIndex: 'menu_type', key: 'menu_type', width: 80 },
  { title: '路由路径', dataIndex: 'path', key: 'path', width: 180 },
  {
    title: '组件路径',
    dataIndex: 'component',
    key: 'component',
    width: 200,
    ellipsis: true,
  },
  { title: '权限标识', dataIndex: 'perm_code', key: 'perm_code', width: 150 },
  { title: '排序', dataIndex: 'sort_order', key: 'sort_order', width: 70 },
  { title: '状态', dataIndex: 'visible', key: 'visible', width: 80 },
  { title: '操作', key: 'action', width: 180, fixed: 'right' as const },
];

const menuTypeOptions = [
  { value: 'M', label: '目录' },
  { value: 'C', label: '菜单' },
  { value: 'F', label: '按钮' },
];

const menuTypeMap: Record<string, { color: string; label: string }> = {
  M: { label: '目录', color: 'blue' },
  C: { label: '菜单', color: 'green' },
  F: { label: '按钮', color: 'orange' },
};

const searchText = ref('');

function filterTreeByKeyword(
  items: TreeMenuItem[],
  keyword: string,
): TreeMenuItem[] {
  if (!keyword) return items;
  const k = keyword.toLowerCase();
  const matchNode = (item: TreeMenuItem) =>
    item.menu_name.toLowerCase().includes(k) ||
    (item.path || '').toLowerCase().includes(k) ||
    (item.perm_code || '').toLowerCase().includes(k) ||
    (item.component || '').toLowerCase().includes(k);

  const loop = (list: TreeMenuItem[]): TreeMenuItem[] => {
    const result: TreeMenuItem[] = [];
    for (const item of list) {
      const children = item.children ? loop(item.children) : [];
      if (matchNode(item) || children.length > 0) {
        result.push({ ...item, children });
      }
    }
    return result;
  };
  return loop(items);
}

const displayData = computed(() =>
  filterTreeByKeyword(dataSource.value, searchText.value),
);

const IconInputVNode = h(Input);

// 清理空的 children 数组，避免表格显示无用的展开按钮
function cleanEmptyChildren(items: TreeMenuItem[]): TreeMenuItem[] {
  return items.map((item) => {
    const newItem = { ...item };
    if (newItem.children && newItem.children.length > 0) {
      newItem.children = cleanEmptyChildren(newItem.children);
    } else {
      // 删除空的 children 数组，这样表格不会显示展开按钮
      delete (newItem as any).children;
    }
    return newItem;
  });
}

// 获取菜单树
async function fetchMenus() {
  loading.value = true;
  try {
    const response = await requestClient.get<TreeMenuItem[]>(
      '/v1/system/menus/tree/full',
    );
    // 清理空的 children，避免显示无用的展开按钮
    dataSource.value = cleanEmptyChildren(response || []);
  } catch (error) {
    console.error('获取菜单树失败:', error);
    message.error('获取菜单树失败');
  } finally {
    loading.value = false;
  }
}

// 获取扁平菜单列表（用于父菜单选择）
async function fetchFlatMenus() {
  try {
    const response = await requestClient.get<Menu[]>('/v1/system/menus');
    flatMenuList.value = response || [];
  } catch (error) {
    console.error('获取菜单列表失败:', error);
  }
}

// 构建父菜单选择树
const parentMenuTree = computed(() => {
  const buildTree = (items: Menu[], parentId: string = '0'): any[] => {
    return items
      .filter((item) => item.parent_id === parentId && item.menu_type !== 'F')
      .map((item) => ({
        value: item.id,
        title: item.menu_name,
        children: buildTree(items, item.id),
      }));
  };

  return [
    {
      value: '0',
      title: '顶级菜单',
      children: buildTree(flatMenuList.value),
    },
  ];
});

function handleAdd(parentId: string = '0') {
  editingMenu.value = null;
  formState.parent_id = parentId;
  formState.menu_name = '';
  formState.menu_type = parentId === '0' ? 'M' : 'C';
  formState.path = '';
  formState.component = '';
  formState.icon = '';
  formState.perm_code = '';
  formState.sort_order = 0;
  formState.visible = 1;
  formState.status = 1;
  formRef.value?.resetFields();
  modalVisible.value = true;
}

function handleAddChild(record: Menu) {
  handleAdd(record.id);
}

function handleEdit(record: Menu) {
  editingMenu.value = record;
  formState.parent_id = record.parent_id || '0';
  formState.menu_name = record.menu_name;
  formState.menu_type = record.menu_type;
  formState.path = record.path || '';
  formState.component = record.component || '';
  formState.icon = record.icon || '';
  formState.perm_code = record.perm_code || '';
  formState.sort_order = record.sort_order;
  formState.visible = record.visible;
  formState.status = record.status;
  modalVisible.value = true;
}

async function handleDelete(record: Menu) {
  try {
    await requestClient.delete(`/v1/system/menus/${record.id}`);
    message.success(`菜单 "${record.menu_name}" 删除成功`);
    fetchMenus();
    fetchFlatMenus();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '删除失败';
    message.error(errorMsg);
  }
}

async function handleSubmit() {
  try {
    isSubmitting.value = true;
    await formRef.value?.validate();

    const payload = {
      parent_id: formState.parent_id,
      menu_name: formState.menu_name,
      menu_type: formState.menu_type,
      path: formState.path || null,
      component: formState.component || null,
      icon: formState.icon || null,
      perm_code: formState.perm_code || null,
      sort_order: formState.sort_order,
      visible: formState.visible,
      status: formState.status,
    };

    if (editingMenu.value) {
      // 更新
      await requestClient.put(
        `/v1/system/menus/${editingMenu.value.id}`,
        payload,
      );
      message.success(`菜单 "${formState.menu_name}" 更新成功`);
    } else {
      // 创建
      await requestClient.post('/v1/system/menus', payload);
      message.success(`菜单 "${formState.menu_name}" 创建成功`);
    }
    modalVisible.value = false;
    fetchMenus();
    fetchFlatMenus();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '操作失败';
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

// 展开的行 keys
const expandedRowKeys = ref<string[]>([]);

// 计算所有有子节点的行 ID（用于初始展开）
function getAllExpandableKeys(items: TreeMenuItem[]): string[] {
  const keys: string[] = [];
  const traverse = (list: TreeMenuItem[]) => {
    list.forEach((item) => {
      if (item.children && item.children.length > 0) {
        keys.push(item.id);
        traverse(item.children);
      }
    });
  };
  traverse(items);
  return keys;
}

// 监听数据变化，自动展开所有节点
watch(
  displayData,
  (newData) => {
    expandedRowKeys.value = getAllExpandableKeys(newData);
  },
  { immediate: true },
);

// 展开/收起事件处理
function handleExpand(expanded: boolean, record: TreeMenuItem) {
  expandedRowKeys.value = expanded
    ? [...expandedRowKeys.value, record.id]
    : expandedRowKeys.value.filter((key) => key !== record.id);
}

// 导出菜单数据
function downloadFile(content: string, filename: string, type: string) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

// 扁平化菜单树
function flattenMenuTree(items: TreeMenuItem[]): Menu[] {
  const result: Menu[] = [];
  const traverse = (list: TreeMenuItem[]) => {
    for (const item of list) {
      result.push({
        id: item.id,
        parent_id: item.parent_id,
        menu_name: item.menu_name,
        menu_type: item.menu_type,
        path: item.path,
        component: item.component,
        icon: item.icon,
        perm_code: item.perm_code,
        sort_order: item.sort_order,
        visible: item.visible,
        status: 1,
        created_at: '',
        updated_at: '',
      });
      if (item.children && item.children.length > 0) {
        traverse(item.children);
      }
    }
  };
  traverse(items);
  return result;
}

// 导出为 JSON
function handleExportJSON() {
  const menus = flattenMenuTree(dataSource.value);
  const exportData = {
    exportTime: new Date().toISOString(),
    totalCount: menus.length,
    menus: menus.map((m) => ({
      id: m.id,
      parent_id: m.parent_id,
      menu_name: m.menu_name,
      menu_type: m.menu_type,
      path: m.path,
      component: m.component,
      icon: m.icon,
      perm_code: m.perm_code,
      sort_order: m.sort_order,
      visible: m.visible,
    })),
  };
  const json = JSON.stringify(exportData, null, 2);
  const now = new Date();
  const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
  downloadFile(json, `menus_export_${timestamp}.json`, 'application/json');
  message.success(`成功导出 ${menus.length} 条菜单数据`);
}

// 导出为 SQL
function handleExportSQL() {
  const menus = flattenMenuTree(dataSource.value);
  const escapeSQL = (str: null | string | undefined) => {
    if (str === null || str === undefined) return 'NULL';
    return `'${str.replaceAll("'", "''")}'`;
  };

  let sql = `-- 菜单数据导出
-- 导出时间: ${new Date().toISOString()}
-- 菜单总数: ${menus.length}

-- 清空现有菜单数据（谨慎使用！）
-- DELETE FROM sys_menu WHERE is_deleted = 0;

-- 插入菜单数据
`;

  for (const m of menus) {
    sql += `INSERT INTO sys_menu (id, parent_id, menu_name, menu_type, path, component, icon, perm_code, sort_order, visible, status, is_deleted) VALUES (
  ${escapeSQL(m.id)},
  ${escapeSQL(m.parent_id)},
  ${escapeSQL(m.menu_name)},
  ${escapeSQL(m.menu_type)},
  ${escapeSQL(m.path)},
  ${escapeSQL(m.component)},
  ${escapeSQL(m.icon)},
  ${escapeSQL(m.perm_code)},
  ${m.sort_order},
  ${m.visible},
  1,
  0
) ON DUPLICATE KEY UPDATE
  parent_id = VALUES(parent_id),
  menu_name = VALUES(menu_name),
  menu_type = VALUES(menu_type),
  path = VALUES(path),
  component = VALUES(component),
  icon = VALUES(icon),
  perm_code = VALUES(perm_code),
  sort_order = VALUES(sort_order),
  visible = VALUES(visible);

`;
  }

  const now = new Date();
  const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
  downloadFile(sql, `menus_export_${timestamp}.sql`, 'text/plain');
  message.success(`成功导出 ${menus.length} 条菜单 SQL`);
}

// 导出菜单下拉处理
function handleExportClick({ key }: { key: string }) {
  if (key === 'json') {
    handleExportJSON();
  } else if (key === 'sql') {
    handleExportSQL();
  }
}

// ============== 导入功能 ==============
const importModalVisible = ref(false);
const importLoading = ref(false);
const importMode = ref<'append' | 'replace'>('append');
const importMenus = ref<any[]>([]);
const importFileName = ref('');

// 打开导入弹窗
function openImportModal() {
  importMenus.value = [];
  importFileName.value = '';
  importMode.value = 'append';
  importModalVisible.value = true;
}

// 处理文件选择
async function handleFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;

  importFileName.value = file.name;

  try {
    const content = await file.text();
    const data = JSON.parse(content);

    // 支持两种格式：{ menus: [...] } 或直接 [...]
    if (Array.isArray(data)) {
      importMenus.value = data;
    } else if (data.menus && Array.isArray(data.menus)) {
      importMenus.value = data.menus;
    } else {
      message.error('JSON 格式错误：需要 menus 数组');
      importMenus.value = [];
      return;
    }

    message.success(`解析成功：${importMenus.value.length} 条菜单`);
  } catch {
    message.error('JSON 解析失败，请检查文件格式');
    importMenus.value = [];
  }
}

// 执行导入
async function handleImport() {
  if (importMenus.value.length === 0) {
    message.warning('请先选择要导入的 JSON 文件');
    return;
  }

  // 覆盖模式二次确认
  if (importMode.value === 'replace') {
    Modal.confirm({
      title: '⚠️ 危险操作确认',
      content: '覆盖模式将删除所有现有菜单！确定要继续吗？',
      okText: '确定覆盖',
      okType: 'danger',
      cancelText: '取消',
      onOk: () => doImport(),
    });
  } else {
    await doImport();
  }
}

async function doImport() {
  try {
    importLoading.value = true;
    // requestClient 配置了 responseReturn: 'data'，返回值已经是 ResponseModel.data
    const result = await requestClient.post('/v1/system/menus/import', {
      menus: importMenus.value,
      mode: importMode.value,
      role_codes: ['admin'],
    });

    message.success(
      `导入完成：创建 ${result.created} 条，跳过 ${result.skipped} 条`,
    );

    if (result.skipped_paths && result.skipped_paths.length > 0) {
      Modal.info({
        title: '跳过的菜单（已存在）',
        content: result.skipped_paths.join(', '),
      });
    }

    importModalVisible.value = false;
    fetchMenus();
    fetchFlatMenus();
  } catch (error: any) {
    console.error('导入失败:', error);
    const errorMsg =
      error?.response?.data?.detail ||
      error?.response?.data?.message ||
      error?.message ||
      '导入失败';
    message.error(errorMsg);
  } finally {
    importLoading.value = false;
  }
}

onMounted(() => {
  fetchMenus();
  fetchFlatMenus();
});
</script>

<template>
  <div class="p-4">
    <!-- 粘性筛选头部 -->
    <div
      class="sticky top-0 z-10 -mx-4 -mt-4 mb-3 bg-background/90 px-4 pb-4 pt-2 shadow-lg backdrop-blur-md"
      style="border-bottom: 1px solid hsl(var(--border) / 30%)"
    >
      <!-- 标题行 -->
      <div class="mb-2 flex items-center gap-3">
        <span
          class="bg-gradient-to-r from-[hsl(var(--primary))] to-[#22c55e] bg-clip-text text-xl font-bold text-transparent"
        >
          菜单管理
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">搜索</span>
          <Input
            v-model:value="searchText"
            placeholder="搜索名称/路径/权限/组件"
            style="width: 240px"
            allow-clear
          />
        </div>
        <div class="filter-actions">
          <Button @click="fetchMenus">🔄 刷新</Button>
          <Dropdown>
            <template #overlay>
              <AMenu @click="handleExportClick">
                <AMenuItem key="json">📄 导出 JSON</AMenuItem>
                <AMenuItem key="sql">🗃️ 导出 SQL</AMenuItem>
              </AMenu>
            </template>
            <Button>📥 导出</Button>
          </Dropdown>
          <Button @click="openImportModal">📤 导入</Button>
          <Button type="primary" @click="handleAdd('0')">➕ 新增菜单</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="displayData"
        :loading="loading"
        v-model:expanded-row-keys="expandedRowKeys"
        row-key="id"
        size="middle"
        :pagination="false"
        :indent-size="20"
        :scroll="{ x: 1400 }"
        @expand="handleExpand"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'icon'">
            <IconifyIcon
              v-if="record.icon"
              :icon="record.icon"
              class="text-lg"
            />
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'icon_code'">
            <code v-if="record.icon" class="text-xs text-gray-500">
              {{ record.icon }}
            </code>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'menu_type'">
            <Tag :color="menuTypeMap[record.menu_type]?.color || 'default'">
              {{ menuTypeMap[record.menu_type]?.label || record.menu_type }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'path'">
            <span v-if="record.path">{{ record.path }}</span>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'component'">
            <span v-if="record.component">{{ record.component }}</span>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'perm_code'">
            <Tag v-if="record.perm_code" color="purple">
              {{ record.perm_code }}
            </Tag>
            <span v-else class="text-gray-400">-</span>
          </template>
          <template v-else-if="column.key === 'visible'">
            <Tag :color="record.visible === 1 ? 'green' : 'red'">
              {{ record.visible === 1 ? '显示' : '隐藏' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                v-if="record.menu_type !== 'F'"
                type="link"
                size="small"
                @click="handleAddChild(record as Menu)"
              >
                添加
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleEdit(record as Menu)"
              >
                ✏️ 编辑
              </Button>
              <Popconfirm
                title="确定要删除此菜单吗？"
                description="删除后子菜单也将被删除"
                ok-text="确定"
                cancel-text="取消"
                @confirm="handleDelete(record as Menu)"
              >
                <Button type="link" danger size="small">🗑️ 删除</Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 菜单编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="editingMenu ? '编辑菜单' : '新增菜单'"
      :width="650"
      :confirm-loading="isSubmitting"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <Form ref="formRef" :model="formState" layout="vertical">
        <FormItem label="上级菜单" name="parent_id">
          <TreeSelect
            v-model:value="formState.parent_id"
            :tree-data="parentMenuTree"
            placeholder="请选择上级菜单"
            tree-default-expand-all
            :dropdown-style="{ maxHeight: '300px', overflow: 'auto' }"
            :get-popup-container="(trigger) => trigger.parentElement"
          />
        </FormItem>

        <FormItem label="菜单类型" name="menu_type">
          <RadioGroup v-model:value="formState.menu_type">
            <Radio
              v-for="item in menuTypeOptions"
              :key="item.value"
              :value="item.value"
            >
              {{ item.label }}
            </Radio>
          </RadioGroup>
        </FormItem>

        <FormItem
          label="菜单名称"
          name="menu_name"
          :rules="[{ required: true, message: '请输入菜单名称' }]"
        >
          <Input
            v-model:value="formState.menu_name"
            placeholder="如：用户管理"
          />
        </FormItem>

        <FormItem
          v-if="formState.menu_type !== 'F'"
          label="路由路径"
          name="path"
        >
          <Input
            v-model:value="formState.path"
            placeholder="如：/system/user"
          />
        </FormItem>

        <FormItem
          v-if="formState.menu_type === 'C'"
          label="组件路径"
          name="component"
        >
          <Input
            v-model:value="formState.component"
            placeholder="如：system/user/index"
          />
        </FormItem>

        <FormItem label="权限标识" name="perm_code">
          <Input
            v-model:value="formState.perm_code"
            placeholder="如：system:user:list"
          />
        </FormItem>

        <FormItem
          v-if="formState.menu_type !== 'F'"
          label="菜单图标"
          name="icon"
        >
          <IconPicker
            v-model="formState.icon"
            prefix="lucide"
            :input-component="IconInputVNode"
            icon-slot="addonAfter"
            model-value-prop="value"
          />
        </FormItem>

        <div class="grid grid-cols-2 gap-4">
          <FormItem label="显示排序" name="sort_order">
            <InputNumber
              v-model:value="formState.sort_order"
              :min="0"
              :max="999"
              style="width: 100%"
            />
          </FormItem>

          <FormItem label="显示状态" name="visible">
            <Switch
              v-model:checked="formState.visible"
              :checked-value="1"
              :un-checked-value="0"
              checked-children="显示"
              un-checked-children="隐藏"
            />
          </FormItem>
        </div>
      </Form>
    </Modal>

    <!-- 导入弹窗 -->
    <Modal
      v-model:open="importModalVisible"
      title="📤 导入菜单"
      :width="600"
      :confirm-loading="importLoading"
      ok-text="开始导入"
      cancel-text="取消"
      @ok="handleImport"
    >
      <div class="import-content">
        <div class="import-section">
          <div class="import-label">选择 JSON 文件</div>
          <div class="import-upload">
            <input
              type="file"
              accept=".json"
              class="file-input"
              @change="handleFileChange"
            />
            <div v-if="importFileName" class="file-name">
              📄 {{ importFileName }}
            </div>
          </div>
        </div>

        <div class="import-section">
          <div class="import-label">导入模式</div>
          <RadioGroup v-model:value="importMode">
            <Radio value="append">
              <span class="mode-label">➕ 追加模式</span>
              <span class="mode-desc"
                >保留现有菜单，跳过已存在的（按路由路径判断）</span
              >
            </Radio>
            <Radio value="replace">
              <span class="mode-label">🔄 覆盖模式</span>
              <span class="mode-desc danger"
                >⚠️ 删除所有现有菜单后导入（危险操作！）</span
              >
            </Radio>
          </RadioGroup>
        </div>

        <div v-if="importMenus.length > 0" class="import-preview">
          <div class="preview-header">
            📋 预览：即将导入 {{ importMenus.length }} 条菜单
          </div>
          <div class="preview-list">
            <div
              v-for="menu in importMenus.slice(0, 10)"
              :key="menu.id || menu.path"
              class="preview-item"
            >
              <span class="preview-type">{{ menu.menu_type }}</span>
              <span class="preview-name">{{ menu.menu_name }}</span>
              <span class="preview-path">{{ menu.path || '-' }}</span>
            </div>
            <div v-if="importMenus.length > 10" class="preview-more">
              ... 还有 {{ importMenus.length - 10 }} 条
            </div>
          </div>
        </div>

        <div class="import-tips">
          <div class="tip-title">💡 提示</div>
          <ul class="tip-list">
            <li>支持从「导出 JSON」功能导出的文件</li>
            <li>追加模式下，已存在的路由路径将被跳过</li>
            <li>导入的菜单将自动分配给 admin 角色</li>
          </ul>
        </div>
      </div>
    </Modal>
  </div>
</template>

<style scoped>
.p-4 {
  padding: 16px;
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

.text-gray-400 {
  color: hsl(var(--muted-foreground));
}

.text-gray-500 {
  color: hsl(var(--muted-foreground));
}

.icon-preview {
  font-family: monospace;
  font-size: 12px;
  color: #6b7280;
}

.grid {
  display: grid;
}

.grid-cols-2 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.gap-4 {
  gap: 16px;
}

/* 导入弹窗样式 */
.import-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.import-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.import-label {
  font-weight: 600;
  color: hsl(var(--foreground));
}

.import-upload {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.file-input {
  padding: 8px;
  cursor: pointer;
  border: 1px dashed hsl(var(--border));
  border-radius: 6px;
}

.file-input:hover {
  border-color: hsl(var(--primary));
}

.file-name {
  padding: 8px 12px;
  font-size: 13px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 10%);
  border-radius: 4px;
}

.mode-label {
  font-weight: 500;
}

.mode-desc {
  display: block;
  margin-left: 24px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.mode-desc.danger {
  color: hsl(var(--destructive));
}

.import-preview {
  padding: 12px;
  background: hsl(var(--muted) / 30%);
  border-radius: 8px;
}

.preview-header {
  margin-bottom: 8px;
  font-weight: 600;
}

.preview-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 200px;
  overflow-y: auto;
}

.preview-item {
  display: flex;
  gap: 12px;
  padding: 4px 8px;
  font-size: 13px;
  background: hsl(var(--background));
  border-radius: 4px;
}

.preview-type {
  flex-shrink: 0;
  width: 24px;
  font-weight: 600;
  color: hsl(var(--primary));
}

.preview-name {
  flex: 1;
}

.preview-path {
  flex-shrink: 0;
  font-family: monospace;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.preview-more {
  padding: 4px 8px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.import-tips {
  padding: 12px;
  background: hsl(var(--info) / 10%);
  border-radius: 8px;
}

.tip-title {
  margin-bottom: 8px;
  font-weight: 600;
}

.tip-list {
  padding-left: 20px;
  margin: 0;
  font-size: 13px;
  color: hsl(var(--muted-foreground));
}

.tip-list li {
  margin-bottom: 4px;
}
</style>
