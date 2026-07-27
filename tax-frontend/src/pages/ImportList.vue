<template>
	<ListView
		:title="__('Coretax Imports')"
		method="erpbio_indonesia_localization.api.tax.list_imports"
		:columns="COLUMNS"
		:quickFilters="QUICK_FILTERS"
		:filterableFields="FILTER_FIELDS"
		:rowTo="(row) => ({ name: 'ImportDetail', params: { name: row.name } })"
	>
		<template #actions>
			<Button variant="solid" :loading="busy" @click="pickFile">
				<template #prefix><FeatherIcon name="upload" class="h-4 w-4" /></template>{{ __("Import Coretax File") }}
			</Button>
			<input ref="fileInput" type="file" accept=".xlsx,.csv" class="hidden" @change="onFile" />
		</template>
		<template #mobileCard="{ row, highlight }">
			<div class="rounded-xl border bg-surface-white p-4">
				<div class="flex items-start justify-between gap-2">
					<span class="min-w-0 truncate text-base font-semibold text-ink-gray-9" v-html="highlight(row.name)" />
					<Badge class="shrink-0" :theme="themeFor(row.status)" variant="subtle">{{ __(row.status) }}</Badge>
				</div>
				<div class="mt-2 text-xs text-ink-gray-6">{{ row.summary || "—" }}</div>
			</div>
		</template>
	</ListView>

	<p v-if="errorMessage" class="px-3 py-2 text-sm text-ink-red-3">{{ errorMessage }}</p>
</template>

<script setup>
import { h, inject, ref } from "vue"
import { useRouter } from "vue-router"
import { Badge, Button, FeatherIcon, call } from "frappe-ui"
import ListView from "@/components/ListView.vue"

const __ = inject("$translate")
const router = useRouter()

const STATUSES = ["Draft", "Previewed", "Applied"]

function themeFor(status) {
	return status === "Applied" ? "green" : status === "Previewed" ? "blue" : "gray"
}

const StatusCell = {
	props: ["value"],
	render() {
		return h(Badge, { theme: themeFor(this.value), variant: "subtle" }, () => this.value || "—")
	},
}

const COLUMNS = [
	{ label: __("Name"), key: "name", cellClass: "font-medium text-ink-gray-9", width: "16rem" },
	{ label: __("Status"), key: "status", component: StatusCell, headerClass: "text-center", cellClass: "text-center" },
	{ label: __("Summary"), key: "summary", sortable: false, format: (v) => v || "—", cellClass: "text-ink-gray-7" },
]

const QUICK_FILTERS = [{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: STATUSES }]
const FILTER_FIELDS = [
	{ fieldname: "name", label: __("Name"), fieldtype: "Data" },
	{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: STATUSES },
]

// --- upload a Coretax download ---
const busy = ref(false)
const errorMessage = ref("")
const fileInput = ref(null)

function pickFile() {
	fileInput.value?.click()
}

async function onFile(e) {
	const file = e.target.files?.[0]
	if (!file) return
	busy.value = true
	errorMessage.value = ""
	try {
		const fd = new FormData()
		fd.append("file", file, file.name)
		fd.append("is_private", "1")
		const res = await fetch("/api/method/upload_file", {
			method: "POST",
			headers: { "X-Frappe-CSRF-Token": window.csrf_token },
			body: fd,
		})
		if (!res.ok) throw new Error(__("Upload failed"))
		const fileUrl = (await res.json())?.message?.file_url
		const r = await call("erpbio_indonesia_localization.api.tax.create_import", { file_url: fileUrl })
		router.push({ name: "ImportDetail", params: { name: r.name } })
	} catch (err) {
		errorMessage.value = err?.messages?.[0] || err?.message || __("Could not import the file.")
	} finally {
		busy.value = false
		if (fileInput.value) fileInput.value.value = ""
	}
}
</script>
