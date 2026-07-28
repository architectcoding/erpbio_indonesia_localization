<!-- Copied from erpbio_general spa-shared rather than imported: this app is
     deliberately self-contained (clean-room MIT, installs without erpbio_general).
     Verbatim apart from this note — it depends on nothing but frappe-ui. -->
<template>
	<Dialog :modelValue="modelValue" :options="{ title: __('About'), size: 'sm' }"
		@update:modelValue="(v) => emit('update:modelValue', v)">
		<template #body-content>
			<div class="flex flex-col items-center gap-2 py-2 text-center">
				<img v-if="branding?.logo" :src="branding.logo" class="h-12 w-12 rounded-lg object-contain" />
				<div v-else class="flex h-12 w-12 items-center justify-center rounded-lg bg-surface-gray-3 text-sm font-semibold text-ink-gray-7">EB</div>
				<div class="text-base font-semibold text-ink-gray-9">{{ branding?.title || "ERPbio" }}</div>
				<div class="text-sm text-ink-gray-5">{{ __("Version {0}", [appVersion || "—"]) }}</div>
				<div class="mt-1 text-xs text-ink-gray-4">{{ __("Powered by ERPbio · Frappe / ERPNext") }}</div>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
import { inject } from "vue"
import { Dialog } from "frappe-ui"

defineProps({ modelValue: { type: Boolean, default: false } })
const emit = defineEmits(["update:modelValue"])
const __ = inject("$translate", (s) => s)
const branding = inject("$branding", null)
const appVersion = window.frappe?.boot?.app_version || ""
</script>
