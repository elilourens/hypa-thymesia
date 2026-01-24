import { ref } from 'vue'
import { loadStripe, type Stripe } from '@stripe/stripe-js'

interface SubscriptionStatus {
  is_subscribed: boolean
  subscription_id?: string
  status?: string
  current_period_end?: number
  cancel_at_period_end?: boolean
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
  const createCheckoutSession = async (supabaseAccessToken: string): Promise<void> => {
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
          success_url: `${window.location.origin}/dashboard/upload?session_id={CHECKOUT_SESSION_ID}`,
          cancel_url: `${window.location.origin}/dashboard/upload?canceled=true`
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

  return {
    loading,
    error,
    subscriptionStatus,
    getSubscriptionStatus,
    createCheckoutSession,
    cancelSubscription
  }
}
