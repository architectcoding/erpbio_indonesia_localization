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
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mt-3 text-sm text-ink-green-3">{{ okMessage }}</p>
	</div>
</template>

<script setup>
import { inject, reactive, ref } from "vue"
import { call } from "frappe-ui"

const __ = inject("$translate")

const codes = ref([])
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
})

async function load() {
	const [s, ctx] = await Promise.all([
		call("erpbio_indonesia_localization.api.tax.get_settings"),
		call("erpbio_indonesia_localization.api.tax.get_context"),
	])
	Object.assign(form, s, { use_dpp_nilai_lain: !!s.use_dpp_nilai_lain })
	codes.value = ctx.transaction_codes || []
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
