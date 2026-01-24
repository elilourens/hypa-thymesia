/**
 * Composable for managing document groups
 */

export interface Group {
  group_id: string
  user_id: string
  name: string
  sort_index: number
  created_at: string
  updated_at: string
}

export interface GroupListResponse {
  items: Group[]
  total: number
}

export function useGroupsApi() {
  const supabase = useSupabaseClient()
  const API_BASE = useRuntimeConfig().public.apiBase ?? 'http://127.0.0.1:8000/api/v1'

  async function token() {
    const { data } = await supabase.auth.getSession()
    return data.session?.access_token
  }

  async function authHeaders() {
    const t = await token()
    if (!t) throw new Error('Not logged in')
    return { Authorization: `Bearer ${t}` }
  }

  /**
   * Create a new document group
   */
  async function createGroup(name: string, sortIndex: number = 0): Promise<Group> {
    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(await authHeaders()),
      }

      return await $fetch<Group>(`${API_BASE}/groups/create`, {
        method: 'POST',
        headers,
        body: { name, sort_index: sortIndex },
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to create group')
    }
  }

  /**
   * List all groups for the current user
   */
  async function listGroups(): Promise<GroupListResponse> {
    try {
      const headers = await authHeaders()
      return await $fetch<GroupListResponse>(`${API_BASE}/groups/list`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to load groups')
    }
  }

  /**
   * Get a single group's details
   */
  async function getGroup(groupId: string): Promise<Group> {
    try {
      const headers = await authHeaders()
      return await $fetch<Group>(`${API_BASE}/groups/${groupId}`, {
        method: 'GET',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to get group')
    }
  }

  /**
   * Update a group
   */
  async function updateGroup(groupId: string, name: string, sortIndex?: number): Promise<Group> {
    try {
      const headers = {
        'Content-Type': 'application/json',
        ...(await authHeaders()),
      }

      const body: any = { name }
      if (sortIndex !== undefined) body.sort_index = sortIndex

      return await $fetch<Group>(`${API_BASE}/groups/${groupId}`, {
        method: 'PUT',
        headers,
        body,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to update group')
    }
  }

  /**
   * Delete a group
   */
  async function deleteGroup(groupId: string): Promise<void> {
    try {
      const headers = await authHeaders()
      await $fetch(`${API_BASE}/groups/${groupId}`, {
        method: 'DELETE',
        headers,
      })
    } catch (err: any) {
      throw new Error(err?.data?.detail || err?.message || 'Failed to delete group')
    }
  }

  return {
    createGroup,
    listGroups,
    getGroup,
    updateGroup,
    deleteGroup,
  }
}
