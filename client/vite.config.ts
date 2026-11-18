import path from "path"
import react from "@vitejs/plugin-react"
import { lingui } from "@lingui/vite-plugin"
import { defineConfig } from "vite"

const mode = process.env.ENV_FLAG;
const host = process.env.CONTAINER_SERVER_NAME;
const port = process.env.CONTAINER_SERVER_PORT;

let URL = "";

if (mode === 'docker') {
  URL = 'http://' + host + ':' + port
}
else{
  URL = 'http://127.0.0.1:8080';
}
 
export default defineConfig({
  plugins: [
    react({
      babel: {
        plugins: ["@lingui/babel-plugin-lingui-macro"],
      },
    }),
    lingui(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    allowedHosts: ["test.kami.mir-ai.it", "ask_test.carraro.net"],
    proxy: {
      '/api': {
        target: URL,
        changeOrigin: true,
        // rewrite: (path) => path.replace(/^\/api/, '')
      },
      '/socket.io': {
        target: URL,
        changeOrigin: true,
        ws: true
      }
    }
  }
})