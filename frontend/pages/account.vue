<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStripe } from '~/composables/useStripe'

const user = useSupabaseUser()
const client = useSupabaseClient()
const { getSubscriptionStatus, getTierInfo, cancelSubscription, downgradeSubscription, loading, error } = useStripe()

const subscriptionStatus = ref<any>(null)
const currentTierInfo = ref<any>(null)
const showCancelModal = ref(false)
const showDowngradeModal = ref(false)
const isCancelling = ref(false)
const isDowngrading = ref(false)

// Redirect if not logged in
onMounted(async () => {
  if (!user.value) {
    await navigateTo('/login')
    return
  }

  // Load subscription status
  try {
    const session = await client.auth.getSession()
    const token = session?.data?.session?.access_token
    if (token) {
      const status = await getSubscriptionStatus(token)
      subscriptionStatus.value = status
      if (status?.tier) {
        currentTierInfo.value = getTierInfo(status.tier)
      }
    }
  } catch (err) {
    console.error('Failed to load subscription status:', err)
  }
})

const handleLogout = async () => {
  await client.auth.signOut()
  await navigateTo('/')
}

const goToPricing = () => {
  navigateTo('/pricing')
}

const getStatusBadgeColor = (tier: string) => {
  if (tier === 'max') return 'amber'
  if (tier === 'pro') return 'blue'
  return 'gray'
}

const getStatusBadgeLabel = (tier: string) => {
  if (tier === 'max') return 'Max Tier'
  if (tier === 'pro') return 'Pro Tier'
  return 'Free Tier'
}

const confirmCancel = async () => {
  try {
    isCancelling.value = true
    const session = await client.auth.getSession()
    const token = session?.data?.session?.access_token

    if (!token) {
      error.value = 'Not authenticated. Please log in first.'
      return
    }

    await cancelSubscription(token)
    showCancelModal.value = false

    // Refresh status
    const status = await getSubscriptionStatus(token)
    subscriptionStatus.value = status
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to cancel subscription'
  } finally {
    isCancelling.value = false
  }
}

const confirmDowngrade = async () => {
  try {
    isDowngrading.value = true
    const session = await client.auth.getSession()
    const token = session?.data?.session?.access_token

    if (!token) {
      error.value = 'Not authenticated. Please log in first.'
      return
    }

    await downgradeSubscription(token, 'pro')
    showDowngradeModal.value = false

    // Refresh status
    const status = await getSubscriptionStatus(token)
    subscriptionStatus.value = status
    if (status?.tier) {
      currentTierInfo.value = getTierInfo(status.tier)
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to downgrade subscription'
  } finally {
    isDowngrading.value = false
  }
}
</script>

<template>
  <div class="min-h-screen py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-3xl mx-auto">
      <!-- Header -->
      <div class="mb-8">
        <h1 class="text-4xl font-bold">Account Settings</h1>
        <p class="mt-2">Manage your account and subscription</p>
      </div>

      <!-- Account Info Card -->
      <UCard class="mb-6" variant="subtle">
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-user-circle-20-solid" class="w-6 h-6" />
            <span class="text-lg font-semibold">Account Information</span>
          </div>
        </template>

        <div class="space-y-6">
          <!-- Email -->
          <div>
            <label class="text-sm font-semibold uppercase tracking-wide">Email</label>
            <p class="mt-2">{{ user?.email }}</p>
          </div>

          <!-- Account Created -->
          <div>
            <label class="text-sm font-semibold uppercase tracking-wide">Account Created</label>
            <p class="mt-2">{{ new Date(user?.created_at || '').toLocaleDateString() }}</p>
          </div>
        </div>

        <template #footer>
          <div class="flex justify-end">
            <UButton
              color="primary"
              icon="i-heroicons-arrow-left-on-rectangle-20-solid"
              @click="handleLogout"
            >
              Logout
            </UButton>
          </div>
        </template>
      </UCard>

      <!-- Subscription Card -->
      <UCard variant="subtle">
        <template #header>
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2">
              <UIcon name="i-heroicons-credit-card-20-solid" class="w-6 h-6" />
              <span class="text-lg font-semibold">Subscription</span>
            </div>
            <div v-if="subscriptionStatus && currentTierInfo">
              <UBadge :color="getStatusBadgeColor(subscriptionStatus.tier)">
                {{ getStatusBadgeLabel(subscriptionStatus.tier) }}
              </UBadge>
            </div>
          </div>
        </template>

        <div class="space-y-6">
          <!-- Current Plan -->
          <div v-if="subscriptionStatus && currentTierInfo">
            <label class="text-sm font-semibold uppercase tracking-wide">Current Plan</label>
            <div class="mt-4 rounded-lg p-4 border border-primary-500">
              <div class="flex items-baseline justify-between mb-4">
                <h3 class="text-2xl font-bold">{{ currentTierInfo.name }}</h3>
                <span class="text-3xl font-bold">
                  £{{ currentTierInfo.price }}
                  <span class="text-lg font-normal">/month</span>
                </span>
              </div>

              <!-- Tier Details -->
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-4">
                <div>
                  <p class="text-sm">Storage</p>
                  <p class="text-lg font-semibold">{{ currentTierInfo.pages.toLocaleString() }} pages</p>
                </div>
                <div>
                  <p class="text-sm">Monthly Uploads</p>
                  <p class="text-lg font-semibold">{{ currentTierInfo.monthlyFiles }} files</p>
                </div>
                <div>
                  <p class="text-sm">Bandwidth</p>
                  <p class="text-lg font-semibold">{{ currentTierInfo.bandwidth }}</p>
                </div>
              </div>
            </div>

            <!-- Subscription Status -->
            <div v-if="subscriptionStatus.is_subscribed" class="mt-6">
              <label class="text-sm font-semibold uppercase tracking-wide">Status</label>
              <div class="mt-2 space-y-2">
                <p>
                  <span class="font-semibold">Status:</span>
                  <UBadge color="green" variant="subtle" class="ml-2">
                    {{ subscriptionStatus.status }}
                  </UBadge>
                </p>
                <p v-if="subscriptionStatus.current_period_end">
                  <span class="font-semibold">Next Billing Date:</span>
                  <span class="ml-2">
                    {{ new Date(subscriptionStatus.current_period_end * 1000).toLocaleDateString() }}
                  </span>
                </p>
                <p v-if="subscriptionStatus.cancel_at_period_end" class="px-3 py-2 rounded-md">
                  <UIcon name="i-heroicons-exclamation-triangle-20-solid" class="inline mr-2 w-4 h-4" />
                  Your subscription will be canceled at the end of the billing period.
                </p>
              </div>
            </div>
          </div>

          <!-- No Subscription -->
          <div v-else>
            <label class="text-sm font-semibold uppercase tracking-wide">Status</label>
            <p class="mt-2">You are currently using the free tier.</p>
          </div>
        </div>

        <template #footer>
          <div class="flex gap-4">
            <UButton
              @click="goToPricing"
              icon="i-heroicons-arrow-up-right-20-solid"
              color="primary"
            >
              {{ subscriptionStatus?.is_subscribed ? 'View All Plans' : 'Upgrade Now' }}
            </UButton>

            <!-- Downgrade button (only for Max tier) -->
            <UButton
              v-if="subscriptionStatus?.is_subscribed && subscriptionStatus?.tier === 'max' && !subscriptionStatus?.cancel_at_period_end"
              @click="showDowngradeModal = true"
              icon="i-heroicons-arrow-down-right-20-solid"
              variant="soft"
            >
              Downgrade to Pro
            </UButton>

            <!-- Cancel button (only if subscribed and not already cancelling) -->
            <UButton
              v-if="subscriptionStatus?.is_subscribed && !subscriptionStatus?.cancel_at_period_end"
              @click="showCancelModal = true"
              icon="i-heroicons-x-mark-20-solid"
              color="red"
              variant="soft"
            >
              Cancel Subscription
            </UButton>
          </div>
        </template>
      </UCard>

      <!-- GDPR Card -->
      <UCard class="mt-6" variant="subtle">
        <template #header>
          <div class="flex items-center gap-2">
            <UIcon name="i-heroicons-shield-check-20-solid" class="w-6 h-6" />
            <span class="text-lg font-semibold">Data Privacy</span>
          </div>
        </template>

        <div class="space-y-4">
          <p class="text-sm">Manage your data and privacy in accordance with GDPR regulations.</p>

          <div class="space-y-3">
            <UButton
              disabled
              icon="i-heroicons-document-text-20-solid"
              class="w-full"
            >
              Request Data Export
              <template #trailing>
                <span class="text-xs">Coming soon</span>
              </template>
            </UButton>

            <UButton
              disabled
              icon="i-heroicons-trash-20-solid"
              color="error"
              variant="soft"
              class="w-full"
            >
              Delete All Data
              <template #trailing>
                <span class="text-xs">Coming soon</span>
              </template>
            </UButton>

            <UButton
              disabled
              icon="i-heroicons-arrow-down-tray-20-solid"
              class="w-full"
            >
              Download My Information
              <template #trailing>
                <span class="text-xs">Coming soon</span>
              </template>
            </UButton>
          </div>
        </div>
      </UCard>

      <!-- Loading State -->
      <div v-if="loading" class="mt-6 text-center">
        <UIcon name="i-heroicons-arrow-path-20-solid" class="w-6 h-6 inline animate-spin" />
        <p class="mt-2">Loading subscription info...</p>
      </div>

      <!-- Error State -->
      <div v-if="error" class="mt-6">
        <UAlert
          icon="i-heroicons-exclamation-triangle-20-solid"
          color="red"
          :title="error"
          variant="soft"
        />
      </div>

      <!-- Cancel Subscription Modal -->
      <UModal v-model:open="showCancelModal" title="Cancel Subscription">
        <template #body>
          <div class="space-y-4">
            <p class="text-zinc-300">
              Your subscription will be cancelled at the end of your current billing period. You'll retain access to all features until the end of the period.
            </p>

            <div class="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
              <p class="text-sm text-zinc-400">
                <strong>After cancellation:</strong><br>
                • You'll be downgraded to the free plan<br>
                • Access to Pro/Max features will end<br>
                • No refund will be issued<br>
                • You can re-subscribe at any time
              </p>
            </div>

            <p class="text-sm text-amber-500/70 border border-amber-500/20 bg-amber-500/5 rounded-lg p-3">
              ⚠️ If you exceed the free plan's limits after cancellation, you won't be able to upload more files.
            </p>
          </div>
        </template>

        <template #footer>
          <div class="flex gap-3 justify-end">
            <UButton variant="ghost" @click="showCancelModal = false" :disabled="isCancelling">
              Keep Subscription
            </UButton>
            <UButton color="red" @click="confirmCancel" :loading="isCancelling">
              Confirm Cancellation
            </UButton>
          </div>
        </template>
      </UModal>

      <!-- Downgrade Modal -->
      <UModal v-model:open="showDowngradeModal" title="Downgrade to Pro">
        <template #body>
          <div class="space-y-4">
            <p class="text-zinc-300">
              You're about to downgrade from Max to Pro. Your plan will change immediately and you'll receive a prorated credit for any unused time.
            </p>

            <div class="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
              <p class="text-sm text-zinc-400">
                <strong>Pro Plan includes:</strong><br>
                • 2,000 total pages (down from 10,000)<br>
                • 500 monthly file uploads (down from 2,000)<br>
                • 20 GB monthly bandwidth (down from 100 GB)
              </p>
            </div>

            <p class="text-sm text-amber-500/70 border border-amber-500/20 bg-amber-500/5 rounded-lg p-3">
              ⚠️ If you exceed the Pro plan's limits, you won't be able to upload more files until you delete some documents.
            </p>
          </div>
        </template>

        <template #footer>
          <div class="flex gap-3 justify-end">
            <UButton variant="ghost" @click="showDowngradeModal = false" :disabled="isDowngrading">
              Cancel
            </UButton>
            <UButton color="amber" @click="confirmDowngrade" :loading="isDowngrading">
              Confirm Downgrade
            </UButton>
          </div>
        </template>
      </UModal>
    </div>
  </div>
</template>
