// composables/useGroups.ts
export interface Group {
  id: string
  name: string
  created_at: string
  sort_index?: number | null
}

// Possible API shapes (we normalize them)
type ApiGroup =
  | { group_id: string; name: string; created_at: string; sort_index?: number | null }
  | { id: string; name: string; created_at: string; sort_index?: number | null }
  | Record<string, any>

function normalizeGroup(g: ApiGroup): Group {
  const id = (g as any).id ?? (g as any).group_id
  if (!id) throw new Error('Group missing id/group_id')
  return {
    id,
    name: (g as any).name ?? (g as any).group_name ?? '(unnamed)',
    created_at: (g as any).created_at ?? new Date().toISOString(),
    sort_index: (g as any).sort_index ?? null,
  }
}

/**
 * UI sentinel value for "No Group" selection in dropdowns.
 * Use this in your list page to represent ungrouped files.
 */
export const NO_GROUP_VALUE = '__NO_GROUP__'

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
    return { Authorization: `Bearer ${t}`, 'Content-Type': 'application/json' }
  }

  /** ---------------- Read ---------------- */
  async function listGroups(): Promise<Group[]> {
    const headers = await authHeaders()
    const res = await $fetch<any>(`${API_BASE}/groups`, { method: 'GET', headers })
    const raw: any[] = Array.isArray(res)
      ? res
      : Array.isArray(res?.items)
        ? res.items
        : Array.isArray(res?.groups)
          ? res.groups
          : []
    return raw.map(normalizeGroup)
  }

  /** ---------------- Create ---------------- */
  async function createGroup(name: string, sort_index = 0): Promise<Group> {
    const headers = await authHeaders()
    const res = await $fetch<any>(`${API_BASE}/groups`, {
      method: 'POST',
      headers,
      body: { name, sort_index }, // matches GroupIn
    })
    return normalizeGroup(res)
  }

  /** ---------------- Update (rename) ---------------- */
  async function renameGroup(id: string, name: string): Promise<Group> {
    const headers = await authHeaders()
    const res = await $fetch<any>(`${API_BASE}/groups/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers,
      body: { name }, // matches GroupRename
    })
    return normalizeGroup(res)
  }

  /** ---------------- Delete ---------------- */
  async function deleteGroup(id: string): Promise<void> {
    const headers = await authHeaders()
    await $fetch<void>(`${API_BASE}/groups/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers,
    })
  }

  /**
   * ---------------- Assign/Clear a document's group ----------------
   * Backend accepts:
   *   { group: "<uuid-or-name>" } -> assign (creates by name if needed)
   *   { group: null }             -> clear
   */
  async function setDocGroup(docId: string, group: string | null): Promise<{ ok: boolean; group_id?: string | null }> {
    const headers = await authHeaders()
    const res = await $fetch<{ ok: boolean; group_id?: string | null }>(
      `${API_BASE}/groups/docs/${encodeURIComponent(docId)}/group`,
      {
        method: 'PUT',
        headers,
        body: { group },
      }
    )
    return res
  }

  return {
    listGroups,
    createGroup,
    renameGroup,
    deleteGroup,
    setDocGroup,
    NO_GROUP_VALUE,
  }
}
