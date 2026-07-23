import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import frappeui from "frappe-ui/vite"
import path from "path"

export default defineConfig({
	server: {
		// other ERPbio SPA dev servers sit on 8080-8089; keep clear of them
		port: 8090,
		proxy: {
			"^/(app|login|api|assets|files|private)": {
				target: "http://127.0.0.1:8000",
				ws: true,
				changeOrigin: true,
				router: () => "http://develop.localhost:8000",
			},
		},
		allowedHosts: true,
	},
	plugins: [vue(), frappeui()],
	resolve: {
		alias: {
			"@": path.resolve(__dirname, "src"),
		},
	},
	build: {
		outDir: "../erpbio_indonesia_localization/public/tax",
		emptyOutDir: true,
		target: "es2015",
	},
	optimizeDeps: {
		include: ["feather-icons"],
	},
})
