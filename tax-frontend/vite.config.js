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
			// The ERPbio shared component library, consumed across the app boundary.
			// This is a BUILD-time dependency only: public/tax/ ships pre-built, so a
			// site can install this app on bare ERPNext without erpbio_general and
			// still get a working SPA. That only holds while every shared component
			// used here degrades gracefully when erpbio_general's endpoints are
			// absent -- ListView's column widths fall back to localStorage,
			// DeleteDocButton hides itself, DocActions still prints untranslated.
			// Before pulling in a new @shared component, check its call sites the
			// same way.
			"@shared": path.resolve(__dirname, "../../erpbio_general/spa-shared/src"),
		},
		// spa-shared sits outside this package root -- outside this repo entirely --
		// so without dedupe its imports of vue/frappe-ui resolve to a second copy
		// up the tree, and two Vue instances break injection and reactivity.
		dedupe: ["vue", "vue-router", "frappe-ui", "vuedraggable"],
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
