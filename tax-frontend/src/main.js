import { createApp } from "vue"
import { FrappeUI, Button, FormControl, FeatherIcon, Badge, setConfig, frappeRequest } from "frappe-ui"

import App from "./App.vue"
import router from "./router"
import { session } from "./session"
import { translate, loadTranslations } from "./translate"
import dayjs from "./utils/dayjs"
import { setNumberFormat } from "./utils/format"
import { vDocPreview, closePreview, configureDocPreview } from "./composables/docPreview"
// Point the hover cards at this app's own api, not erpbio_general's.
configureDocPreview("erpbio_indonesia_localization.api.tax")
// Side-effect import: applies the saved/system theme to <html> before anything
// renders, so the Login page (which has no toggle) opens in the right theme too.
import "./composables/useTheme"

import "./main.css"

const app = createApp(App)

setConfig("resourceFetcher", frappeRequest)
app.use(FrappeUI)
app.use(router)

app.component("Button", Button)
app.component("FormControl", FormControl)
app.component("FeatherIcon", FeatherIcon)
app.component("Badge", Badge)

// Frappe-style hover quick-info on any doc link: v-doc-preview="{ doctype, name }"
app.directive("doc-preview", vDocPreview)
// Close a stranded preview card whenever the route changes.
router.afterEach(() => closePreview())

app.provide("$session", session)
app.provide("$translate", translate)
app.provide("$dayjs", dayjs)

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

	// Amounts should read the way Desk renders them (1.234.567,89 on an
	// Indonesian site), so pick the site's format up before the first render.
	// Rides the shell's existing context call rather than adding a round-trip —
	// which also carries the signed-in user for the sidebar account menu.
	let ctx = null
	if (session.isLoggedIn) {
		ctx = await frappeRequest({
			url: "/api/method/erpbio_indonesia_localization.api.tax.get_context",
		}).catch(() => null)
		if (ctx) {
			setNumberFormat({
				number_format: ctx.number_format,
				currency: ctx.currency,
				precision: ctx.float_precision,
			})
		}
	}

	document.title = window.frappe?.boot?.app_title || "ERPbio Tax"
	// Provided before mount so the footer renders the right name on first paint
	// rather than flashing the email.
	app.provide("$user", ctx?.user || null)
	// Translated, so About matches the sidebar heading (which renders __()).
	app.provide("$branding", {
		title: translate(window.frappe?.boot?.app_title || "ERPbio Tax"),
		logo: window.frappe?.boot?.app_logo || "",
	})
	app.mount("#app")
})
