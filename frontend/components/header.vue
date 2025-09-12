<template>
  <div class="border-b border-white">
    <div class="flex justify-between items-center mx-[5%] py-2">
      <!-- Left side -->
      <div class="flex items-center gap-2">
        
        <h1 class="text-lg font-bold">Mind Palace</h1>
      </div>

      <!-- Right side -->
      <div class="flex gap-6">
        <div v-if="!$route.path.startsWith('/dashboard')">
          <!-- Only shows if NOT on /dashboard -->
          <UButton icon="i-lucide-rocket" size="md" color="primary" variant="solid">Sign Up</UButton>
        </div>
        <a>Contact Us</a>
        <a>Use Cases</a>
        <a>Demo</a>
        <a>Pricing</a>
      </div>
    </div>
  </div>
</template>
