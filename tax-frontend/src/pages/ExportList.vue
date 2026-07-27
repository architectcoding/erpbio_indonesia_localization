<template>
	<div class="mx-auto max-w-4xl p-4">
		<div class="mb-4 flex items-center gap-2">
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ __("Coretax Exports") }}</h1>
			<div class="flex-1" />
			<Button variant="solid" @click="showNew = true">
				<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>{{ __("New Export") }}
			</Button>
		</div>
		<p class="mb-4 text-sm text-ink-gray-5">
			{{ __("Turn a period's Sales Invoices into the DJP workbook for the official Excel-to-XML converter.") }}
		</p>

		<div class="overflow-x-auto rounded-lg border bg-surface-white">
			<table class="w-full text-sm">
				<thead>
					<tr class="border-b text-left text-xs text-ink-gray-5">
						<th class="px-3 py-2">{{ __("Name") }}</th>
						<th class="px-3 py-2">{{ __("Company") }}</th>
						<th class="px-3 py-2">{{ __("Period") }}</th>
						<th class="px-3 py-2">{{ __("Status") }}</th>
						<th class="px-3 py-2">{{ __("File") }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="row in rows" :key="row.name"
						class="cursor-pointer border-b border-outline-gray-1 last:border-0 hover:bg-surface-gray-1"
						@click="$router.push({ name: 'ExportDetail', params: { name: row.name } })">
						<td class="px-3 py-2 font-medium text-ink-gray-8">{{ row.name }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.company }}</td>
						<td class="px-3 py-2 text-ink-gray-7">{{ row.from_date }} → {{ row.to_date }}</td>
						<td class="px-3 py-2">
							<Badge :theme="row.status === 'Generated' ? 'green' : 'gray'" variant="subtle">{{ __(row.status) }}</Badge>
						</td>
						<td class="px-3 py-2" @click.stop>
							<a v-if="row.export_file" :href="row.export_file" class="text-ink-blue-link hover:underline">{{ __("Download") }}</a>
							<span v-else class="text-ink-gray-4">—</span>
						</td>
					</tr>
					<tr v-if="!rows.length && !loading">
						<td colspan="5" class="px-3 py-8 text-center text-ink-gray-4">{{ __("No exports yet.") }}</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- new export -->
		<div v-if="showNew" class="fixed inset-0 z-20 flex items-center justify-center bg-black/30 p-4" @click.self="showNew = false">
			<div class="w-full max-w-sm rounded-lg bg-surface-white p-4">
				<h2 class="mb-3 text-base font-semibold text-ink-gray-9">{{ __("New Export") }}</h2>
				<div class="flex flex-col gap-3">
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Company") }}</label>
						<select v-model="form.company" class="form-select h-8 text-sm">
							<option v-for="c in companies" :key="c" :value="c">{{ c }}</option>
						</select>
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("From Date") }}</label>
						<DatePickerPopover :modelValue="form.from_date" clearable
							@update:modelValue="(v) => (form.from_date = v || '')" />
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("To Date") }}</label>
						<DatePickerPopover :modelValue="form.to_date" clearable
							@update:modelValue="(v) => (form.to_date = v || '')" />
					</div>
					<div class="flex justify-end gap-2">
						<Button @click="showNew = false">{{ __("Cancel") }}</Button>
						<Button variant="solid" :loading="busy" :disabled="!form.company || !form.from_date || !form.to_date" @click="create">
							{{ __("Create") }}
						</Button>
					</div>
					<p v-if="errorMessage" class="text-sm text-ink-red-3">{{ errorMessage }}</p>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import DatePickerPopover from "@/components/DatePickerPopover.vue"
import { inject, reactive, ref } from "vue"
import { useRouter } from "vue-router"
import { call } from "frappe-ui"

const __ = inject("$translate")
const router = useRouter()

const rows = ref([])
const companies = ref([])
const loading = ref(true)
const showNew = ref(false)
const busy = ref(false)
const errorMessage = ref("")
const form = reactive({ company: "", from_date: "", to_date: "" })

async function load() {
	loading.value = true
	try {
		const [list, ctx] = await Promise.all([
			call("erpbio_indonesia_localization.api.tax.list_exports"),
			call("erpbio_indonesia_localization.api.tax.get_context"),
		])
		rows.value = list || []
		companies.value = ctx.companies || []
		if (companies.value.length === 1) form.company = companies.value[0]
	} finally {
		loading.value = false
	}
}
load()

async function create() {
	busy.value = true
	errorMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.create_export", { ...form })
		router.push({ name: "ExportDetail", params: { name: r.name } })
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not create the export.")
	} finally {
		busy.value = false
	}
}
</script>
