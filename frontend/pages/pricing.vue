<template>
  <div class="py-12 px-4 sm:px-6 lg:px-8">
    <div class="max-w-7xl mx-auto">
      <!-- Header -->
      <div class="text-center mb-16">
        <h1 class="text-4xl font-bold mb-4">Simple, Transparent Pricing</h1>
        <p class="text-xl ">Choose the plan that works best for you</p>
      </div>

      <!-- Pricing Cards Grid -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 max-w-6xl mx-auto mb-12">
        <!-- Free Tier Card -->
        <UCard
          variant="subtle"
          class="rounded-xl overflow-hidden"
        >
          <!-- Card Header -->
          <template #header>
            <div class="p-6">
              <h3 class="text-2xl font-bold ">Free</h3>
              <p class="text-sm  mt-1">Get started for free</p>
            </div>
          </template>

          <!-- Card Body -->
          <div class="p-6">
            <!-- Price -->
            <div class="mb-6">
              <div class="text-5xl font-bold text-primary">£0</div>
              <div class="text-sm  mt-2">/month</div>
            </div>

            <!-- Divider -->
            <div class="border-t my-6"></div>

            <!-- Features -->
            <div class="space-y-4">
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">200 total pages</span>
                <UButton icon="i-heroicons-question-mark-circle" variant="ghost" size="xs" :padded="false" @click="showConversions = true" class="ml-1" />
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">50 monthly file uploads</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">5 GB monthly bandwidth</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">Basic document search</span>
              </div>
            </div>
          </div>
        </UCard>

        <!-- Pro Tier Card -->
        <UCard
          variant="subtle"
          class="rounded-xl overflow-hidden ring-2 ring-primary/20"
        >
          <!-- Card Header -->
          <template #header>
            <div class="p-6">
              <div class="flex items-center justify-between mb-2">
                <h3 class="text-2xl font-bold text-primary">Pro</h3>
                <UBadge color="primary" variant="subtle">Popular</UBadge>
              </div>
              <p class="text-sm  mt-1">Perfect for growing teams</p>
            </div>
          </template>

          <!-- Card Body -->
          <div class="p-6">
            <!-- Price -->
            <div class="mb-6">
              <div class="text-5xl font-bold text-primary">£15</div>
              <div class="text-sm  mt-2">/month</div>
            </div>

            <!-- Divider -->
            <div class="border-t my-6"></div>

            <!-- Features -->
            <div class="space-y-4">
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">2,000 total pages</span>
                <UButton icon="i-heroicons-question-mark-circle" variant="ghost" size="xs" :padded="false" @click="showConversions = true" class="ml-1" />
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">500 monthly file uploads</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">20 GB monthly bandwidth</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">AI summarization for document search</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">Priority support</span>
              </div>
            </div>
          </div>
        </UCard>

        <!-- Max Tier Card -->
        <UCard
          variant="subtle"
          class="rounded-xl overflow-hidden ring-2 ring-white/20"
        >
          <!-- Card Header -->
          <template #header>
            <div class="p-6">
              <h3 class="text-2xl font-bold text-primary">Max</h3>
              <p class="text-sm  mt-1">For power users and professionals</p>
            </div>
          </template>

          <!-- Card Body -->
          <div class="p-6">
            <!-- Price -->
            <div class="mb-6">
              <div class="text-5xl font-bold text-primary">£90</div>
              <div class="text-sm  mt-2">/month</div>
            </div>

            <!-- Divider -->
            <div class="border-t my-6"></div>

            <!-- Features -->
            <div class="space-y-4">
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">10,000 total pages</span>
                <UButton icon="i-heroicons-question-mark-circle" variant="ghost" size="xs" :padded="false" @click="showConversions = true" class="ml-1" />
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">2,000 monthly file uploads</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">100 GB monthly bandwidth</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">AI summarization for document search</span>
              </div>
              <div class="flex items-center ">
                <UIcon name="i-heroicons-check-circle-20-solid" class="w-5 h-5 text-white mr-3 flex-shrink-0" />
                <span class="text-sm">Priority support</span>
              </div>
            </div>
          </div>
        </UCard>
      </div>

      <!-- Action Buttons Grid - Aligned with Cards Above -->
      <div class="grid grid-cols-1 lg:grid-cols-3 gap-8 max-w-6xl mx-auto mb-12">
        <!-- Free Tier Button -->
        <div>
          <UButton
            v-if="!user"
            to="/login"
            class="w-full"
            size="lg"
          >
            Get Started
          </UButton>
          <UButton
            v-else-if="!userTier || userTier === 'free'"
            disabled
            variant="soft"
            class="w-full"
            size="lg"
          >
            <UIcon name="i-heroicons-check-20-solid" class="w-5 h-5 mr-2" />
            Current Plan
          </UButton>
          <UButton
            v-else
            @click="navigateToUpgrade"
            variant="soft"
            class="w-full"
            size="lg"
          >
            Downgrade
          </UButton>
        </div>

        <!-- Pro Tier Button -->
        <div>
          <UButton
            v-if="!user"
            to="/login"
            class="w-full"
            size="lg"
          >
            Choose Pro
          </UButton>
          <UButton
            v-else-if="!userTier || userTier === 'free'"
            @click="selectTier('pro')"
            :loading="loading"
            class="w-full"
            size="lg"
          >
            Upgrade to Pro
          </UButton>
          <UButton
            v-else-if="userTier === 'pro'"
            disabled
            variant="soft"
            class="w-full"
            size="lg"
          >
            <UIcon name="i-heroicons-check-20-solid" class="w-5 h-5 mr-2" />
            Current Plan
          </UButton>
          <UButton
            v-else-if="userTier === 'max'"
            @click="navigateToBillingPortal('pro')"
            variant="soft"
            class="w-full"
            size="lg"
          >
            Downgrade to Pro
          </UButton>
        </div>

        <!-- Max Tier Button -->
        <div>
          <UButton
            v-if="!user"
            to="/login"
            class="w-full"
            size="lg"
          >
            Choose Max
          </UButton>
          <UButton
            v-else-if="!userTier || userTier === 'free'"
            @click="selectTier('max')"
            :loading="loading"
            class="w-full"
            size="lg"
          >
            Upgrade to Max
          </UButton>
          <UButton
            v-else-if="userTier === 'max'"
            disabled
            variant="soft"
            class="w-full"
            size="lg"
          >
            <UIcon name="i-heroicons-check-20-solid" class="w-5 h-5 mr-2" />
            Current Plan
          </UButton>
          <UButton
            v-else-if="userTier === 'pro'"
            @click="selectTier('max')"
            :loading="loading"
            class="w-full"
            size="lg"
          >
            Upgrade to Max
          </UButton>
        </div>
      </div>

      <!-- Conversion Rates Modal -->
      <UModal v-model:open="showConversions" title="Storage Conversion Rates">
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

      <!-- Downgrade Confirmation Modal -->
      <UModal v-model:open="showDowngradeModal" :title="`Downgrade to ${downgradeTarget === 'free' ? 'Free' : 'Pro'}`">
        <template #body>
          <div class="space-y-4">
            <p class="text-zinc-300">
              <span v-if="downgradeTarget === 'free'">
                You're about to cancel your subscription and downgrade to the free plan. Your access will be downgraded immediately.
              </span>
              <span v-else>
                You're about to downgrade from Max to Pro. Your plan will change immediately and you'll receive a prorated credit for any unused time.
              </span>
            </p>

            <div v-if="downgradeTarget === 'pro'" class="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
              <p class="text-sm text-zinc-400">
                <strong>Pro Plan includes:</strong><br>
                • 2,000 total pages<br>
                • 500 monthly file uploads<br>
                • 20 GB monthly bandwidth
              </p>
            </div>

            <div v-if="downgradeTarget === 'free'" class="bg-zinc-800/50 border border-zinc-700 rounded-lg p-4">
              <p class="text-sm text-zinc-400">
                <strong>Free Plan includes:</strong><br>
                • 200 total pages<br>
                • 50 monthly file uploads<br>
                • 5 GB monthly bandwidth
              </p>
            </div>

            <p class="text-sm text-amber-500/70 border border-amber-500/20 bg-amber-500/5 rounded-lg p-3">
              ⚠️ If you exceed the new plan's limits, you won't be able to upload more files until you delete some documents.
            </p>
          </div>
        </template>

        <template #footer>
          <div class="flex gap-3 justify-end">
            <UButton variant="ghost" @click="showDowngradeModal = false" :disabled="isDowngrading">
              Cancel
            </UButton>
            <UButton color="red" @click="confirmDowngrade" :loading="isDowngrading">
              Confirm Downgrade
            </UButton>
          </div>
        </template>
      </UModal>

      <!-- Error Message -->
      <div v-if="error" class="mt-8 max-w-2xl mx-auto">
        <UAlert
          icon="i-heroicons-exclamation-triangle-20-solid"
          color="error"
          :title="error"
          variant="soft"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useStripe } from '~/composables/useStripe'

const user = useSupabaseUser()
const client = useSupabaseClient()
const { createCheckoutSession, getSubscriptionStatus, downgradeSubscription, loading, error } = useStripe()

const userTier = ref<'free' | 'pro' | 'max' | null>(null)
const showConversions = ref(false)
const showDowngradeModal = ref(false)
const downgradeTarget = ref<'pro' | 'free' | null>(null)
const isDowngrading = ref(false)

onMounted(async () => {
  try {
    if (user.value) {
      const session = await client.auth.getSession()
      const token = session?.data?.session?.access_token
      if (token) {
        const status = await getSubscriptionStatus(token)
        userTier.value = (status?.tier || 'free') as 'free' | 'pro' | 'max'
      }
    }
  } catch (err) {
    console.error('Failed to load subscription status:', err)
  }
})

const selectTier = async (tier: 'pro' | 'max') => {
  try {
    const session = await client.auth.getSession()
    const token = session?.data?.session?.access_token
    if (token) {
      await createCheckoutSession(token, tier)
    } else {
      error.value = 'Not authenticated. Please log in first.'
    }
  } catch (err) {
    console.error('Failed to select tier:', err)
  }
}

const navigateToBillingPortal = (target: 'pro' | 'free' = 'pro') => {
  downgradeTarget.value = target
  showDowngradeModal.value = true
}

const confirmDowngrade = async () => {
  if (!downgradeTarget.value) return

  try {
    isDowngrading.value = true
    const session = await client.auth.getSession()
    const token = session?.data?.session?.access_token

    if (!token) {
      error.value = 'Not authenticated. Please log in first.'
      return
    }

    await downgradeSubscription(token, downgradeTarget.value)

    // Show success message based on target tier
    const message = downgradeTarget.value === 'free'
      ? 'Your subscription has been cancelled. You have been downgraded to the free plan.'
      : 'Your subscription has been downgraded to Pro. You\'ll receive a prorated credit.'

    // Close modal and show success
    showDowngradeModal.value = false
    error.value = null

    // Refresh tier
    const status = await getSubscriptionStatus(token)
    userTier.value = (status?.tier || 'free') as 'free' | 'pro' | 'max'
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to downgrade subscription'
  } finally {
    isDowngrading.value = false
  }
}

const navigateToUpgrade = () => {
  navigateTo('/pricing')
}
</script>
