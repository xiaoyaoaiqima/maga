<script setup lang="ts">
import { onMounted } from 'vue';
import { useRoute } from 'vue-router';

import { Card, Descriptions } from 'ant-design-vue';

const route = useRoute();
const agentCode = route.params.code as string;

onMounted(() => {
  // TODO: 加载 Agent 详情
});
</script>

<template>
  <div class="agent-detail">
    <Card title="Agent 详情">
      <Descriptions bordered :column="2">
        <Descriptions.Item label="Agent 编码">
          {{ agentCode }}
        </Descriptions.Item>
        <Descriptions.Item label="状态"> 待加载 </Descriptions.Item>
      </Descriptions>
    </Card>
  </div>
</template>

<style scoped>
.agent-detail {
  padding: 16px;
}
</style>
