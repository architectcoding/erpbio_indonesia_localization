<template>
	<div class="mx-auto max-w-5xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("PPN Masukan") }}</h1>
		</div>
		<p class="mb-4 text-sm text-ink-gray-5">
			{{ __("The period's input-VAT register: supplier fakturs and the creditable PPN.") }}
		</p>

		<div class="mb-4 rounded-lg border bg-surface-white p-4">
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-4">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("Company") }}</label>
					<select v-model="company" class="form-select h-8 text-sm">
						<option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
					</select>
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("From Date") }}</label>
					<DatePickerPopover :modelValue="fromDate" clearable
						@update:modelValue="(v) => (fromDate = v || '')" />
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("To Date") }}</label>
					<DatePickerPopover :modelValue="toDate" clearable
						@update:modelValue="(v) => (toDate = v || '')" />
				</div>
				<div class="flex items-end">
					<Button variant="solid" class="w-full" :loading="loading" :disabled="!company || !fromDate || !toDate" @click="run">
						<template #prefix><FeatherIcon name="play" class="h-3.5 w-3.5" /></template>{{ __("Run") }}
					</Button>
				</div>
			</div>
		</div>

		<div v-if="rows.length" class="mb-3 grid grid-cols-2 gap-3">
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("DPP") }}</div>
				<div class="text-lg font-semibold tabular-nums text-ink-gray-9">{{ money(total("dpp")) }}</div>
			</div>
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("PPN Masukan (creditable)") }}</div>
				<div class="text-lg font-semibold tabular-nums text-ink-gray-9">{{ money(creditableTotal) }}</div>
			</div>
		</div>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full min-w-max text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Invoice") }}</th>
						<th class="px-3 py-2">{{ __("Date") }}</th>
						<th class="px-3 py-2">{{ __("Supplier") }}</th>
						<th class="px-3 py-2">{{ __("NPWP Penjual") }}</th>
						<th class="px-3 py-2 text-right">{{ __("DPP") }}</th>
						<th class="px-3 py-2 text-right">{{ __("PPN") }}</th>
						<th class="px-3 py-2">{{ __("Nomor Faktur") }}</th>
						<th class="px-3 py-2">{{ __("Creditable") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.purchase_invoice" class="border-b border-outline-gray-1 last:border-0">
						<td class="px-3 py-2 font-medium text-ink-gray-8">{{ row.purchase_invoice }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.posting_date }}</td>
						<td class="max-w-[14rem] truncate px-3 py-2 text-ink-gray-7">{{ row.supplier_name }}</td>
						<td class="px-3 py-2 tabular-nums text-ink-gray-7">{{ row.supplier_npwp || "—" }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.dpp) }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.ppn) }}</td>
						<td class="px-3 py-2 tabular-nums text-ink-gray-7">{{ row.faktur_number || "—" }}</td>
						<td class="px-3 py-2">
							<Badge :theme="row.creditable ? 'green' : 'gray'" variant="subtle">
								{{ row.creditable ? __("Yes") : __("No") }}
							</Badge>
						</td>
					</tr>
					<tr v-if="!rows.length && ran">
						<td colspan="8" class="px-3 py-8 text-center text-ink-gray-4">{{ __("No purchase invoices in this period.") }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
	</div>
</template>

<script setup>
import DatePickerPopover from "@/components/DatePickerPopover.vue"
import { computed, inject, ref } from "vue"
import { call } from "frappe-ui"
import { formatCurrency } from "@/utils/format"

const __ = inject("$translate")

const companies = ref([])
const company = ref("")
const fromDate = ref(monthStart())
const toDate = ref(new Date().toISOString().slice(0, 10))
const rows = ref([])
const loading = ref(false)
const ran = ref(false)
const errorMessage = ref("")

const creditableTotal = computed(() => rows.value.filter((r) => r.creditable).reduce((a, r) => a + (Number(r.ppn) || 0), 0))

function monthStart() {
	const d = new Date()
	return new Date(d.getFullYear(), d.getMonth(), 1).toISOString().slice(0, 10)
}
function money(v) {
	return formatCurrency(v ?? 0)
}
function total(field) {
	return rows.value.reduce((a, r) => a + (Number(r[field]) || 0), 0)
}

call("erpbio_indonesia_localization.api.tax.get_context").then((ctx) => {
	companies.value = ctx.companies || []
	if (companies.value.length === 1) company.value = companies.value[0]
})

async function run() {
	loading.value = true
	errorMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.ppn_masukan", {
			company: company.value,
			from_date: fromDate.value,
			to_date: toDate.value,
		})
		rows.value = r.data || []
		ran.value = true
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not run the report.")
	} finally {
		loading.value = false
	}
}
</script>
