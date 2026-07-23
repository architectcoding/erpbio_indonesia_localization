<template>
	<div class="mx-auto max-w-2xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Tax Settings") }}</h1>
			<div class="flex-1" />
			<Button variant="solid" :loading="busy" @click="save">{{ __("Save") }}</Button>
		</div>

		<div class="rounded-lg border bg-surface-white p-4">
			<h2 class="mb-3 text-sm font-semibold text-ink-gray-9">{{ __("e-Faktur (Coretax)") }}</h2>
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("Default Transaction Code") }}</label>
					<select v-model="form.default_transaction_code" class="form-select h-8 text-sm">
						<option v-for="c in codes" :key="c.name" :value="c.name">{{ c.name }} — {{ c.description }}</option>
					</select>
				</div>
				<FormControl type="text" :label="__('Default Buyer Country Code')" v-model="form.default_buyer_country" />
				<FormControl type="number" :label="__('Tarif PPN (%)')" v-model="form.tarif_ppn" />
				<div class="flex items-end pb-1.5">
					<label class="flex items-center gap-2 text-sm text-ink-gray-7">
						<input type="checkbox" v-model="form.use_dpp_nilai_lain" class="form-checkbox" />
						{{ __("Use DPP Nilai Lain (PMK 131/2024)") }}
					</label>
				</div>
				<template v-if="form.use_dpp_nilai_lain">
					<FormControl type="number" :label="__('DPP Fraction Numerator')" v-model="form.dpp_numerator" />
					<FormControl type="number" :label="__('DPP Fraction Denominator')" v-model="form.dpp_denominator" />
				</template>
			</div>
			<p class="mt-3 text-xs text-ink-gray-4">
				{{ __("With DPP Nilai Lain 11/12 and 12% PPN, the effective rate is 11% — the current treatment for non-luxury goods and services.") }}
			</p>
		</div>

		<!-- withholding automation -->
		<div class="mt-4 rounded-lg border bg-surface-white p-4">
			<h2 class="mb-1 text-sm font-semibold text-ink-gray-9">{{ __("Withholding (Bukti Potong Automation)") }}</h2>
			<p class="mb-3 text-xs text-ink-gray-4">
				{{ __("When a submitted Payment Entry has a deduction row using one of these accounts, an Expected Bukti Potong is created automatically.") }}
			</p>
			<div v-for="(row, i) in form.withholding_accounts" :key="i" class="mb-2 flex items-center gap-2">
				<select v-model="row.account" class="form-select h-8 min-w-0 flex-1 text-sm">
					<option value="">{{ __("Select account") }}</option>
					<option v-for="a in accounts" :key="a" :value="a">{{ a }}</option>
				</select>
				<select v-model="row.tax_type" class="form-select h-8 w-28 text-sm">
					<option>PPh 22</option>
					<option>PPh 23</option>
					<option>PPh 4(2)</option>
				</select>
				<input type="number" step="any" v-model.number="row.rate" class="form-input h-8 w-20 text-sm" :placeholder="__('Rate %')" />
				<button class="p-1 text-ink-gray-4 hover:text-ink-red-3" :title="__('Remove')" @click="form.withholding_accounts.splice(i, 1)">
					<FeatherIcon name="x" class="h-4 w-4" />
				</button>
			</div>
			<Button variant="subtle" @click="form.withholding_accounts.push({ account: '', tax_type: 'PPh 22', rate: 1.5 })">
				<template #prefix><FeatherIcon name="plus" class="h-3.5 w-3.5" /></template>{{ __("Add Account") }}
			</Button>
		</div>
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mt-3 text-sm text-ink-green-3">{{ okMessage }}</p>
	</div>
</template>

<script setup>
import { inject, reactive, ref } from "vue"
import { call } from "frappe-ui"

const __ = inject("$translate")

const codes = ref([])
const accounts = ref([])
const busy = ref(false)
const errorMessage = ref("")
const okMessage = ref("")
const form = reactive({
	default_transaction_code: "",
	default_buyer_country: "IDN",
	tarif_ppn: 12,
	use_dpp_nilai_lain: true,
	dpp_numerator: 11,
	dpp_denominator: 12,
	withholding_accounts: [],
})

async function load() {
	const [s, ctx, accts] = await Promise.all([
		call("erpbio_indonesia_localization.api.tax.get_settings"),
		call("erpbio_indonesia_localization.api.tax.get_context"),
		call("erpbio_indonesia_localization.api.tax.account_options"),
	])
	Object.assign(form, s, {
		use_dpp_nilai_lain: !!s.use_dpp_nilai_lain,
		withholding_accounts: s.withholding_accounts || [],
	})
	codes.value = ctx.transaction_codes || []
	accounts.value = accts || []
}
load()

async function save() {
	busy.value = true
	errorMessage.value = ""
	okMessage.value = ""
	try {
		await call("erpbio_indonesia_localization.api.tax.save_settings", {
			payload: JSON.stringify({ ...form, use_dpp_nilai_lain: form.use_dpp_nilai_lain ? 1 : 0 }),
		})
		okMessage.value = __("Saved.")
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not save.")
	} finally {
		busy.value = false
	}
}
</script>
