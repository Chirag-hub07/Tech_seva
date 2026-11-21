import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Enables React's automatic JSX runtime. Without this, the browser expects a
// `React` global in every JSX component and renders a blank page at runtime.
export default defineConfig({
  plugins: [react()],
})
