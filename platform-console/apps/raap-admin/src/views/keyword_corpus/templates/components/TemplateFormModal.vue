<script setup lang="ts">
import type {
  CategoryTypeOption,
  CorpusTemplate,
  TemplateFormData,
} from '../types';

import { computed, ref, watch } from 'vue';

import { Input as AInput, Form, message, Modal, Select } from 'ant-design-vue';

import FieldEditor from './FieldEditor.vue';

interface Props {
  open: boolean;
  isEditing: boolean;
  template?: CorpusTemplate;
  categoryTypeOptions: CategoryTypeOption[];
}

interface Emits {
  (e: 'update:open', value: boolean): void;
  (e: 'submit', data: { formData: TemplateFormData; isEditing: boolean }): void;
}

const props = withDefaults(defineProps<Props>(), {
  template: undefined,
});

const emit = defineEmits<Emits>();

const modalVisible = computed({
  get: () => props.open,
  set: (value) => emit('update:open', value),
});

const loading = ref(false);
const isCodeManuallyEdited = ref(false); // 标记用户是否手动编辑过 code

// 生成随机字符串（8位）
const generateRandomString = () => {
  return Math.random().toString(36).slice(2, 10);
};

const DEFAULT_TENANT_CODE = 'default';

const form = ref<TemplateFormData>({
  code: '', // 可为空，由后端自动生成或前端自动生成
  name: '',
  category_type: '',
  description: '',
  tenant_code: DEFAULT_TENANT_CODE,
  fields: [
    {
      key: '',
      label: '',
      type: 'textarea',
      required: false,
      placeholder: '',
    },
  ],
});

// 重置表单
const resetForm = () => {
  isCodeManuallyEdited.value = false; // 重置标记
  form.value = {
    code: '',
    name: '',
    category_type: '',
    description: '',
    tenant_code: DEFAULT_TENANT_CODE,
    fields: [
      {
        key: '',
        label: '',
        type: 'textarea',
        required: false,
        placeholder: '',
      },
    ],
  };
};

// 编辑时填充表单
watch(
  () => [props.open, props.template] as const,
  ([open, template]) => {
    if (open && props.isEditing && template && typeof template !== 'boolean') {
      form.value = {
        code: template.code,
        name: template.name,
        category_type: template.category_type,
        description: template.description || '',
        tenant_code: template.tenant_code,
        fields: [...template.fields],
      };
    } else if (open && !props.isEditing) {
      resetForm();
    }
  },
  { immediate: true },
);

const modalTitle = computed(() => (props.isEditing ? '编辑模板' : '新增模板'));

// 获取分类类型的显示名称
const categoryTypeLabel = computed(() => {
  if (!form.value.category_type) return '';
  const option = props.categoryTypeOptions.find(
    (opt) => opt.value === form.value.category_type,
  );
  return option?.label || form.value.category_type;
});

// 自动生成编码：分类类型-template-随机ID（与后端保持一致）
const generateCode = () => {
  const category = form.value.category_type || '';
  if (!category) return '';
  // 格式：分类类型-template-随机ID（如：品牌信息-template-a1b2c3d4）
  return `${category}-template-${generateRandomString()}`;
};

// 监听 category_type 的变化，自动生成 code（仅新建时且用户未手动编辑）
watch(
  () => [form.value.category_type, props.isEditing] as const,
  () => {
    // 只在新建模式下，且用户没有手动编辑过 code 时才自动生成
    if (!props.isEditing && !isCodeManuallyEdited.value) {
      const newCode = generateCode();
      if (newCode) {
        form.value.code = newCode;
      }
    }
  },
  { immediate: true },
);

// 表单验证
const validateForm = (): boolean => {
  if (!form.value.category_type) {
    message.warning('请先选择分类类型');
    return false;
  }
  if (!form.value.name.trim()) {
    message.warning('请输入模板名称');
    return false;
  }
  if (form.value.fields.length === 0) {
    message.warning('请至少添加一个字段');
    return false;
  }
  for (const field of form.value.fields) {
    if (!field.key.trim() || !field.label.trim()) {
      message.warning('请填写完整的字段信息');
      return false;
    }
  }
  return true;
};

const handleOk = async () => {
  if (!validateForm()) {
    return;
  }

  loading.value = true;
  try {
    emit('submit', {
      isEditing: props.isEditing,
      formData: form.value,
    });
    // 不在这里关闭弹窗，由父组件根据结果决定是否关闭
  } finally {
    loading.value = false;
  }
};

const handleCancel = () => {
  modalVisible.value = false;
};

// 处理 code 输入框失焦事件
const handleCodeBlur = () => {
  if (form.value.code) {
    // 去除首尾空格，并将中间空格替换为下划线
    form.value.code = form.value.code.trim().replaceAll(' ', '_');
  }
};

// 处理 code 输入事件，标记用户已手动编辑
const handleCodeInput = () => {
  isCodeManuallyEdited.value = true;
};
</script>

<template>
  <Modal
    v-model:open="modalVisible"
    :title="modalTitle"
    :confirm-loading="loading"
    width="700px"
    @ok="handleOk"
    @cancel="handleCancel"
  >
    <Form layout="vertical">
      <div class="grid grid-cols-2 gap-4">
        <Form.Item label="分类类型" required>
          <AInput
            v-if="isEditing"
            :model-value="categoryTypeLabel"
            disabled
            placeholder="分类类型"
          />
          <Select
            v-else
            v-model:value="form.category_type"
            :options="categoryTypeOptions"
            show-search
            :filter-option="true"
            placeholder="选择分类类型"
          />
        </Form.Item>
        <Form.Item label="模板名称" required>
          <AInput v-model:value="form.name" placeholder="如：人设语料模板" />
        </Form.Item>
      </div>

      <div class="grid grid-cols-2 gap-4">
        <Form.Item label="模板编码">
          <AInput
            v-model:value="form.code"
            :placeholder="
              isEditing
                ? '编辑模式不可修改'
                : '留空则自动生成（格式：分类类型-template-xxx）'
            "
            :disabled="isEditing"
            @input="handleCodeInput"
            @blur="handleCodeBlur"
          />
          <div v-if="!isEditing" class="mt-1 text-xs text-muted-foreground">
            提示：选择分类类型后自动生成，或手动输入
          </div>
        </Form.Item>
      </div>

      <Form.Item label="描述">
        <AInput.TextArea
          v-model:value="form.description"
          placeholder="模板描述"
          :rows="2"
        />
      </Form.Item>

      <Form.Item label="字段定义" required>
        <FieldEditor v-model:fields="form.fields" :min-fields="1" />
      </Form.Item>
    </Form>
  </Modal>
</template>
