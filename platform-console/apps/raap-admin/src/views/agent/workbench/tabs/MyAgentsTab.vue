<script setup lang="ts">
import { useRouter } from 'vue-router';

import { Button, Card, Result, Space } from 'ant-design-vue';

const router = useRouter();

// 跳转到现有的 Agent 管理页面
function goToAgentManagement() {
  router.push('/job/agent');
}
</script>

<template>
  <div class="my-agents-tab">
    <Card>
      <Result
        title="Agent 管理"
        sub-title="请前往 Agent 管理页面进行 Agent 的创建、编辑和管理操作"
      >
        <template #icon>
          <span class="result-icon">🤖</span>
        </template>
        <template #extra>
          <Space>
            <Button type="primary" size="large" @click="goToAgentManagement">
              前往 Agent 管理
            </Button>
          </Space>
        </template>
      </Result>
    </Card>
  </div>
</template>

<style scoped>
.my-agents-tab {
  padding: 8px 0;
}

.result-icon {
  font-size: 72px;
}
</style>
