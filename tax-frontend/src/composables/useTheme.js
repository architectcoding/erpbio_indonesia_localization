// Copied from erpbio_general spa-shared rather than imported: this app is
// deliberately self-contained (clean-room MIT, installs without erpbio_general),
// so it must not take a build-time dependency on it. Keep in sync by hand.
import { ref } from "vue"

// frappe-ui's tailwind preset is configured with
// darkMode: ['selector', '[data-theme="dark"]'], and its semantic color
// tokens (surface-*, ink-*, outline-*) flip via CSS variables under that
// attribute -- so toggling data-theme on <html> switches the whole app.
const STORAGE_KEY = "erpbio-tax-theme"

function initialTheme() {
	const saved = localStorage.getItem(STORAGE_KEY)
	if (saved === "light" || saved === "dark") return saved
	return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

const theme = ref(initialTheme())

function apply(value) {
	document.documentElement.setAttribute("data-theme", value)
	syncBrowserChrome(value)
}

// Keep the browser/PWA chrome in step with the app theme: the theme-color meta
// paints the installed app's title bar (and Android's status bar). It ships as
// a static #fff, so without this a dark-mode app sits under a white header.
// Source of truth is the app's own background token, read AFTER the attribute
// flips so we get the theme's computed value.
function syncBrowserChrome(value) {
	try {
		const bg =
			getComputedStyle(document.documentElement).getPropertyValue("--surface-white").trim() ||
			(value === "dark" ? "#181818" : "#ffffff")
		let meta = document.querySelector('meta[name="theme-color"]')
		if (!meta) {
			meta = document.createElement("meta")
			meta.name = "theme-color"
			document.head.appendChild(meta)
		}
		meta.setAttribute("content", bg)
	} catch (e) {
		// cosmetic only -- never let chrome syncing break theming
	}
}
apply(theme.value)

export function useTheme() {
	function setTheme(value) {
		theme.value = value
		localStorage.setItem(STORAGE_KEY, value)
		apply(value)
	}
	function toggleTheme() {
		setTheme(theme.value === "dark" ? "light" : "dark")
	}
	return { theme, setTheme, toggleTheme }
}
