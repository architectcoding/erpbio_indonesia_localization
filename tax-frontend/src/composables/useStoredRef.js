import { ref, watch } from "vue"

// A ref that remembers itself in localStorage.
//
// For the choices a screen should not keep asking about — which company, which
// bank account, which date range. Reopening the bank reconciliation and having
// to re-pick all three is the friction this removes.
//
// Deliberately NOT for anything the server owns. This is a UI preference store:
// if the value matters to the ledger it belongs in a document, not here.
export function useStoredRef(key, initial) {
	const value = ref(read(key, initial))

	// deep, because the useful cases are objects — a {from, to} date range, a
	// selected account. A shallow watch would miss `range.from = …`.
	watch(value, (v) => {
		try {
			if (v === null || v === undefined) localStorage.removeItem(key)
			else localStorage.setItem(key, JSON.stringify(v))
		} catch (e) {
			// private browsing, or the quota is full — the feature is a convenience,
			// so losing the memory is acceptable; losing the screen is not
		}
	}, { deep: true })

	return value
}

function read(key, fallback) {
	try {
		const raw = localStorage.getItem(key)
		// stored data is a previous version of our own code talking to us, and it
		// can be older than the current shape — treat anything unparseable as absent
		return raw === null ? fallback : JSON.parse(raw)
	} catch (e) {
		return fallback
	}
}
