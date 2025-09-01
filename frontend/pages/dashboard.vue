<script setup lang="ts">
import type { TabsItem } from '@nuxt/ui'

const router = useRouter()
const route = useRoute()

// values match your child routes: /dashboard/:value
const items: TabsItem[] = [
  { label: 'Query',  value: 'query'  },
  { label: 'Upload', value: 'upload' },
  { label: 'List',   value: 'list'   },
  { label: 'AI',     value: 'ai'     }
]

const active = computed<string>({
  get() {
    const seg = route.path.startsWith('/dashboard/')
      ? route.path.split('/')[2] || 'query'
      : 'query'
    return ['query','upload','list','ai'].includes(seg) ? seg : 'query'
  },
  set(val) {
    if (val !== active.value) router.push(`/dashboard/${val}`)
  }
})
</script>

<template>
  <div class="mx-auto">
    <!-- full-width bar styled with Nuxt UI tokens -->
    <div class=" bg-slate-200 border-b border-default">
      <div class="mx-[5%] py-2">
        <UTabs
          v-model="active"
          :items="items"
          :content="false"
          color="neutral"
          variant="pill"
          size="md"
          class="w-full"
          :ui="{
            // these match the docs look
            list: 'bg-elevated rounded-lg p-1',
            trigger: 'grow',
            indicator: 'rounded-md shadow-xs'
          }"
        />
      </div>
    </div>

    <!-- child routes render here -->
    <NuxtPage :keepalive="true" />
  </div>
</template>
