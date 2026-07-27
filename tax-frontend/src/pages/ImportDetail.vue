<template>
	<div class="mx-auto max-w-4xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<RouterLink :to="{ name: 'ImportList' }" class="p-1 text-ink-gray-5 hover:text-ink-gray-8">
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
			</RouterLink>
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ name }}</h1>
			<Badge v-if="doc" :theme="doc.status === 'Applied' ? 'green' : doc.status === 'Previewed' ? 'blue' : 'gray'" variant="subtle">
				{{ __(doc.status) }}
			</Badge>
			<DocActions v-if="doc" doctype="Coretax Faktur Import" :name="name"
				apiModule="erpbio_indonesia_localization.api.tax" :shareText="shareText" />
			<div class="flex-1" />
			<Button v-if="doc && doc.status !== 'Applied'" :loading="busy === 'preview'" @click="preview">
				<template #prefix><FeatherIcon name="eye" class="h-3.5 w-3.5" /></template>{{ __("Preview") }}
			</Button>
			<Button v-if="doc && doc.status === 'Previewed' && matchedCount" variant="solid" :loading="busy === 'apply'" @click="apply">
				<template #prefix><FeatherIcon name="check" class="h-3.5 w-3.5" /></template>{{ __("Apply to Sales Invoices") }}
			</Button>
		</div>
		<p v-if="doc?.summary" class="mb-4 text-sm text-ink-gray-5">{{ doc.summary }}</p>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Referensi") }}</th>
						<th class="px-3 py-2">{{ __("Nomor Faktur") }}</th>
						<th class="px-3 py-2">{{ __("Tanggal") }}</th>
						<th class="px-3 py-2">{{ __("DJP Status") }}</th>
						<th class="px-3 py-2">{{ __("Result") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="(row, i) in rows" :key="i" class="border-b border-outline-gray-1 last:border-0">
						<td class="px-3 py-2 font-medium text-ink-gray-8">{{ row.referensi }}</td>
						<td class="px-3 py-2 tabular-nums text-ink-gray-7">{{ row.faktur_number }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.faktur_date || "—" }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.djp_status || "—" }}</td>
						<td class="px-3 py-2">
							<span :class="row.ok ? 'text-ink-green-3' : 'text-ink-red-3'">{{ row.message }}</span>
						</td>
					</tr>
					<tr v-if="!rows.length">
						<td colspan="5" class="px-3 py-8 text-center text-ink-gray-4">{{ __("Run Preview to read the file.") }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mt-3 text-sm text-ink-green-3">{{ okMessage }}</p>
	</div>
</template>

<script setup>
import { computed, inject, ref } from "vue"
import { RouterLink } from "vue-router"
import { call } from "frappe-ui"
import DocActions from "@/components/DocActions.vue"

const props = defineProps({ name: { type: String, required: true } })
const __ = inject("$translate")

const doc = ref(null)
const rows = ref([])
const busy = ref("")
const errorMessage = ref("")
const okMessage = ref("")

const matchedCount = computed(() => rows.value.filter((r) => r.ok).length)

// One-line summary for the Share action.
const shareText = computed(() => {
	const d = doc.value
	if (!d) return ""
	return [`*${__("Coretax Import")} ${d.name}*`, `${__("Status")}: ${d.status}`, d.summary]
		.filter(Boolean)
		.join("\n")
})

async function load() {
	const r = await call("erpbio_indonesia_localization.api.tax.get_import", { name: props.name })
	doc.value = r.doc
	rows.value = r.rows || []
}
load()

async function preview() {
	busy.value = "preview"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.preview_import", { name: props.name })
		okMessage.value = __("{0} rows, {1} matched", [r.total, r.matched])
		await load()
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not read the file.")
	} finally {
		busy.value = ""
	}
}

async function apply() {
	busy.value = "apply"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.apply_import", { name: props.name })
		okMessage.value = __("Applied to {0} Sales Invoices", [r.applied])
		await load()
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not apply.")
	} finally {
		busy.value = ""
	}
}
</script>
