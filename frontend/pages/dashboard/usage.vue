<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useQuota } from '@/composables/useQuota'
import BodyCard from '@/components/BodyCard.vue'

const { getQuota } = useQuota()

const quotaInfo = ref<{
  current_count: number
  max_files: number
  remaining: number
  over_limit: number
  is_over_limit: boolean
  can_upload: boolean
  percentage_used: number
} | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

async function loadQuota() {
  try {
    loading.value = true
    error.value = null
    quotaInfo.value = await getQuota()
  } catch (e: any) {
    console.error('Failed to load quota:', e)
    error.value = e?.message ?? 'Failed to load quota information'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadQuota()
})
</script>

<template>
  <BodyCard>
    <div class="flex items-center justify-between mb-6">
      <h1 class="font-semibold text-lg">Usage & Quota</h1>
      <UButton
        icon="i-heroicons-arrow-path"
        :loading="loading"
        @click="loadQuota"
        variant="soft"
        size="sm"
      >
        Refresh
      </UButton>
    </div>

    <div v-if="error" class="text-red-500 text-sm mb-4">
      {{ error }}
    </div>

    <div v-if="quotaInfo" class="max-w-2xl space-y-4">
      <!-- Over Limit Warning Banner -->
      <div v-if="quotaInfo.is_over_limit" class="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
        <div class="flex items-start gap-3">
          <UIcon name="i-heroicons-exclamation-triangle" class="text-red-400 text-xl flex-shrink-0 mt-0.5" />
          <div>
            <h3 class="font-semibold text-red-400 mb-1">Storage Limit Exceeded</h3>
            <p class="text-sm text-red-300 mb-3">
              Your account has <strong>{{ quotaInfo.current_count }} files</strong> but your current plan allows only <strong>{{ quotaInfo.max_files }} files</strong>.
              You need to delete <strong>{{ quotaInfo.over_limit }} file(s)</strong> before you can upload new ones.
            </p>
            <div class="flex gap-2">
              <UButton to="/dashboard/account" size="sm" color="error" variant="solid">
                Upgrade Plan
              </UButton>
              <UButton to="/dashboard" size="sm" color="error" variant="outline">
                Manage Files
              </UButton>
            </div>
          </div>
        </div>
      </div>

      <div class="p-8 bg-zinc-900 rounded-lg border border-zinc-800">
        <div class="flex items-center justify-between mb-4">
          <span class="text-base font-medium text-zinc-200">
            File Storage
          </span>
        </div>

        <div class="text-center mb-6">
          <div class="text-5xl font-bold mb-2" :class="{
            'text-red-400': quotaInfo.is_over_limit || quotaInfo.remaining <= 5,
            'text-orange-400': !quotaInfo.is_over_limit && quotaInfo.remaining <= 10 && quotaInfo.remaining > 5,
            'text-white': !quotaInfo.is_over_limit && quotaInfo.remaining > 10
          }">
            {{ quotaInfo.current_count }}
          </div>
          <div class="text-base text-zinc-400">
            of {{ quotaInfo.max_files }} file tokens
          </div>
          <div class="text-xs text-zinc-500 mt-1">
            (Videos: 5 min = 1 token, Other files: 1 token each)
          </div>
        </div>

        <UProgress
          :model-value="quotaInfo.percentage_used"
          :color="quotaInfo.is_over_limit || quotaInfo.remaining <= 5 ? 'error' : quotaInfo.remaining <= 10 ? 'warning' : 'primary'"
          size="lg"
        />

        <div class="mt-6 text-center">
          <span class="text-base" :class="{
            'text-red-400': quotaInfo.is_over_limit || quotaInfo.remaining <= 5,
            'text-orange-400': !quotaInfo.is_over_limit && quotaInfo.remaining <= 10 && quotaInfo.remaining > 5,
            'text-zinc-400': !quotaInfo.is_over_limit && quotaInfo.remaining > 10
          }">
            <template v-if="quotaInfo.is_over_limit">
              {{ quotaInfo.over_limit }} tokens over limit
            </template>
            <template v-else>
              {{ quotaInfo.remaining }} tokens remaining
            </template>
          </span>
        </div>

        <div v-if="!quotaInfo.is_over_limit && quotaInfo.remaining <= 5" class="mt-6 p-4 bg-orange-500/10 border border-orange-500/20 rounded-lg">
          <p class="text-sm text-orange-400 text-center">
            You're running low on storage. Consider upgrading your plan to upload more files.
          </p>
        </div>
      </div>
    </div>

    <div v-else-if="!error && !loading" class="text-zinc-500">
      No quota information available
    </div>

    <div v-if="loading && !quotaInfo" class="flex items-center justify-center py-12">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin text-2xl text-zinc-400" />
    </div>
  </BodyCard>
</template>
