<script setup lang="ts">
import type { DropdownMenuItem } from '@nuxt/ui'

const route = useRoute()
const user = useSupabaseUser()
const client = useSupabaseClient()

const handleLogout = async () => {
  await client.auth.signOut()
  await navigateTo('/')
}

const dropdownItems = computed<DropdownMenuItem[][]>(() => [
  [{ label: user.value?.email || '', type: 'label' as const }],
  [
    { label: 'Account Settings', icon: 'i-lucide-settings', to: '/account' },
    { label: 'Logout', icon: 'i-lucide-log-out', onSelect: handleLogout }
  ]
])
</script>

<template>
  <div class="header-container" :class="{ 'header-overlay': route.path === '/' }">
    <div class="header-content">
      <!-- Left side -->
      <div class="flex items-center gap-2">
        <UButton
          to="/"
          variant="ghost"
          color="neutral"
          size="lg"
          class="font-bold text-lg hover:text-primary transition-colors"
        >
          <template #leading>
            <img src="/icon.png" alt="SmartQuery" class="w-6 h-6" />
          </template>
          SmartQuery
        </UButton>
      </div>

      <!-- Right side -->
      <div class="flex gap-4 items-center">
        <!-- Logged out: Navigation buttons -->
        <template v-if="!user">
          <UButton size="md" color="neutral" variant="ghost" class="hidden md:inline-flex hover:text-primary transition-colors">Contact us</UButton>
          <UButton size="md" color="neutral" variant="ghost" class="hidden md:inline-flex hover:text-primary transition-colors">Use Cases</UButton>
          <UButton size="md" color="neutral" variant="ghost" class="hidden lg:inline-flex hover:text-primary transition-colors">Demo</UButton>
          <UButton to="/pricing" size="md" color="neutral" variant="ghost" class="hidden sm:inline-flex hover:text-primary transition-colors">Pricing</UButton>
          <UButton to="/login" icon="i-lucide-rocket" size="md" color="primary" variant="solid" class="hover:shadow-lg transition-all">Sign Up</UButton>
        </template>

        <!-- Logged in: Profile dropdown -->
        <template v-else>
          <UButton to="/dashboard/query" icon="i-lucide-home" size="md" color="neutral" variant="ghost" class="hover:text-primary transition-colors">Dashboard</UButton>
          <UButton to="/pricing" size="md" color="neutral" variant="ghost" class="hidden md:inline-flex hover:text-primary transition-colors">Pricing</UButton>

          <UDropdownMenu :items="dropdownItems" :ui="{ content: 'w-48' }">
            <UButton icon="i-lucide-user" color="neutral" variant="ghost" size="md" trailing-icon="i-lucide-chevron-down" />
          </UDropdownMenu>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.header-container {
  background: transparent;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(8px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
  position: sticky;
  top: 0;
  z-index: 50;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 1400px;
  margin: 0 auto;
  padding: 1rem 2rem;
  gap: 2rem;
}

@media (max-width: 768px) {
  .header-content {
    padding: 1rem 1rem;
    gap: 1rem;
  }
}

.header-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  width: 100%;
}
</style>
