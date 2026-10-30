import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {'/api': 'http://127.0.0.1:8000'},
    // Windows 下原子写会产生临时目录/文件，fs.watch 会报 EBUSY；改用轮询
    watch: {usePolling: true, interval: 300, ignored: ['**/.*.tmpdir/**', '**/*.tmp']},
  },
});

