<template>
	<div class="mx-auto max-w-4xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Coretax Imports") }}</h1>
			<div class="flex-1" />
			<Button variant="solid" :loading="busy" @click="pickFile">
				<template #prefix><FeatherIcon name="upload" class="h-4 w-4" /></template>{{ __("Import Coretax File") }}
			</Button>
			<input ref="fileInput" type="file" accept=".xlsx,.csv" class="hidden" @change="onFile" />
		</div>
		<p class="mb-4 text-sm text-ink-gray-5">
			{{ __("Upload the faktur list downloaded from Coretax to stamp official faktur numbers onto your Sales Invoices.") }}
		</p>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Name") }}</th>
						<th class="px-3 py-2">{{ __("Status") }}</th>
						<th class="px-3 py-2">{{ __("Summary") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.name"
						class="cursor-pointer border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
						@click="$router.push({ name: 'ImportDetail', params: { name: row.name } })">
						<td class="px-3 py-2 font-medium text-ink-gray-8">{{ row.name }}</td>
						<td class="px-3 py-2">
							<Badge :theme="row.status === 'Applied' ? 'green' : row.status === 'Previewed' ? 'blue' : 'gray'" variant="subtle">
								{{ __(row.status) }}
							</Badge>
						</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.summary || "—" }}</td>
					</tr>
					<tr v-if="!rows.length && !loading">
						<td colspan="3" class="px-3 py-8 text-center text-ink-gray-4">{{ __("No imports yet.") }}</td>
					</tr>
				</tbody>
			</table>
		</div>
		<p v-if="errorMessage" class="mt-3 text-sm text-ink-red-3">{{ errorMessage }}</p>
	</div>
</template>

<script setup>
import { inject, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"

const __ = inject("$translate")
const router = useRouter()

const rows = ref([])
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref("")
const fileInput = ref(null)

async function load() {
	loading.value = true
	try {
		rows.value = (await call("erpbio_indonesia_localization.api.tax.list_imports")) || []
	} finally {
		loading.value = false
	}
}
load()

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
