/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ['lucide-react'],
  },
  server: {
    host: true, // Allows access from other devices on the network
    port: 5173, // Or your preferred port
  },
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
  },
});
