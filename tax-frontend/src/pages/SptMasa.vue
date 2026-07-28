<template>
	<div class="mx-auto max-w-3xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("SPT Masa PPN") }}</h1>
		</div>
		<p class="mb-4 text-sm text-ink-gray-5">
			{{ __("The month's VAT position: PPN Keluaran minus creditable PPN Masukan.") }}
		</p>

		<div class="mb-4 rounded-lg border bg-surface-white p-4">
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-3">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("Company") }}</label>
					<select v-model="company" class="form-select h-8 text-sm">
						<option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
					</select>
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("Masa (Month)") }}</label>
					<input type="month" v-model="month" class="form-input h-8 text-sm" />
				</div>
				<div class="flex items-end">
					<Button variant="solid" class="w-full" :loading="loading" :disabled="!company || !month" @click="run">
						<template #prefix><FeatherIcon name="play" class="h-3.5 w-3.5" /></template>{{ __("Run") }}
					</Button>
				</div>
			</div>
		</div>

		<template v-if="result">
			<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
				<div class="rounded-lg border bg-surface-white p-4">
					<div class="text-xs text-ink-gray-5">{{ __("PPN Keluaran") }} · {{ result.keluaran_count }} {{ __("invoices") }}</div>
					<div class="mt-1 text-xl font-semibold tabular-nums text-ink-gray-9">{{ money(result.keluaran) }}</div>
					<RouterLink :to="{ name: 'PpnKeluaran' }" class="mt-1 inline-block text-xs text-ink-blue-link hover:underline">{{ __("View register") }} →</RouterLink>
				</div>
				<div class="rounded-lg border bg-surface-white p-4">
					<div class="text-xs text-ink-gray-5">{{ __("PPN Masukan (creditable)") }} · {{ result.masukan_count }} {{ __("invoices") }}</div>
					<div class="mt-1 text-xl font-semibold tabular-nums text-ink-gray-9">{{ money(result.masukan) }}</div>
					<RouterLink :to="{ name: 'PpnMasukan' }" class="mt-1 inline-block text-xs text-ink-blue-link hover:underline">{{ __("View register") }} →</RouterLink>
				</div>
			</div>
			<div class="mt-3 rounded-lg border p-4"
				:class="result.net > 0 ? 'border-outline-amber-2 bg-surface-amber-1' : 'border-outline-green-2 bg-surface-green-1'">
				<div class="text-xs" :class="result.net > 0 ? 'text-ink-amber-3' : 'text-ink-green-3'">
					{{ result.net > 0 ? __("Kurang Bayar (to pay)") : __("Lebih Bayar (overpaid / carry forward)") }}
				</div>
				<div class="mt-1 text-2xl font-semibold tabular-nums" :class="result.net > 0 ? 'text-ink-amber-3' : 'text-ink-green-3'">
					{{ money(Math.abs(result.net)) }}
				</div>
				<p class="mt-1 text-xs" :class="result.net > 0 ? 'text-ink-amber-3' : 'text-ink-green-3'">
					{{ __("Figures follow the registers above — reconcile against Coretax before filing.") }}
				</p>
			</div>
		</template>
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
	</div>
</template>

<script setup>
import { inject, ref } from "vue"
import { RouterLink } from "vue-router"
import { call } from "frappe-ui"
import { formatCurrency } from "@/utils/format"

const __ = inject("$translate")

const companies = ref([])
const company = ref("")
const month = ref(new Date().toISOString().slice(0, 7))
const result = ref(null)
const loading = ref(false)
const errorMessage = ref("")

function money(v) {
	return formatCurrency(v ?? 0)
}

call("erpbio_indonesia_localization.api.tax.get_context").then((ctx) => {
	companies.value = ctx.companies || []
	if (companies.value.length === 1) company.value = companies.value[0]
})

async function run() {
	loading.value = true
	errorMessage.value = ""
	try {
		const [y, m] = month.value.split("-").map(Number)
		const from = `${month.value}-01`
		const to = `${month.value}-${String(new Date(y, m, 0).getDate()).padStart(2, "0")}`
		result.value = await call("erpbio_indonesia_localization.api.tax.spt_masa", {
			company: company.value, from_date: from, to_date: to,
		})
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not run the report.")
	} finally {
		loading.value = false
	}
}
</script>
