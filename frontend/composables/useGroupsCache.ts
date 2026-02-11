// composables/useGroupsCache.ts
import { ref, computed } from 'vue'
import { useGroupsApi, type Group } from './useGroups'

// Shared state (singleton pattern)
const groups = ref<Group[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
const lastFetched = ref<number | null>(null)

const CACHE_TTL = 5 * 60 * 1000 // 5 minutes

export function useGroupsCache() {
  const { listGroups } = useGroupsApi()

  const isCacheValid = computed(() => {
    if (!lastFetched.value) return false
    return Date.now() - lastFetched.value < CACHE_TTL
  })

  const sortedGroups = computed(() =>
    [...groups.value].sort(
      (a, b) =>
        (a.sort_index ?? 0) - (b.sort_index ?? 0) ||
        a.name.localeCompare(b.name)
    )
  )

  async function fetchGroups(force = false) {
    // Skip if cache is valid and not forcing
    if (!force && isCacheValid.value && groups.value.length > 0) {
      return groups.value
    }

    loading.value = true
    error.value = null

    try {
      groups.value = await listGroups()
      lastFetched.value = Date.now()
      return groups.value
    } catch (e: any) {
      error.value = e?.message ?? 'Failed to load groups'
      throw e
    } finally {
      loading.value = false
    }
  }

  function invalidateCache() {
    lastFetched.value = null
  }

  return {
    groups: sortedGroups,
    loading,
    error,
    fetchGroups,
    invalidateCache,
  }
}
