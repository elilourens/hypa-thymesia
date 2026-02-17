<script setup lang="ts">
import { ref, onMounted, computed, h, resolveComponent } from 'vue'
import BodyCard from '@/components/BodyCard.vue'
import type { ApiKey, ApiKeyCreated } from '@/composables/useApiKeys'
import type { TableColumn } from '@nuxt/ui'

const UButton = resolveComponent('UButton')
const UBadge = resolveComponent('UBadge')

const { listApiKeys, createApiKey, revokeApiKey } = useApiKeys()
const config = useRuntimeConfig()

const keys = ref<ApiKey[]>([])
const loading = ref(true)
const error = ref('')

// Create modal state
const showCreate = ref(false)
const newKeyName = ref('')
const creating = ref(false)
const createdKey = ref<ApiKeyCreated | null>(null)
const showCreatedModal = ref(false)
const copied = ref(false)

// Setup tab state
const setupTab = ref('claude')

// Revoke state
const revokingId = ref<string | null>(null)

const apiBase = (config.public.apiBase as string) ?? 'http://127.0.0.1:8000/api/v1'
const mcpUrl = apiBase.replace('/api/v1', '/mcp')

// Table columns
const tableColumns = computed<TableColumn<ApiKey>[]>(() => [
  { accessorKey: 'name', header: 'Name', cell: ({ row }) => h('span', { class: row.original.is_active ? '' : 'text-muted line-through' }, row.getValue('name') as string) },
  { accessorKey: 'key_prefix', header: 'Key', cell: ({ row }) => h('code', { class: 'font-mono text-sm bg-muted px-2 py-0.5 rounded' }, `${row.getValue('key_prefix')}...`) },
  { accessorKey: 'is_active', header: 'Status', cell: ({ row }) => h(UBadge, { color: row.getValue('is_active') ? 'primary' : 'neutral', variant: 'subtle', size: 'sm' }, () => row.getValue('is_active') ? 'Active' : 'Inactive') },
  { accessorKey: 'created_at', header: 'Created', cell: ({ row }) => h('span', { class: 'text-sm text-muted' }, formatDate(row.getValue('created_at') as string | null)) },
  { accessorKey: 'last_used_at', header: 'Last Used', cell: ({ row }) => h('span', { class: 'text-sm text-muted' }, formatDate(row.getValue('last_used_at') as string | null)) },
  { accessorKey: 'use_count', header: 'Uses', cell: ({ row }) => h('span', { class: 'text-sm tabular-nums' }, (row.getValue('use_count') as number).toLocaleString()) },
  {
    accessorKey: 'id',
    header: '',
    cell: ({ row }) => h('div', { class: 'flex justify-end' },
      h(UButton, {
        icon: 'i-lucide-trash-2',
        color: 'error',
        variant: 'ghost',
        size: 'sm',
        loading: revokingId.value === row.getValue('id'),
        onClick: () => handleRevoke(row.getValue('id') as string)
      })
    )
  }
])

onMounted(async () => {
  await loadKeys()
})

async function loadKeys() {
  loading.value = true
  error.value = ''
  try {
    keys.value = await listApiKeys()
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Failed to load API keys'
  } finally {
    loading.value = false
  }
}

async function handleCreate() {
  const name = newKeyName.value.trim()
  if (!name) return
  creating.value = true
  error.value = ''
  try {
    const result = await createApiKey(name)
    createdKey.value = result
    keys.value.unshift(result)
    newKeyName.value = ''
    showCreate.value = false
    showCreatedModal.value = true
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Failed to create API key'
  } finally {
    creating.value = false
  }
}

async function handleRevoke(id: string) {
  revokingId.value = id
  error.value = ''
  try {
    await revokeApiKey(id)
    keys.value = keys.value.filter(k => k.id !== id)
  } catch (e: any) {
    error.value = e?.data?.detail || e?.message || 'Failed to revoke key'
  } finally {
    revokingId.value = null
  }
}

function formatDate(iso: string | null) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

async function copyToClipboard(text: string, setter?: () => void) {
  await navigator.clipboard.writeText(text)
  if (setter) setter()
}

async function copyKey() {
  if (!createdKey.value) return
  await navigator.clipboard.writeText(createdKey.value.key)
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

function mcpConfig(key: string) {
  return JSON.stringify({
    mcpServers: {
      'smartquery': {
        type: 'http',
        url: mcpUrl,
        headers: { Authorization: `Bearer ${key}` }
      }
    }
  }, null, 2)
}

function claudeConfig(key: string) {
  return mcpConfig(key)
}

function clineConfig(key: string) {
  return JSON.stringify({
    customInstructions: `You have access to SmartQuery via MCP. Use it to search and list documents.`,
    mcpServers: {
      smartquery: {
        type: 'http',
        url: mcpUrl,
        headers: { Authorization: `Bearer ${key}` }
      }
    }
  }, null, 2)
}

function curlExample(key: string) {
  return `curl -H "Authorization: Bearer ${key}" \\
  ${mcpUrl}/documents`
}
</script>

<template>
  <BodyCard>
    <div class="space-y-8 p-2">

      <!-- Header -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold">API Access</h1>
          <p class="text-sm text-muted mt-1">
            Connect AI assistants and tools to your files via the
            <a href="https://modelcontextprotocol.io" target="_blank" class="underline hover:text-primary">Model Context Protocol</a>.
          </p>
        </div>
        <UButton
          icon="i-lucide-plus"
          color="primary"
          @click="showCreate = true"
        >
          New API Key
        </UButton>
      </div>

      <!-- Error banner -->
      <UAlert v-if="error" color="error" icon="i-lucide-alert-circle" :description="error" />

      <!-- Create modal -->
      <UModal v-model:open="showCreate" title="Create API Key">
        <template #body>
          <div class="space-y-4 p-1">
            <p class="text-sm text-muted">Give this key a name so you know where it's used (e.g. "Claude Desktop", "Cline", "My App").</p>
            <div>
              <p class="text-xs font-medium mb-1">Key name</p>
              <UInput
                v-model="newKeyName"
                placeholder="e.g. Claude Desktop, Cline, API Integration"
                autofocus
                @keydown.enter="handleCreate"
              />
            </div>
          </div>
        </template>
        <template #footer>
          <div class="flex gap-2 justify-end">
            <UButton color="neutral" variant="ghost" @click="showCreate = false">Cancel</UButton>
            <UButton
              color="primary"
              :loading="creating"
              :disabled="!newKeyName.trim()"
              @click="handleCreate"
            >
              Create
            </UButton>
          </div>
        </template>
      </UModal>

      <!-- New key reveal modal -->
      <UModal
        v-model:open="showCreatedModal"
        title="API Key Created"
        :dismissible="true"
        scrollable
      >
        <template #body>
          <div class="space-y-6 p-1">
            <UAlert
              color="warning"
              icon="i-lucide-triangle-alert"
              description="Copy your API key now — it won't be shown again."
            />

            <!-- Key display -->
            <div class="space-y-2">
              <p class="text-xs font-medium">Your API Key</p>
              <div class="flex items-center gap-2">
                <UInput
                  :model-value="createdKey?.key"
                  readonly
                  class="font-mono text-sm flex-1"
                />
                <UButton
                  :icon="copied ? 'i-lucide-check' : 'i-lucide-copy'"
                  :color="copied ? 'success' : 'neutral'"
                  variant="outline"
                  @click="copyKey"
                >
                  {{ copied ? 'Copied!' : 'Copy' }}
                </UButton>
              </div>
            </div>

            <!-- Setup tabs -->
            <div class="space-y-2">
              <p class="text-xs font-medium">Setup Instructions</p>
              <UTabs v-model="setupTab" :items="[
                { label: 'Claude', value: 'claude' },
                { label: 'Cline', value: 'cline' },
                { label: 'curl/REST', value: 'curl' },
              ]" />

              <!-- Claude setup -->
              <div v-if="setupTab === 'claude'" class="space-y-3 py-3">
                <div class="space-y-2">
                  <p class="text-sm font-medium">Claude Desktop / Code Config</p>
                  <div class="relative">
                    <pre class="bg-muted rounded-lg p-3 text-xs overflow-x-auto font-mono">{{ createdKey ? claudeConfig(createdKey.key) : '' }}</pre>
                    <UButton
                      icon="i-lucide-copy"
                      size="xs"
                      color="neutral"
                      variant="ghost"
                      class="absolute top-2 right-2"
                      @click="createdKey && copyToClipboard(claudeConfig(createdKey.key))"
                    />
                  </div>
                </div>
                <div class="space-y-2">
                  <p class="text-xs font-medium">Config File Location</p>
                  <ul class="text-xs text-muted space-y-1">
                    <li><strong>Claude Code:</strong> <code class="bg-muted px-1 rounded">~/.claude/claude.json</code></li>
                    <li><strong>Claude Desktop:</strong> <code class="bg-muted px-1 rounded">%APPDATA%\Claude\claude_desktop_config.json</code></li>
                  </ul>
                </div>
                <p class="text-xs text-muted">After updating the config, restart Claude. You can then ask: <em>"Search my files for X"</em> or <em>"List my documents"</em></p>
              </div>

              <!-- Cline setup -->
              <div v-if="setupTab === 'cline'" class="space-y-3 py-3">
                <div class="space-y-2">
                  <p class="text-sm font-medium">Cline MCP Server Config</p>
                  <div class="relative">
                    <pre class="bg-muted rounded-lg p-3 text-xs overflow-x-auto font-mono">{{ createdKey ? clineConfig(createdKey.key) : '' }}</pre>
                    <UButton
                      icon="i-lucide-copy"
                      size="xs"
                      color="neutral"
                      variant="ghost"
                      class="absolute top-2 right-2"
                      @click="createdKey && copyToClipboard(clineConfig(createdKey.key))"
                    />
                  </div>
                </div>
                <div class="space-y-2">
                  <p class="text-xs font-medium">Config File Location</p>
                  <ul class="text-xs text-muted space-y-1">
                    <li>Cline settings in VS Code or your editor</li>
                    <li>Add the above MCP server configuration to enable SmartQuery access</li>
                  </ul>
                </div>
              </div>

              <!-- curl/REST setup -->
              <div v-if="setupTab === 'curl'" class="space-y-3 py-3">
                <div class="space-y-2">
                  <p class="text-sm font-medium">Direct HTTP Request Example</p>
                  <div class="relative">
                    <pre class="bg-muted rounded-lg p-3 text-xs overflow-x-auto font-mono">{{ createdKey ? curlExample(createdKey.key) : '' }}</pre>
                    <UButton
                      icon="i-lucide-copy"
                      size="xs"
                      color="neutral"
                      variant="ghost"
                      class="absolute top-2 right-2"
                      @click="createdKey && copyToClipboard(curlExample(createdKey.key))"
                    />
                  </div>
                </div>
                <div class="space-y-2">
                  <p class="text-xs font-medium">Available Endpoints</p>
                  <ul class="text-xs text-muted space-y-1 list-disc list-inside">
                    <li><code class="bg-muted px-1 rounded">GET /api/v1/documents</code> - List documents</li>
                    <li><code class="bg-muted px-1 rounded">POST /api/v1/search</code> - Search files</li>
                    <li><code class="bg-muted px-1 rounded">GET /api/v1/documents/:id</code> - Get document details</li>
                  </ul>
                </div>
                <p class="text-xs text-muted">Include the API key in the <code class="bg-muted px-1 rounded">Authorization: Bearer &lt;key&gt;</code> header for all requests.</p>
              </div>
            </div>
          </div>
        </template>
        <template #footer>
          <div class="flex justify-end">
            <UButton color="primary" @click="showCreatedModal = false; createdKey = null">Done</UButton>
          </div>
        </template>
      </UModal>

      <!-- Keys table -->
      <div>
        <div v-if="loading" class="space-y-2">
          <div v-for="i in 3" :key="i" class="h-12 bg-muted rounded animate-pulse" />
        </div>

        <div v-else-if="keys.length === 0" class="text-center py-12 text-muted">
          <div class="text-5xl mx-auto mb-3 opacity-30">🔑</div>
          <p>No API keys yet. Create one to get started.</p>
        </div>

        <UTable
          v-else
          :data="keys"
          :columns="tableColumns"
          :ui="{
            base: 'rounded-lg overflow-hidden border border-foreground/10 backdrop-blur-md bg-background/30 table-striped',
            thead: 'bg-zinc-900 backdrop-blur-sm sticky top-0 z-10',
            th: 'text-left font-semibold text-sm text-foreground/80 px-3 py-2',
            tbody: '',
            tr: 'transition-colors hover:bg-foreground/5',
            td: 'px-3 py-2'
          }"
        />

      </div>

      <USeparator />

      <!-- How it works section -->
      <div class="p-6 bg-zinc-900 rounded-lg border border-zinc-800 space-y-3">
          <h2 class="font-semibold"> How API Access Works</h2>
          <ol class="text-sm text-muted space-y-2 list-decimal list-inside">
            <li>Create an API key above</li>
            <li>Choose your setup (Claude, Cline, or REST API + more)</li>
            <li>Copy the configuration or credentials</li>
            <li>Integrate with your tool or client</li>
            <li>Start using SmartQuery programmatically or via AI assistants</li>
          </ol>
          <div class="bg-zinc-800/50 rounded-lg p-3 space-y-2 text-xs border border-zinc-700">
            <p><strong>MCP Endpoint:</strong> <code class="bg-muted px-1 rounded font-mono">{{ mcpUrl }}</code></p>
            <p><strong>Server Name:</strong> <code class="bg-muted px-1 rounded font-mono">smartquery</code></p>
            <p class="text-muted">All requests require Bearer token authentication with your API key.</p>
          </div>
      </div>

    </div>
  </BodyCard>
</template>
