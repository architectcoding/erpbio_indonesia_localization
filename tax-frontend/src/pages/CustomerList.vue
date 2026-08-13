<template>
	<ListView
		ref="listRef"
		:title="__('Customers')"
		method="erpbio_indonesia_localization.api.tax.list_customers"
		:columns="COLUMNS"
		:quickFilters="QUICK_FILTERS"
		:filterableFields="FILTER_FIELDS"
		orderBy="customer_name asc"
		:rowTo="(row) => ({ name: 'CustomerTaxDetail', params: { name: row.name } })"
	>
		<template #actions>
			<!-- The readiness of the whole book, not just this page — a faktur is
			     rejected for any buyer without an NPWP/NIK, so the backlog size is
			     the number that matters. -->
			<div v-if="summary" class="flex items-center gap-2 text-xs">
				<span v-if="summary.Blocked" class="rounded-full bg-surface-red-1 px-2 py-1 font-medium text-ink-red-3">
					{{ __("{0} without NPWP/NIK", [summary.Blocked]) }}
				</span>
				<span v-if="summary.Incomplete" class="rounded-full bg-surface-amber-1 px-2 py-1 font-medium text-ink-amber-3">
					{{ __("{0} incomplete", [summary.Incomplete]) }}
				</span>
				<span class="rounded-full bg-surface-gray-2 px-2 py-1 text-ink-gray-6">
					{{ __("{0} of {1} ready", [summary.Ready, summary.total]) }}
				</span>
			</div>
		</template>

		<template #mobileCard="{ row, highlight }">
			<div class="rounded-xl border bg-surface-white p-4">
				<div class="flex items-start justify-between gap-2">
					<span class="min-w-0 truncate text-base font-semibold text-ink-gray-9" v-html="highlight(row.customer_name || row.name)" />
					<Badge class="shrink-0" :theme="themeFor(row.tax_status)" variant="subtle">{{ __(row.tax_status) }}</Badge>
				</div>
				<div class="mt-2 text-xs tabular-nums text-ink-gray-6">{{ row.tax_id || __("No NPWP/NIK") }}</div>
			</div>
		</template>
	</ListView>
</template>

<script setup>
import { h, inject, ref } from "vue"
import { Badge, call } from "frappe-ui"
import ListView from "@shared/components/ListView.vue"

const __ = inject("$translate")

const ID_TYPES = ["TIN", "NIK", "Passport", "Other"]

function themeFor(status) {
	return status === "Ready" ? "green" : status === "Incomplete" ? "orange" : "red"
}

const StatusCell = {
	props: ["value", "row"],
	render() {
		return h(
			Badge,
			{ theme: themeFor(this.value), variant: "subtle", title: this.row?.tax_message || "" },
			() => this.value || "—"
		)
	},
}

// "Government" is true either from the customer's own flag or from its customer
// group being listed in Indonesia Tax Settings — showing which avoids the
// "why is this treated as government when the box is unticked?" question.
const PemungutCell = {
	props: ["row"],
	render() {
		if (!this.row?.is_pemungut) return h("span", { class: "text-ink-gray-4" }, "—")
		return h(
			Badge,
			{ theme: "blue", variant: "subtle", title: this.row.pemungut_source === "group" ? "via customer group" : "" },
			() => (this.row.pemungut_source === "group" ? "Group" : "Yes")
		)
	},
}

const COLUMNS = [
	{ label: __("Customer"), key: "customer_name", cellClass: "font-medium text-ink-gray-9", width: "16rem" },
	{ label: __("Tax Status"), key: "tax_status", component: StatusCell, sortable: false, headerClass: "text-center", cellClass: "text-center" },
	{ label: __("ID Type"), key: "eil_id_type", format: (v) => v || "TIN", cellClass: "text-ink-gray-7" },
	{
		label: __("NPWP / NIK"),
		key: "tax_id",
		sortable: true,
		format: (v) => v || "—",
		cellClass: "tabular-nums text-ink-gray-7",
	},
	{ label: __("NITKU"), key: "eil_nitku", sortable: false, format: (v) => v || "—", cellClass: "tabular-nums text-ink-gray-7" },
	{ label: __("Customer Group"), key: "customer_group", format: (v) => v || "—", cellClass: "text-ink-gray-7" },
	{ label: __("Government"), key: "is_pemungut", component: PemungutCell, sortable: false, headerClass: "text-center", cellClass: "text-center" },
]

const QUICK_FILTERS = [
	{
		fieldname: "missing_tax_id",
		label: __("Missing NPWP/NIK"),
		fieldtype: "Select",
		options: [
			{ label: __("Yes"), value: "1" },
			{ label: __("No"), value: "0" },
		],
	},
	{ fieldname: "eil_id_type", label: __("ID Type"), fieldtype: "Select", options: ID_TYPES },
]
const FILTER_FIELDS = [
	{ fieldname: "customer_name", label: __("Customer"), fieldtype: "Data" },
	{ fieldname: "customer_group", label: __("Customer Group"), fieldtype: "Link", options: "Customer Group" },
	{ fieldname: "eil_id_type", label: __("ID Type"), fieldtype: "Select", options: ID_TYPES },
	{ fieldname: "eil_is_pemungut", label: __("Government (flagged)"), fieldtype: "Check" },
	{ fieldname: "missing_tax_id", label: __("Missing NPWP/NIK"), fieldtype: "Select", options: ["1", "0"] },
]

const summary = ref(null)
call("erpbio_indonesia_localization.api.tax.customer_tax_summary")
	.then((r) => (summary.value = r))
	.catch(() => {})
</script>
