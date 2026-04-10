<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

import ExpertConfigPage from '#/views/config/expert-config/index.vue';

const route = useRoute();
const code = computed(() => {
  const value = route.query.code;
  return typeof value === 'string' ? value : '';
});
</script>

<template>
  <ExpertConfigPage :page-mode="true" :initial-code="code" />
</template>
