<script setup lang="ts">
import type { KeywordSelection } from '../composables/useWizardState';

import { computed, h, onMounted, ref } from 'vue';

import { PlusOutlined, SearchOutlined } from '@ant-design/icons-vue';
import {
  Button,
  Card,
  Checkbox,
  Col,
  Empty,
  Input,
  Row,
  Space,
  Tag,
} from 'ant-design-vue';

import { logger } from '#/utils/logger';

interface Props {
  modelValue: KeywordSelection[];
}

interface Emits {
  (e: 'update:modelValue', value: KeywordSelection[]): void;
  (e: 'next'): void;
}

const props = defineProps<Props>();

const emit = defineEmits<Emits>();

// 状态
const isLoading = ref(false);
const dimensions = ref<Array<{ count: number; id: string; name: string }>>([]);
const selectedDimension = ref<string>('');
const keywordSearch = ref('');
const keywords = ref<Array<{ id: string; name: string }>>([]);
const showKeywordSelect = ref(false);

// 当前维度的已选关键词
const currentSelectedKeywords = computed(() => {
  const current = props.modelValue.find(
    (k) => k.dimensionId === selectedDimension.value,
  );
  return current?.selectedKeywords || [];
});

// 已选数量统计
const totalSelected = computed(() => {
  return props.modelValue.reduce(
    (sum, k) => sum + k.selectedKeywords.length,
    0,
  );
});

// 已选维度列表
const selectedDimensions = computed(() => {
  return props.modelValue.map((k) => ({
    id: k.dimensionId,
    name: k.dimensionName,
    count: k.selectedKeywords.length,
  }));
});

/**
 * 加载维度列表
 */
async function loadDimensions() {
  isLoading.value = true;
  try {
    // TODO: 调用后端 API 获取关键词维度
    // const data = await getKeywordDimensionsApi();
    // dimensions.value = data;

    // 模拟数据
    dimensions.value = [
      { id: 'category', name: '品类', count: 20 },
      { id: 'style', name: '风格', count: 15 },
      { id: 'scene', name: '场景', count: 12 },
      { id: 'tone', name: '语调', count: 8 },
      { id: 'length', name: '篇幅', count: 5 },
      { id: 'platform', name: '平台', count: 6 },
      { id: 'audience', name: '受众', count: 10 },
    ];
  } catch (error) {
    logger.error('加载维度失败:', error);
  } finally {
    isLoading.value = false;
  }
}

/**
 * 选择维度
 */
function selectDimension(dimensionId: string) {
  selectedDimension.value = dimensionId;
  keywordSearch.value = '';
  loadKeywords(dimensionId);
}

/**
 * 加载关键词
 */
async function loadKeywords(dimensionId: string) {
  isLoading.value = true;
  try {
    // TODO: 调用后端 API
    // const data = await getKeywordsByDimensionApi(dimensionId);
    // keywords.value = data;

    // 模拟数据
    const mockKeywords: Record<string, string[]> = {
      category: [
        '数码',
        '家电',
        '美妆',
        '服饰',
        '食品',
        '母婴',
        '家居',
        '运动',
        '汽车',
        '图书',
      ],
      style: ['专业', '亲切', '幽默', '严肃', '活泼', '简洁', '详细', '故事化'],
      scene: ['种草', '测评', '教程', '对比', '推荐', '科普', '新闻', '故事'],
      tone: ['正式', '轻松', '热情', '客观', '主观', '中立'],
      length: ['短', '中', '长'],
      platform: ['小红书', '抖音', '公众号', '微博', 'B站', '知乎'],
      audience: ['年轻人', '中年人', '专业人士', '大众', '高端人群', '学生'],
    };
    keywords.value = (mockKeywords[dimensionId] || []).map((name) => ({
      id: name,
      name,
    }));
  } catch (error) {
    logger.error('加载关键词失败:', error);
  } finally {
    isLoading.value = false;
  }
}

/**
 * 过滤关键词
 */
const filteredKeywords = computed(() => {
  if (!keywordSearch.value) return keywords.value;
  const search = keywordSearch.value.toLowerCase();
  return keywords.value.filter((k) => k.name.toLowerCase().includes(search));
});

/**
 * 切换关键词选中状态
 */
function toggleKeyword(keywordName: string) {
  const newValue = [...props.modelValue];
  const existingIndex = newValue.findIndex(
    (k) => k.dimensionId === selectedDimension.value,
  );

  if (existingIndex === -1) {
    // 新增维度
    const dimension = dimensions.value.find(
      (d) => d.id === selectedDimension.value,
    );
    newValue.push({
      dimensionId: selectedDimension.value,
      dimensionName: dimension?.name || selectedDimension.value,
      selectedKeywords: [keywordName],
    });
  } else {
    const existing = newValue[existingIndex];
    const keywordIndex = existing.selectedKeywords.indexOf(keywordName);

    if (keywordIndex === -1) {
      existing.selectedKeywords.push(keywordName);
    } else {
      existing.selectedKeywords.splice(keywordIndex, 1);
      // 如果没有选中的关键词了，移除该维度
      if (existing.selectedKeywords.length === 0) {
        newValue.splice(existingIndex, 1);
      }
    }
  }

  emit('update:modelValue', newValue);
}

/**
 * 检查关键词是否选中
 */
function isKeywordSelected(keywordName: string): boolean {
  return currentSelectedKeywords.value.includes(keywordName);
}

/**
 * 移除维度
 */
function removeDimension(dimensionId: string) {
  const newValue = props.modelValue.filter(
    (k) => k.dimensionId !== dimensionId,
  );
  emit('update:modelValue', newValue);
  if (selectedDimension.value === dimensionId) {
    selectedDimension.value = '';
    keywords.value = [];
  }
}

/**
 * 全选当前维度
 */
function selectAllCurrent() {
  const dimension = dimensions.value.find(
    (d) => d.id === selectedDimension.value,
  );
  if (!dimension) return;

  const newValue = [...props.modelValue];
  const existingIndex = newValue.findIndex(
    (k) => k.dimensionId === selectedDimension.value,
  );
  const allKeywords = filteredKeywords.value.map((k) => k.name);

  if (existingIndex === -1) {
    newValue.push({
      dimensionId: selectedDimension.value,
      dimensionName: dimension.name,
      selectedKeywords: allKeywords,
    });
  } else {
    newValue[existingIndex].selectedKeywords = [
      ...new Set([...allKeywords, ...newValue[existingIndex].selectedKeywords]),
    ];
  }

  emit('update:modelValue', newValue);
}

/**
 * 清空当前维度
 */
function clearCurrent() {
  removeDimension(selectedDimension.value);
}

/**
 * 快速添加维度
 */
function quickAddDimension(dimensionId: string) {
  selectDimension(dimensionId);
  showKeywordSelect.value = true;
}

onMounted(() => {
  loadDimensions();
});
</script>

<template>
  <div class="step-keywords">
    <Row :gutter="24">
      <!-- 左侧：维度选择 -->
      <Col :span="8">
        <Card title="关键词维度" class="dimension-card">
          <template #extra>
            <span class="selected-count">已选 {{ totalSelected }} 个</span>
          </template>

          <div class="dimension-list">
            <div
              v-for="dim in dimensions"
              :key="dim.id"
              class="dimension-item"
              :class="[{ active: selectedDimension === dim.id }]"
              @click="selectDimension(dim.id)"
            >
              <div class="dimension-info">
                <span class="dimension-name">{{ dim.name }}</span>
                <span class="dimension-count">{{ dim.count }}</span>
              </div>
              <div v-if="selectedDimension === dim.id" class="dimension-arrow">
                →
              </div>
            </div>
          </div>
        </Card>

        <!-- 已选维度标签 -->
        <Card title="已选维度" class="selected-dimensions-card" size="small">
          <div v-if="selectedDimensions.length === 0" class="empty-hint">
            请从左侧选择维度
          </div>
          <div v-else class="selected-tags">
            <Tag
              v-for="dim in selectedDimensions"
              :key="dim.id"
              closable
              @close="removeDimension(dim.id)"
            >
              {{ dim.name }} ({{ dim.count }})
            </Tag>
          </div>
        </Card>
      </Col>

      <!-- 右侧：关键词选择 -->
      <Col :span="16">
        <Card v-if="!selectedDimension" class="keyword-empty-card">
          <Empty description="请选择一个关键词维度">
            <template #image>
              <component
                :is="SearchOutlined"
                style="font-size: 48px; color: #ccc"
              />
            </template>
          </Empty>
        </Card>

        <Card v-else class="keyword-card">
          <template #title>
            {{ dimensions.find((d) => d.id === selectedDimension)?.name }}关键词
          </template>
          <template #extra>
            <Space>
              <span class="current-selected"
                >已选 {{ currentSelectedKeywords.length }} 个</span
              >
              <Button size="small" @click="selectAllCurrent">全选</Button>
              <Button size="small" @click="clearCurrent">清空</Button>
            </Space>
          </template>

          <!-- 搜索框 -->
          <Input
            v-model:value="keywordSearch"
            placeholder="搜索关键词..."
            :prefix="h(SearchOutlined)"
            allow-clear
            class="keyword-search"
          />

          <!-- 关键词列表 -->
          <div class="keyword-list">
            <Checkbox.Group :value="currentSelectedKeywords">
              <div class="keyword-grid">
                <Checkbox
                  v-for="keyword in filteredKeywords"
                  :key="keyword.id"
                  :value="keyword.name"
                  :checked="isKeywordSelected(keyword.name)"
                  @change="toggleKeyword(keyword.name)"
                >
                  {{ keyword.name }}
                </Checkbox>
              </div>
            </Checkbox.Group>
          </div>
        </Card>
      </Col>
    </Row>

    <!-- 快速添加提示 -->
    <div v-if="selectedDimensions.length > 0" class="quick-add-hint">
      <Space>
        <span class="hint-text">推荐添加更多维度以获得更丰富的组合：</span>
        <Button
          v-for="dim in dimensions
            .filter((d) => !selectedDimensions.some((s) => s.id === d.id))
            .slice(0, 3)"
          :key="dim.id"
          size="small"
          @click="quickAddDimension(dim.id)"
        >
          <PlusOutlined /> {{ dim.name }}
        </Button>
      </Space>
    </div>
  </div>
</template>

<style scoped>
.step-keywords {
  padding: 8px 0;
}

.dimension-card {
  min-height: 400px;
}

.selected-count {
  font-size: 13px;
  color: #999;
}

.dimension-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dimension-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  cursor: pointer;
  border-radius: 6px;
  transition: all 0.2s;
}

.dimension-item:hover {
  background: #f5f5f5;
}

.dimension-item.active {
  color: #1890ff;
  background: #e6f7ff;
}

.dimension-info {
  display: flex;
  gap: 8px;
  align-items: center;
}

.dimension-name {
  font-weight: 500;
}

.dimension-count {
  padding: 2px 6px;
  font-size: 12px;
  color: #999;
  background: #f0f0f0;
  border-radius: 10px;
}

.dimension-arrow {
  color: #1890ff;
}

.selected-dimensions-card {
  margin-top: 16px;
}

.empty-hint {
  padding: 20px 0;
  color: #999;
  text-align: center;
}

.selected-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.keyword-empty-card {
  min-height: 400px;
}

.keyword-card {
  min-height: 400px;
}

.current-selected {
  font-size: 13px;
  color: #999;
}

.keyword-search {
  margin-bottom: 16px;
}

.keyword-list {
  max-height: 300px;
  overflow-y: auto;
}

.keyword-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.quick-add-hint {
  padding: 16px;
  margin-top: 24px;
  background: #f5f5f5;
  border-radius: 8px;
}

.hint-text {
  font-size: 13px;
  color: #666;
}
</style>
