// Copied from erpbio_general spa-shared, not imported: this app must build and
// install without erpbio_general present. The api module is set via
// configureDocPreview() in main.js. Keep in sync by hand.
// Frappe-style hover quick-info for document links. A single popover (rendered
// once by DocPreviewHost) is driven by this shared reactive state; the
// `v-doc-preview="{ doctype, name }"` directive shows/hides it on hover.
//
// The preview data comes from an app-specific endpoint — each app calls
// configureDocPreview() once at boot (in its main.js) to point it at its own
// `…get_doc_preview`.
import { reactive } from "vue"
import { call } from "frappe-ui"

const cache = new Map() // key -> resolved data (or null)

// Overridden per app via configureDocPreview(); accounting is the default.
let apiModule = "erpbio_general.api.accounting.masters"
export function configureDocPreview(mod) {
	if (mod) apiModule = mod
}

export const previewState = reactive({
	visible: false,
	x: 0,
	y: 0,
	loading: false,
	data: null,
	key: "",
})

let showTimer = null
let hideTimer = null
let hovering = false

async function fetchPreview(doctype, name) {
	const key = `${doctype}::${name}`
	if (cache.has(key)) return cache.get(key)
	const data = await call(`${apiModule}.get_doc_preview`, { doctype, name }).catch(() => null)
	cache.set(key, data)
	return data
}

export function showPreview(el, doctype, name) {
	if (!doctype || !name) return
	clearTimeout(hideTimer)
	clearTimeout(showTimer)
	hovering = true
	const key = `${doctype}::${name}`
	// ~350ms hover intent, like Desk — avoids flashing on quick pass-overs.
	showTimer = setTimeout(async () => {
		if (!hovering) return
		const rect = el.getBoundingClientRect()
		previewState.x = rect.left
		previewState.y = rect.bottom + 6
		previewState.key = key
		previewState.loading = true
		previewState.data = null
		previewState.visible = true
		const data = await fetchPreview(doctype, name)
		if (previewState.key === key && hovering) {
			previewState.data = data
			previewState.loading = false
		}
	}, 350)
}

// Keep the popover open while the pointer is over the card itself.
export function keepPreview() {
	hovering = true
	clearTimeout(hideTimer)
}

export function hidePreview() {
	hovering = false
	clearTimeout(showTimer)
	hideTimer = setTimeout(() => {
		previewState.visible = false
	}, 160)
}

// Immediate close (no delay) — used when the trigger is removed or the route
// changes, so a card can't get stranded on the next page.
export function closePreview() {
	hovering = false
	clearTimeout(showTimer)
	clearTimeout(hideTimer)
	previewState.visible = false
}

export const vDocPreview = {
	mounted(el, binding) {
		el.__dp = binding.value || {}
		el.__dpEnter = () => {
			const v = el.__dp || {}
			if (v.doctype && v.name) showPreview(el, v.doctype, v.name)
		}
		el.__dpLeave = () => hidePreview()
		el.addEventListener("mouseenter", el.__dpEnter)
		el.addEventListener("mouseleave", el.__dpLeave)
	},
	updated(el, binding) {
		el.__dp = binding.value || {}
	},
	unmounted(el) {
		el.removeEventListener("mouseenter", el.__dpEnter)
		el.removeEventListener("mouseleave", el.__dpLeave)
		// The trigger is gone (e.g. navigated away mid-hover) — don't strand the card.
		closePreview()
	},
}
