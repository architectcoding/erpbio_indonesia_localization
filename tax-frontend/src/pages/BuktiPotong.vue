<template>
	<div class="mx-auto max-w-5xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Bukti Potong") }}</h1>
			<div class="flex-1" />
			<Button v-if="tab === 'Issued'" :loading="busy === 'export'" @click="exportEbupot">
				<template #prefix><FeatherIcon name="download" class="h-3.5 w-3.5" /></template>{{ __("Export e-Bupot") }}
			</Button>
			<Button variant="solid" @click="openNew">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>{{ __("New Bukti Potong") }}
			</Button>
		</div>

		<!-- direction tabs -->
		<div class="mb-3 flex gap-4 border-b text-sm">
			<button class="-mb-px border-b-2 pb-2" :class="tab === 'Received' ? 'border-b-[color:var(--ink-gray-9)] font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5'" @click="switchTab('Received')">
				{{ __("Received (customer withheld from us)") }}
			</button>
			<button class="-mb-px border-b-2 pb-2" :class="tab === 'Issued' ? 'border-b-[color:var(--ink-gray-9)] font-medium text-ink-gray-9' : 'border-transparent text-ink-gray-5'" @click="switchTab('Issued')">
				{{ __("Issued (we withheld from suppliers)") }}
			</button>
		</div>
		<p class="mb-4 text-sm text-ink-gray-5">
			{{ tab === "Received"
				? __("Certificates owed to us by customers who withheld PPh — your prepaid-tax credit evidence.")
				: __("PPh we withheld from supplier payments — to report via e-Bupot (SPT Masa PPh Unifikasi).") }}
		</p>

		<div v-if="rows.length" class="mb-3 grid grid-cols-3 gap-3">
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("Total Withheld") }}</div>
				<div class="text-lg font-semibold tabular-nums text-ink-gray-9">{{ money(total()) }}</div>
			</div>
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ tab === "Received" ? __("Received") : __("Reported") }}</div>
				<div class="text-lg font-semibold tabular-nums text-ink-green-3">{{ money(total(doneStatus)) }}</div>
			</div>
			<div class="rounded-lg p-3" :class="total(pendingStatus) ? 'bg-surface-amber-1' : 'bg-surface-gray-1'">
				<div class="text-xs" :class="total(pendingStatus) ? 'text-ink-amber-3' : 'text-ink-gray-5'">
					{{ tab === "Received" ? __("Still Expected") : __("To Report") }}
				</div>
				<div class="text-lg font-semibold tabular-nums" :class="total(pendingStatus) ? 'text-ink-amber-3' : 'text-ink-gray-9'">{{ money(total(pendingStatus)) }}</div>
			</div>
		</div>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full min-w-max text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Name") }}</th>
						<th class="px-3 py-2">{{ tab === "Received" ? __("Customer") : __("Supplier") }}</th>
						<th class="px-3 py-2">{{ __("Type") }}</th>
						<th v-if="tab === 'Issued'" class="px-3 py-2">{{ __("Kode Objek") }}</th>
						<th class="px-3 py-2">{{ __("Date") }}</th>
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
						<td class="max-w-[13rem] truncate px-3 py-2 text-ink-gray-7">{{ tab === "Received" ? row.customer : row.supplier }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.tax_type }}</td>
						<td v-if="tab === 'Issued'" class="px-3 py-2 text-ink-gray-7">{{ row.tax_object_code || "—" }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.withholding_date || "—" }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.gross_amount) }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.tax_amount) }}</td>
						<td class="px-3 py-2 tabular-nums text-ink-gray-7">{{ row.bp_number || "—" }}</td>
						<td class="px-3 py-2">
							<Badge :theme="doneStatus.includes(row.status) ? 'green' : 'orange'" variant="subtle">{{ __(row.status) }}</Badge>
						</td>
					</tr>
					<tr v-if="!rows.length && !loading">
						<td :colspan="tab === 'Issued' ? 9 : 8" class="px-3 py-8 text-center text-ink-gray-4">{{ __("No withholding certificates yet.") }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mt-3 text-sm text-ink-green-3">{{ okMessage }}</p>

		<!-- dialog -->
		<div v-if="show" class="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4" @click.self="show = false">
			<div class="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-lg bg-surface-white p-4">
				<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ form.name || __("New Bukti Potong") }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label class="text-xs text-ink-gray-5">{{ __("Direction") }}</label>
						<select v-model="form.direction" class="form-select h-8 text-sm">
							<option value="Received">{{ __("Received (customer withheld from us)") }}</option>
							<option value="Issued">{{ __("Issued (we withheld from suppliers)") }}</option>
						</select>
					</div>
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label class="text-xs text-ink-gray-5">
							{{ form.direction === "Issued" ? __("Supplier (Dipotong)") : __("Customer (Pemotong)") }}
							<span class="text-ink-red-3">*</span>
						</label>
						<select v-if="form.direction === 'Issued'" v-model="form.supplier" class="form-select h-8 text-sm">
							<option v-for="s in suppliers" :key="s" :value="s">{{ s }}</option>
						</select>
						<select v-else v-model="form.customer" class="form-select h-8 text-sm">
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
					<FormControl v-if="form.direction === 'Issued'" type="text" :label="__('Kode Objek Pajak')" v-model="form.tax_object_code" :placeholder="__('e.g. 24-104-01')" />
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Withholding Date") }}</label>
						<DatePickerPopover :modelValue="form.withholding_date" clearable
							@update:modelValue="(v) => (form.withholding_date = v || '')" />
					</div>
					<FormControl type="text" :label="__('Bukti Potong Number')" v-model="form.bp_number" :placeholder="form.direction === 'Issued' ? __('Fills = Reported') : __('Fills = Received')" />
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Bukti Potong Date") }}</label>
						<DatePickerPopover :modelValue="form.bp_date" clearable
							@update:modelValue="(v) => (form.bp_date = v || '')" />
					</div>
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label class="text-xs text-ink-gray-5">{{ __("Notes") }}</label>
						<textarea v-model="form.notes" rows="2" class="form-textarea text-sm" />
					</div>
				</div>
				<div class="mt-4 flex justify-end gap-2">
					<Button @click="show = false">{{ __("Cancel") }}</Button>
					<Button variant="solid" :loading="busy === 'save'"
						:disabled="!(form.direction === 'Issued' ? form.supplier : form.customer) || !form.gross_amount" @click="save">
						{{ __("Save") }}
					</Button>
				</div>
				<p v-if="errorMessage" class="mt-2 text-sm text-ink-red-3">{{ errorMessage }}</p>
			</div>
		</div>
	</div>
</template>

<script setup>
import DatePickerPopover from "@/components/DatePickerPopover.vue"
import { computed, inject, reactive, ref } from "vue"
import { call } from "frappe-ui"

const __ = inject("$translate")

const tab = ref("Received")
const rows = ref([])
const customers = ref([])
const suppliers = ref([])
const defaultRates = ref({ "PPh 22": 1.5, "PPh 23": 2.0, "PPh 4(2)": 10.0 })
const loading = ref(true)
const show = ref(false)
const busy = ref("")
const errorMessage = ref("")
const okMessage = ref("")
const form = reactive(blank())

const doneStatus = computed(() => (tab.value === "Received" ? ["Received"] : ["Reported"]))
const pendingStatus = computed(() => (tab.value === "Received" ? ["Expected"] : ["To Report"]))

function blank() {
	return {
		name: null, direction: tab.value, customer: "", supplier: "", tax_type: "PPh 22", rate: 1.5,
		gross_amount: null, tax_amount: null, tax_object_code: "", withholding_date: "",
		bp_number: "", bp_date: "", notes: "",
	}
}
function money(v) {
	return new Intl.NumberFormat("id-ID").format(v || 0)
}
function total(statuses) {
	const set = statuses ? (Array.isArray(statuses) ? statuses : statuses.value) : null
	return rows.value.filter((r) => !set || set.includes(r.status)).reduce((a, r) => a + (Number(r.tax_amount) || 0), 0)
}
function applyDefaultRate() {
	form.rate = defaultRates.value[form.tax_type] ?? form.rate
}

async function load() {
	loading.value = true
	try {
		const [list, lk] = await Promise.all([
			call("erpbio_indonesia_localization.api.tax.list_bukti_potong", { direction: tab.value }),
			call("erpbio_indonesia_localization.api.tax.bukti_potong_lookups"),
		])
		rows.value = list || []
		customers.value = lk.customers || []
		suppliers.value = lk.suppliers || []
		defaultRates.value = lk.default_rates || defaultRates.value
	} finally {
		loading.value = false
	}
}
load()

function switchTab(t) {
	tab.value = t
	okMessage.value = ""
	errorMessage.value = ""
	load()
}
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
	busy.value = "save"
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
		busy.value = ""
	}
}

// export the visible period: this month back to the earliest listed certificate
async function exportEbupot() {
	busy.value = "export"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		const dates = rows.value.map((r) => r.withholding_date).filter(Boolean).sort()
		const from = dates[0] || new Date().toISOString().slice(0, 10)
		const to = dates[dates.length - 1] || new Date().toISOString().slice(0, 10)
		const r = await call("erpbio_indonesia_localization.api.tax.export_ebupot", { from_date: from, to_date: to })
		okMessage.value = __("Exported {0} certificates.", [r.rows])
		window.open(r.file_url, "_blank")
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not export.")
	} finally {
		busy.value = ""
	}
}
</script>
