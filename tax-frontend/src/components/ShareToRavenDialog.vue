<template>
	<Dialog v-model="open" :options="{ title: __('Send in chat'), size: 'sm' }">
		<template #body-content>
			<div class="flex flex-col gap-3 py-1">
				<div class="rounded-md border px-3 py-2">
					<div class="truncate text-sm font-medium text-ink-gray-9">{{ label || doctype }}</div>
					<div class="truncate text-xs text-ink-gray-5">{{ name }}</div>
				</div>

				<div v-if="!ravenAvailable" class="text-sm text-ink-gray-6">
					{{ __("Chat is not enabled for your account.") }}
					<span class="block text-xs text-ink-gray-5">
						{{ __("Ask an administrator to add you as a Raven User.") }}
					</span>
				</div>

				<template v-else>
					<div>
						<label class="mb-1 block text-xs text-ink-gray-5">{{ __("Send to") }}</label>
						<input
							v-model="filter"
							type="text"
							class="form-input h-8 w-full text-sm"
							:placeholder="__('Search people and channels')"
						/>
					</div>

					<div class="max-h-56 overflow-y-auto rounded-md border">
						<button
							v-for="r in results"
							:key="r.key"
							type="button"
							class="flex w-full items-center gap-2 px-3 py-2 text-left text-sm"
							:class="selectedKey === r.key ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-7 hover:bg-surface-gray-2'"
							@click="selectedKey = r.key"
						>
							<FeatherIcon :name="r.isChannel ? 'hash' : 'user'" class="h-3.5 w-3.5 shrink-0 text-ink-gray-5" />
							<span class="min-w-0 flex-1 truncate">{{ r.label }}</span>
							<span v-if="r.isNewDm" class="shrink-0 text-[10px] uppercase tracking-wide text-ink-gray-4">{{ __("New") }}</span>
							<FeatherIcon v-if="selectedKey === r.key" name="check" class="h-4 w-4 shrink-0 text-ink-gray-7" />
						</button>
						<p v-if="!loading && !results.length" class="px-3 py-6 text-center text-sm text-ink-gray-5">
							{{ __("No matches.") }}
						</p>
					</div>

					<div>
						<label class="mb-1 block text-xs text-ink-gray-5">{{ __("Note (optional)") }}</label>
						<textarea v-model="note" rows="2" class="form-textarea w-full resize-none text-sm" />
					</div>

					<div v-if="error" class="text-xs text-ink-red-3">{{ error }}</div>
				</template>
			</div>
		</template>
		<template #actions>
			<div class="flex justify-end gap-2">
				<Button variant="subtle" @click="open = false">{{ __("Cancel") }}</Button>
				<Button variant="solid" :loading="sending" :disabled="!selected || !ravenAvailable" @click="send">
					{{ __("Send") }}
				</Button>
			</div>
		</template>
	</Dialog>
</template>

<script setup>
// "Share → Send in chat" on any document. Mirrors what Raven's own Desk timeline
// button does (raven/public/js/timeline_button.js): insert a Raven Message with
// link_doctype/link_document set, and let Raven render the preview card.
//
// The recipient sees a card, not a URL, and clicking it lands them in the right
// SPA because erpbio registers raven_document_link_override (see
// erpbio_general/raven_links.py).
import { computed, inject, ref, watch } from "vue"
import { Dialog, Button, FeatherIcon, call } from "frappe-ui"
import { ravenAvailable, refreshUnread } from "@/composables/useChat"

const props = defineProps({
	doctype: { type: String, required: true },
	name: { type: String, required: true },
	label: { type: String, default: "" },
})
const emit = defineEmits(["sent"])

const __ = inject("$translate")

// defineModel, matching CompanyDialog and the other shared dialogs. A hand-rolled
// computed({get, set}) over a modelValue prop looks equivalent but does not close
// the dialog: frappe-ui's Dialog tracks its own open state internally, so writing
// through the setter never reached it and the dialog stayed up after a successful
// send.
const open = defineModel({ type: Boolean, default: false })

const channels = ref([])
const users = ref([])
const loading = ref(false)
const filter = ref("")
const selectedKey = ref("")
const note = ref("")
const sending = ref(false)
const error = ref("")

const currentUser = window.frappe?.session?.user || ""

// Existing channels and DMs, plus — once they type — anyone they have no thread
// with yet. "Send this CO to whoever is responsible" usually means someone you
// have never messaged, so a list of existing conversations alone is the wrong
// list; picking such a person creates the DM as part of sending.
const results = computed(() => {
	const q = filter.value.trim().toLowerCase()

	const existing = channels.value
		.filter((c) => !q || channelLabel(c).toLowerCase().includes(q))
		.map((c) => ({
			key: `c:${c.name}`,
			channelId: c.name,
			label: channelLabel(c),
			isChannel: !c.is_direct_message,
			isNewDm: false,
		}))

	if (!q) return existing

	const dmPeers = new Set(channels.value.filter((c) => c.is_direct_message).map((c) => c.peer_user_id))
	const people = users.value
		.filter((u) => u.enabled !== 0 && u.name !== currentUser && !dmPeers.has(u.name))
		.filter((u) => (u.full_name || u.name || "").toLowerCase().includes(q))
		.map((u) => ({
			key: `u:${u.name}`,
			userId: u.name,
			label: u.full_name || u.name,
			isChannel: false,
			isNewDm: true,
		}))

	return [...existing, ...people]
})

const selected = computed(() => results.value.find((r) => r.key === selectedKey.value) || null)

function channelLabel(c) {
	return c.is_direct_message ? c.full_name || c.peer_user_id || c.channel_name : c.channel_name
}

async function load() {
	loading.value = true
	error.value = ""
	try {
		const [chans, people] = await Promise.all([
			call("raven.api.raven_channel.get_channels", { hide_archived: true }),
			call("raven.api.raven_users.get_list").catch(() => []),
		])
		channels.value = chans || []
		users.value = people || []
		ravenAvailable.value = true
	} catch (e) {
		channels.value = []
		users.value = []
		ravenAvailable.value = false
	}
	loading.value = false
}

watch(open, (v) => {
	if (!v) return
	selectedKey.value = ""
	note.value = ""
	filter.value = ""
	error.value = ""
	load()
})

function escapeHtml(s) {
	return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

async function send() {
	if (!selected.value || sending.value) return
	sending.value = true
	error.value = ""
	const plain = note.value.trim()
	try {
		// A person with no thread yet needs one before a message can be addressed
		// to it. create_direct_message_channel is idempotent, so a thread created
		// meanwhile is returned rather than duplicated.
		const channelId = selected.value.isNewDm
			? await call("raven.api.raven_channel.create_direct_message_channel", { user_id: selected.value.userId })
			: selected.value.channelId
		// send_message() has no link_doctype/link_document parameters, so the
		// document link has to go on a directly-inserted doc — the same route the
		// Desk timeline button takes. Raven fills `content` from the link when the
		// note is empty, so a bare share still reads sensibly in the list.
		await call("frappe.client.insert", {
			doc: {
				doctype: "Raven Message",
				channel_id: channelId,
				message_type: "Text",
				text: plain ? `<p>${escapeHtml(plain).replace(/\n/g, "<br>")}</p>` : "",
				json: plain
					? { type: "doc", content: [{ type: "paragraph", content: [{ type: "text", text: plain }] }] }
					: null,
				link_doctype: props.doctype,
				link_document: props.name,
			},
		})
		refreshUnread()
		emit("sent")
		open.value = false
	} catch (e) {
		error.value = e?.messages?.[0] || e?.message || __("Could not send.")
	}
	sending.value = false
}
</script>
