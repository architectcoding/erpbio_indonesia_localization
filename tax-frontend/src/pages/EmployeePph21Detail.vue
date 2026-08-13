<template>
	<div class="mx-auto max-w-3xl p-4">
		<div class="mb-4 flex flex-wrap items-center gap-2">
			<RouterLink :to="{ name: 'EmployeePph21List' }" class="p-1 text-ink-gray-5 hover:text-ink-gray-8">
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
			</RouterLink>
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ doc?.employee_name || name }}</h1>
			<Badge v-if="doc" :theme="themeFor(status)" variant="subtle">{{ __(status) }}</Badge>
			<Badge v-if="inScope" theme="blue" variant="subtle">{{ __("On a PPh 21 structure") }}</Badge>
			<a
				v-if="doc"
				:href="`/app/employee/${encodeURIComponent(name)}`"
				target="_blank"
				rel="noopener"
				class="text-xs text-ink-blue-link"
				>{{ __("Open in Desk") }}</a
			>
			<div class="flex-1" />
			<Button v-if="canWrite" variant="solid" :loading="busy" :disabled="!dirty" @click="save">
				<template #prefix><FeatherIcon name="check" class="h-3.5 w-3.5" /></template>{{ __("Save") }}
			</Button>
		</div>

		<p v-if="errorMessage" class="mb-3 rounded-md bg-surface-red-1 px-3 py-2 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mb-3 rounded-md bg-surface-green-1 px-3 py-2 text-sm text-ink-green-3">{{ okMessage }}</p>
		<p v-if="doc && !canWrite" class="mb-3 rounded-md bg-surface-gray-2 px-3 py-2 text-sm text-ink-gray-6">
			{{ __("You can view this employee's tax identity but not change it — editing an Employee is an HR permission. Ask HR to set the PTKP status, or open it in Desk if you have the role.") }}
		</p>

		<div v-if="loading" class="py-10 text-center text-sm text-ink-gray-4">{{ __("Loading…") }}</div>

		<template v-else-if="doc">
			<div
				v-if="status !== 'Ready'"
				class="mb-4 rounded-lg border px-4 py-3 text-sm"
				:class="status === 'Unsupported'
					? 'border-outline-amber-1 bg-surface-amber-1 text-ink-amber-3'
					: 'border-outline-red-1 bg-surface-red-1 text-ink-red-3'"
			>
				{{ message }}
				<span v-if="!inScope" class="block text-xs opacity-80">
					{{ __("Not urgent: this employee is not on a salary structure that carries PPh 21.") }}
				</span>
			</div>

			<section class="mb-4 rounded-lg border bg-surface-white p-4">
				<h2 class="mb-3 text-sm font-semibold text-ink-gray-8">{{ __("PPh 21") }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("PTKP Status") }}</label>
						<select v-model="form.eil_ptkp_status" :disabled="!canWrite" class="form-select h-8 text-sm">
							<option value="">{{ __("Not set") }}</option>
							<option v-for="s in PTKP_STATUSES" :key="s" :value="s">{{ s }}</option>
						</select>
						<span class="text-xs text-ink-gray-4">
							{{ __("Marital status and dependants at the start of the tax year. TK = tidak kawin, K = kawin.") }}
						</span>
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Scheme") }}</label>
						<select v-model="form.eil_pph21_scheme" :disabled="!canWrite" class="form-select h-8 text-sm">
							<option v-for="s in SCHEMES" :key="s" :value="s">{{ s }}</option>
						</select>
						<span class="text-xs text-ink-gray-4">{{ __("Only Permanent (pegawai tetap) is calculated today.") }}</span>
					</div>
					<FormControl type="text" :label="__('NPWP')" v-model="form.eil_npwp" :disabled="!canWrite" />
					<FormControl type="text" :label="__('NIK')" v-model="form.eil_nik" :disabled="!canWrite" />
				</div>
			</section>

			<!-- What the PTKP status resolves to, so the choice is not opaque. -->
			<section v-if="doc.eil_ptkp_status" class="rounded-lg border bg-surface-white p-4">
				<h2 class="mb-1 text-sm font-semibold text-ink-gray-8">{{ __("What this resolves to") }}</h2>
				<p class="mb-3 text-xs text-ink-gray-4">{{ __("Saved values, from the loaded rate tables.") }}</p>
				<dl class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("PTKP Status") }}</dt>
						<dd class="font-medium text-ink-gray-8">{{ doc.eil_ptkp_status }}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("TER Category") }}</dt>
						<dd class="font-medium text-ink-gray-8">{{ doc.eil_ter_category || "—" }}</dd>
					</div>
					<div>
						<dt class="text-xs text-ink-gray-5">{{ __("Annual PTKP") }}</dt>
						<dd class="tabular-nums font-medium" :class="ptkpAnnual ? 'text-ink-gray-8' : 'text-ink-gray-4'">
							{{ ptkpAnnual ? money(ptkpAnnual) : __("rate tables not verified") }}
						</dd>
					</div>
				</dl>
			</section>
		</template>
	</div>
</template>

<script setup>
import { computed, inject, reactive, ref } from "vue"
import { RouterLink } from "vue-router"
import { call } from "frappe-ui"
import { formatCurrency } from "@shared/utils/format"

const props = defineProps({ name: { type: String, required: true } })
const __ = inject("$translate")

const PTKP_STATUSES = ["TK/0", "TK/1", "TK/2", "TK/3", "K/0", "K/1", "K/2", "K/3"]
const SCHEMES = ["Permanent", "Non-permanent", "Expatriate", "Pensioner"]
const EDITABLE = ["eil_ptkp_status", "eil_pph21_scheme", "eil_npwp", "eil_nik"]

const doc = ref(null)
const status = ref("")
const message = ref("")
const ptkpAnnual = ref(null)
const inScope = ref(false)
const canWrite = ref(false)
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref("")
const okMessage = ref("")
const form = reactive({})
const pristine = ref("{}")

function themeFor(s) {
	return s === "Ready" ? "green" : s === "Unsupported" ? "orange" : "red"
}
function money(v) {
	return formatCurrency(v)
}
function snapshot() {
	return EDITABLE.reduce((acc, f) => ({ ...acc, [f]: form[f] ?? "" }), {})
}
const dirty = computed(() => JSON.stringify(snapshot()) !== pristine.value)

function apply(r) {
	doc.value = r.doc
	status.value = r.pph21_status
	message.value = r.pph21_message
	ptkpAnnual.value = r.ptkp_annual
	inScope.value = !!r.in_scope
	canWrite.value = !!r.can_write
	for (const f of EDITABLE) form[f] = r.doc[f] ?? ""
	pristine.value = JSON.stringify(snapshot())
}

async function load() {
	loading.value = true
	try {
		apply(await call("erpbio_indonesia_localization.api.tax.get_employee_pph21", { name: props.name }))
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not load this employee.")
	} finally {
		loading.value = false
	}
}
load()

async function save() {
	busy.value = true
	errorMessage.value = ""
	okMessage.value = ""
	try {
		apply(
			await call("erpbio_indonesia_localization.api.tax.save_employee_pph21", {
				payload: JSON.stringify({ name: props.name, ...snapshot() }),
			})
		)
		okMessage.value = __("Saved.")
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not save.")
	} finally {
		busy.value = false
	}
}
</script>
