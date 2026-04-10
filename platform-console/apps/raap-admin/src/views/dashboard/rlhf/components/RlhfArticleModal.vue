<script setup lang="ts">
import type { RLHFInspectionDetailItem } from '../types';

import { computed } from 'vue';

import { Badge, Descriptions, Modal, Tag } from 'ant-design-vue';
import dayjs from 'dayjs';

interface Props {
  open: boolean;
  article: null | RLHFInspectionDetailItem;
}

const props = withDefaults(defineProps<Props>(), {
  open: false,
  article: null,
});

const emit = defineEmits<{
  'update:open': [value: boolean];
}>();

const handleClose = () => {
  emit('update:open', false);
};

// 评分颜色
const getScoreColor = (score: number) => {
  if (score >= 90) return 'success';
  if (score >= 80) return 'processing';
  if (score >= 60) return 'warning';
  return 'error';
};

// 评分等级
const getScoreLevel = (score: number) => {
  if (score >= 90) return '优秀';
  if (score >= 80) return '良好';
  if (score >= 60) return '一般';
  return '待提升';
};

// 维度名称映射
const dimensionNameMap: Record<string, string> = {
  platform_adaptability: '平台适应度',
  content_quality: '整体内容质量',
  brand_alignment: '品牌调性匹配',
  creativity: '内容创造力',
  persona_consistency: '内容人设一致性',
  grammar_correctness: '语法正确性',
};

// 模拟反馈记录（实际应该从后端获取）
const mockFeedbackRecords = computed(() => {
  if (!props.article) return [];
  return [
    {
      id: 1,
      type: 'quality',
      comment: '内容结构清晰，但结尾有些突兀，建议补充总结',
      user: '张三',
      time: props.article.inspected_at || dayjs().format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      id: 2,
      type: 'brand',
      comment: '品牌调性基本符合，但可以增加更多品牌元素',
      user: '李四',
      time: props.article.inspected_at || dayjs().format('YYYY-MM-DD HH:mm:ss'),
    },
  ];
});
</script>

<template>
  <Modal
    :open="open"
    :footer="null"
    :width="900"
    title="文章审查详情"
    @cancel="handleClose"
  >
    <div v-if="article" class="article-modal-content">
      <!-- 基本信息区 -->
      <div class="info-section">
        <div class="section-title">基本信息</div>
        <Descriptions :column="2" bordered size="small">
          <Descriptions.Item label="文章ID">
            {{ article.id }}
          </Descriptions.Item>
          <Descriptions.Item label="审查状态">
            <Badge
              :status="article.status === 'passed' ? 'success' : 'error'"
              :text="article.status === 'passed' ? '通过' : '不通过'"
            />
          </Descriptions.Item>
          <Descriptions.Item label="综合评分">
            <Tag :color="getScoreColor(article.score || 0)">
              {{ article.score || 0 }}分 -
              {{ getScoreLevel(article.score || 0) }}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="审查员">
            {{ article.inspector_name || '-' }}
          </Descriptions.Item>
          <Descriptions.Item label="审查时间" :span="2">
            {{
              article.inspected_at
                ? dayjs(article.inspected_at).format('YYYY-MM-DD HH:mm:ss')
                : '-'
            }}
          </Descriptions.Item>
        </Descriptions>
      </div>

      <!-- 内容预览区 -->
      <div class="content-section">
        <div class="section-title">内容预览</div>
        <div class="content-preview-box">
          <div class="content-title-text">
            {{ article.title || '无标题' }}
          </div>
          <div class="content-body-text">
            {{ article.content || '无内容' }}
          </div>
        </div>
      </div>

      <!-- 评分维度详情 -->
      <div
        v-if="article.dimensions && article.dimensions.length > 0"
        class="dimensions-section"
      >
        <div class="section-title">评分维度详情</div>
        <div class="dimensions-grid">
          <div
            v-for="dim in article.dimensions"
            :key="dim.dimension"
            class="dimension-item"
          >
            <div class="dimension-name">
              {{ dimensionNameMap[dim.dimension] || dim.dimension }}
            </div>
            <div class="dimension-score-bar">
              <div
                class="dimension-score-fill"
                :style="{
                  width: `${(dim.score / dim.full_score) * 100}%`,
                  background:
                    dim.score >= 80
                      ? '#22c55e'
                      : dim.score >= 60
                        ? '#f59e0b'
                        : '#ef4444',
                }"
              ></div>
            </div>
            <div class="dimension-score-text">
              {{ dim.score }}/{{ dim.full_score }}
            </div>
          </div>
        </div>
      </div>

      <!-- 反馈记录 -->
      <div v-if="article.feedback" class="feedback-section">
        <div class="section-title">反馈意见</div>
        <div class="feedback-content">
          {{ article.feedback }}
        </div>
      </div>

      <!-- 标签 -->
      <div v-if="article.tags && article.tags.length > 0" class="tags-section">
        <div class="section-title">问题标签</div>
        <div class="tags-list">
          <Tag v-for="tag in article.tags" :key="tag" color="warning">
            {{ tag }}
          </Tag>
        </div>
      </div>
    </div>
    <div v-else class="empty-state">暂无数据</div>
  </Modal>
</template>

<style scoped>
.article-modal-content {
  max-height: 70vh;
  overflow-y: auto;
}

.info-section,
.content-section,
.dimensions-section,
.feedback-section,
.tags-section {
  margin-bottom: 24px;
}

.section-title {
  padding-bottom: 8px;
  margin-bottom: 12px;
  font-size: 15px;
  font-weight: 600;
  color: hsl(var(--foreground));
  border-bottom: 1px solid hsl(var(--border));
}

.content-preview-box {
  padding: 16px;
  background: hsl(var(--muted) / 20%);
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.content-title-text {
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.content-body-text {
  font-size: 14px;
  line-height: 1.8;
  color: hsl(var(--muted-foreground));
  overflow-wrap: break-word;
  white-space: pre-wrap;
}

.dimensions-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.dimension-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  overflow: hidden;
  background: hsl(var(--muted) / 20%);
  border-radius: 8px;
}

.dimension-name {
  font-size: 13px;
  font-weight: 500;
  color: hsl(var(--foreground));
}

.dimension-score-bar {
  height: 8px;
  overflow: hidden;
  background: hsl(var(--border));
  border-radius: 4px;
}

.dimension-score-fill {
  height: 100%;
  transition: width 0.5s ease;
}

.dimension-score-text {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-align: right;
}

.feedback-content {
  padding: 16px;
  font-size: 14px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 20%);
  border-left: 3px solid hsl(var(--primary));
  border-radius: 8px;
}

.tags-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-state {
  padding: 40px;
  font-size: 14px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

:deep(.ant-descriptions-item-label) {
  font-weight: 500;
  background: hsl(var(--muted) / 20%) !important;
}

:deep(.ant-modal-body) {
  padding: 24px;
}
</style>
