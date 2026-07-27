<!-- Copied from erpbio_general spa-shared, not imported: this app must build and
     install without erpbio_general present. Its backend module is a prop/config,
     so it points at this app's own api. Keep in sync by hand. -->
<template>
	<Teleport to="body">
		<Transition
			enter-active-class="transition duration-150 ease-out"
			enter-from-class="opacity-0 translate-y-1"
			enter-to-class="opacity-100 translate-y-0"
			leave-active-class="transition duration-100 ease-in"
			leave-from-class="opacity-100 translate-y-0"
			leave-to-class="opacity-0 translate-y-1"
		>
		<div
			v-if="previewState.visible"
			class="fixed z-[60] w-72 rounded-lg border border-outline-gray-2 bg-surface-white p-3 shadow-xl"
			:style="cardStyle"
			@mouseenter="keepPreview"
			@mouseleave="hidePreview"
		>
			<div v-if="previewState.loading" class="flex justify-center py-4">
				<LoadingIndicator class="h-5 w-5 text-ink-gray-4" />
			</div>
			<div v-else-if="previewState.data" class="flex flex-col gap-2">
				<div class="flex items-center gap-2">
					<img
						v-if="previewState.data.image"
						:src="previewState.data.image"
						class="h-9 w-9 shrink-0 rounded-md border border-outline-gray-2 bg-white object-contain"
					/>
					<div class="min-w-0">
						<div class="truncate text-sm font-semibold text-ink-gray-9">{{ previewState.data.title }}</div>
						<div v-if="previewState.data.subtitle" class="truncate text-xs text-ink-gray-5">
							{{ previewState.data.subtitle }}
						</div>
					</div>
				</div>
				<dl v-if="previewState.data.fields?.length" class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
					<template v-for="f in previewState.data.fields" :key="f.label">
						<dt class="text-ink-gray-5">{{ f.label }}</dt>
						<dd class="truncate text-ink-gray-8">{{ f.value }}</dd>
					</template>
				</dl>

				<!-- Linked contacts (Customer preview) -->
				<div v-if="previewState.data.contacts?.length" class="border-t border-outline-gray-2 pt-2">
					<div class="mb-1 text-[10px] font-medium uppercase tracking-wide text-ink-gray-4">{{ __("Contacts") }}</div>
					<div class="flex flex-col gap-0.5">
						<div v-for="c in previewState.data.contacts" :key="c.name" class="flex items-center justify-between gap-2 text-xs">
							<span class="truncate text-ink-gray-8">{{ c.name }}</span>
							<span v-if="c.detail" class="shrink-0 text-ink-gray-5">{{ c.detail }}</span>
						</div>
					</div>
				</div>

				<!-- Linked addresses (Customer preview) -->
				<div v-if="previewState.data.addresses?.length" class="border-t border-outline-gray-2 pt-2">
					<div class="mb-1 text-[10px] font-medium uppercase tracking-wide text-ink-gray-4">{{ __("Addresses") }}</div>
					<div class="flex flex-col gap-1">
						<div v-for="a in previewState.data.addresses" :key="a.name" class="text-xs">
							<div class="truncate text-ink-gray-8">{{ a.name }}</div>
							<div v-if="a.detail" class="truncate text-ink-gray-5">{{ a.detail }}</div>
						</div>
					</div>
				</div>
			</div>
			<div v-else class="py-2 text-center text-xs text-ink-gray-5">{{ __("No preview available") }}</div>
		</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { computed, inject } from "vue"
import { LoadingIndicator } from "frappe-ui"
import { previewState, keepPreview, hidePreview } from "@/composables/docPreview"
const __ = inject("$translate")

const CARD_W = 288 // w-72
const cardStyle = computed(() => {
	let x = previewState.x
	let y = previewState.y
	if (typeof window !== "undefined") {
		if (x + CARD_W > window.innerWidth - 8) x = window.innerWidth - CARD_W - 8
		if (x < 8) x = 8
		// Flip above the trigger if it would spill past the bottom.
		if (y > window.innerHeight - 160) y = Math.max(8, y - 200)
	}
	return { left: x + "px", top: y + "px" }
})
</script>
