<template>
	<div class="flex h-screen bg-surface-gray-1">
		<!-- sidebar -->
		<aside class="flex w-56 shrink-0 flex-col border-r bg-surface-white">
			<div class="flex items-center gap-2 border-b px-4 py-3">
				<div class="flex h-7 w-7 items-center justify-center rounded-md bg-surface-gray-7 text-sm font-bold text-ink-white">T</div>
				<span class="text-sm font-semibold text-ink-gray-9">{{ __("ERPbio Tax") }}</span>
				<div class="ml-auto"><NotificationsBell /></div>
			</div>
			<nav class="flex-1 overflow-y-auto p-2">
				<template v-for="group in NAV" :key="group.label">
					<div class="mb-1 px-2 pt-2 text-[11px] font-medium uppercase text-ink-gray-4">{{ __(group.label) }}</div>
					<RouterLink v-for="item in group.items" :key="item.route" :to="{ name: item.route }"
						class="flex items-center gap-2.5 rounded px-2 py-1.5 text-sm"
						:class="isActive(item) ? 'bg-surface-gray-2 font-medium text-ink-gray-9' : 'text-ink-gray-6 hover:bg-surface-gray-1'">
						<FeatherIcon :name="item.icon" class="h-4 w-4" />
						{{ __(item.label) }}
					</RouterLink>
				</template>
			</nav>
			<SidebarUserFooter />
		</aside>

		<!-- content -->
		<main class="min-w-0 flex-1 overflow-y-auto">
			<slot />
		</main>

		<!-- Hover quick-info card for doc links; teleports itself to <body>. -->
		<DocPreviewHost />
	</div>
</template>

<script setup>
import { inject } from "vue"
import { RouterLink, useRoute } from "vue-router"
import DocPreviewHost from "@/components/DocPreviewHost.vue"
import NotificationsBell from "@/components/NotificationsBell.vue"
import SidebarUserFooter from "@/components/SidebarUserFooter.vue"

const __ = inject("$translate")
const route = useRoute()

const NAV = [
	{
		label: "e-Faktur",
		items: [
			{ label: "Exports", route: "ExportList", icon: "upload", match: "/exports" },
			{ label: "Imports", route: "ImportList", icon: "download", match: "/imports" },
		],
	},
	{
		label: "PPN",
		items: [
			{ label: "PPN Keluaran", route: "PpnKeluaran", icon: "bar-chart-2", match: "/reports/ppn-keluaran" },
			{ label: "PPN Masukan", route: "PpnMasukan", icon: "bar-chart", match: "/reports/ppn-masukan" },
			{ label: "SPT Masa", route: "SptMasa", icon: "clipboard", match: "/reports/spt-masa" },
		],
	},
	{
		label: "Withholding",
		items: [{ label: "Bukti Potong", route: "BuktiPotong", icon: "file-minus", match: "/bukti-potong" }],
	},
	{
		label: "Setup",
		items: [
			{ label: "Customers", route: "CustomerList", icon: "users", match: "/customers" },
			{ label: "Settings", route: "Settings", icon: "settings", match: "/settings" },
		],
	},
]

function isActive(item) {
	return route.path.startsWith(item.match)
}
</script>
