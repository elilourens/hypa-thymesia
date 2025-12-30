<template>
  <div class="border-b border-white">
    <div class="flex justify-between items-center mx-[20%] py-2">
      <!-- Left side -->
      <div class="flex items-center gap-2">

        <UButton
          to="/"
          variant="ghost"
          color="neutral"
          size="lg"
          class="font-bold text-lg"
        >
          <template #leading>
            <img src="/icon.png" alt="SmartQuery" class="w-6 h-6" />
          </template>
          SmartQuery
        </UButton>
      </div>

      <!-- Right side -->
      <div class="flex gap-6">
        <div v-if="!$route.path.startsWith('/dashboard')">
          <!-- Only shows if NOT on /dashboard -->
          <UButton to="/login" icon="i-lucide-rocket" size="md" color="primary" variant="solid">Sign Up</UButton>
        </div>
        <UButton size="md" color="neutral" variant="ghost">Contact us</UButton>
        <UButton size="md" color="neutral" variant="ghost">Use Cases</UButton>
        <UButton size="md" color="neutral" variant="ghost">Demo</UButton>
        <UButton size="md" color="neutral" variant="ghost">Pricing</UButton>
      </div>
    </div>
  </div>
</template>
