<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useStripe } from '@/composables/useStripe'
import { useQuota } from '@/composables/useQuota'
import BodyCard from '@/components/BodyCard.vue'

const client = useSupabaseClient()
const toast = useToast()
const route = useRoute()

const { getSubscriptionStatus, createCheckoutSession, cancelSubscription, subscriptionStatus, loading, error } = useStripe()
const { getQuota } = useQuota()

const quotaInfo = ref<{ current_count: number; max_files: number; remaining: number } | null>(null)
const loadingQuota = ref(false)

// Computed properties
const isSubscribed = computed(() => subscriptionStatus.value?.is_subscribed || false)
const subscriptionPeriodEnd = computed(() => {
  if (!subscriptionStatus.value?.current_period_end) return null
  return new Date(subscriptionStatus.value.current_period_end * 1000).toLocaleDateString()
})

const willCancelAtPeriodEnd = computed(() => subscriptionStatus.value?.cancel_at_period_end || false)

async function loadData() {
  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) {
      toast.add({
        title: 'Error',
        description: 'You must be logged in',
        color: 'error'
      })
      return
    }

    // Load both subscription status and quota in parallel
    await Promise.all([
      getSubscriptionStatus(session.access_token),
      loadQuota()
    ])
  } catch (err) {
    console.error('Error loading account data:', err)
  }
}

async function loadQuota() {
  try {
    loadingQuota.value = true
    quotaInfo.value = await getQuota()
  } catch (e: any) {
    console.error('Failed to load quota:', e)
  } finally {
    loadingQuota.value = false
  }
}

async function handleUpgrade() {
  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) {
      toast.add({
        title: 'Error',
        description: 'You must be logged in',
        color: 'error'
      })
      return
    }

    await createCheckoutSession(session.access_token)
  } catch (err) {
    toast.add({
      title: 'Error',
      description: error.value || 'Failed to start checkout',
      color: 'error'
    })
  }
}

async function handleCancelSubscription() {
  if (!confirm('Are you sure you want to cancel your subscription? You will retain access until the end of your current billing period.')) {
    return
  }

  try {
    const { data: { session } } = await client.auth.getSession()
    if (!session?.access_token) return

    await cancelSubscription(session.access_token)

    toast.add({
      title: 'Subscription cancelled',
      description: 'Your subscription will end at the end of the current billing period',
      color: 'success'
    })
  } catch (err) {
    toast.add({
      title: 'Error',
      description: error.value || 'Failed to cancel subscription',
      color: 'error'
    })
  }
}

// Check for successful payment redirect
onMounted(async () => {
  await loadData()

  // Check if redirected from successful payment
  if (route.query.session_id) {
    toast.add({
      title: 'Payment successful!',
      description: 'Your account has been upgraded to Premium',
      color: 'success',
      icon: 'i-lucide-check'
    })

    // Clean up URL
    const url = new URL(window.location.href)
    url.searchParams.delete('session_id')
    window.history.replaceState({}, '', url.toString())

    // Reload data to show updated subscription
    await loadData()
  } else if (route.query.canceled) {
    toast.add({
      title: 'Payment cancelled',
      description: 'No charges were made',
      color: 'neutral',
      icon: 'i-lucide-info'
    })

    // Clean up URL
    const url = new URL(window.location.href)
    url.searchParams.delete('canceled')
    window.history.replaceState({}, '', url.toString())
  }
})
</script>

<template>
  <BodyCard>
    <h1 class="font-semibold text-lg mb-6">Account Settings</h1>

    <!-- Subscription Status Card -->
    <div class="mb-8">
      <h2 class="text-base font-medium mb-4">Subscription Plan</h2>

      <div class="p-6 bg-zinc-900 rounded-lg border border-zinc-800">
        <!-- Current Plan -->
        <div class="flex items-center justify-between mb-6">
          <div>
            <div class="text-xl font-semibold mb-1">
              {{ isSubscribed ? 'Premium Plan' : 'Free Plan' }}
            </div>
            <div class="text-sm text-zinc-400">
              {{ isSubscribed ? '100 files • £2.99/month' : '50 files • Free forever' }}
            </div>
          </div>
          <div v-if="isSubscribed" class="px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-md">
            <span class="text-sm font-medium text-green-400">Active</span>
          </div>
        </div>

        <!-- Current Usage -->
        <div v-if="quotaInfo" class="mb-6">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-zinc-400">Current Usage</span>
            <span class="text-sm font-medium">{{ quotaInfo.current_count }} / {{ quotaInfo.max_files }} files</span>
          </div>
          <UProgress
            :model-value="(quotaInfo.current_count / quotaInfo.max_files) * 100"
            :color="quotaInfo.remaining <= 5 ? 'error' : quotaInfo.remaining <= 10 ? 'warning' : 'primary'"
            size="sm"
          />
        </div>

        <!-- Subscription Details -->
        <div v-if="isSubscribed" class="mb-6 p-4 bg-zinc-800/50 rounded-lg border border-zinc-700">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm text-zinc-400">Billing Period</span>
            <span class="text-sm">{{ subscriptionPeriodEnd }}</span>
          </div>
          <div v-if="willCancelAtPeriodEnd" class="mt-3 p-3 bg-orange-500/10 border border-orange-500/20 rounded-md">
            <p class="text-sm text-orange-400">
              Your subscription will be cancelled on {{ subscriptionPeriodEnd }}
            </p>
          </div>
        </div>

        <!-- Actions -->
        <div class="flex gap-3">
          <UButton
            v-if="!isSubscribed"
            @click="handleUpgrade"
            :loading="loading"
            color="primary"
            size="lg"
            icon="i-lucide-sparkles"
          >
            Upgrade to Premium
          </UButton>

          <UButton
            v-if="isSubscribed && !willCancelAtPeriodEnd"
            @click="handleCancelSubscription"
            :loading="loading"
            variant="soft"
            color="error"
          >
            Cancel Subscription
          </UButton>
        </div>
      </div>
    </div>

    <!-- Premium Features -->
    <div v-if="!isSubscribed">
      <h2 class="text-base font-medium mb-4">Premium Features</h2>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div class="p-4 bg-zinc-900 rounded-lg border border-zinc-800">
          <div class="flex items-start gap-3">
            <div class="mt-1 p-2 bg-blue-500/10 rounded-lg">
              <UIcon name="i-lucide-files" class="text-lg text-blue-400" />
            </div>
            <div>
              <div class="font-medium mb-1">100 File Limit</div>
              <div class="text-sm text-zinc-400">Upload up to 100 files instead of 50</div>
            </div>
          </div>
        </div>

        <div class="p-4 bg-zinc-900 rounded-lg border border-zinc-800">
          <div class="flex items-start gap-3">
            <div class="mt-1 p-2 bg-green-500/10 rounded-lg">
              <UIcon name="i-lucide-zap" class="text-lg text-green-400" />
            </div>
            <div>
              <div class="font-medium mb-1">Priority Support</div>
              <div class="text-sm text-zinc-400">Get faster responses to your questions</div>
            </div>
          </div>
        </div>

        <div class="p-4 bg-zinc-900 rounded-lg border border-zinc-800">
          <div class="flex items-start gap-3">
            <div class="mt-1 p-2 bg-purple-500/10 rounded-lg">
              <UIcon name="i-lucide-shield-check" class="text-lg text-purple-400" />
            </div>
            <div>
              <div class="font-medium mb-1">Premium Security</div>
              <div class="text-sm text-zinc-400">Enhanced data protection and backup</div>
            </div>
          </div>
        </div>

        <div class="p-4 bg-zinc-900 rounded-lg border border-zinc-800">
          <div class="flex items-start gap-3">
            <div class="mt-1 p-2 bg-orange-500/10 rounded-lg">
              <UIcon name="i-lucide-heart" class="text-lg text-orange-400" />
            </div>
            <div>
              <div class="font-medium mb-1">Support Development</div>
              <div class="text-sm text-zinc-400">Help us build more features</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Pricing -->
      <div class="mt-6 p-6 bg-gradient-to-br from-blue-500/10 to-purple-500/10 rounded-lg border border-blue-500/20">
        <div class="text-center">
          <div class="text-4xl font-bold mb-2">£2.99<span class="text-lg font-normal text-zinc-400">/month</span></div>
          <p class="text-sm text-zinc-400 mb-4">Cancel anytime, no commitments</p>
          <UButton
            @click="handleUpgrade"
            :loading="loading"
            size="lg"
            color="primary"
            icon="i-lucide-sparkles"
          >
            Upgrade Now
          </UButton>
        </div>
      </div>
    </div>

    <!-- Error Display -->
    <UAlert
      v-if="error"
      :title="error"
      color="error"
      variant="subtle"
      class="mt-4"
    />
  </BodyCard>
</template>
