<template>
	<div class="mx-auto max-w-4xl p-4">
		<div class="mb-4 flex flex-wrap items-center gap-2">
			<RouterLink :to="{ name: 'CustomerList' }" class="p-1 text-ink-gray-5 hover:text-ink-gray-8">
				<FeatherIcon name="arrow-left" class="h-4 w-4" />
			</RouterLink>
			<h1 class="text-lg font-semibold text-ink-gray-9" v-doc-preview="{ doctype: 'Customer', name }">
				{{ doc?.customer_name || name }}
			</h1>
			<Badge v-if="doc" :theme="themeFor(taxStatus)" variant="subtle">{{ __(taxStatus) }}</Badge>
			<Badge v-if="isPemungut" theme="blue" variant="subtle">{{ __("Government (Pemungut)") }}</Badge>
			<a
				v-if="doc"
				:href="`/app/customer/${encodeURIComponent(name)}`"
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
			{{ __("You can view this buyer's tax identity but not change it — that needs write access to Customer.") }}
		</p>

		<div v-if="loading" class="py-10 text-center text-sm text-ink-gray-4">{{ __("Loading…") }}</div>

		<template v-else-if="doc">
			<div v-if="taxStatus !== 'Ready'" class="mb-4 rounded-lg border border-outline-red-1 bg-surface-red-1 px-4 py-3 text-sm text-ink-red-3">
				{{ taxMessage }}
			</div>

			<section class="mb-4 rounded-lg border bg-surface-white p-4">
				<h2 class="mb-3 text-sm font-semibold text-ink-gray-8">{{ __("Buyer Identity (Coretax)") }}</h2>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Buyer ID Type") }}</label>
						<select v-model="form.eil_id_type" :disabled="!canWrite" class="form-select h-8 text-sm">
							<option v-for="t in ID_TYPES" :key="t" :value="t">{{ t }}</option>
						</select>
						<span class="text-xs text-ink-gray-4">{{ __("TIN = NPWP. The number itself goes in NPWP / NIK.") }}</span>
					</div>
					<div class="flex flex-col gap-1">
						<FormControl
							type="text"
							:label="__('NPWP / NIK')"
							v-model="form.tax_id"
							:disabled="!canWrite"
							:placeholder="__('e.g. 09.876.543.2-109.000')"
						/>
						<span class="text-xs text-ink-gray-4">{{ __("Punctuation is fine — the faktur uses digits only.") }}</span>
					</div>
					<FormControl
						v-if="['Passport', 'Other'].includes(form.eil_id_type)"
						type="text"
						:label="__('Buyer Document Number')"
						v-model="form.eil_document_number"
						:disabled="!canWrite"
					/>
					<div class="flex flex-col gap-1">
						<FormControl type="text" :label="__('NITKU / ID TKU')" v-model="form.eil_nitku" :disabled="!canWrite" />
						<span class="text-xs text-ink-gray-4">{{ __("Blank = NPWP + 000000 (pusat).") }}</span>
					</div>
					<FormControl type="text" :label="__('Tax Email')" v-model="form.eil_tax_email" :disabled="!canWrite" />
					<FormControl type="text" :label="__('Buyer Country Code')" v-model="form.eil_country_code" :disabled="!canWrite" placeholder="IDN" />
				</div>
			</section>

			<section class="mb-4 rounded-lg border bg-surface-white p-4">
				<h2 class="mb-1 text-sm font-semibold text-ink-gray-8">{{ __("Government (Pemungut / WAPU)") }}</h2>
				<label class="mt-2 flex items-start gap-2 text-sm text-ink-gray-8">
					<input type="checkbox" v-model="form.eil_is_pemungut" :disabled="!canWrite" class="mt-0.5" :true-value="1" :false-value="0" />
					<span>
						{{ __("This buyer deposits the PPN itself and withholds PPh 22") }}
						<span class="block text-xs text-ink-gray-4">
							{{ __("Sets the flag on new orders and invoices for this customer.") }}
						</span>
					</span>
				</label>
				<!-- A customer can be government purely through its group, which makes an
				     unticked box look wrong; say so instead of leaving it puzzling. -->
				<p v-if="pemungutSource === 'group'" class="mt-3 rounded-md bg-surface-blue-1 px-3 py-2 text-xs text-ink-blue-3">
					{{ __("Already treated as government because its customer group ({0}) is listed in Indonesia Tax Settings — the checkbox above is not needed.", [doc.customer_group]) }}
				</p>
			</section>

			<!-- The blank-means-derived fields above are hard to trust without this. -->
			<section class="rounded-lg border bg-surface-white p-4">
				<h2 class="mb-1 text-sm font-semibold text-ink-gray-8">{{ __("What the faktur will send") }}</h2>
				<p class="mb-3 text-xs text-ink-gray-4">{{ __("The buyer values this customer's e-Faktur rows will carry, after the blank-means-derived defaults are applied.") }}</p>
				<dl class="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
					<div v-for="f in PREVIEW_FIELDS" :key="f.key">
						<dt class="text-xs text-ink-gray-5">{{ f.label }}</dt>
						<dd class="truncate tabular-nums font-medium" :class="preview[f.key] ? 'text-ink-gray-8' : 'text-ink-gray-4'">
							{{ preview[f.key] || "—" }}
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

const props = defineProps({ name: { type: String, required: true } })
const __ = inject("$translate")

const ID_TYPES = ["TIN", "NIK", "Passport", "Other"]
const EDITABLE = [
	"eil_id_type",
	"tax_id",
	"eil_document_number",
	"eil_nitku",
	"eil_tax_email",
	"eil_country_code",
	"eil_is_pemungut",
]
const PREVIEW_FIELDS = [
	{ key: "npwp", label: __("NPWP (digits)") },
	{ key: "id_type", label: __("ID Type") },
	{ key: "document_number", label: __("Document Number") },
	{ key: "idtku", label: __("ID TKU") },
	{ key: "country", label: __("Country") },
	{ key: "email", label: __("Email") },
]

const doc = ref(null)
const preview = ref({})
const taxStatus = ref("")
const taxMessage = ref("")
const isPemungut = ref(false)
const pemungutSource = ref("")
const canWrite = ref(false)
const loading = ref(true)
const busy = ref(false)
const errorMessage = ref("")
const okMessage = ref("")
const form = reactive({})
// A ref, not a plain let: saving writes identical values back into the form,
// which triggers nothing reactive, so `dirty` would keep a stale true.
const pristine = ref("{}")

function themeFor(status) {
	return status === "Ready" ? "green" : status === "Incomplete" ? "orange" : "red"
}
function snapshot() {
	return EDITABLE.reduce(
		(acc, f) => ({ ...acc, [f]: f === "eil_is_pemungut" ? (form[f] ? 1 : 0) : form[f] ?? "" }),
		{}
	)
}
const dirty = computed(() => JSON.stringify(snapshot()) !== pristine.value)

function apply(r) {
	doc.value = r.doc
	preview.value = r.faktur_preview || {}
	taxStatus.value = r.tax_status
	taxMessage.value = r.tax_message
	isPemungut.value = !!r.is_pemungut
	pemungutSource.value = r.pemungut_source || ""
	canWrite.value = !!r.can_write
	for (const f of EDITABLE) form[f] = f === "eil_is_pemungut" ? (r.doc[f] ? 1 : 0) : r.doc[f] ?? ""
	pristine.value = JSON.stringify(snapshot())
}

async function load() {
	loading.value = true
	try {
		apply(await call("erpbio_indonesia_localization.api.tax.get_customer_tax", { name: props.name }))
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Could not load this customer.")
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
			await call("erpbio_indonesia_localization.api.tax.save_customer_tax", {
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
