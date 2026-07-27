<!-- Copied from erpbio_general spa-shared, not imported: this app must build and
     install without erpbio_general present. Backend-agnostic (it calls whatever
     `method` you pass), so nothing here reaches into that app. Keep in sync by hand. -->
<template>
	<input
		v-if="fieldtype === 'Data'"
		type="text"
		class="h-8 rounded-lg border-0 bg-surface-gray-2 px-3 text-sm text-ink-gray-8 placeholder-ink-gray-4 focus:bg-surface-gray-1 focus:ring-1 focus:ring-gray-300"
		:placeholder="label"
		:value="modelValue"
		@input="(e) => debouncedEmit(e.target.value)"
	/>
	<select
		v-else
		class="h-8 rounded-lg border-0 bg-surface-gray-2 px-2 text-sm text-ink-gray-8 focus:bg-surface-gray-1 focus:ring-1 focus:ring-gray-300"
		:class="modelValue ? 'text-ink-gray-8' : 'text-ink-gray-4'"
		:value="modelValue"
		@change="(e) => emit('update:modelValue', e.target.value)"
	>
		<option value="">{{ label }}</option>
		<option v-for="o in resolvedOptions" :key="optVal(o)" :value="optVal(o)">{{ optLabel(o) }}</option>
	</select>
</template>

<script setup>
import { computed } from "vue"
import { createListResource, debounce } from "frappe-ui"

const props = defineProps({
	label: { type: String, required: true },
	fieldtype: { type: String, default: "Data" },
	options: { type: Array, default: null },
	doctype: { type: String, default: "" },
	modelValue: { type: String, default: "" },
})

const emit = defineEmits(["update:modelValue"])

const debouncedEmit = debounce((v) => emit("update:modelValue", v), 400)

// Link-type quick filters load their options from the doctype's records.
const resource =
	props.fieldtype === "Link" && props.doctype
		? createListResource({
				doctype: props.doctype,
				fields: ["name"],
				orderBy: "name asc",
				pageLength: 500,
				auto: true,
		  })
		: null

const resolvedOptions = computed(() => {
	if (props.options) return props.options
	return (resource?.data || []).map((r) => r.name)
})

// Options may be plain strings or { value, label } objects.
const optVal = (o) => (o && typeof o === "object" ? o.value : o)
const optLabel = (o) => (o && typeof o === "object" ? o.label : o)
</script>
