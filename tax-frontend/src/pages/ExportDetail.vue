<template>
	<div class="mx-auto max-w-4xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<RouterLink :to="{ name: 'ExportList' }" class="p-1 text-ink-gray-5 hover:text-ink-gray-8">
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
			</RouterLink>
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ name }}</h1>
			<Badge v-if="doc" :theme="doc.status === 'Generated' ? 'green' : 'gray'" variant="subtle">{{ __(doc.status) }}</Badge>
			<DocActions v-if="doc" doctype="Coretax Faktur Export" :name="name"
				apiModule="erpbio_indonesia_localization.api.tax" :shareText="shareText" />
			<div class="flex-1" />
			<Button :loading="busy === 'fetch'" @click="fetchInvoices">
				<template #prefix><FeatherIcon name="refresh-cw" class="h-3.5 w-3.5" /></template>{{ __("Fetch Invoices") }}
			</Button>
			<Button v-if="validCount" :loading="busy === 'xml'" :title="__('Direct XML — validate against Coretax before relying on it; the Excel + official converter is the safe route.')" @click="generateXml">
				<template #prefix><FeatherIcon name="code" class="h-3.5 w-3.5" /></template>{{ __("Generate XML") }}
			</Button>
			<Button v-if="validCount" variant="solid" :loading="busy === 'generate'" @click="generate">
				<template #prefix><FeatherIcon name="file-text" class="h-3.5 w-3.5" /></template>{{ __("Generate Coretax File") }}
			</Button>
		</div>

		<div v-if="doc" class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("Company") }}</div>
				<div class="truncate text-sm font-medium text-ink-gray-8">{{ doc.company }}</div>
			</div>
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("NPWP Penjual") }}</div>
				<div class="text-sm font-medium tabular-nums text-ink-gray-8">{{ doc.npwp_penjual || "—" }}</div>
			</div>
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("Period") }}</div>
				<div class="text-sm font-medium text-ink-gray-8">{{ doc.from_date }} → {{ doc.to_date }}</div>
			</div>
			<div class="rounded-lg bg-surface-gray-1 p-3">
				<div class="text-xs text-ink-gray-5">{{ __("Export File") }}</div>
				<a v-if="doc.export_file" :href="doc.export_file" class="text-sm font-medium text-ink-blue-link hover:underline">{{ __("Download") }}</a>
				<div v-else class="text-sm text-ink-gray-4">—</div>
			</div>
		</div>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Invoice") }}</th>
						<th class="px-3 py-2">{{ __("Customer") }}</th>
						<th class="px-3 py-2">{{ __("Date") }}</th>
						<th class="px-3 py-2 text-right">{{ __("Total") }}</th>
						<th class="px-3 py-2">{{ __("Kode") }}</th>
						<th class="px-3 py-2">{{ __("Validation") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in invoices" :key="row.sales_invoice" class="border-b border-outline-gray-1 last:border-0">
						<td class="px-3 py-2 font-medium text-ink-gray-8"
							v-doc-preview="row.sales_invoice ? { doctype: 'Sales Invoice', name: row.sales_invoice } : undefined">{{ row.sales_invoice }}</td>
						<td class="max-w-[16rem] truncate px-3 py-2 text-ink-gray-7"
							v-doc-preview="row.customer ? { doctype: 'Customer', name: row.customer } : undefined">{{ row.customer }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.posting_date }}</td>
						<td class="px-3 py-2 text-right tabular-nums text-ink-gray-7">{{ money(row.grand_total) }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.kode_transaksi }}</td>
						<td class="px-3 py-2">
							<span :class="row.ok ? 'text-ink-green-3' : 'text-ink-red-3'">{{ row.message }}</span>
						</td>
					</tr>
					<tr v-if="!invoices.length">
						<td colspan="6" class="px-3 py-8 text-center text-ink-gray-4">
							{{ __("Run Fetch Invoices to pull this period's Sales Invoices.") }}
						</td>
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
const invoices = ref([])
const busy = ref("")
const errorMessage = ref("")
const okMessage = ref("")

const validCount = computed(() => invoices.value.filter((r) => r.ok).length)

// One-line summary for the Share action.
const shareText = computed(() => {
	const d = doc.value
	if (!d) return ""
	return [
		`*${__("Coretax Export")} ${d.name}*`,
		d.company,
		`${d.from_date} \u2192 ${d.to_date}`,
		`${__("Status")}: ${d.status}`,
	].filter(Boolean).join("\n")
})

function money(v) {
	return new Intl.NumberFormat("id-ID").format(v || 0)
}

async function load() {
	const r = await call("erpbio_indonesia_localization.api.tax.get_export", { name: props.name })
	doc.value = r.doc
	invoices.value = r.invoices || []
}
load()

async function fetchInvoices() {
	busy.value = "fetch"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.fetch_export_invoices", { name: props.name })
		okMessage.value = __("{0} invoices found, {1} valid", [r.total, r.valid])
		await load()
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not fetch invoices.")
	} finally {
		busy.value = ""
	}
}

async function generate() {
	busy.value = "generate"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.generate_export", { name: props.name })
		okMessage.value = __("Generated for {0} invoices — feed the file to DJP's Excel-to-XML converter.", [r.invoices])
		await load()
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not generate the file.")
	} finally {
		busy.value = ""
	}
}

async function generateXml() {
	busy.value = "xml"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.generate_export_xml", { name: props.name })
		okMessage.value = __("XML generated for {0} invoices — check the first upload against Coretax carefully.", [r.invoices])
		await load()
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not generate the XML.")
	} finally {
		busy.value = ""
	}
}
</script>
