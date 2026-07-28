import { createResource } from "frappe-ui"

// The ERPbio apps the current user may open (server role-filtered), for the
// account menu's app selector. Shared singleton so the footer and the flyout
// read the same fetch. Points at this app's own endpoint, which returns an
// empty list when erpbio_general isn't installed — see api/tax.py.
export const launcherApps = createResource({
	url: "erpbio_indonesia_localization.api.tax.get_launcher_apps",
})

let requested = false
export function ensureLauncherAppsLoaded() {
	if (requested) return
	requested = true
	launcherApps.fetch()
}
