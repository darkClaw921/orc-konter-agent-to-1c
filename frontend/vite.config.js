import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Отключаем HMR в Docker окружении для предотвращения проблем с WebSocket
const isDocker = process.env.DOCKER_ENV === 'true' || process.env.NODE_ENV === 'production'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    strictPort: true,
    hmr: isDocker ? false : {
      clientPort: 3000,
      protocol: 'ws',
      overlay: false,
    },
    watch: {
      usePolling: true, // Используем polling для Docker
      interval: 1000,
      ignored: [
        '**/node_modules/**',
        '**/dist/**',
        '**/.git/**',
        '**/.cursor/**',
        '**/index.html', // Игнорировать index.html в корне
      ],
    },
    proxy: {
      '/api': {
        target: 'http://backend:8000',
        changeOrigin: true,
        secure: false,
        ws: false, // Отключаем WebSocket для API прокси
        rewrite: (path) => {
          // Убеждаемся, что путь не изменяется
          return path;
        },
        configure: (proxy, _options) => {
          proxy.on('error', (err, _req, res) => {
            console.error('Proxy error:', err.message);
            if (res && !res.headersSent) {
              res.writeHead(500, {
                'Content-Type': 'text/plain',
              });
              res.end('Proxy error: ' + err.message);
            }
          });
          proxy.on('proxyReq', (proxyReq, req, res) => {
            console.log('Proxying request:', req.method, req.url, '->', proxyReq.path);
          });
          proxy.on('proxyRes', (proxyRes, req, res) => {
            console.log('Proxy response:', req.url, '->', proxyRes.statusCode);
          });
        },
      },
    },
    // Предотвращаем обработку API запросов как статических файлов
    fs: {
      strict: false,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
})
