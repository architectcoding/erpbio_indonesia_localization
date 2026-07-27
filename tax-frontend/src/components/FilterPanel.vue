<!-- Copied from erpbio_general spa-shared, not imported: this app must build and
     install without erpbio_general present. Backend-agnostic (it calls whatever
     `method` you pass), so nothing here reaches into that app. Keep in sync by hand. -->
<template>
	<div class="relative">
		<!-- Single inline-flex/nowrap wrapper keeps the icon + label on one line
		     (raw default-slot children wrapped to 2 lines under a narrow button);
		     centred on phones when the label is hidden. -->
		<!-- Icon via the #prefix slot (like the sibling toolbar buttons) so it's a
		     direct, vertically-centred flex child; !gap-0 keeps it centred when the
		     label is hidden on phones. -->
		<Button variant="subtle" class="!gap-0 sm:!gap-2" @click="togglePanel">
			<template #prefix><FeatherIcon name="filter" class="h-4 w-4" /></template>
			<span class="hidden whitespace-nowrap sm:inline">{{ __("Filter") }}</span>
			<span v-if="appliedCount" class="ml-1 rounded bg-gray-800 px-1.5 text-xs font-medium text-white">
				{{ appliedCount }}
			</span>
		</Button>

		<!-- click-outside backdrop -->
		<div v-if="open" class="fixed inset-0 z-40" @click="open = false" />

		<!-- panel (Desk-style: roomy rows, explicit Apply). On phones it takes
		     the screen width with small side margins; on desktop it stays a
		     dropdown anchored to the button. -->
		<div
			v-if="open"
			class="fixed inset-x-3 top-24 z-50 rounded-xl border bg-surface-white p-4 shadow-xl md:absolute md:inset-x-auto md:right-0 md:top-auto md:mt-2 md:w-[30rem]"
		>
			<div v-if="!rows.length" class="py-2 text-center text-sm text-ink-gray-5">
				{{ __("No filters applied") }}
			</div>

			<!-- On mobile: field + operator share row 1, the value input spans row 2
			     (so none of the three is squashed). Inline on desktop. -->
			<div v-for="(row, i) in rows" :key="i" class="mb-3 flex items-start gap-2">
				<div class="grid min-w-0 flex-1 grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)_minmax(0,1.4fr)]">
					<select
						class="form-select h-8 min-w-0 text-sm"
						:value="row.field"
						@change="(e) => onFieldChange(i, e.target.value)"
					>
						<option v-for="f in fields" :key="f.fieldname" :value="f.fieldname">{{ f.label }}</option>
					</select>

					<select
						class="form-select h-8 min-w-0 text-sm"
						:value="row.operator"
						@change="(e) => (row.operator = e.target.value)"
					>
						<option v-for="op in operatorsFor(row.field)" :key="op[0]" :value="op[0]">
							{{ op[1] }}
						</option>
					</select>

					<!-- value control -->
					<select
						v-if="fieldType(row.field) === 'Select'"
						class="form-select col-span-2 h-8 min-w-0 text-sm sm:col-span-1"
						:value="row.value"
						@change="(e) => (row.value = e.target.value)"
					>
						<option value="">—</option>
						<option v-for="opt in selectOptions(row.field)" :key="opt" :value="opt">{{ opt }}</option>
					</select>
					<select
						v-else-if="fieldType(row.field) === 'Check'"
						class="form-select col-span-2 h-8 min-w-0 text-sm sm:col-span-1"
						:value="row.value"
						@change="(e) => (row.value = e.target.value)"
					>
						<option value="">—</option>
						<option value="1">{{ __("Yes") }}</option>
						<option value="0">{{ __("No") }}</option>
					</select>
					<input
						v-else
						:type="inputType(row.field)"
						class="form-input col-span-2 h-8 min-w-0 text-sm sm:col-span-1"
						:value="row.value"
						@input="(e) => (row.value = e.target.value)"
						@keyup.enter="applyFilters"
					/>
				</div>

				<button class="mt-1 shrink-0 p-1 text-ink-gray-4 hover:text-ink-gray-7" @click="removeRow(i)">
					<FeatherIcon name="x" class="h-4 w-4" />
				</button>
			</div>

			<div class="mt-3 flex items-center justify-between gap-2 pt-1">
				<button
					class="flex items-center gap-1 text-sm font-medium text-ink-gray-7 hover:text-ink-gray-9"
					@click="addRow"
				>
					<FeatherIcon name="plus" class="h-3.5 w-3.5" /> {{ __("Add a Filter") }}
				</button>
				<div class="flex items-center gap-2">
					<Button v-if="rows.length || appliedCount" variant="subtle" @click="clearAll">{{ __("Clear Filters") }}</Button>
					<Button variant="solid" @click="applyFilters">{{ __("Apply Filters") }}</Button>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup>
import { inject, ref } from "vue"
import { Button, FeatherIcon } from "frappe-ui"
const __ = inject("$translate")

const props = defineProps({
	// [{ fieldname, label, fieldtype, options? }]
	fields: { type: Array, required: true },
})

const emit = defineEmits(["update:modelValue"])

const open = ref(false)
const rows = ref([])
// Filters actually sent to the list (set on Apply / Clear), for the badge.
const appliedCount = ref(0)

function togglePanel() {
	open.value = !open.value
	// Desk-style convenience: opening an empty panel starts with one blank row.
	if (open.value && !rows.value.length) addRow()
}

const OPERATORS = {
	Data: [
		["like", "contains"],
		["=", "equals"],
		["!=", "≠"],
	],
	Select: [
		["=", "equals"],
		["!=", "≠"],
	],
	Number: [
		["=", "="],
		[">", ">"],
		["<", "<"],
		[">=", "≥"],
		["<=", "≤"],
	],
	Date: [
		["=", "on"],
		[">", "after"],
		["<", "before"],
		[">=", "on/after"],
		["<=", "on/before"],
	],
	Check: [["=", "is"]],
}

function fieldType(fieldname) {
	return props.fields.find((f) => f.fieldname === fieldname)?.fieldtype || "Data"
}

function category(fieldname) {
	const t = fieldType(fieldname)
	if (t === "Select") return "Select"
	if (t === "Check") return "Check"
	if (["Int", "Float", "Currency"].includes(t)) return "Number"
	if (t === "Date") return "Date"
	return "Data"
}

function operatorsFor(fieldname) {
	return OPERATORS[category(fieldname)]
}

function inputType(fieldname) {
	const c = category(fieldname)
	if (c === "Number") return "number"
	if (c === "Date") return "date"
	return "text"
}

function selectOptions(fieldname) {
	const opts = props.fields.find((f) => f.fieldname === fieldname)?.options || []
	return Array.isArray(opts) ? opts : String(opts).split("\n").filter(Boolean)
}

function complete() {
	return rows.value.filter((r) => r.field && r.operator && r.value !== "" && r.value != null)
}

// Explicit apply, like Desk: edits stay local until Apply Filters is pressed.
function applyFilters() {
	const filters = complete().map((r) => ({ field: r.field, operator: r.operator, value: r.value }))
	appliedCount.value = filters.length
	emit("update:modelValue", filters)
	open.value = false
}

function addRow() {
	const first = props.fields[0]
	rows.value.push({
		field: first.fieldname,
		operator: operatorsFor(first.fieldname)[0][0],
		value: "",
	})
}

function onFieldChange(i, fieldname) {
	rows.value[i].field = fieldname
	rows.value[i].operator = operatorsFor(fieldname)[0][0]
	rows.value[i].value = ""
}

function removeRow(i) {
	rows.value.splice(i, 1)
}

function clearAll() {
	rows.value = []
	appliedCount.value = 0
	emit("update:modelValue", [])
}
</script>
