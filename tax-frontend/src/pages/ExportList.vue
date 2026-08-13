<template>
	<ListView
		:title="__('Coretax Exports')"
		method="erpbio_indonesia_localization.api.tax.list_exports"
		:columns="COLUMNS"
		:quickFilters="QUICK_FILTERS"
		:filterableFields="FILTER_FIELDS"
		:rowTo="(row) => ({ name: 'ExportDetail', params: { name: row.name } })"
	>
		<template #actions>
			<Button variant="solid" @click="openNew">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>{{ __("New Export") }}
			</Button>
		</template>
		<template #mobileCard="{ row, highlight }">
			<div class="rounded-xl border bg-surface-white p-4">
				<div class="flex items-start justify-between gap-2">
					<span class="min-w-0 truncate text-base font-semibold text-ink-gray-9" v-html="highlight(row.name)" />
					<Badge class="shrink-0" :theme="row.status === 'Generated' ? 'green' : 'gray'" variant="subtle">{{ __(row.status) }}</Badge>
				</div>
				<div class="mt-1 truncate text-xs text-ink-gray-5">{{ row.company }}</div>
				<div class="mt-2 text-xs text-ink-gray-6">{{ row.from_date }} → {{ row.to_date }}</div>
			</div>
		</template>
	</ListView>

	<!-- New export -->
	<div v-if="showNew" class="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4" @click.self="showNew = false">
		<div class="w-full max-w-sm rounded-lg border bg-surface-white p-4 shadow-xl">
			<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ __("New Export") }}</h2>
			<div class="flex flex-col gap-3">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("Company") }}</label>
					<select v-model="form.company" class="form-select h-8 text-sm">
						<option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
					</select>
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("From Date") }}</label>
					<DatePickerPopover :modelValue="form.from_date" clearable
						@update:modelValue="(v) => (form.from_date = v || '')" />
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("To Date") }}</label>
					<DatePickerPopover :modelValue="form.to_date" clearable
						@update:modelValue="(v) => (form.to_date = v || '')" />
				</div>
				<div class="flex justify-end gap-2">
					<Button @click="showNew = false">{{ __("Cancel") }}</Button>
					<Button variant="solid" :loading="busy" :disabled="!form.company || !form.from_date || !form.to_date" @click="create">
						{{ __("Create") }}
					</Button>
				</div>
				<p v-if="errorMessage" class="text-sm text-ink-red-3">{{ errorMessage }}</p>
			</div>
		</div>
	</div>
</template>

<script setup>
import { h, inject, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { Badge, Button, FeatherIcon, call } from "frappe-ui"
import ListView from "@shared/components/ListView.vue"
import DatePickerPopover from "@shared/components/DatePickerPopover.vue"

const __ = inject("$translate")
const router = useRouter()

const STATUSES = ["Draft", "Generated"]

// Status as a Badge, and the workbook as a direct download that doesn't open the row.
const StatusCell = {
	props: ["value"],
	render() {
		return h(Badge, { theme: this.value === "Generated" ? "green" : "gray", variant: "subtle" }, () => this.value || "—")
	},
}
const FileCell = {
	props: ["value"],
	render() {
		return this.value
			? h("a", { href: this.value, class: "text-ink-blue-link", onClick: (e) => e.stopPropagation() }, "Download")
			: h("span", { class: "text-ink-gray-4" }, "—")
	},
}

const COLUMNS = [
	{ label: __("Name"), key: "name", cellClass: "font-medium text-ink-gray-9", width: "14rem" },
	{ label: __("Company"), key: "company", cellClass: "truncate", width: "18rem" },
	{ label: __("From"), key: "from_date", cellClass: "whitespace-nowrap" },
	{ label: __("To"), key: "to_date", cellClass: "whitespace-nowrap" },
	{ label: __("Status"), key: "status", component: StatusCell, headerClass: "text-center", cellClass: "text-center" },
	{ label: __("File"), key: "export_file", component: FileCell, sortable: false },
]

const QUICK_FILTERS = [{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: STATUSES }]
const FILTER_FIELDS = [
	{ fieldname: "name", label: __("Name"), fieldtype: "Data" },
	{ fieldname: "company", label: __("Company"), fieldtype: "Link", doctype: "Company" },
	{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: STATUSES },
]

// --- new export ---
const showNew = ref(false)
const busy = ref(false)
const errorMessage = ref("")
const companies = ref([])
const form = reactive({ company: "", from_date: "", to_date: "" })

async function openNew() {
	errorMessage.value = ""
	showNew.value = true
	if (companies.value.length) return
	try {
		const ctx = await call("erpbio_indonesia_localization.api.tax.get_context")
		companies.value = ctx.companies || []
		if (companies.value.length === 1) form.company = companies.value[0]
	} catch (e) {
		companies.value = []
	}
}

async function create() {
	busy.value = true
	errorMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.create_export", { ...form })
		router.push({ name: "ExportDetail", params: { name: r.name } })
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not create the export.")
	} finally {
		busy.value = false
	}
}
</script>
