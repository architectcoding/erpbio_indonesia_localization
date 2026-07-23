<template>
	<div class="mx-auto max-w-5xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Bukti Potong") }}</h1>
			<div class="flex-1" />
			<Button variant="solid" @click="openNew">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>{{ __("New Bukti Potong") }}
			</Button>
		</div>
		<p class="mb-4 text-sm text-ink-gray-5">
			{{ __("Withholding certificates from customers who withheld PPh (e.g. a government bendahara withholding PPh 22). Track them from Expected to Received — the certificate is your prepaid-tax credit evidence.") }}
		</p>

		<div v-if="rows.length" class="mb-3 grid grid-cols-3 gap-3">
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("Total Withheld") }}</div>
				<div class="text-lg font-semibold tabular-nums text-ink-gray-9">{{ money(total()) }}</div>
			</div>
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("Received") }}</div>
				<div class="text-lg font-semibold tabular-nums text-ink-green-3">{{ money(total("Received")) }}</div>
			</div>
			<div class="rounded-lg p-3" :class="total('Expected') ? 'bg-surface-amber-1' : 'bg-surface-gray-1'">
				<div class="text-xs" :class="total('Expected') ? 'text-ink-amber-3' : 'text-ink-gray-5'">{{ __("Still Expected") }}</div>
				<div class="text-lg font-semibold tabular-nums" :class="total('Expected') ? 'text-ink-amber-3' : 'text-ink-gray-9'">{{ money(total("Expected")) }}</div>
			</div>
		</div>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full min-w-max text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Name") }}</th>
						<th class="px-3 py-2">{{ __("Customer") }}</th>
						<th class="px-3 py-2">{{ __("Type") }}</th>
						<th class="px-3 py-2 text-right">{{ __("Gross") }}</th>
						<th class="px-3 py-2 text-right">{{ __("Withheld") }}</th>
						<th class="px-3 py-2">{{ __("BP Number") }}</th>
						<th class="px-3 py-2">{{ __("Status") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.name"
						class="cursor-pointer border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
						@click="openEdit(row)">
						<td class="px-3 py-2 font-medium text-ink-gray-8">{{ row.name }}</td>
						<td class="max-w-[13rem] truncate px-3 py-2 text-ink-gray-7">{{ row.customer }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.tax_type }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.gross_amount) }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.tax_amount) }}</td>
						<td class="px-3 py-2 tabular-nums text-ink-gray-7">{{ row.bp_number || "—" }}</td>
						<td class="px-3 py-2">
							<Badge :theme="row.status === 'Received' ? 'green' : 'orange'" variant="subtle">{{ __(row.status) }}</Badge>
						</td>
					</tr>
					<tr v-if="!rows.length && !loading">
						<td colspan="7" class="px-3 py-8 text-center text-ink-gray-4">{{ __("No withholding certificates yet.") }}</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- dialog -->
		<div v-if="show" class="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4" @click.self="show = false">
			<div class="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-surface-white p-4">
				<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ form.name || __("New Bukti Potong") }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label class="text-xs text-ink-gray-5">{{ __("Customer (Pemotong)") }} <span class="text-ink-red-3">*</span></label>
						<select v-model="form.customer" class="form-select h-8 text-sm">
							<option v-for="c in customers" :key="c" :value="c">{{ c }}</option>
						</select>
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Tax Type") }}</label>
						<select v-model="form.tax_type" class="form-select h-8 text-sm" @change="applyDefaultRate">
							<option v-for="t in Object.keys(defaultRates)" :key="t" :value="t">{{ t }}</option>
						</select>
					</div>
					<FormControl type="number" :label="__('Rate (%)')" v-model="form.rate" />
					<FormControl type="number" :label="__('Gross Amount (DPP)')" v-model="form.gross_amount" />
					<FormControl type="number" :label="__('Tax Withheld (blank = Gross × Rate)')" v-model="form.tax_amount" />
					<FormControl type="text" :label="__('Sales Invoice')" v-model="form.sales_invoice" :placeholder="__('Optional')" />
					<FormControl type="text" :label="__('Payment Entry')" v-model="form.payment_entry" :placeholder="__('Optional')" />
					<FormControl type="text" :label="__('Bukti Potong Number')" v-model="form.bp_number" :placeholder="__('Fills = Received')" />
					<FormControl type="date" :label="__('Bukti Potong Date')" v-model="form.bp_date" />
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label class="text-xs text-ink-gray-5">{{ __("Notes") }}</label>
						<textarea v-model="form.notes" rows="2" class="form-textarea text-sm" />
					</div>
				</div>
				<div class="mt-4 flex justify-end gap-2">
					<Button @click="show = false">{{ __("Cancel") }}</Button>
					<Button variant="solid" :loading="busy" :disabled="!form.customer || !form.gross_amount" @click="save">{{ __("Save") }}</Button>
				</div>
				<p v-if="errorMessage" class="mt-2 text-sm text-ink-red-3">{{ errorMessage }}</p>
			</div>
		</div>
	</div>
</template>

<script setup>
import { inject, reactive, ref } from "vue"
import { call } from "frappe-ui"

const __ = inject("$translate")

const rows = ref([])
const customers = ref([])
const defaultRates = ref({ "PPh 22": 1.5, "PPh 23": 2.0, "PPh 4(2)": 10.0 })
const loading = ref(true)
const show = ref(false)
const busy = ref(false)
const errorMessage = ref("")
const form = reactive(blank())

function blank() {
	return {
		name: null, customer: "", tax_type: "PPh 22", rate: 1.5, gross_amount: null,
		tax_amount: null, sales_invoice: "", payment_entry: "", bp_number: "", bp_date: "", notes: "",
	}
}
function money(v) {
	return new Intl.NumberFormat("id-ID").format(v || 0)
}
function total(status) {
	return rows.value.filter((r) => !status || r.status === status).reduce((a, r) => a + (Number(r.tax_amount) || 0), 0)
}
function applyDefaultRate() {
	form.rate = defaultRates.value[form.tax_type] ?? form.rate
}

async function load() {
	loading.value = true
	try {
		const [list, lk] = await Promise.all([
			call("erpbio_indonesia_localization.api.tax.list_bukti_potong"),
			call("erpbio_indonesia_localization.api.tax.bukti_potong_lookups"),
		])
		rows.value = list || []
		customers.value = lk.customers || []
		defaultRates.value = lk.default_rates || defaultRates.value
	} finally {
		loading.value = false
	}
}
load()

function openNew() {
	Object.assign(form, blank())
	errorMessage.value = ""
	show.value = true
}
function openEdit(row) {
	Object.assign(form, blank(), row)
	errorMessage.value = ""
	show.value = true
}

async function save() {
	busy.value = true
	errorMessage.value = ""
	try {
		await call("erpbio_indonesia_localization.api.tax.save_bukti_potong", {
			payload: JSON.stringify({ ...form }),
		})
		show.value = false
		await load()
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not save.")
	} finally {
		busy.value = false
	}
}
</script>
