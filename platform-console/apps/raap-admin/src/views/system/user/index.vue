<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import { useRoute } from 'vue-router';

import {
  Button,
  Card,
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
} from 'ant-design-vue';

import { requestClient } from '#/api/request';

interface User {
  id: string;
  username: string;
  name: string;
  email: string;
  phone: string;
  status: number;
  roles: string[];
  role_names: string[];
  created_at: string;
}

interface Role {
  id: string;
  role_code: string;
  role_name: string;
}

const route = useRoute();

const loading = ref(false);
const dataSource = ref<User[]>([]);
const roles = ref<Role[]>([]);
const searchText = ref('');
const modalVisible = ref(false);
const passwordModalVisible = ref(false);
const editingUser = ref<null | User>(null);
const selectedUserId = ref('');
const isSubmitting = ref(false);
const formRef = ref();
const passwordFormRef = ref();
const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
  showSizeChanger: true,
  showTotal: (total: number) => `共 ${total} 条`,
});

const formState = reactive({
  username: '',
  name: '',
  email: '',
  phone: '',
  password: '',
  status: 1,
  role_ids: [] as string[],
});

const passwordForm = reactive({
  new_password: '',
  confirm_password: '',
});

const columns = [
  { title: '用户名', dataIndex: 'username', key: 'username', width: 120 },
  { title: '姓名', dataIndex: 'name', key: 'name', width: 120 },
  { title: '邮箱', dataIndex: 'email', key: 'email', width: 180 },
  { title: '手机号', dataIndex: 'phone', key: 'phone', width: 130 },
  { title: '角色', dataIndex: 'roles', key: 'roles', width: 200 },
  { title: '状态', dataIndex: 'status', key: 'status', width: 100 },
  { title: '创建时间', dataIndex: 'created_at', key: 'created_at', width: 180 },
  { title: '操作', key: 'action', width: 200 },
];

async function fetchUsers() {
  loading.value = true;
  try {
    const response = await requestClient.get<{
      items: User[];
      total: number;
    }>('/v1/system/users', {
      params: {
        username: searchText.value || undefined,
        page: pagination.current,
        page_size: pagination.pageSize,
      },
    });
    dataSource.value = response.items || [];
    pagination.total = response.total || 0;
  } catch (error) {
    console.error('获取用户列表失败:', error);
    message.error('获取用户列表失败');
  } finally {
    loading.value = false;
  }
}

async function fetchRoles() {
  try {
    const response = await requestClient.get<Role[]>(
      '/v1/system/roles/list/all',
    );
    roles.value = response || [];
  } catch (error) {
    console.error('获取角色列表失败:', error);
    // 使用静态数据作为后备
    roles.value = [
      { id: 'role-admin', role_code: 'admin', role_name: '超级管理员' },
      { id: 'role-user', role_code: 'user', role_name: '用户' },
      { id: 'role-guest', role_code: 'guest', role_name: '游客' },
    ];
  }
}

function handleAdd() {
  editingUser.value = null;
  formState.username = '';
  formState.name = '';
  formState.email = '';
  formState.phone = '';
  formState.password = '';
  formState.status = 1;
  formState.role_ids = [];
  formRef.value?.resetFields();
  modalVisible.value = true;
}

function handleEdit(record: User) {
  editingUser.value = record;
  formState.username = record.username;
  formState.name = record.name || '';
  formState.email = record.email || '';
  formState.phone = record.phone || '';
  formState.password = '';
  formState.status = record.status;
  // 将角色编码转换为角色ID
  formState.role_ids = roles.value
    .filter((r) => record.roles.includes(r.role_code))
    .map((r) => r.id);
  modalVisible.value = true;
}

function handleResetPassword(record: User) {
  selectedUserId.value = record.id;
  passwordForm.new_password = '';
  passwordForm.confirm_password = '';
  passwordFormRef.value?.resetFields();
  passwordModalVisible.value = true;
}

async function handleDelete(record: User) {
  if (record.username === 'admin') {
    message.warning('系统管理员账户不允许删除');
    return;
  }
  try {
    await requestClient.delete(`/v1/system/users/${record.id}`);
    message.success(`用户 "${record.name || record.username}" 删除成功`);
    fetchUsers();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '删除失败';
    message.error(errorMsg);
  }
}

async function handleSubmit() {
  try {
    isSubmitting.value = true;
    await formRef.value?.validate();

    if (editingUser.value) {
      // 更新
      await requestClient.put(`/v1/system/users/${editingUser.value.id}`, {
        name: formState.name,
        email: formState.email,
        phone: formState.phone,
        status: formState.status,
        role_ids: formState.role_ids,
      });
      message.success(
        `用户 "${formState.name || formState.username}" 更新成功`,
      );
    } else {
      // 创建
      await requestClient.post('/v1/system/users', {
        username: formState.username,
        password: formState.password,
        name: formState.name,
        email: formState.email,
        phone: formState.phone,
        status: formState.status,
        role_ids: formState.role_ids,
      });
      message.success(
        `用户 "${formState.name || formState.username}" 创建成功`,
      );
    }
    modalVisible.value = false;
    fetchUsers();
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '操作失败';
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

async function handlePasswordSubmit() {
  try {
    isSubmitting.value = true;
    await passwordFormRef.value?.validate();

    if (passwordForm.new_password !== passwordForm.confirm_password) {
      message.error('两次输入的密码不一致');
      return;
    }

    await requestClient.put(
      `/v1/system/users/${selectedUserId.value}/password`,
      {
        new_password: passwordForm.new_password,
      },
    );
    message.success('密码重置成功');
    passwordModalVisible.value = false;
  } catch (error: any) {
    const errorMsg = error?.response?.data?.detail || '密码重置失败';
    message.error(errorMsg);
  } finally {
    isSubmitting.value = false;
  }
}

function handleTableChange(pag: any) {
  pagination.current = pag.current;
  pagination.pageSize = pag.pageSize;
  fetchUsers();
}

function handleSearch() {
  pagination.current = 1;
  fetchUsers();
}

const roleOptions = () => {
  return roles.value.map((item) => ({
    value: item.id,
    label: item.role_name,
  }));
};

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
  fetchUsers();
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
          {{ route.meta.title || '用户管理' }}
        </span>
      </div>
      <!-- 筛选行 -->
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">用户名/姓名</span>
          <Input
            v-model:value="searchText"
            placeholder="搜索用户名/姓名..."
            style="width: 200px"
            allow-clear
            @press-enter="handleSearch"
          >
            <template #prefix>🔍</template>
          </Input>
        </div>
        <div class="filter-actions">
          <Button @click="handleSearch">搜索</Button>
          <Button type="primary" @click="handleAdd">➕ 新增用户</Button>
        </div>
      </div>
    </div>

    <Card :bordered="false">
      <Table
        :columns="columns"
        :data-source="dataSource"
        :loading="loading"
        :pagination="pagination"
        row-key="id"
        size="middle"
        @change="handleTableChange"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'roles'">
            <Space wrap>
              <Tag
                v-for="(roleName, index) in record.role_names"
                :key="index"
                color="blue"
              >
                {{ roleName }}
              </Tag>
              <span v-if="!record.role_names?.length" class="text-gray-400">
                未分配角色
              </span>
            </Space>
          </template>
          <template v-else-if="column.key === 'status'">
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
                @click="handleEdit(record as User)"
              >
                ✏️ 编辑
              </Button>
              <Button
                type="link"
                size="small"
                @click="handleResetPassword(record as User)"
              >
                🔑 重置密码
              </Button>
              <Popconfirm
                title="确定要删除此用户吗？"
                ok-text="确定"
                cancel-text="取消"
                @confirm="handleDelete(record as User)"
              >
                <Button
                  type="link"
                  danger
                  size="small"
                  :disabled="record.username === 'admin'"
                >
                  🗑️ 删除
                </Button>
              </Popconfirm>
            </Space>
          </template>
        </template>
      </Table>
    </Card>

    <!-- 用户编辑弹窗 -->
    <Modal
      v-model:open="modalVisible"
      :title="editingUser ? '编辑用户' : '新增用户'"
      :width="600"
      :confirm-loading="isSubmitting"
      @ok="handleSubmit"
      @cancel="modalVisible = false"
    >
      <Form ref="formRef" :model="formState" layout="vertical">
        <FormItem
          label="用户名"
          name="username"
          :rules="[
            { required: true, message: '请输入用户名' },
            {
              pattern: /^[a-zA-Z][a-zA-Z0-9_]{1,63}$/,
              message: '用户名以字母开头，只能包含字母、数字和下划线',
            },
          ]"
        >
          <Input
            v-model:value="formState.username"
            placeholder="请输入用户名"
            :disabled="!!editingUser"
          />
        </FormItem>
        <FormItem label="姓名" name="name">
          <Input v-model:value="formState.name" placeholder="请输入姓名" />
        </FormItem>
        <FormItem
          label="邮箱"
          name="email"
          :rules="[{ type: 'email', message: '请输入有效的邮箱地址' }]"
        >
          <Input v-model:value="formState.email" placeholder="请输入邮箱" />
        </FormItem>
        <FormItem label="手机号" name="phone">
          <Input v-model:value="formState.phone" placeholder="请输入手机号" />
        </FormItem>
        <FormItem
          v-if="!editingUser"
          label="密码"
          name="password"
          :rules="[
            { required: true, message: '请输入密码' },
            { min: 6, message: '密码至少6位' },
          ]"
        >
          <Input.Password
            v-model:value="formState.password"
            placeholder="请输入密码（至少6位）"
          />
        </FormItem>
        <FormItem label="角色" name="role_ids">
          <Select
            v-model:value="formState.role_ids"
            mode="multiple"
            :options="roleOptions()"
            placeholder="请选择角色"
            style="width: 100%"
            show-search
            :filter-option="true"
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

    <!-- 重置密码弹窗 -->
    <Modal
      v-model:open="passwordModalVisible"
      title="重置密码"
      :width="400"
      :confirm-loading="isSubmitting"
      @ok="handlePasswordSubmit"
      @cancel="passwordModalVisible = false"
    >
      <Form ref="passwordFormRef" :model="passwordForm" layout="vertical">
        <FormItem
          label="新密码"
          name="new_password"
          :rules="[
            { required: true, message: '请输入新密码' },
            { min: 6, message: '密码至少6位' },
          ]"
        >
          <Input.Password
            v-model:value="passwordForm.new_password"
            placeholder="请输入新密码（至少6位）"
          />
        </FormItem>
        <FormItem
          label="确认密码"
          name="confirm_password"
          :rules="[{ required: true, message: '请确认密码' }]"
        >
          <Input.Password
            v-model:value="passwordForm.confirm_password"
            placeholder="请再次输入新密码"
          />
        </FormItem>
      </Form>
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
  color: #9ca3af;
}
</style>
