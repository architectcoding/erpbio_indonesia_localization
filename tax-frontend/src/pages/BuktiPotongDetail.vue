<template>
	<div class="mx-auto max-w-4xl p-4">
		<div class="mb-4 flex flex-wrap items-center gap-2">
			<RouterLink :to="{ name: 'BuktiPotong' }" class="p-1 text-ink-gray-5 hover:text-ink-gray-8">
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
			</RouterLink>
			<h1 class="text-lg font-semibold text-ink-gray-9">{{ name }}</h1>
			<Badge v-if="doc" :theme="DONE.includes(doc.status) ? 'green' : 'orange'" variant="subtle">{{ __(doc.status) }}</Badge>
			<Badge v-if="doc?.auto_created" theme="blue" variant="subtle">{{ __("Auto-created") }}</Badge>
			<DocActions v-if="doc" doctype="Bukti Potong" :name="name"
				apiModule="erpbio_indonesia_localization.api.tax" :shareText="shareText" />
			<div class="flex-1" />
			<Button v-if="canWrite" variant="solid" :loading="busy === 'save'" :disabled="!dirty" @click="save">
				<template #prefix><FeatherIcon name="check" class="h-3.5 w-3.5" /></template>{{ __("Save") }}
			</Button>
		</div>

		<p v-if="errorMessage" class="mb-3 rounded-md bg-surface-red-1 px-3 py-2 text-sm text-ink-red-3">{{ errorMessage }}</p>
		<p v-if="okMessage" class="mb-3 rounded-md bg-surface-green-1 px-3 py-2 text-sm text-ink-green-3">{{ okMessage }}</p>

		<div v-if="loading" class="py-10 text-center text-sm text-ink-gray-4">{{ __("Loading…") }}</div>

		<template v-else-if="doc">
			<!-- headline numbers -->
			<div class="mb-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
				<div class="rounded-lg bg-surface-gray-1 p-3">
					<div class="text-xs text-ink-gray-5">{{ isIssued ? __("Supplier (Dipotong)") : __("Customer (Pemotong)") }}</div>
					<div class="truncate text-sm font-medium text-ink-gray-8"
						v-doc-preview="partyPreview">{{ party || "—" }}</div>
				</div>
				<div class="rounded-lg bg-surface-gray-1 p-3">
					<div class="text-xs text-ink-gray-5">{{ __("Tax Type") }}</div>
					<div class="text-sm font-medium text-ink-gray-8">
						{{ doc.tax_type || "—" }}<span v-if="doc.tax_object_code" class="text-ink-gray-5"> · {{ doc.tax_object_code }}</span>
					</div>
				</div>
				<div class="rounded-lg bg-surface-gray-1 p-3">
					<div class="text-xs text-ink-gray-5">{{ __("Gross (DPP)") }}</div>
					<div class="text-sm font-semibold tabular-nums text-ink-gray-8">{{ money(doc.gross_amount) }}</div>
				</div>
				<div class="rounded-lg bg-surface-gray-1 p-3">
					<div class="text-xs text-ink-gray-5">{{ __("Withheld") }} · {{ formatNumber(doc.rate, 2) }}%</div>
					<div class="text-sm font-semibold tabular-nums text-ink-gray-9">{{ money(doc.tax_amount) }}</div>
				</div>
			</div>

			<!-- the certificate: what makes the withholding claimable -->
			<section class="mb-4 rounded-lg border bg-surface-white">
				<div class="flex items-center gap-2 border-b px-4 py-2.5">
					<FeatherIcon name="paperclip" class="h-4 w-4 text-ink-gray-5" />
					<h2 class="text-sm font-semibold text-ink-gray-8">{{ __("Certificate & Attachments") }}</h2>
					<Badge v-if="attachments.length" theme="gray" variant="subtle">{{ attachments.length }}</Badge>
					<div class="flex-1" />
					<Button v-if="canWrite" :loading="busy === 'upload'" @click="pickFile">
						<template #prefix><FeatherIcon name="upload" class="h-3.5 w-3.5" /></template>{{ __("Attach File") }}
					</Button>
					<input ref="fileInput" type="file" multiple class="hidden"
						accept=".pdf,.png,.jpg,.jpeg,.webp,.tif,.tiff,.doc,.docx,.xls,.xlsx,.zip" @change="onFiles" />
				</div>

				<p v-if="!attachments.length" class="px-4 py-6 text-center text-sm text-ink-gray-4">
					{{ isIssued
						? __("No file yet. Attach the certificate you issued, so the reported PPh has its evidence on file.")
						: __("No file yet. Attach the certificate the customer issued — it is the evidence for your prepaid-tax credit.") }}
				</p>

				<ul v-else class="divide-y divide-outline-gray-1">
					<li v-for="f in attachments" :key="f.name" class="flex items-center gap-3 px-4 py-2.5">
						<a :href="f.file_url" target="_blank" rel="noopener"
							class="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded border bg-surface-gray-1">
							<img v-if="isImage(f)" :src="f.file_url" :alt="f.file_name" class="h-full w-full object-cover" />
							<FeatherIcon v-else :name="iconFor(f)" class="h-4 w-4 text-ink-gray-5" />
						</a>
						<div class="min-w-0 flex-1">
							<a :href="f.file_url" target="_blank" rel="noopener"
								class="block truncate text-sm font-medium text-ink-blue-link">{{ f.file_name }}</a>
							<div class="flex items-center gap-1.5 text-xs text-ink-gray-5">
								<span>{{ fileSize(f.file_size) }}</span>
								<span>·</span>
								<span>{{ $dayjs(f.creation).format("DD MMM YYYY") }}</span>
								<Badge v-if="f.file_url === doc.bp_file" theme="green" variant="subtle">{{ __("Certificate") }}</Badge>
							</div>
						</div>
						<Button v-if="canWrite && f.file_url !== doc.bp_file" variant="ghost"
							:title="__('Mark as the certificate')" :loading="busy === `mark-${f.name}`"
							@click="markCertificate(f)">
							<template #icon><FeatherIcon name="award" class="h-4 w-4" /></template>
						</Button>
						<Button v-if="canWrite" variant="ghost" :title="__('Remove')"
							:loading="busy === `rm-${f.name}`" @click="removeFile(f)">
							<template #icon><FeatherIcon name="trash-2" class="h-4 w-4 text-ink-gray-5" /></template>
						</Button>
					</li>
				</ul>
			</section>

			<!-- fields -->
			<section class="mb-4 rounded-lg border bg-surface-white p-4">
				<h2 class="mb-3 text-sm font-semibold text-ink-gray-8">{{ __("Withholding") }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Direction") }}</label>
						<select v-model="form.direction" :disabled="!canWrite" class="form-select h-8 text-sm">
							<option value="Received">{{ __("Received (customer withheld from us)") }}</option>
							<option value="Issued">{{ __("Issued (we withheld from suppliers)") }}</option>
						</select>
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">
							{{ form.direction === "Issued" ? __("Supplier (Dipotong)") : __("Customer (Pemotong)") }}
						</label>
						<select v-if="form.direction === 'Issued'" v-model="form.supplier" :disabled="!canWrite" class="form-select h-8 text-sm">
							<option v-for="s in suppliers" :key="s" :value="s">{{ s }}</option>
						</select>
						<select v-else v-model="form.customer" :disabled="!canWrite" class="form-select h-8 text-sm">
							<option v-for="c in customers" :key="c" :value="c">{{ c }}</option>
						</select>
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Tax Type") }}</label>
						<select v-model="form.tax_type" :disabled="!canWrite" class="form-select h-8 text-sm" @change="applyDefaultRate">
							<option v-for="t in Object.keys(defaultRates)" :key="t" :value="t">{{ t }}</option>
						</select>
					</div>
					<FormControl type="number" :label="__('Rate (%)')" v-model="form.rate" :disabled="!canWrite" />
					<FormControl type="number" :label="__('Gross Amount (DPP)')" v-model="form.gross_amount" :disabled="!canWrite" />
					<FormControl type="number" :label="__('Tax Withheld (blank = Gross × Rate)')" v-model="form.tax_amount" :disabled="!canWrite" />
					<FormControl v-if="form.direction === 'Issued'" type="text" :label="__('Kode Objek Pajak')"
						v-model="form.tax_object_code" :disabled="!canWrite" :placeholder="__('e.g. 24-104-01')" />
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Withholding Date") }}</label>
						<DatePickerPopover :modelValue="form.withholding_date" clearable :disabled="!canWrite"
							@update:modelValue="(v) => (form.withholding_date = v || '')" />
					</div>
				</div>
			</section>

			<section class="mb-4 rounded-lg border bg-surface-white p-4">
				<h2 class="mb-3 text-sm font-semibold text-ink-gray-8">{{ __("Certificate Details") }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<FormControl type="text" :label="__('Bukti Potong Number')" v-model="form.bp_number" :disabled="!canWrite"
						:placeholder="form.direction === 'Issued' ? __('Fills = Reported') : __('Fills = Received')" />
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Bukti Potong Date") }}</label>
						<DatePickerPopover :modelValue="form.bp_date" clearable :disabled="!canWrite"
							@update:modelValue="(v) => (form.bp_date = v || '')" />
					</div>
					<div class="flex flex-col gap-1 sm:col-span-2">
						<label class="text-xs text-ink-gray-5">{{ __("Notes") }}</label>
						<textarea v-model="form.notes" rows="2" :disabled="!canWrite" class="form-textarea text-sm" />
					</div>
				</div>
			</section>

			<!-- where this withholding came from -->
			<section v-if="doc.sales_invoice || doc.payment_entry || doc.company" class="rounded-lg border bg-surface-white p-4">
				<h2 class="mb-3 text-sm font-semibold text-ink-gray-8">{{ __("References") }}</h2>
				<dl class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
					<div v-if="doc.company">
						<dt class="text-xs text-ink-gray-5">{{ __("Company") }}</dt>
						<dd class="truncate font-medium text-ink-gray-8">{{ doc.company }}</dd>
					</div>
					<div v-if="doc.sales_invoice">
						<dt class="text-xs text-ink-gray-5">{{ __("Sales Invoice") }}</dt>
						<dd>
							<a :href="`/app/sales-invoice/${encodeURIComponent(doc.sales_invoice)}`" target="_blank" rel="noopener"
								class="font-medium text-ink-blue-link"
								v-doc-preview="{ doctype: 'Sales Invoice', name: doc.sales_invoice }">{{ doc.sales_invoice }}</a>
						</dd>
					</div>
					<div v-if="doc.payment_entry">
						<dt class="text-xs text-ink-gray-5">{{ __("Payment Entry") }}</dt>
						<dd>
							<a :href="`/app/payment-entry/${encodeURIComponent(doc.payment_entry)}`" target="_blank" rel="noopener"
								class="font-medium text-ink-blue-link"
								v-doc-preview="{ doctype: 'Payment Entry', name: doc.payment_entry }">{{ doc.payment_entry }}</a>
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
import DatePickerPopover from "@/components/DatePickerPopover.vue"
import DocActions from "@/components/DocActions.vue"
import { formatCurrency, formatNumber } from "@/utils/format"

const props = defineProps({ name: { type: String, required: true } })
const __ = inject("$translate")
const $dayjs = inject("$dayjs")

const DONE = ["Received", "Reported"]
const EDITABLE = [
	"direction", "customer", "supplier", "tax_type", "tax_object_code",
	"withholding_date", "gross_amount", "rate", "tax_amount", "bp_number", "bp_date", "notes",
]

const doc = ref(null)
const attachments = ref([])
const canWrite = ref(false)
const customers = ref([])
const suppliers = ref([])
const defaultRates = ref({ "PPh 22": 1.5, "PPh 23": 2.0, "PPh 4(2)": 10.0 })
const loading = ref(true)
const busy = ref("")
const errorMessage = ref("")
const okMessage = ref("")
const form = reactive({})
// A ref, not a plain let: re-saving writes identical values back into `form`,
// which triggers nothing reactive, so `dirty` would keep its stale true and
// leave Save lit after a successful save.
const pristine = ref("{}")

const isIssued = computed(() => doc.value?.direction === "Issued")
const party = computed(() => (isIssued.value ? doc.value?.supplier : doc.value?.customer))
const partyPreview = computed(() =>
	party.value ? { doctype: isIssued.value ? "Supplier" : "Customer", name: party.value } : undefined
)
const dirty = computed(() => JSON.stringify(snapshot()) !== pristine.value)
const shareText = computed(() =>
	doc.value
		? `${__("Bukti Potong")} ${props.name} · ${doc.value.tax_type || ""} · ${party.value || ""} — ${money(doc.value.tax_amount)}`
		: ""
)

function money(v) {
	return formatCurrency(v)
}
// Number inputs hand their value back as a string, so a freshly loaded 1.5 and
// the input's "1.5" would otherwise read as an edit and leave Save lit forever.
const NUMERIC = new Set(["gross_amount", "rate", "tax_amount"])

function snapshot() {
	return EDITABLE.reduce((acc, f) => {
		const v = form[f] ?? ""
		return { ...acc, [f]: NUMERIC.has(f) && v !== "" ? Number(v) : v }
	}, {})
}
function applyDefaultRate() {
	form.rate = defaultRates.value[form.tax_type] ?? form.rate
}

// --- files ---
const fileInput = ref(null)
const IMAGE = /\.(png|jpe?g|webp|gif|bmp|tiff?)$/i

function isImage(f) {
	return IMAGE.test(f.file_name || f.file_url || "")
}
function iconFor(f) {
	return /\.pdf$/i.test(f.file_name || "") ? "file-text" : "file"
}
// upload_file is a raw fetch, so Frappe's error arrives as _server_messages —
// a JSON string of JSON strings — rather than the `messages` array `call` gives.
function firstServerMessage(payload) {
	try {
		const first = JSON.parse(payload?._server_messages || "[]")[0]
		return first ? JSON.parse(first).message : ""
	} catch {
		return ""
	}
}
function fileSize(bytes) {
	const n = Number(bytes) || 0
	if (n < 1024) return `${n} B`
	if (n < 1024 * 1024) return `${formatNumber(n / 1024, 0)} KB`
	return `${formatNumber(n / (1024 * 1024), 1)} MB`
}

async function load() {
	loading.value = true
	try {
		const [r, lk] = await Promise.all([
			call("erpbio_indonesia_localization.api.tax.get_bukti_potong", { name: props.name }),
			call("erpbio_indonesia_localization.api.tax.bukti_potong_lookups"),
		])
		doc.value = r.doc
		attachments.value = r.attachments || []
		canWrite.value = !!r.can_write
		customers.value = lk.customers || []
		suppliers.value = lk.suppliers || []
		defaultRates.value = lk.default_rates || defaultRates.value
		for (const f of EDITABLE) form[f] = r.doc[f] ?? ""
		pristine.value = JSON.stringify(snapshot())
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not load this certificate.")
	} finally {
		loading.value = false
	}
}
load()

async function save() {
	busy.value = "save"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		await call("erpbio_indonesia_localization.api.tax.save_bukti_potong", {
			payload: JSON.stringify({ name: props.name, ...snapshot() }),
		})
		await load()
		okMessage.value = __("Saved.")
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not save.")
	} finally {
		busy.value = ""
	}
}

function pickFile() {
	fileInput.value?.click()
}

// Core upload_file files the File row against this doc, but it does NOT stamp
// the target field on a fresh upload (it only writes bp_file back when a file's
// privacy later changes) — so the first upload is promoted explicitly.
async function onFiles(e) {
	const files = Array.from(e.target.files || [])
	if (!files.length) return
	busy.value = "upload"
	errorMessage.value = ""
	okMessage.value = ""
	try {
		let promote = doc.value.bp_file ? null : undefined
		for (const file of files) {
			const fd = new FormData()
			fd.append("file", file, file.name)
			fd.append("is_private", "1")
			fd.append("doctype", "Bukti Potong")
			fd.append("docname", props.name)
			fd.append("fieldname", "bp_file")
			const res = await fetch("/api/method/upload_file", {
				method: "POST",
				headers: { "X-Frappe-CSRF-Token": window.csrf_token },
				body: fd,
			})
			const payload = await res.json().catch(() => null)
			if (!res.ok) {
				throw new Error(
					firstServerMessage(payload) || payload?.exception || __("Upload failed")
				)
			}
			// first file of the batch becomes the certificate when there isn't one
			if (promote === undefined) promote = payload?.message?.file_url || null
		}
		if (promote) {
			await call("erpbio_indonesia_localization.api.tax.set_bukti_potong_certificate", {
				name: props.name,
				file_url: promote,
			})
		}
		await load()
		okMessage.value = __("Attached {0} file(s).", [files.length])
	} catch (err) {
		errorMessage.value = err?.messages?.[0] || err?.message || __("Could not attach the file.")
	} finally {
		busy.value = ""
		if (fileInput.value) fileInput.value.value = ""
	}
}

async function markCertificate(f) {
	busy.value = `mark-${f.name}`
	errorMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.set_bukti_potong_certificate", {
			name: props.name,
			file_url: f.file_url,
		})
		doc.value.bp_file = r.bp_file
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not mark the certificate.")
	} finally {
		busy.value = ""
	}
}

async function removeFile(f) {
	if (!window.confirm(__("Remove {0}?", [f.file_name]))) return
	busy.value = `rm-${f.name}`
	errorMessage.value = ""
	try {
		const r = await call("erpbio_indonesia_localization.api.tax.remove_bukti_potong_attachment", {
			name: props.name,
			file: f.name,
		})
		attachments.value = r.attachments || []
		doc.value.bp_file = r.bp_file
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not remove the file.")
	} finally {
		busy.value = ""
	}
}
</script>
