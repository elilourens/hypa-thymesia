<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useQuota } from '@/composables/useQuota'

interface QuotaInfo {
  current_page_count: number
  max_pages: number
  page_remaining: number
  page_over_limit: number
  page_is_over_limit: boolean
  page_can_upload: boolean
  page_percentage_used: number
  monthly_file_count: number
  max_monthly_files: number
  monthly_remaining: number
  monthly_can_upload: boolean
  monthly_percentage_used: number
  can_upload: boolean
}

const props = defineProps<{
  quotaInfo?: QuotaInfo | null
  loading?: boolean
}>()

const { getQuota } = useQuota()
const refreshing = ref(false)
const error = ref<string | null>(null)
const showConversionRates = ref(false)
const showMonthlyLimits = ref(false)
const localQuotaInfo = ref<QuotaInfo | null>(props.quotaInfo ?? null)

const isLoading = computed(() => props.loading ?? refreshing.value)
const displayQuotaInfo = computed(() => localQuotaInfo.value ?? props.quotaInfo)

onMounted(() => {
  if (props.quotaInfo) {
    localQuotaInfo.value = props.quotaInfo
  }
})

async function refreshQuota() {
  try {
    refreshing.value = true
    error.value = null
    const updatedQuota = await getQuota()
    localQuotaInfo.value = updatedQuota
  } catch (e: any) {
    console.error('Failed to refresh quota:', e)
    error.value = e?.message ?? 'Failed to refresh quota information'
  } finally {
    refreshing.value = false
  }
}
</script>

<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="font-semibold text-lg">Usage & Quota</h2>
      <UButton
        icon="i-heroicons-arrow-path"
        :loading="isLoading"
        @click="refreshQuota"
        variant="soft"
        size="sm"
      >
        Refresh
      </UButton>
    </div>

    <div v-if="error" class="text-red-500 text-sm mb-4">
      {{ error }}
    </div>

    <div v-if="displayQuotaInfo" class="space-y-4">
      <!-- Over Limit Warning Banner -->
      <div v-if="!displayQuotaInfo!.can_upload" class="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
        <div class="flex items-start gap-3">
          <div>
            <h3 class="font-semibold text-red-400 mb-1">Limit Exceeded</h3>
            <div v-if="!displayQuotaInfo!.page_can_upload" class="text-sm text-red-300 mb-3">
              Your account has <strong>{{ displayQuotaInfo!.current_page_count }} pages</strong> but your current plan allows only <strong>{{ displayQuotaInfo!.max_pages }} pages</strong>.
              You need to delete documents totaling <strong>{{ displayQuotaInfo!.page_over_limit }} page(s)</strong> before you can upload new ones.
            </div>
            <div v-else-if="!displayQuotaInfo!.monthly_can_upload" class="text-sm text-red-300 mb-3">
              You have reached your monthly file upload limit of <strong>{{ displayQuotaInfo!.max_monthly_files }} files</strong>.
              You've already uploaded <strong>{{ displayQuotaInfo!.monthly_file_count }} files</strong> this month. Please try again next month or upgrade to premium.
            </div>
            <div class="flex gap-2">
              <UButton to="/dashboard" size="sm" color="error" variant="solid">
                Manage Files
              </UButton>
            </div>
          </div>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- Page Storage Card -->
        <div class="p-8 bg-zinc-900 rounded-lg border border-zinc-800">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
              <span class="text-base font-medium text-zinc-200">
                Page Storage
              </span>
              <UButton
                icon="i-heroicons-question-mark-circle"
                variant="ghost"
                size="xs"
                :padded="false"
                @click="showConversionRates = true"
              />
            </div>
          </div>

          <div class="text-center mb-6">
            <div class="text-5xl font-bold mb-2" :class="{
              'text-red-400': displayQuotaInfo!.page_is_over_limit || displayQuotaInfo!.page_remaining <= 5,
              'text-orange-400': !displayQuotaInfo!.page_is_over_limit && displayQuotaInfo!.page_remaining <= 10 && displayQuotaInfo!.page_remaining > 5,
              'text-white': !displayQuotaInfo!.page_is_over_limit && displayQuotaInfo!.page_remaining > 10
            }">
              {{ displayQuotaInfo!.current_page_count }}
            </div>
            <div class="text-base text-zinc-400">
              of {{ displayQuotaInfo!.max_pages }} pages
            </div>
          </div>

          <UProgress
            :model-value="displayQuotaInfo!.page_percentage_used"
            :color="displayQuotaInfo!.page_is_over_limit || displayQuotaInfo!.page_remaining <= 5 ? 'error' : displayQuotaInfo!.page_remaining <= 10 ? 'warning' : 'primary'"
            size="lg"
          />

          <div class="mt-6 text-center">
            <span class="text-base" :class="{
              'text-red-400': displayQuotaInfo!.page_is_over_limit || displayQuotaInfo!.page_remaining <= 5,
              'text-orange-400': !displayQuotaInfo!.page_is_over_limit && displayQuotaInfo!.page_remaining <= 10 && displayQuotaInfo!.page_remaining > 5,
              'text-zinc-400': !displayQuotaInfo!.page_is_over_limit && displayQuotaInfo!.page_remaining > 10
            }">
              <template v-if="displayQuotaInfo!.page_is_over_limit">
                {{ displayQuotaInfo!.page_over_limit }} pages over limit
              </template>
              <template v-else>
                {{ displayQuotaInfo!.page_remaining }} pages remaining
              </template>
            </span>
          </div>

          <div v-if="!displayQuotaInfo!.page_is_over_limit && displayQuotaInfo!.page_remaining <= 5" class="mt-6 p-4 bg-orange-500/10 border border-orange-500/20 rounded-lg">
            <p class="text-sm text-orange-400 text-center">
              You're running low on storage. Consider upgrading your plan to upload more pages.
            </p>
          </div>
        </div>

        <!-- Monthly File Upload Card -->
        <div class="p-8 bg-zinc-900 rounded-lg border border-zinc-800">
          <div class="flex items-center justify-between mb-4">
            <div class="flex items-center gap-2">
              <span class="text-base font-medium text-zinc-200">
                Monthly Uploads
              </span>
              <UButton
                icon="i-heroicons-question-mark-circle"
                variant="ghost"
                size="xs"
                :padded="false"
                @click="showMonthlyLimits = true"
              />
            </div>
          </div>

          <div class="text-center mb-6">
            <div class="text-5xl font-bold mb-2" :class="{
              'text-red-400': !displayQuotaInfo!.monthly_can_upload || displayQuotaInfo!.monthly_remaining <= 3,
              'text-orange-400': displayQuotaInfo!.monthly_can_upload && displayQuotaInfo!.monthly_remaining <= 5 && displayQuotaInfo!.monthly_remaining > 3,
              'text-white': displayQuotaInfo!.monthly_can_upload && displayQuotaInfo!.monthly_remaining > 5
            }">
              {{ displayQuotaInfo!.monthly_file_count }}
            </div>
            <div class="text-base text-zinc-400">
              of {{ displayQuotaInfo!.max_monthly_files }} files
            </div>
          </div>

          <UProgress
            :model-value="displayQuotaInfo!.monthly_percentage_used"
            :color="!displayQuotaInfo!.monthly_can_upload || displayQuotaInfo!.monthly_remaining <= 3 ? 'error' : displayQuotaInfo!.monthly_remaining <= 5 ? 'warning' : 'primary'"
            size="lg"
          />

          <div class="mt-6 text-center">
            <span class="text-base" :class="{
              'text-red-400': !displayQuotaInfo!.monthly_can_upload || displayQuotaInfo!.monthly_remaining <= 3,
              'text-orange-400': displayQuotaInfo!.monthly_can_upload && displayQuotaInfo!.monthly_remaining <= 5 && displayQuotaInfo!.monthly_remaining > 3,
              'text-zinc-400': displayQuotaInfo!.monthly_can_upload && displayQuotaInfo!.monthly_remaining > 5
            }">
              <template v-if="!displayQuotaInfo!.monthly_can_upload">
                Limit reached
              </template>
              <template v-else>
                {{ displayQuotaInfo!.monthly_remaining }} uploads remaining
              </template>
            </span>
          </div>

          <div v-if="displayQuotaInfo!.monthly_can_upload && displayQuotaInfo!.monthly_remaining <= 5" class="mt-6 p-4 bg-orange-500/10 border border-orange-500/20 rounded-lg">
            <p class="text-sm text-orange-400 text-center">
              You're approaching your monthly upload limit. Upgrade to upload more files per month.
            </p>
          </div>
        </div>
      </div>

      <!-- Upgrade CTA -->
      <div class="p-8 bg-zinc-900 rounded-lg border border-zinc-800">
        <div class="text-center">
          <h3 class="text-lg font-semibold text-zinc-200 mb-3">Want higher limits?</h3>
          
          <UButton
            color="primary"
            variant="solid"
          >
            Upgrade Now
          </UButton>
        </div>
      </div>
    </div>

    <div v-else-if="!error && !loading" class="text-zinc-500">
      No quota information available
    </div>

    <div v-if="loading && !displayQuotaInfo" class="flex items-center justify-center py-12">
      <UIcon name="i-heroicons-arrow-path" class="animate-spin text-2xl text-zinc-400" />
    </div>

    <!-- Conversion Rates Modal -->
    <UModal v-model:open="showConversionRates" title="Storage Conversion Rates">
      <template #body>
        <div class="space-y-4 text-zinc-300">
          <div class="border-l-2 border-primary-500 pl-4">
            <p class="font-medium text-white mb-1">Document Pages</p>
            <p class="text-sm">1 page in a text document = 1 page of storage</p>
          </div>

          <div class="border-l-2 border-primary-500 pl-4">
            <p class="font-medium text-white mb-1">Images</p>
            <p class="text-sm">1 image = 1 page of storage</p>
          </div>

          <div class="border-l-2 border-primary-500 pl-4">
            <p class="font-medium text-white mb-1">Videos</p>
            <p class="text-sm">100 MB of video = 5 pages of storage</p>
            <p class="text-xs text-zinc-400 mt-1">(Minimum 1 page per video)</p>
          </div>
        </div>
      </template>
    </UModal>

    <!-- Monthly Limits Modal -->
    <UModal v-model:open="showMonthlyLimits" title="Monthly Limits">
      <template #body>
        <div class="space-y-4 text-zinc-300">
          <div class="border-l-2 border-primary-500 pl-4">
            <p class="font-medium text-white mb-1">Monthly Upload Limit</p>
            <p class="text-sm">Maximum number of files you can upload per month. This limit resets on the 1st of each month.</p>
          </div>

          <div class="border-l-2 border-primary-500 pl-4">
            <p class="font-medium text-white mb-1">Bandwidth Limit</p>
            <p class="text-sm">Maximum total data you can upload per month. This also resets on the 1st of each month.</p>
          </div>

          <div class="bg-zinc-800/50 p-3 rounded border border-zinc-700">
            <p class="text-xs text-zinc-400">
              Once your monthly uploads or bandwidth limit is reached, you won't be able to upload new files until the limits reset. Upgrade your plan for higher monthly limits.
            </p>
          </div>
        </div>
      </template>
    </UModal>
  </div>
</template>
