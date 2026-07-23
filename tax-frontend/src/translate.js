// Minimal __() backed by boot.__messages (filled by load_translations for the
// session user's language) — same contract as the other ERPbio SPAs.
let messages = {}

export function loadTranslations() {
	messages = window.frappe?.boot?.__messages || {}
}

export function translate(text, args) {
	let translated = messages[text] || text
	if (args) {
		args.forEach((value, index) => {
			translated = translated.replace(`{${index}}`, value)
		})
	}
	return translated
}
