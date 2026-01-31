export default defineRouteMiddleware((to, from) => {
  const user = useSupabaseUser()

  if (!user.value) {
    navigateTo('/login')
  }
})
