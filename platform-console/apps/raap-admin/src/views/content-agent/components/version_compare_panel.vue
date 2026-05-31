<script setup lang="ts">
import type { ContentAgentApi } from '#/api/core/content-agent';

import { computed } from 'vue';

import { Space, Tag } from 'ant-design-vue';

type TextField = 'body' | 'title';
type TextSide = 'after' | 'before';

const props = defineProps<{
  item: ContentAgentApi.BatchReportItem;
}>();

const compare = computed(() => props.item.version_compare || null);

const compareTypeLabel = computed(() => {
  if (compare.value?.compare_type === 'auto_rewrite') return '系统改写';
  if (compare.value?.compare_type === 'manual_edit') return '人工编辑';
  return compare.value?.compare_type || '修改';
});

const versionLabel = computed(() => {
  const before = compare.value?.before.version_no;
  const after = compare.value?.after.version_no;
  if (before !== null && before !== undefined && after) {
    return `v${before} -> v${after}`;
  }
  return after ? `v${after}` : '版本对比';
});

const bodyDeltaLabel = computed(() => {
  if (!compare.value) return '';
  const delta =
    compare.value.body_after_chars - compare.value.body_before_chars;
  if (delta === 0) return '字数无变化';
  return delta > 0 ? `字数 +${delta}` : `字数 ${delta}`;
});

const hasTitle = computed(
  () =>
    Boolean(compare.value?.before.title) || Boolean(compare.value?.after.title),
);

const changed = (field: TextField) => {
  if (!compare.value) return false;
  return field === 'title'
    ? compare.value.title_changed
    : compare.value.body_changed;
};

const textDiffParts = (
  before: null | string | undefined = '',
  after: null | string | undefined = '',
) => {
  const beforeText = before ?? '';
  const afterText = after ?? '';
  // 轻量高亮：保留共同前后缀，只标出中间真正变化的文本。
  let start = 0;
  while (
    start < beforeText.length &&
    start < afterText.length &&
    beforeText[start] === afterText[start]
  ) {
    start += 1;
  }

  let beforeEnd = beforeText.length;
  let afterEnd = afterText.length;
  while (
    beforeEnd > start &&
    afterEnd > start &&
    beforeText[beforeEnd - 1] === afterText[afterEnd - 1]
  ) {
    beforeEnd -= 1;
    afterEnd -= 1;
  }

  return {
    afterChanged: afterText.slice(start, afterEnd),
    beforeChanged: beforeText.slice(start, beforeEnd),
    prefix: beforeText.slice(0, start),
    suffix: beforeText.slice(beforeEnd),
  };
};

const compareTextParts = (field: TextField, side: TextSide) => {
  const before = compare.value?.before[field] || '';
  const after = compare.value?.after[field] || '';
  const parts = textDiffParts(before, after);
  return {
    changed: side === 'before' ? parts.beforeChanged : parts.afterChanged,
    prefix: parts.prefix,
    suffix: parts.suffix,
  };
};
</script>

<template>
  <div v-if="compare" class="version-compare-panel">
    <div class="compare-head">
      <Space wrap>
        <strong>修改对比</strong>
        <Tag color="blue">{{ compareTypeLabel }}</Tag>
        <Tag>{{ versionLabel }}</Tag>
        <Tag>{{ bodyDeltaLabel }}</Tag>
        <span v-if="compare.after.feedback_text" class="compare-feedback">
          反馈：{{ compare.after.feedback_text }}
        </span>
      </Space>
    </div>

    <div
      v-if="!compare.title_changed && !compare.body_changed"
      class="compare-no-change"
    >
      系统已生成一个改写版本，但正文暂无明显文本变化。
    </div>

    <div class="compare-grid">
      <section class="compare-pane">
        <div class="compare-pane-title">
          修改前
          <span>{{ compare.body_before_chars }} 字</span>
        </div>
        <h4 v-if="hasTitle" class="compare-title">
          <span>{{ compareTextParts('title', 'before').prefix }}</span>
          <mark v-if="changed('title')" class="diff-mark diff-delete">
            {{ compareTextParts('title', 'before').changed || ' ' }}
          </mark>
          <span>{{ compareTextParts('title', 'before').suffix }}</span>
        </h4>
        <div class="compare-body">
          <span>{{ compareTextParts('body', 'before').prefix }}</span>
          <mark v-if="changed('body')" class="diff-mark diff-delete">
            {{ compareTextParts('body', 'before').changed || ' ' }}
          </mark>
          <span>{{ compareTextParts('body', 'before').suffix }}</span>
        </div>
      </section>

      <section class="compare-pane">
        <div class="compare-pane-title">
          修改后
          <span>{{ compare.body_after_chars }} 字</span>
        </div>
        <h4 v-if="hasTitle" class="compare-title">
          <span>{{ compareTextParts('title', 'after').prefix }}</span>
          <mark v-if="changed('title')" class="diff-mark diff-insert">
            {{ compareTextParts('title', 'after').changed || ' ' }}
          </mark>
          <span>{{ compareTextParts('title', 'after').suffix }}</span>
        </h4>
        <div class="compare-body">
          <span>{{ compareTextParts('body', 'after').prefix }}</span>
          <mark v-if="changed('body')" class="diff-mark diff-insert">
            {{ compareTextParts('body', 'after').changed || ' ' }}
          </mark>
          <span>{{ compareTextParts('body', 'after').suffix }}</span>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.version-compare-panel {
  margin-top: 12px;
  padding: 12px;
  border: 1px solid #d9e8ff;
  border-radius: 8px;
  background: #f8fbff;
}

.compare-head {
  margin-bottom: 10px;
}

.compare-feedback {
  color: #595959;
  font-size: 12px;
}

.compare-no-change {
  margin-bottom: 10px;
  color: #8c8c8c;
  font-size: 12px;
}

.compare-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.compare-pane {
  min-width: 0;
  padding: 10px;
  border: 1px solid #edf1f7;
  border-radius: 6px;
  background: #fff;
}

.compare-pane-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  color: #595959;
  font-size: 12px;
  font-weight: 600;
}

.compare-pane-title span {
  color: #8c8c8c;
  font-weight: 400;
}

.compare-title {
  margin: 0 0 8px;
  color: #262626;
  font-size: 14px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.compare-body {
  max-height: 300px;
  overflow: auto;
  color: #262626;
  font-size: 13px;
  line-height: 1.8;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

.diff-mark {
  padding: 1px 2px;
  border-radius: 3px;
  color: inherit;
}

.diff-delete {
  background: #fff1f0;
  text-decoration: line-through;
}

.diff-insert {
  background: #f6ffed;
}

@media (max-width: 768px) {
  .compare-grid {
    grid-template-columns: 1fr;
  }
}
</style>
