<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';

import {
  Button,
  Card,
  Form,
  FormItem,
  Input,
  message,
  Modal,
  Popconfirm,
  Space,
  Switch,
  Table,
  Tag,
  Textarea,
  Tree,
} from 'ant-design-vue';

import { requestClient } from '#/api/request';

interface Role {
  id: string;
  role_code: string;
  role_name: string;
  description: string;
  status: number;
  menu_ids: string[];
  created_at: string;
}

interface MenuItem {
  key: string;
  title: string;
  children?: MenuItem[];
}

const loading = ref(false);
const dataSource = ref<Role[]>([]);
const searchText = ref('');
const modalVisible = ref(false);
const permModalVisible = ref(false);
const editingRole = ref<null | Role>(null);
const selectedRole = ref<null | Role>(null);
const isSubmitting = ref(false);
const formRef = ref();
const pagination = reactive({
  current: 1,
  pageSize: 10,
  showSizeChanger: true,
  pageSizeOptions: ['10', '20', '50', '100'],
  showTotal: (total: number) => `共 ${total} 条`,
});

const formState = reactive({
  role_code: '',
  role_name: '',
  description: '',
  status: 1,
});

const selectedMenuIds = ref<string[]>([]);
const halfCheckedMenuIds = ref<string[]>([]); // 半选状态的父节点
const menuTree = ref<MenuItem[]>([]);

const columns = [
  { title: '角色编码', dataIndex: 'role_code', key: 'role_code', width: 150 },
  { title: '角色名称', dataIndex: 'role_name', key: 'role_name', width: 150 },
  {
    title: '描述',
    dataIndex: 'description',
    key: 'description',
    ellipsis: true,
  },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 200 },
];

async function fetchRoles() {
  loading.value = true;
  try {
    const response = await requestClient.get<{
      items: Role[];
      total: number;
    }>('/v1/system/roles', {
      params: {
        page: 1,
        page_size: 100,
      },
    });
    dataSource.value = response.items || [];
  } catch (error) {
    console.error('获取角色列表失败:', error);
    message.error('获取角色列表失败');
  } finally {
    loading.value = false;
  }
}

async function fetchMenuTree() {
  try {
    const response = await requestClient.get<MenuItem[]>(
      '/v1/system/menus/tree/simple',
    );
    menuTree.value = response || [];
  } catch (error) {
    console.error('获取菜单树失败:', error);
    // 如果获取失败，使用默认静态数据
    menuTree.value = [
      {
        key: 'dashboard',
        title: 'Dashboard',
        children: [{ key: 'dashboard:workspace', title: '工作台' }],
      },
      {
        key: 'config',
        title: '配置管理',
        children: [
          { key: 'config:plugin', title: 'Plugin 管理' },
          { key: 'config:expert-config', title: 'ExpertConfig 管理' },
        ],
      },
      {
        key: 'job',
        title: 'Job 工作台',
        children: [
          { key: 'job:list', title: '任务列表' },
          { key: 'job:create', title: '创建任务' },
        ],
      },
      {
        key: 'expert',
        title: 'Expert 调试',
        children: [{ key: 'expert:debug', title: '调试面板' }],
      },
      {
        key: 'trace',
        title: '调用追踪',
        children: [{ key: 'trace:list', title: '调用记录' }],
      },
      {
        key: 'system',
        title: '系统设置',
        children: [
          { key: 'system:user', title: '用户管理' },
          { key: 'system:role', title: '角色管理' },
          { key: 'system:menu', title: '菜单管理' },
        ],
      },
    ];
  }
}

function handleAdd() {
  editingRole.value = null;
  formState.role_code = '';
  formState.role_name = '';
  formState.description = '';
  formState.status = 1;
  formRef.value?.resetFields();
  modalVisible.value = true;
}

function handleEdit(record: Role) {
  editingRole.value = record;
  formState.role_code = record.role_code;
  formState.role_name = record.role_name;
  formState.description = record.description || '';
  formState.status = record.status;
  modalVisible.value = true;
}

function handlePerm(record: Role) {
  selectedRole.value = record;
  // 后端返回的是所有菜单ID（包括父节点和子节点）
  // 需要根据菜单树计算出哪些是叶子节点（用于 checked-keys）
  // 哪些是半选状态的父节点（用于 half-checked-keys）
  const allMenuIds = new Set(record.menu_ids || []);
  const leafIds: string[] = [];
  const parentIds: string[] = [];

  // 递归遍历菜单树，分离叶子节点和父节点
  const separateNodes = (nodes: MenuItem[]) => {
    for (const node of nodes) {
      if (allMenuIds.has(node.key)) {
        if (node.children && node.children.length > 0) {
          // 有子节点的是父节点
          parentIds.push(node.key);
          separateNodes(node.children);
        } else {
          // 没有子节点的是叶子节点
          leafIds.push(node.key);
        }
      } else if (node.children && node.children.length > 0) {
        // 父节点没有被选中，但仍需要递归检查子节点
        separateNodes(node.children);
      }
    }
  };

  separateNodes(menuTree.value);

  // Tree 组件的 checked-keys 应该只包含叶子节点
  selectedMenuIds.value = leafIds;
  // 半选状态的父节点
  halfCheckedMenuIds.value = parentIds;

  permModalVisible.value = true;
}

// Tree 组件的 check 事件处理
function handleTreeCheck(
  checkedKeys: string[] | { checked: string[]; halfChecked: string[] },
) {
  if (Array.isArray(checkedKeys)) {
    selectedMenuIds.value = checkedKeys;
    halfCheckedMenuIds.value = [];
  } else {
    selectedMenuIds.value = checkedKeys.checked;
    halfCheckedMenuIds.value = checkedKeys.halfChecked;
  }
}

async function handleDelete(record: Role) {
  if (record.role_code === 'admin') {
    message.warning('系统管理员角色不允许删除');
    return;
  }
  try {
    await requestClient.delete(`/v1/system/roles/${record.id}`);
    message.success(`角色 "${record.role_name}" 删除成功`);
    fetchRoles();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '删除失败';
    message.error(errorMsg);
  }
}

async function handleSubmit() {
  try {
    isSubmitting.value = true;
    await formRef.value?.validate();

    if (editingRole.value) {
      // 更新
      await requestClient.put(`/v1/system/roles/${editingRole.value.id}`, {
        role_name: formState.role_name,
        description: formState.description,
        status: formState.status,
      });
      message.success(`角色 "${formState.role_name}" 更新成功`);
    } else {
      // 创建
      await requestClient.post('/v1/system/roles', {
        role_code: formState.role_code,
        role_name: formState.role_name,
        description: formState.description,
        status: formState.status,
        menu_ids: [],
      });
      message.success(`角色 "${formState.role_name}" 创建成功`);
    }
    modalVisible.value = false;
    fetchRoles();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '操作失败';
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

async function handlePermSubmit() {
  if (!selectedRole.value) return;

  try {
    isSubmitting.value = true;
    // 合并选中的叶子节点和半选状态的父节点
    const allMenuIds = [
      ...new Set([...halfCheckedMenuIds.value, ...selectedMenuIds.value]),
    ];
    await requestClient.put(`/v1/system/roles/${selectedRole.value.id}/menus`, {
      menu_ids: allMenuIds,
    });
    message.success('权限配置成功');
    permModalVisible.value = false;
    fetchRoles();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '配置失败';
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

const filteredData = () => {
  if (!searchText.value) return dataSource.value;
  const keyword = searchText.value.toLowerCase();
  return dataSource.value.filter(
    (item) =>
      item.role_name.toLowerCase().includes(keyword) ||
      item.role_code.toLowerCase().includes(keyword),
  );
};

function handleTableChange(pag: any) {
  pagination.current = pag.current || 1;
  pagination.pageSize = pag.pageSize || pagination.pageSize;
}

function formatDateTime(dateStr: string | undefined) {
  if (!dateStr) return '-';
  const date = new Date(dateStr);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

onMounted(() => {
  fetchRoles();
  fetchMenuTree();
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
          角色管理
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">角色</span>
          <Input
            v-model:value="searchText"
            placeholder="搜索角色..."
            style="width: 200px"
            allow-clear
          >
            <template #prefix>🔍</template>
          </Input>
        </div>
        <div class="filter-actions">
          <Button type="primary" @click="handleAdd">➕ 新增角色</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="filteredData()"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'status'">
            <Tag :color="record.status === 1 ? 'green' : 'red'">
              {{ record.status === 1 ? '启用' : '禁用' }}
            </Tag>
          </template>
          <template v-else-if="column.key === 'created_at'">
            {{ formatDateTime(record.created_at) }}
          </template>
          <template v-else-if="column.key === 'action'">
            <Space>
              <Button
                type="link"
                size="small"
                @click="handleEdit(record as Role)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                @click="handlePerm(record as Role)"
              >
                🔐 权限
              </Button>
              <Popconfirm
                title="确定要删除此角色吗？"
                ok-text="确定"
                cancel-text="取消"
                @confirm="handleDelete(record as Role)"
              >
                <Button
                  type="link"
                  danger
                  size="small"
                  :disabled="record.role_code === 'admin'"
                >
                  🗑️ 删除
                </Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 角色编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="editingRole ? '编辑角色' : '新增角色'"
      :width="500"
      :confirm-loading="isSubmitting"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <Form ref="formRef" :model="formState" layout="vertical">
        <FormItem
          label="角色编码"
          name="role_code"
          :rules="[
            { required: true, message: '请输入角色编码' },
            {
              pattern: /^[a-zA-Z_][a-zA-Z0-9_]*$/,
              message:
                '角色编码只能包含字母、数字和下划线，且以字母或下划线开头',
            },
          ]"
        >
          <Input
            v-model:value="formState.role_code"
            placeholder="如: developer"
            :disabled="!!editingRole"
          />
        </FormItem>
        <FormItem
          label="角色名称"
          name="role_name"
          :rules="[{ required: true, message: '请输入角色名称' }]"
        >
          <Input v-model:value="formState.role_name" placeholder="如: 开发者" />
        </FormItem>
        <FormItem label="描述" name="description">
          <Textarea
            v-model:value="formState.description"
            placeholder="角色描述..."
            :rows="3"
          />
        </FormItem>
        <FormItem label="状态" name="status">
          <Switch
            v-model:checked="formState.status"
            :checked-value="1"
            :un-checked-value="0"
            checked-children="启用"
            un-checked-children="禁用"
          />
        </FormItem>
      </Form>
    </Modal>

    <!-- 权限配置弹窗 -->
    <Modal
      v-model:open="permModalVisible"
      :title="`配置权限 - ${selectedRole?.role_name || ''}`"
      :width="500"
      :confirm-loading="isSubmitting"
      @ok="handlePermSubmit"
      @cancel="permModalVisible = false"
    >
      <div style="max-height: 400px; overflow-y: auto">
        <Tree
          v-model:checked-keys="selectedMenuIds"
          :tree-data="menuTree"
          checkable
          default-expand-all
          @check="handleTreeCheck"
        />
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
</style>
