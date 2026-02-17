<script setup lang="ts">
import { ref, watch } from 'vue'
import BodyCard from '@/components/BodyCard.vue'

// Tab selection persisted in localStorage
const selectedTab = ref(
  typeof window !== 'undefined'
    ? localStorage.getItem('dashboardTab') || '0'
    : '0'
)

// Watch for tab changes and persist
watch(selectedTab, (newTab) => {
  if (typeof window !== 'undefined') {
    localStorage.setItem('dashboardTab', newTab)
  }
})

const tabs = [
  { label: 'Search', slot: 'search' },
  { label: 'Upload', slot: 'upload' },
  { label: 'Groups', slot: 'groups' },
  { label: 'Connections', slot: 'connections' },
  { label: 'AI Assistant', slot: 'ai' },
  { label: 'MCP Access', slot: 'mcp' },
]
</script>

<template>
  <BodyCard>
    <div class="space-y-4">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold">Dashboard</h1>
      </div>

      <!-- Tabs -->
      <UTabs v-model="selectedTab" :items="tabs" class="w-full">
        <!-- Search tab -->
        <template #search>
          <LazyDashboardQuery />
        </template>

        <!-- Upload tab -->
        <template #upload>
          <LazyDashboardUpload />
        </template>

        <!-- Groups tab -->
        <template #groups>
          <LazyDashboardGroups />
        </template>

        <!-- Connections tab -->
        <template #connections>
          <LazyDashboardConnections />
        </template>

        <!-- AI Assistant tab -->
        <template #ai>
          <LazyDashboardAi />
        </template>

        <!-- MCP Access tab -->
        <template #mcp>
          <LazyDashboardMcp />
        </template>
      </UTabs>
    </div>
  </BodyCard>
</template>
