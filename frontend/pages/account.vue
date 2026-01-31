<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStripe } from '~/composables/useStripe'

const user = useSupabaseUser()
const client = useSupabaseClient()
const { getSubscriptionStatus, getTierInfo, loading, error } = useStripe()

const subscriptionStatus = ref<any>(null)
const currentTierInfo = ref<any>(null)

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
    </div>
  </div>
</template>
