import { createApp } from "vue"
import { FrappeUI, Button, FormControl, FeatherIcon, Badge, setConfig, frappeRequest } from "frappe-ui"

import App from "./App.vue"
import router from "./router"
import { session } from "./session"
import { translate, loadTranslations } from "./translate"

import "./main.css"

const app = createApp(App)

setConfig("resourceFetcher", frappeRequest)
app.use(FrappeUI)
app.use(router)

app.component("Button", Button)
app.component("FormControl", FormControl)
app.component("FeatherIcon", FeatherIcon)
app.component("Badge", Badge)

app.provide("$session", session)
app.provide("$translate", translate)

router.isReady().then(async () => {
	if (import.meta.env.DEV) {
		await frappeRequest({
			url: "/api/method/erpbio_indonesia_localization.www.erpbio_tax.get_context_for_dev",
		}).then((values) => {
			if (!window.frappe) window.frappe = {}
			window.frappe.boot = values
		})
	}
	loadTranslations()
	document.title = window.frappe?.boot?.app_title || "ERPbio Tax"
	app.mount("#app")
})
