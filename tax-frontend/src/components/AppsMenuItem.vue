<!-- Still forked from erpbio_general's spa-shared rather than imported through
     the @shared alias, for a RUNTIME reason: the shared version resolves the app
     list through erpbio_general.api.home, while this copy reads this app's own
     data/launcherApps.js, which returns an empty list (and hides the menu) when
     erpbio_general isn't installed. Otherwise verbatim — keep in sync by hand. -->
<template>
	<!-- Account-menu "Apps" row that opens a flyout of the user's permitted apps
	     (à la the Frappe CRM app switcher). Rendered as a Dropdown item.component,
	     which only receives `active`, so it reads the shared launcherApps resource
	     itself rather than via props. -->
	<div class="relative" @mouseenter="show" @mouseleave="scheduleHide">
		<button
			type="button"
			class="group flex h-7 w-full items-center rounded px-2 text-base"
			:class="active || open ? 'bg-surface-gray-3' : ''"
			@click="open = !open"
		>
			<FeatherIcon name="grid" class="mr-2 h-4 w-4 flex-shrink-0 text-ink-gray-6" />
			<span class="flex-1 whitespace-nowrap text-left text-ink-gray-7">{{ __("Apps") }}</span>
			<FeatherIcon name="chevron-right" class="h-4 w-4 flex-shrink-0 text-ink-gray-4" />
		</button>

		<div
			v-if="open"
			class="absolute left-full top-0 z-20 ml-1 min-w-56 rounded-lg bg-surface-modal p-1.5 shadow-2xl ring-1 ring-black ring-opacity-5"
			@mouseenter="show"
			@mouseleave="scheduleHide"
		>
			<a
				v-for="a in apps"
				:key="a.key"
				:href="a.route"
				class="flex items-center gap-2.5 rounded-md px-2 py-1.5 transition-colors hover:bg-surface-gray-3"
				:class="isCurrent(a) ? 'bg-surface-gray-2' : ''"
				@click.prevent="go(a)"
			>
				<span class="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg" :style="{ backgroundColor: color(a.key) }">
					<FeatherIcon :name="a.icon" class="h-4 w-4 text-white" />
				</span>
				<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">{{ a.label }}</span>
				<FeatherIcon v-if="isCurrent(a)" name="check" class="h-3.5 w-3.5 shrink-0 text-ink-gray-5" />
			</a>
			<div v-if="!apps.length" class="px-2 py-3 text-center text-xs text-ink-gray-4">{{ __("Loading…") }}</div>
		</div>
	</div>
</template>

<script setup>
import { computed, inject, onBeforeUnmount, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { launcherApps, ensureLauncherAppsLoaded } from "@/data/launcherApps"

defineProps({ active: { type: Boolean, default: false } })
const __ = inject("$translate", (s) => s)

ensureLauncherAppsLoaded()
const apps = computed(() => launcherApps.data || [])

const open = ref(false)
let timer = null
function show() {
	clearTimeout(timer)
	open.value = true
}
function scheduleHide() {
	// small grace period so moving from the row into the flyout doesn't close it
	clearTimeout(timer)
	timer = setTimeout(() => (open.value = false), 140)
}
onBeforeUnmount(() => clearTimeout(timer))

// A coloured tile per app (matches the Home dashboard accents), so the flyout
// reads like the app-switcher example rather than a plain list.
const COLORS = {
	home: "#475569",
	sales: "#2563eb",
	purchasing: "#d97706",
	inventory: "#0891b2",
	accounting: "#16a34a",
	tax: "#dc2626",
	hr: "#7c3aed",
}
function color(key) {
	return COLORS[key] || "#475569"
}
function isCurrent(a) {
	return window.location.pathname.startsWith(a.route)
}
function go(a) {
	window.location.href = a.route
}
</script>
