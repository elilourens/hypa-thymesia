import { ref } from 'vue'
import { loadStripe, type Stripe } from '@stripe/stripe-js'

interface SubscriptionStatus {
  is_subscribed: boolean
  subscription_id?: string
  status?: string
  tier?: 'free' | 'pro' | 'max'
  current_period_end?: number
  cancel_at_period_end?: boolean
}

interface TierInfo {
  name: string
  price: number
  pages: number
  monthlyFiles: number
  bandwidth: string
}

export const useStripe = () => {
  const config = useRuntimeConfig()
  const API_BASE = config.public.apiBase ?? 'http://127.0.0.1:8000/api/v1'
  const loading = ref(false)
  const error = ref<string | null>(null)
  const subscriptionStatus = ref<SubscriptionStatus | null>(null)

  /**
   * Get the user's current subscription status
   */
  const getSubscriptionStatus = async (supabaseAccessToken: string): Promise<SubscriptionStatus | null> => {
    try {
      loading.value = true
      error.value = null

      const response = await fetch(`${API_BASE}/stripe/subscription-status`, {
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to get subscription status')
      }

      const data = await response.json()
      subscriptionStatus.value = data
      return data
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to get subscription status'
      return null
    } finally {
      loading.value = false
    }
  }

  /**
   * Create a Stripe checkout session and redirect to payment page
   */
  const createCheckoutSession = async (
    supabaseAccessToken: string,
    tier: 'pro' | 'max' = 'pro'
  ): Promise<void> => {
    try {
      loading.value = true
      error.value = null

      // Create checkout session
      const response = await fetch(`${API_BASE}/stripe/create-checkout-session`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          tier,
          success_url: `${window.location.origin}/account?session_id={CHECKOUT_SESSION_ID}`,
          cancel_url: `${window.location.origin}/pricing?canceled=true`
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to create checkout session')
      }

      const data = await response.json()

      // Redirect to Stripe checkout
      window.location.href = data.url
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to start checkout'
      loading.value = false
      throw err
    }
  }

  /**
   * Cancel the user's subscription at the end of the billing period
   */
  const cancelSubscription = async (supabaseAccessToken: string): Promise<void> => {
    try {
      loading.value = true
      error.value = null

      const response = await fetch(`${API_BASE}/stripe/cancel-subscription`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        }
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to cancel subscription')
      }

      // Refresh subscription status
      await getSubscriptionStatus(supabaseAccessToken)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to cancel subscription'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Downgrade the user's subscription to a lower tier or free
   */
  const downgradeSubscription = async (
    supabaseAccessToken: string,
    targetTier: 'pro' | 'free'
  ): Promise<void> => {
    try {
      loading.value = true
      error.value = null

      const response = await fetch(`${API_BASE}/stripe/downgrade-subscription`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${supabaseAccessToken}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          target_tier: targetTier
        })
      })

      if (!response.ok) {
        const errorData = await response.json()
        throw new Error(errorData.detail || 'Failed to downgrade subscription')
      }

      // Refresh subscription status
      await getSubscriptionStatus(supabaseAccessToken)
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to downgrade subscription'
      throw err
    } finally {
      loading.value = false
    }
  }

  /**
   * Get tier information including pricing and limits
   */
  const getTierInfo = (tier: 'free' | 'pro' | 'max'): TierInfo => {
    const tiers: Record<'free' | 'pro' | 'max', TierInfo> = {
      free: {
        name: 'Free',
        price: 0,
        pages: 200,
        monthlyFiles: 50,
        bandwidth: '5 GB'
      },
      pro: {
        name: 'Pro',
        price: 15,
        pages: 2000,
        monthlyFiles: 500,
        bandwidth: '20 GB'
      },
      max: {
        name: 'Max',
        price: 90,
        pages: 10000,
        monthlyFiles: 2000,
        bandwidth: '100 GB'
      }
    }
    return tiers[tier]
  }

  return {
    loading,
    error,
    subscriptionStatus,
    getSubscriptionStatus,
    createCheckoutSession,
    cancelSubscription,
    downgradeSubscription,
    getTierInfo
  }
}
