<script setup lang="ts">
import type { TemplateField } from '../types';

import { computed } from 'vue';

import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue';
import { Button, Input, Select, Switch } from 'ant-design-vue';

interface Props {
  fields: TemplateField[];
  minFields?: number;
}

interface Emits {
  (e: 'update:fields', value: TemplateField[]): void;
}

const props = withDefaults(defineProps<Props>(), {
  minFields: 1,
});

const emit = defineEmits<Emits>();

const fields = computed<TemplateField[]>({
  get: () => props.fields,
  set: (value: TemplateField[]) => emit('update:fields', value),
});

const fieldTypeOptions = [
  { value: 'textarea', label: '多行文本' },
  { value: 'input', label: '单行输入' },
  { value: 'select', label: '下拉选择' },
];

const handleAddField = () => {
  fields.value = [
    ...fields.value,
    {
      key: '',
      label: '',
      type: 'textarea',
      required: false,
      placeholder: '',
    },
  ];
};

const handleRemoveField = (index: number) => {
  const newFields = [...fields.value];
  newFields.splice(index, 1);
  fields.value = newFields;
};
</script>

<template>
  <div class="fields-container">
    <div v-for="(field, index) in fields" :key="index" class="field-row">
      <Input
        v-model:value="field.key"
        placeholder="字段 key"
        style="width: 120px"
      />
      <Input
        v-model:value="field.label"
        placeholder="显示名称"
        style="width: 120px"
      />
      <Select
        v-model:value="field.type"
        :options="fieldTypeOptions"
        style="width: 100px"
      />
      <div class="flex items-center gap-1">
        <Switch v-model:checked="field.required" size="small" />
        <span class="text-xs text-gray-500">必填</span>
      </div>
      <Input
        v-model:value="field.placeholder"
        placeholder="占位提示"
        style="flex: 1"
      />
      <Button
        type="text"
        danger
        size="small"
        :disabled="fields.length <= minFields"
        @click="handleRemoveField(index)"
      >
        <template #icon><DeleteOutlined /></template>
      </Button>
    </div>
    <Button type="dashed" block @click="handleAddField">
      <template #icon><PlusOutlined /></template>
      添加字段
    </Button>
  </div>
</template>

<style scoped>
.fields-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.field-row {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px;
  border-radius: 4px;
}
</style>
