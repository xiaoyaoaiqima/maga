<script setup lang="ts">
import { Page } from '@vben/common-ui';

import DailyStatsRebuildCard from './components/DailyStatsRebuildCard.vue';
import TraceRecalcCard from './components/TraceRecalcCard.vue';

interface ToolItem {
  component: any;
  description: string;
  id: string;
  title: string;
}

const tools: ToolItem[] = [
  {
    component: TraceRecalcCard,
    description:
      '根据最新定价模型，回算历史 Trace 的成本数据。支持按时间范围分批处理。',
    id: 'trace-recalc',
    title: 'Trace 成本回算',
  },
  {
    component: DailyStatsRebuildCard,
    description:
      '根据 Trace 明细数据，重新生成每日聚合统计报表（trace_daily_stats）。',
    id: 'stats-rebuild',
    title: '日统计数据重建',
  },
];
</script>

<template>
  <Page
    description="管理员运维工具箱，支持数据回算、统计重建等高级维护任务。"
    title="管理工具"
  >
    <div class="p-4">
      <div class="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <template v-for="tool in tools" :key="tool.id">
          <component
            :is="tool.component"
            :description="tool.description"
            :title="tool.title"
          />
        </template>
      </div>
    </div>
  </Page>
</template>
