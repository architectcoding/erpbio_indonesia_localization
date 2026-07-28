<template>
	<div class="mx-auto max-w-5xl p-4">
		<div class="mb-4 flex flex-wrap items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("PPh 21 Rate Tables") }}</h1>
			<Badge v-if="settings" :theme="settings.tables_verified ? 'green' : 'orange'" variant="subtle">
				{{ settings.tables_verified ? __("Verified") : __("Not verified") }}
			</Badge>
			<Badge v-if="settings" :theme="settings.enabled ? 'green' : 'gray'" variant="subtle">
				{{ settings.enabled ? __("Enabled on salary slips") : __("Not enabled") }}
			</Badge>
			<div class="flex-1" />
			<a href="/app/eil-pph-21-settings" target="_blank" rel="noopener" class="text-xs text-ink-blue-link">
				{{ __("Open settings in Desk") }}
			</a>
		</div>

		<p class="mb-4 text-sm text-ink-gray-5">
			{{ __("The statutory tables PPh 21 is calculated from. They were extracted from the regulation rather than typed in, but a person still has to confirm them before anything is withheld.") }}
		</p>

		<p v-if="errorMessage" class="mb-3 rounded-md bg-surface-red-1 px-3 py-2 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mb-3 rounded-md bg-surface-green-1 px-3 py-2 text-sm text-ink-green-3">{{ okMessage }}</p>

		<div v-if="loading" class="py-10 text-center text-sm text-ink-gray-4">{{ __("Loading…") }}</div>

		<template v-else-if="settings">
			<!-- the gate -->
			<section class="mb-4 rounded-lg border bg-surface-white p-4">
				<h2 class="text-sm font-semibold text-ink-gray-8">{{ __("Verification") }}</h2>
				<p class="mt-1 text-xs text-ink-gray-5">{{ settings.tables_source || __("No source recorded.") }}</p>

				<div v-if="problems.length" class="mt-3 rounded-md bg-surface-red-1 px-3 py-2 text-xs text-ink-red-3">
					<div class="font-medium">{{ __("These tables fail their own structural checks:") }}</div>
					<ul class="mt-1 list-inside list-disc">
						<li v-for="p in problems" :key="p">{{ p }}</li>
					</ul>
				</div>
				<p v-else class="mt-3 text-xs text-ink-green-3">
					{{ __("All bands are contiguous, their rates never fall, and every PTKP status has a rate.") }}
				</p>

				<label class="mt-3 flex items-start gap-2 text-sm text-ink-gray-8">
					<input
						type="checkbox"
						class="desk-checkbox mt-0.5"
						:checked="!!settings.tables_verified"
						:disabled="!canWrite || busy || (problems.length && !settings.tables_verified)"
						@change="setVerified($event.target.checked)"
					/>
					<span>
						{{ __("I have checked these tables against the regulation") }}
						<span class="block text-xs text-ink-gray-4">
							{{ __("Until this is ticked, PPh 21 refuses to compute — a blocked payroll run is a better failure than a silently wrong withholding.") }}
						</span>
					</span>
				</label>
			</section>

			<!-- PTKP, and the TER category each status maps to -->
			<section class="mb-4 rounded-lg border bg-surface-white">
				<h2 class="border-b px-4 py-2.5 text-sm font-semibold text-ink-gray-8">
					{{ __("PTKP") }} <span class="font-normal text-ink-gray-4">· {{ __("annual allowance per status") }}</span>
				</h2>
				<div class="grid grid-cols-2 gap-x-6 gap-y-1 p-4 sm:grid-cols-4">
					<div v-for="row in ptkp" :key="row.ptkp_status" class="flex items-baseline justify-between gap-2 text-sm">
						<span class="text-ink-gray-6">{{ row.ptkp_status }} <span class="text-ink-gray-4">({{ row.ter_category }})</span></span>
						<span class="tabular-nums font-medium text-ink-gray-8">{{ money(row.annual_amount) }}</span>
					</div>
				</div>
			</section>

			<!-- Pasal 17 -->
			<section class="mb-4 rounded-lg border bg-surface-white">
				<h2 class="border-b px-4 py-2.5 text-sm font-semibold text-ink-gray-8">
					{{ __("Pasal 17") }} <span class="font-normal text-ink-gray-4">· {{ __("annual progressive brackets") }}</span>
				</h2>
				<BandTable :rows="pasal17" />
			</section>

			<!-- TER -->
			<section class="rounded-lg border bg-surface-white">
				<div class="flex flex-wrap items-center gap-1 border-b px-4 py-2.5">
					<h2 class="text-sm font-semibold text-ink-gray-8">{{ __("TER") }}</h2>
					<span class="mr-2 text-xs text-ink-gray-4">· {{ __("effective rate on one period's gross") }}</span>
					<button
						v-for="cat in CATEGORIES"
						:key="cat"
						type="button"
						class="rounded px-2 py-1 text-xs"
						:class="cat === category ? 'bg-surface-gray-3 font-medium text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-2'"
						@click="category = cat"
					>
						{{ cat === "Harian" ? __("Harian") : `${__("Category")} ${cat}` }}
						<span class="text-ink-gray-4">({{ (ter[cat] || []).length }})</span>
					</button>
				</div>
				<p class="px-4 pt-3 text-xs text-ink-gray-5">{{ CATEGORY_NOTE[category] }}</p>
				<BandTable :rows="ter[category] || []" />
			</section>
		</template>
	</div>
</template>

<script setup>
import { computed, h, inject, ref } from "vue"
import { Badge, call } from "frappe-ui"
import { formatCurrency, formatNumber } from "@/utils/format"

const __ = inject("$translate")

const CATEGORIES = ["A", "B", "C", "Harian"]

function money(v) {
	return formatCurrency(v)
}

// A band table reads the same for TER and for Pasal 17, so it is one local
// component rather than the markup twice.
const BandTable = {
	props: { rows: { type: Array, default: () => [] } },
	setup(props) {
		const cell = (text, cls = "") => h("td", { class: `px-4 py-1.5 ${cls}` }, text)
		return () =>
			h("div", { class: "overflow-x-auto" }, [
				h("table", { class: "w-full min-w-max text-sm" }, [
					h("thead", [
						h("tr", { class: "border-b text-left text-xs text-ink-gray-5" }, [
							h("th", { class: "px-4 py-2" }, "#"),
							h("th", { class: "px-4 py-2" }, __("From")),
							h("th", { class: "px-4 py-2" }, __("To")),
							h("th", { class: "px-4 py-2 text-right" }, __("Rate")),
						]),
					]),
					h(
						"tbody",
						props.rows.map((row, i) =>
							h("tr", { key: i, class: "border-b border-outline-gray-1 last:border-0" }, [
								cell(String(i + 1), "text-ink-gray-4"),
								cell(money(row.from_amount), "tabular-nums text-ink-gray-7"),
								cell(row.to_amount ? money(row.to_amount) : __("and above"), "tabular-nums text-ink-gray-7"),
								cell(`${formatNumber(row.rate, 2)}%`, "text-right tabular-nums font-medium text-ink-gray-9"),
							])
						)
					),
				]),
			])
	},
}

const CATEGORY_NOTE = computed(() => ({
	A: __("PTKP status TK/0, TK/1 and K/0."),
	B: __("PTKP status TK/2, TK/3, K/1 and K/2."),
	C: __("PTKP status K/3."),
	Harian: __("Daily-paid workers. Above the top band the daily rate no longer applies at all."),
}))

const settings = ref(null)
const ter = ref({})
const ptkp = ref([])
const pasal17 = ref([])
const problems = ref([])
const canWrite = ref(false)
const category = ref("A")
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref("")
const okMessage = ref("")

async function load() {
	loading.value = true
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.get_pph21_tables")
		settings.value = r.settings
		ter.value = r.ter || {}
		ptkp.value = r.ptkp || []
		pasal17.value = r.pasal_17 || []
		problems.value = r.problems || []
		canWrite.value = !!r.can_write
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not load the rate tables.")
	} finally {
		loading.value = false
	}
}
load()

async function setVerified(verified) {
	busy.value = true
	errorMessage.value = ""
	okMessage.value = ""
	try {
		await call("erpbio_indonesia_localization.api.tax.set_pph21_tables_verified", {
			verified: verified ? 1 : 0,
		})
		settings.value.tables_verified = verified ? 1 : 0
		okMessage.value = verified
			? __("Recorded. PPh 21 will now compute on salary slips that carry the component.")
			: __("Verification withdrawn. PPh 21 will refuse to compute.")
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not save.")
		await load()
	} finally {
		busy.value = false
	}
}
</script>
