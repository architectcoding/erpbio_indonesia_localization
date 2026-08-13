<template>
	<ListView
		:title="__('Employees')"
		:searchNoun="__('employees')"
		method="erpbio_indonesia_localization.api.tax.list_employees_pph21"
		:columns="COLUMNS"
		:quickFilters="QUICK_FILTERS"
		:filterableFields="FILTER_FIELDS"
		orderBy="employee_name asc"
		:rowTo="(row) => ({ name: 'EmployeePph21Detail', params: { name: row.name } })"
	>
		<template #actions>
			<div v-if="summary" class="flex items-center gap-2 text-xs">
				<!-- The number that actually matters is the one that would stop a
				     payroll run, not the raw count of unset statuses. -->
				<span
					v-if="summary.blocked_in_scope"
					class="rounded-full bg-surface-red-1 px-2 py-1 font-medium text-ink-red-3"
				>
					{{ __("{0} would block payroll", [summary.blocked_in_scope]) }}
				</span>
				<span v-if="summary.Blocked" class="rounded-full bg-surface-amber-1 px-2 py-1 font-medium text-ink-amber-3">
					{{ __("{0} without PTKP status", [summary.Blocked]) }}
				</span>
				<span class="rounded-full bg-surface-gray-2 px-2 py-1 text-ink-gray-6">
					{{ __("{0} of {1} on a PPh 21 structure", [summary.in_scope, summary.total]) }}
				</span>
			</div>
		</template>

		<template #mobileCard="{ row, highlight }">
			<div class="rounded-xl border bg-surface-white p-4">
				<div class="flex items-start justify-between gap-2">
					<span class="min-w-0 truncate text-base font-semibold text-ink-gray-9" v-html="highlight(row.employee_name || row.name)" />
					<Badge class="shrink-0" :theme="themeFor(row.pph21_status)" variant="subtle">{{ __(row.pph21_status) }}</Badge>
				</div>
				<div class="mt-2 text-xs text-ink-gray-6">{{ row.eil_ptkp_status || __("No PTKP status") }}</div>
			</div>
		</template>
	</ListView>
</template>

<script setup>
import { h, inject, ref } from "vue"
import { Badge, call } from "frappe-ui"
import ListView from "@shared/components/ListView.vue"

const __ = inject("$translate")

const PTKP_STATUSES = ["TK/0", "TK/1", "TK/2", "TK/3", "K/0", "K/1", "K/2", "K/3"]
const SCHEMES = ["Permanent", "Non-permanent", "Expatriate", "Pensioner"]

function themeFor(status) {
	return status === "Ready" ? "green" : status === "Unsupported" ? "orange" : "red"
}

const StatusCell = {
	props: ["value", "row"],
	render() {
		return h(
			Badge,
			{ theme: themeFor(this.value), variant: "subtle", title: this.row?.pph21_message || "" },
			() => this.value || "—"
		)
	},
}

// Whether the employee is on a salary structure that carries PPh 21 at all —
// a missing PTKP status only matters for the ones that are.
const ScopeCell = {
	props: ["row"],
	render() {
		return this.row?.in_scope
			? h(Badge, { theme: "blue", variant: "subtle" }, () => "PPh 21")
			: h("span", { class: "text-ink-gray-4" }, "—")
	},
}

const COLUMNS = [
	{ label: __("Employee"), key: "employee_name", cellClass: "font-medium text-ink-gray-9", width: "16rem" },
	{ label: __("Status"), key: "pph21_status", component: StatusCell, sortable: false, headerClass: "text-center", cellClass: "text-center" },
	{ label: __("PTKP"), key: "eil_ptkp_status", format: (v) => v || "—", cellClass: "text-ink-gray-7" },
	{ label: __("TER"), key: "eil_ter_category", sortable: false, format: (v) => v || "—", cellClass: "text-ink-gray-7" },
	{ label: __("Scheme"), key: "eil_pph21_scheme", format: (v) => v || "Permanent", cellClass: "text-ink-gray-7" },
	{ label: __("NPWP / NIK"), key: "eil_npwp", sortable: false, format: (v) => v || "—", cellClass: "tabular-nums text-ink-gray-7" },
	{ label: __("On structure"), key: "in_scope", component: ScopeCell, sortable: false, headerClass: "text-center", cellClass: "text-center" },
	{ label: __("Department"), key: "department", format: (v) => v || "—", cellClass: "text-ink-gray-7" },
]

const QUICK_FILTERS = [
	{ fieldname: "eil_ptkp_status", label: __("PTKP"), fieldtype: "Select", options: PTKP_STATUSES },
	{ fieldname: "status", label: __("Employee Status"), fieldtype: "Select", options: ["Active", "Inactive", "Suspended", "Left"] },
]
const FILTER_FIELDS = [
	{ fieldname: "employee_name", label: __("Employee"), fieldtype: "Data" },
	{ fieldname: "department", label: __("Department"), fieldtype: "Link", options: "Department" },
	{ fieldname: "eil_ptkp_status", label: __("PTKP"), fieldtype: "Select", options: PTKP_STATUSES },
	{ fieldname: "eil_pph21_scheme", label: __("Scheme"), fieldtype: "Select", options: SCHEMES },
	{ fieldname: "status", label: __("Employee Status"), fieldtype: "Select", options: ["Active", "Inactive", "Suspended", "Left"] },
]

const summary = ref(null)
call("erpbio_indonesia_localization.api.tax.employee_pph21_summary")
	.then((r) => (summary.value = r))
	.catch(() => {})
</script>
