<template>
	<div class="flex h-screen bg-surface-gray-1">
		<!-- sidebar -->
		<aside class="flex w-56 shrink-0 flex-col border-r bg-surface-white">
			<div class="flex items-center gap-2 border-b px-4 py-3">
				<div class="flex h-7 w-7 items-center justify-center rounded-md bg-surface-gray-7 text-sm font-bold text-ink-white">T</div>
				<span class="text-sm font-semibold text-ink-gray-9">{{ __("ERPbio Tax") }}</span>
			</div>
			<nav class="flex-1 overflow-y-auto p-2">
				<div class="mb-1 px-2 pt-2 text-[11px] font-medium uppercase text-ink-gray-4">{{ __("e-Faktur") }}</div>
				<RouterLink v-for="item in NAV" :key="item.route" :to="{ name: item.route }"
					class="flex items-center gap-2.5 rounded px-2 py-1.5 text-sm"
					:class="isActive(item) ? 'bg-surface-gray-2 font-medium text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-1'">
					<FeatherIcon :name="item.icon" class="h-4 w-4" />
					{{ __(item.label) }}
				</RouterLink>
			</nav>
			<div class="border-t p-2">
				<button class="flex w-full items-center gap-2.5 rounded px-2 py-1.5 text-sm text-ink-gray-6 hover:bg-surface-gray-1" @click="session.logout()">
					<FeatherIcon name="log-out" class="h-4 w-4" />
					{{ __("Log Out") }} <span class="ml-auto truncate text-[11px] text-ink-gray-4">{{ session.user }}</span>
				</button>
			</div>
		</aside>

		<!-- content -->
		<main class="min-w-0 flex-1 overflow-y-auto">
			<slot />
		</main>
	</div>
</template>

<script setup>
import { inject } from "vue"
import { RouterLink, useRoute } from "vue-router"

const session = inject("$session")
const __ = inject("$translate")
const route = useRoute()

const NAV = [
	{ label: "Exports", route: "ExportList", icon: "upload", match: "/exports" },
	{ label: "Imports", route: "ImportList", icon: "download", match: "/imports" },
	{ label: "PPN Keluaran", route: "PpnKeluaran", icon: "bar-chart-2", match: "/reports/ppn-keluaran" },
	{ label: "Settings", route: "Settings", icon: "settings", match: "/settings" },
]

function isActive(item) {
	return route.path.startsWith(item.match)
}
</script>
