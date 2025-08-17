// nuxt.config.ts
export default defineNuxtConfig({
  modules: ['@nuxtjs/supabase', '@nuxt/ui',],
  css: ['~/assets/css/main.css'],
  supabase: {
    redirectOptions: {
      login: '/login',
      callback: '/confirm', // or whatever you use for magic-link/email callbacks
      exclude: [
        '/',               // homepage
        '/login',
        '/signup',
        '/reset-password',
        '/confirm',        // callback itself
        '/auth/**'         // if you have any auth-prefixed routes
      ]
    }
  }
})