import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from './stores/auth.js'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('./components/Login.vue'),
    meta: { requiresAuth: false }
  },
  {
    path: '/',
    redirect: '/faders'
  },
  {
    path: '/faders',
    name: 'Faders',
    component: () => import('./components/FaderControl.vue'),
    meta: { requiresAuth: true, page: 'faders' }
  },
  {
    path: '/fixtures',
    name: 'Fixtures',
    component: () => import('./components/FixtureLibrary.vue'),
    meta: { requiresAuth: true, page: 'fixtures' }
  },
  {
    path: '/patch',
    name: 'Patch',
    component: () => import('./components/PatchManager.vue'),
    meta: { requiresAuth: true, page: 'patch' }
  },
  {
    path: '/io',
    name: 'InputOutput',
    component: () => import('./components/InputOutput.vue'),
    meta: { requiresAuth: true, page: 'io' }
  },
  {
    path: '/mapping',
    name: 'ChannelMapping',
    component: () => import('./components/ChannelMapping.vue'),
    meta: { requiresAuth: true, page: 'io' }
  },
  {
    path: '/groups',
    name: 'Groups',
    component: () => import('./components/Groups.vue'),
    meta: { requiresAuth: true, page: 'groups' }
  },
  {
    path: '/scenes',
    name: 'Scenes',
    component: () => import('./components/SceneManager.vue'),
    meta: { requiresAuth: true, page: 'scenes' }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: () => import('./components/Settings.vue'),
    meta: { requiresAuth: true, page: 'settings' }
  },
  {
    path: '/remote-api',
    name: 'RemoteAPI',
    component: () => import('./components/RemoteAPI.vue'),
    meta: { requiresAuth: true, page: 'settings' }
  },
  {
    path: '/help',
    name: 'Help',
    component: () => import('./components/Help.vue'),
    meta: { requiresAuth: true, page: 'help' }
  },
  {
    path: '/unauthorized',
    name: 'Unauthorized',
    component: () => import('./components/Unauthorized.vue'),
    meta: { requiresAuth: true }
  },
  {
    path: '/monitor',
    name: 'NetworkMonitor',
    component: () => import('./components/NetworkMonitor.vue'),
    meta: { requiresAuth: true, page: 'monitor' }
  },
  {
    path: '/control-flow',
    name: 'ControlFlow',
    component: () => import('./components/ControlFlow.vue'),
    meta: { requiresAuth: true, page: 'io' }
  },
  {
    path: '/midi',
    name: 'MIDIControl',
    component: () => import('./components/MIDIControl.vue'),
    meta: { requiresAuth: true, page: 'midi' }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // Check auth status if not already checked
  if (!authStore.checked) {
    await authStore.checkAuth()
  }

  // Redirect to login if not authenticated
  if (to.meta.requiresAuth && !authStore.authenticated) {
    next('/login')
    return
  }

  // Redirect to first allowed page if already authenticated and going to login
  if (to.path === '/login' && authStore.authenticated) {
    const firstPage = authStore.allowedPages[0] || 'faders'
    next(`/${firstPage}`)
    return
  }

  // Check page access for protected routes
  if (to.meta.page && authStore.authenticated) {
    if (!authStore.hasPageAccess(to.meta.page)) {
      next('/unauthorized')
      return
    }
  }

  next()
})

export default router
