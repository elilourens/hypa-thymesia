// nuxt.config.ts
export default defineNuxtConfig({
  modules: ['@nuxtjs/supabase', '@nuxt/ui',],
  css: ['~/assets/css/main.css'],

  app: {
    head: {
      link: [
        { rel: 'icon', type: 'image/png', href: '/icon.png' }
      ]
    }
  },

  runtimeConfig: {
    public: {
      apiBase: process.env.NODE_ENV === 'production'
        ? 'https://hypa-thymesia-production.up.railway.app/api/v1'
        : 'http://127.0.0.1:8000/api/v1',
    }
  },

  nitro: {
    preset: 'cloudflare-pages'
  },

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
        '/auth/**',        // if you have any auth-prefixed routes
        '/privacy'         // privacy policy page
      ]
    }
  }
})