<template>
	<div>
		<button
			type="button"
			class="relative rounded-md p-1.5 text-ink-gray-5 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-9"
			:title="__('Notifications')"
			@click="togglePanel"
		>
			<FeatherIcon name="bell" class="h-4 w-4" />
			<span
				v-if="unread"
				class="absolute -right-1 -top-1 flex h-[16px] min-w-[16px] items-center justify-center rounded-full px-1 text-[10px] font-bold leading-none text-white shadow"
				style="background:#ef4444"
			>{{ unread > 99 ? "99+" : unread }}</span>
		</button>

		<!-- Panel -->
		<Teleport to="body">
			<div v-if="open" class="fixed inset-0 z-[70]" @click.self="open = false">
				<div class="fixed left-4 top-14 flex max-h-[70vh] w-96 max-w-[92vw] flex-col rounded-lg border bg-surface-white shadow-xl">
					<div class="flex items-center gap-2 border-b px-3 py-2">
						<h3 class="text-sm font-semibold text-ink-gray-9">{{ __("Notifications") }}</h3>
						<span v-if="unread" class="rounded-full bg-surface-gray-3 px-1.5 text-xs text-ink-gray-6">{{ __("{0} new", [unread]) }}</span>
						<div class="flex-1" />
						<button v-if="unread" type="button" class="text-xs text-ink-blue-link hover:underline" @click="markAllRead">{{ __("Mark all read") }}</button>
						<button class="p-1 text-ink-gray-5 hover:text-ink-gray-8" @click="open = false">
							<FeatherIcon name="x" class="h-4 w-4" />
						</button>
					</div>
					<div class="flex-1 overflow-y-auto p-1.5">
						<button
							v-for="n in items"
							:key="n.name"
							type="button"
							class="flex w-full items-start gap-2 rounded-md p-2 text-left hover:bg-surface-gray-2"
							:class="n.read ? 'opacity-60' : ''"
							@click="openNotification(n)"
						>
							<span class="mt-1.5 h-2 w-2 shrink-0 rounded-full" :class="n.read ? 'bg-surface-gray-3' : 'bg-blue-500'" />
							<div class="min-w-0 flex-1">
								<div class="text-sm text-ink-gray-8 [&_b]:font-semibold" v-html="n.subject" />
								<div class="mt-0.5 text-xs text-ink-gray-4">
									{{ n.document_type ? `${n.document_type} · ` : "" }}{{ formatWhen(n.creation) }}
								</div>
							</div>
						</button>
						<p v-if="!items.length" class="py-8 text-center text-sm text-ink-gray-5">{{ __("No notifications.") }}</p>
					</div>
				</div>
			</div>
		</Teleport>
	</div>
</template>

<script setup>
// Copied from erpbio_general spa-shared rather than imported: this app is
// deliberately self-contained (clean-room MIT, installs without erpbio_general),
// so it must not take a build-time dependency on it. Keep in sync by hand.
// Two deviations from the original, both required here:
//   * it reads THIS app's api.tax notification endpoints, which wrap core's
//     Notification Log — the shared component's erpbio_general.api.sales_tools
//     calls would be a *runtime* dependency on that app being installed.
//   * `__` is injected: erpbio_general's apps get a global __ from frappe-ui's
//     translation plugin, while this app provides $translate.
import { inject, ref } from "vue"
import { useRouter } from "vue-router"
import { FeatherIcon, call } from "frappe-ui"

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const router = useRouter()

// Where a notification about a tax doc goes when clicked. Returning falsy skips
// navigation (the panel still marks it read) — which is what happens for the
// Sales Invoice / Payment Entry notifications this app has no page for.
const ROUTES = {
	"Coretax Faktur Export": (n) => n.document_name && { name: "ExportDetail", params: { name: n.document_name } },
	"Coretax Faktur Import": (n) => n.document_name && { name: "ImportDetail", params: { name: n.document_name } },
	"Bukti Potong": (n) => n.document_name && { name: "BuktiPotongDetail", params: { name: n.document_name } },
}

const open = ref(false)
const items = ref([])
const unread = ref(0)

async function load() {
	try {
		const d = await call("erpbio_indonesia_localization.api.tax.get_notifications", { limit: 20 })
		items.value = d.items || []
		unread.value = d.unread || 0
	} catch (e) {}
}
load()

function togglePanel() {
	open.value = !open.value
	if (open.value) load()
}

async function openNotification(n) {
	if (!n.read) {
		n.read = 1
		unread.value = Math.max(0, unread.value - 1)
		call("erpbio_indonesia_localization.api.tax.mark_notifications_read", {
			names: JSON.stringify([n.name]),
		}).catch(() => {})
	}
	const fn = ROUTES[n.document_type]
	const to = fn && fn(n)
	if (to) {
		open.value = false
		router.push(to)
	}
}

async function markAllRead() {
	try {
		await call("erpbio_indonesia_localization.api.tax.mark_notifications_read")
		items.value = items.value.map((n) => ({ ...n, read: 1 }))
		unread.value = 0
	} catch (e) {}
}

function formatWhen(v) {
	if (!v) return ""
	const d = dayjs(v)
	const mins = dayjs().diff(d, "minute")
	if (mins < 1) return __("just now")
	if (mins < 60) return __("{0}m ago", [mins])
	if (mins < 60 * 24) return __("{0}h ago", [Math.floor(mins / 60)])
	return d.format("D MMM YYYY")
}
</script>
