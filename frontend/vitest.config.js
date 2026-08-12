import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  test: {
    // happy-dom gives us localStorage, document and timers without a browser
    environment: 'happy-dom',
    setupFiles: ['tests/setup.js'],
    include: ['tests/**/*.test.js'],
    restoreMocks: true,
    coverage: {
      include: ['src/**/*.js'],
      exclude: ['src/main.js']
    }
  }
})
