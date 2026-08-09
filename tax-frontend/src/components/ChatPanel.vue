<template>
	<Teleport to="body">
		<!-- Incoming-message toasts. Top-right, NOT bottom-right: the chat window
		     docks bottom-right by default and these sit at a higher z-index, so
		     down there a notification would land squarely on top of the window it
		     is telling you to look at. Clicking one opens that conversation. -->
		<div class="pointer-events-none fixed right-4 top-4 z-[90] flex flex-col items-end gap-2">
			<TransitionGroup
				enter-active-class="transition duration-200 ease-out"
				enter-from-class="translate-x-4 opacity-0"
				leave-active-class="transition duration-150 ease-in"
				leave-to-class="translate-x-4 opacity-0"
			>
				<button
					v-for="t in toasts"
					:key="t.id"
					type="button"
					class="pointer-events-auto flex w-[19rem] max-w-[calc(100vw-2rem)] items-start gap-2 rounded-lg border bg-surface-white p-2.5 text-left shadow-xl hover:bg-surface-gray-2"
					@click="openFromToast(t)"
				>
					<img v-if="toastImage(t)" :src="toastImage(t)" alt="" class="h-7 w-7 shrink-0 rounded-full object-cover" />
					<span
						v-else
						class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-[11px] font-medium text-ink-gray-7"
					>{{ initialsOf(t.title) }}</span>
					<span class="min-w-0 flex-1">
						<span class="block truncate text-xs font-semibold text-ink-gray-9">{{ t.title }}</span>
						<span class="line-clamp-2 block text-xs text-ink-gray-6">{{ t.body }}</span>
					</span>
					<span
						class="shrink-0 rounded p-0.5 text-ink-gray-5 hover:text-ink-gray-8"
						@click.stop="dismissToast(t.id)"
					>
						<FeatherIcon name="x" class="h-3.5 w-3.5" />
					</span>
				</button>
			</TransitionGroup>
		</div>
	</Teleport>

	<Teleport to="body">
		<!-- Odoo-shaped: a floating window docked bottom-right, not a full-height
		     drawer. It deliberately does not cover the page — you keep working with
		     the conversation open beside you — and it collapses to its header bar
		     instead of closing, so a thread stays live while you go elsewhere. -->
		<div
			v-if="chatOpen"
			ref="windowEl"
			class="fixed z-[80] flex flex-col overflow-hidden border bg-surface-white shadow-2xl"
			:class="[
				// Phone: a full-width sheet pinned to the bottom. A 22rem window
				// docked to the right runs off a 380-430px viewport, and a draggable
				// window is meaningless without a pointer.
				'inset-x-0 bottom-0 rounded-t-lg border-b-0',
				chatMinimized ? '' : 'h-[85vh]',
				// sm and up: the floating window, docked bottom-right until dragged.
				'sm:inset-x-auto sm:w-[22rem] sm:max-w-[calc(100vw-2rem)]',
				chatMinimized ? '' : 'sm:h-[32rem] sm:max-h-[calc(100vh-4rem)]',
				chatPos && !isMobile ? 'sm:rounded-lg sm:border-b' : 'sm:bottom-0 sm:right-4 sm:rounded-t-lg sm:border-b-0',
			]"
			:style="windowStyle"
		>
			<!-- Header. Doubles as the drag handle — grab anywhere that isn't a
			     button, as Odoo does. -->
			<div
				class="flex shrink-0 select-none items-center gap-2 border-b bg-surface-gray-2 px-3 py-2"
				:class="chatMinimized ? 'cursor-pointer' : 'cursor-move'"
				:title="chatPos ? __('Drag to move · double-click to dock bottom-right') : ''"
				@pointerdown="onHeaderPointerDown"
				@click="onHeaderClick"
				@dblclick="resetPosition"
			>
				<button
					v-if="activeChannel && !chatMinimized"
					type="button"
					class="rounded p-0.5 text-ink-gray-6 hover:bg-surface-gray-3 hover:text-ink-gray-9"
					:title="__('Back to conversations')"
					@click.stop="closeConversation"
				>
					<FeatherIcon name="arrow-left" class="h-4 w-4" />
				</button>
				<template v-if="activeChannel">
					<img v-if="activeChannelImage" :src="activeChannelImage" :alt="activeChannelLabel" class="h-6 w-6 shrink-0 rounded-full object-cover" />
					<span
						v-else
						class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-gray-4 text-[10px] font-semibold text-ink-gray-7"
					>{{ activeChannelInitials }}</span>
				</template>
				<h3 class="min-w-0 flex-1 truncate text-sm font-semibold text-ink-gray-9">
					{{ activeChannel ? activeChannelLabel : __("Chat") }}
				</h3>
				<span
					v-if="chatMinimized && unreadTotal"
					class="flex h-[16px] min-w-[16px] items-center justify-center rounded-full px-1 text-[10px] font-bold leading-none text-white"
					style="background:#ef4444"
				>{{ unreadTotal > 99 ? "99+" : unreadTotal }}</span>
				<a
					v-if="!chatMinimized"
					:href="activeChannel ? `/raven/channel/${activeChannel}` : '/raven'"
					target="_blank"
					rel="noopener"
					class="rounded p-0.5 text-ink-gray-6 hover:bg-surface-gray-3 hover:text-ink-gray-9"
					:title="__('Open in Raven')"
					@click.stop
				>
					<FeatherIcon name="external-link" class="h-4 w-4" />
				</a>
				<button
					type="button"
					class="rounded p-0.5 text-ink-gray-6 hover:bg-surface-gray-3 hover:text-ink-gray-9"
					:title="chatMinimized ? __('Expand') : __('Minimise')"
					@click.stop="toggleMinimized"
				>
					<FeatherIcon :name="chatMinimized ? 'chevron-up' : 'minus'" class="h-4 w-4" />
				</button>
				<button
					type="button"
					class="rounded p-0.5 text-ink-gray-6 hover:bg-surface-gray-3 hover:text-ink-gray-9"
					:title="__('Close')"
					@click.stop="closeChat"
				>
					<FeatherIcon name="x" class="h-4 w-4" />
				</button>
			</div>

			<template v-if="!chatMinimized">
				<!-- No Raven User record: the APIs return a permission error rather
				     than empty data, so say why instead of showing a dead window. -->
				<div v-if="!ravenAvailable" class="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
					<FeatherIcon name="message-circle" class="h-8 w-8 text-ink-gray-4" />
					<p class="text-sm text-ink-gray-7">{{ __("Chat is not enabled for your account.") }}</p>
					<p class="text-xs text-ink-gray-5">{{ __("Ask an administrator to add you as a Raven User.") }}</p>
				</div>

				<!-- Conversation list -->
				<div v-else-if="!activeChannel" class="flex min-h-0 flex-1 flex-col">
					<div class="shrink-0 border-b px-2 py-1.5">
						<input v-model="channelFilter" type="text" class="form-input h-7 w-full text-sm" :placeholder="__('Search people, groups and conversations')" />
					</div>
					<div class="min-h-0 flex-1 overflow-y-auto p-1">
						<button
							v-for="r in searchResults"
							:key="r.key"
							type="button"
							class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-gray-2 disabled:opacity-50"
							:disabled="startingDm === r.key"
							@click="pickResult(r)"
						>
							<img v-if="r.image" :src="r.image" :alt="r.label" class="h-7 w-7 shrink-0 rounded-full object-cover" />
							<span
								v-else
								class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-[11px] font-medium text-ink-gray-7"
							>{{ r.initials }}</span>
							<span class="min-w-0 flex-1 truncate text-sm text-ink-gray-8">{{ r.label }}</span>
							<!-- Somebody with no thread yet: say so, so it is obvious the
							     click starts one rather than opening history. -->
							<span v-if="r.isNewDm" class="shrink-0 text-[10px] uppercase tracking-wide text-ink-gray-4">
								{{ startingDm === r.key ? __("Starting…") : __("New") }}
							</span>
							<span
								v-else-if="unreadByChannel[r.channelId]"
								class="flex h-[16px] min-w-[16px] items-center justify-center rounded-full px-1 text-[10px] font-bold leading-none text-white"
								style="background:#ef4444"
							>{{ unreadByChannel[r.channelId] > 99 ? "99+" : unreadByChannel[r.channelId] }}</span>
						</button>
						<p v-if="!channelsLoading && !searchResults.length" class="py-8 text-center text-sm text-ink-gray-5">
							{{ channelFilter ? __("No matches.") : __("No conversations yet.") }}
						</p>
					</div>
				</div>

				<!-- Conversation -->
				<div v-else class="flex min-h-0 flex-1 flex-col">
					<div ref="scroller" class="min-h-0 flex-1 overflow-y-auto px-3 py-2">
						<button v-if="hasOlder" type="button" class="mx-auto mb-2 block text-xs text-ink-blue-link hover:underline" @click="loadOlder">
							{{ __("Load earlier messages") }}
						</button>

						<template v-for="row in rows" :key="row.key">
							<!-- Date divider: rule / label / rule, as Odoo separates days -->
							<div v-if="row.type === 'date'" class="my-2 flex items-center gap-2">
								<span class="h-px flex-1 bg-outline-gray-2" />
								<span class="text-[11px] text-ink-gray-4">{{ row.label }}</span>
								<span class="h-px flex-1 bg-outline-gray-2" />
							</div>

							<!-- Thread replies sit indented under their parent, with a rule
							     down the left so a bot answer reads as a reply to the
							     question above it rather than a new message. -->
							<div
								v-else
								class="flex gap-2"
								:class="[
									row.own ? 'flex-row-reverse' : '',
									row.head ? 'mt-2' : 'mt-0.5',
									row.indent ? 'ml-3 border-l pl-2' : '',
								]"
							>
								<!-- Avatar only on the first message of a run, so a burst
								     from one person reads as one block. -->
								<span v-if="!row.own" class="h-6 w-6 shrink-0" :class="row.head ? '' : 'invisible'">
									<img
										v-if="row.image"
										:src="row.image"
										:alt="row.sender"
										class="h-6 w-6 rounded-full object-cover"
									/>
									<span
										v-else
										class="flex h-6 w-6 items-center justify-center rounded-full bg-surface-gray-3 text-[10px] font-semibold text-ink-gray-7"
									>{{ initialsOf(row.sender) }}</span>
								</span>
								<div class="flex min-w-0 max-w-[85%] flex-col" :class="row.own ? 'items-end' : 'items-start'">
									<div v-if="row.head" class="mb-0.5 flex items-baseline gap-1.5 text-[11px]">
										<span v-if="!row.own" class="font-medium text-ink-gray-7">{{ row.sender }}</span>
										<span class="text-ink-gray-4">{{ row.time }}</span>
									</div>
									<div
										v-if="row.body"
										class="whitespace-pre-wrap break-words rounded-lg px-2.5 py-1.5 text-sm"
										:class="row.own ? 'bg-surface-blue-2 text-ink-gray-9' : 'bg-surface-gray-2 text-ink-gray-8'"
									>{{ row.body }}</div>

									<a v-if="row.m.file" :href="row.m.file" target="_blank" rel="noopener"
										class="mt-1 inline-flex items-center gap-1 text-xs text-ink-blue-link hover:underline">
										<FeatherIcon name="paperclip" class="h-3 w-3" />{{ fileName(row.m.file) }}
									</a>

									<!-- Shared document card. Routes into the owning SPA via
									     erpbio's raven_document_link_override. -->
									<button
										v-if="row.m.link_doctype && row.m.link_document"
										type="button"
										class="mt-1 flex w-full items-start gap-2 rounded-md border bg-surface-white p-2 text-left hover:bg-surface-gray-2"
										@click="openLinkedDocument(row.m)"
									>
										<FeatherIcon name="file-text" class="mt-0.5 h-4 w-4 shrink-0 text-ink-gray-5" />
										<span class="min-w-0">
											<span class="block truncate text-xs font-medium text-ink-gray-9">{{ previewTitle(row.m) }}</span>
											<span class="block truncate text-[11px] text-ink-gray-5">{{ row.m.link_doctype }}</span>
										</span>
									</button>
								</div>
							</div>
						</template>

						<p v-if="!messagesLoading && !rows.length" class="py-8 text-center text-sm text-ink-gray-5">
							{{ __("No messages yet.") }}
						</p>
					</div>

					<!-- Composer -->
					<div class="relative shrink-0 border-t p-2">
						<div v-if="mentionOpen && mentionMatches.length"
							class="absolute bottom-full left-2 right-2 mb-1 max-h-44 overflow-y-auto rounded-md border bg-surface-white shadow-lg">
							<button v-for="(u, i) in mentionMatches" :key="u.name" type="button"
								class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm"
								:class="i === mentionIndex ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-7 hover:bg-surface-gray-2'"
								@click="applyMention(u)">
								<span class="truncate">{{ u.full_name || u.name }}</span>
							</button>
						</div>

						<div v-if="attachment" class="mb-1 flex items-center gap-2 rounded bg-surface-gray-2 px-2 py-1 text-xs text-ink-gray-7">
							<FeatherIcon name="paperclip" class="h-3 w-3 shrink-0" />
							<span class="min-w-0 flex-1 truncate">{{ attachment.name }}</span>
							<button type="button" class="text-ink-gray-5 hover:text-ink-gray-9" @click="attachment = null">
								<FeatherIcon name="x" class="h-3 w-3" />
							</button>
						</div>

						<div v-if="sendError" class="mb-1 text-xs text-ink-red-3">{{ sendError }}</div>

						<!-- One rounded row: attach on the left, send on the right, as Odoo -->
						<div class="flex items-end gap-1 rounded-full border bg-surface-white py-1 pl-1 pr-1">
							<button type="button"
								class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-gray-6 hover:bg-surface-gray-2"
								:title="__('Attach file')" @click="$refs.fileInput.click()">
								<FeatherIcon name="plus-circle" class="h-4 w-4" />
							</button>
							<input ref="fileInput" type="file" class="hidden" @change="onFilePicked" />
							<textarea ref="input" v-model="draft" rows="1"
								class="max-h-24 min-h-[1.75rem] flex-1 resize-none border-0 bg-transparent px-1 py-1 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:outline-none focus:ring-0"
								:placeholder="composerPlaceholder" @input="onDraftInput" @keydown="onKeydown" />
							<button type="button"
								class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-ink-gray-6 hover:bg-surface-gray-2 disabled:opacity-40"
								:disabled="sending || (!draft.trim() && !attachment)" :title="__('Send')" @click="send">
								<FeatherIcon :name="sending ? 'loader' : 'send'" class="h-4 w-4" :class="sending ? 'animate-spin' : ''" />
							</button>
						</div>
					</div>
				</div>
			</template>
		</div>
	</Teleport>
</template>

<script setup>
// The in-app chat window. Backed entirely by Raven's existing REST + socketio —
// erpbio adds no chat doctypes. Deliberately a subset of Raven's own UI:
// conversations, history, sending, files and mentions. Threads, reactions,
// polls and calls stay in Raven proper, reachable via the header link.
import { computed, inject, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import { useRouter } from "vue-router"
import { FeatherIcon, call } from "frappe-ui"
import {
	chatOpen,
	chatMinimized,
	chatPos,
	setChatPos,
	closeChat,
	toggleMinimized,
	activeChannel,
	unreadByChannel,
	unreadTotal,
	ravenAvailable,
	refreshUnread,
	clearUnreadFor,
	ravenUsers,
	ravenUser,
	ensureRavenUsersLoaded,
	requestNotificationPermission,
	toasts,
	dismissToast,
	openChat,
} from "@/composables/useChat"

const __ = inject("$translate")
const dayjs = inject("$dayjs")
const socket = inject("$socket", null)
const router = useRouter()

const channels = ref([])
const channelsLoading = ref(false)
const channelFilter = ref("")

const messages = ref([])
const messagesLoading = ref(false)
const hasOlder = ref(false)

const draft = ref("")
const sending = ref(false)
const sendError = ref("")
const attachment = ref(null)
const scroller = ref(null)
const input = ref(null)
const windowEl = ref(null)
const startingDm = ref("")

// parent message name -> its thread's replies, oldest first.
const threadReplies = ref({})

// Mentions picked from the autocomplete. Kept as {label, id} so that on send we
// can turn each "@Label" back into the span Raven's parser looks for
// (data-type="userMention"); typing a name by hand is deliberately NOT a mention.
const pendingMentions = ref([])
const mentionOpen = ref(false)
const mentionQuery = ref("")
const mentionIndex = ref(0)

// $session is what the SPAs actually provide; frappe.boot.user.name is not
// populated in the website boot these apps load, so reading only that left
// currentUser empty and every message rendered as somebody else's.
const session = inject("$session", null)
const currentUser = computed(
	() => session?.user || window.frappe?.session?.user || window.frappe?.boot?.user?.name || ""
)

// Channels and DMs the user is already in, plus — once they type — every other
// Raven user they could start a DM with. Without the second half, messaging
// somebody new meant leaving for Raven proper to create the thread first.
const searchResults = computed(() => {
	const q = channelFilter.value.trim().toLowerCase()

	const existing = channels.value
		.filter((c) => !q || channelLabel(c).toLowerCase().includes(q))
		.map((c) => ({
			key: `c:${c.name}`,
			channelId: c.name,
			label: channelLabel(c),
			initials: initialsOf(channelLabel(c)),
			// Only DMs have a face; a group channel keeps its initials.
			image: c.is_direct_message ? ravenUser(c.peer_user_id)?.user_image || "" : "",
			isNewDm: false,
		}))

	if (!q) return existing

	// Anyone who already has a DM channel is in `existing` — offering them twice
	// would be two rows that do different things under the same name.
	const dmPeers = new Set(channels.value.filter((c) => c.is_direct_message).map((c) => c.peer_user_id))
	const people = ravenUsers.value
		.filter((u) => u.enabled !== 0 && u.name !== currentUser.value && !dmPeers.has(u.name))
		.filter((u) => (u.full_name || u.name || "").toLowerCase().includes(q))
		.map((u) => ({
			key: `u:${u.name}`,
			userId: u.name,
			label: u.full_name || u.name,
			initials: initialsOf(u.full_name || u.name),
			image: u.user_image || "",
			isNewDm: true,
		}))

	return [...existing, ...people]
})

const activeChannelLabel = computed(() => {
	const c = channels.value.find((x) => x.name === activeChannel.value)
	return c ? channelLabel(c) : ""
})
const activeChannelInitials = computed(() => initialsOf(activeChannelLabel.value))
const activeChannelImage = computed(() => {
	const c = channels.value.find((x) => x.name === activeChannel.value)
	return c?.is_direct_message ? ravenUser(c.peer_user_id)?.user_image || "" : ""
})
const composerPlaceholder = computed(() =>
	activeChannelLabel.value ? `${__("Message")} ${activeChannelLabel.value}…` : __("Write a message")
)

const mentionMatches = computed(() => {
	const q = mentionQuery.value.toLowerCase()
	return ravenUsers.value
		.filter((u) => (u.full_name || u.name || "").toLowerCase().includes(q))
		.slice(0, 8)
})

// Flatten oldest-first into render rows, inserting a date divider whenever the
// day changes and marking the first message of each same-sender run so only it
// carries an avatar and a name.
//
// Thread replies are folded in directly under their parent. Raven answers a bot
// DM by opening a *thread* on the question and replying there, not in the DM —
// so without this the panel shows your question and nothing else, and an AI bot
// looks broken. Reading them inline also just suits a narrow window better than
// making people open a thread per message.
const rows = computed(() => {
	const out = []
	let lastDay = null
	let lastSender = null

	const push = (m, indent) => {
		const d = dayjs(m.creation)
		const day = d.format("YYYY-MM-DD")
		if (day !== lastDay) {
			out.push({ type: "date", key: `d-${day}`, label: dayLabel(d) })
			lastDay = day
			lastSender = null
		}
		const sender = senderName(m)
		out.push({
			type: "msg",
			key: m.name,
			m,
			sender,
			image: ravenUser(m.owner)?.user_image || "",
			own: m.owner === currentUser.value && !m.is_bot_message,
			head: sender !== lastSender,
			time: d.format("HH:mm"),
			body: messageBody(m),
			indent,
		})
		lastSender = sender
	}

	for (const m of [...messages.value].reverse()) {
		push(m, false)
		// The thread channel's id IS the parent message's name, which is what
		// makes this lookup a plain map hit rather than another round trip.
		for (const reply of threadReplies.value[m.name] || []) push(reply, true)
	}
	return out
})

function dayLabel(d) {
	const today = dayjs().format("YYYY-MM-DD")
	const yday = dayjs().subtract(1, "day").format("YYYY-MM-DD")
	const day = d.format("YYYY-MM-DD")
	if (day === today) return __("Today")
	if (day === yday) return __("Yesterday")
	return d.format("D MMM YYYY")
}

function channelLabel(c) {
	return c.is_direct_message ? c.full_name || c.peer_user_id || c.channel_name : c.channel_name
}

function initialsOf(text) {
	return (text || "?")
		.split(" ")
		.map((w) => w[0])
		.slice(0, 2)
		.join("")
		.toUpperCase()
}
function channelInitials(c) {
	return initialsOf(channelLabel(c))
}

function senderName(m) {
	if (m.is_bot_message && m.bot) return m.bot
	const u = ravenUser(m.owner)
	return u?.full_name || m.owner
}

function messageBody(m) {
	// `content` is Raven's server-derived plain text. Fall back to stripping the
	// HTML ourselves for older rows written before that field was populated. We
	// never v-html `text`: it is author-supplied markup from another user.
	if (m.content) return m.content
	if (!m.text) return ""
	const el = document.createElement("div")
	el.innerHTML = m.text
	return el.textContent || ""
}

function previewTitle(m) {
	// The document's own id, never `content`: Raven sets content to the sender's
	// note, which is already shown in the bubble directly above the card — using
	// it here printed the same sentence twice.
	return m.link_document
}

function fileName(url) {
	try {
		return decodeURIComponent(String(url).split("/").pop())
	} catch (e) {
		return String(url)
	}
}

async function loadChannels() {
	channelsLoading.value = true
	try {
		channels.value = (await call("raven.api.raven_channel.get_channels", { hide_archived: true })) || []
		ravenAvailable.value = true
	} catch (e) {
		channels.value = []
		ravenAvailable.value = false
	}
	channelsLoading.value = false
}

async function loadMessages() {
	if (!activeChannel.value) return
	messagesLoading.value = true
	try {
		// get_messages also calls track_channel_visit server-side, so opening a
		// conversation is what marks it read — no separate mark-read call needed.
		const d = await call("raven.api.chat_stream.get_messages", { channel_id: activeChannel.value, limit: 30 })
		messages.value = d?.messages || []
		hasOlder.value = !!d?.has_old_messages
		clearUnreadFor(activeChannel.value)
		refreshUnread()
		await loadThreadReplies()
		await nextTick()
		scrollToBottom()
	} catch (e) {
		messages.value = []
	}
	messagesLoading.value = false
}

// Fetch the replies for every message that opened a thread, and join those
// thread rooms so their replies arrive live too. A bot answer lands in the
// thread channel, which the DM's own room never publishes.
async function loadThreadReplies() {
	const parents = messages.value.filter((m) => m.is_thread).map((m) => m.name)
	if (!parents.length) {
		threadReplies.value = {}
		return
	}

	const results = await Promise.all(
		parents.map((name) =>
			call("raven.api.chat_stream.get_messages", { channel_id: name, limit: 20 })
				.then((d) => [
					name,
					(d?.messages || [])
						// Raven opens a thread per bot question and each one gets an
						// "X joined" system message. Useful in a real channel, pure
						// noise repeated under every single exchange with a bot.
						.filter((m) => m.message_type !== "System")
						.slice()
						.reverse(),
				])
				// A thread we cannot read is not worth failing the whole panel over.
				.catch(() => [name, []])
		)
	)
	threadReplies.value = Object.fromEntries(results)
	subscribeThreads(parents)
}

async function loadOlder() {
	const oldest = messages.value[messages.value.length - 1]
	if (!oldest) return
	try {
		const d = await call("raven.api.chat_stream.get_older_messages", {
			channel_id: activeChannel.value,
			from_message: oldest.name,
			limit: 30,
		})
		messages.value = messages.value.concat(d?.messages || [])
		hasOlder.value = !!d?.has_old_messages
	} catch (e) {}
}

function toastImage(t) {
	return ravenUser(t.userId)?.user_image || ""
}

function openFromToast(t) {
	dismissToast(t.id)
	openChat(t.channelId)
}

function scrollToBottom() {
	if (scroller.value) scroller.value.scrollTop = scroller.value.scrollHeight
}

function openConversation(id) {
	activeChannel.value = id
}

// A row is either an existing channel (open it) or a person with no thread yet
// (create the DM, then open it). create_direct_message_channel is idempotent —
// it returns the existing channel if one appeared in the meantime.
async function pickResult(r) {
	if (!r.isNewDm) {
		openConversation(r.channelId)
		return
	}
	if (startingDm.value) return
	startingDm.value = r.key
	try {
		const channelId = await call("raven.api.raven_channel.create_direct_message_channel", { user_id: r.userId })
		await loadChannels()
		channelFilter.value = ""
		openConversation(channelId)
	} catch (e) {
		sendError.value = e?.messages?.[0] || e?.message || __("Could not start that conversation.")
	}
	startingDm.value = ""
}

function closeConversation() {
	activeChannel.value = null
	messages.value = []
	draft.value = ""
	pendingMentions.value = []
	attachment.value = null
}

async function openLinkedDocument(m) {
	closeChat()
	// Ask Raven for the link so the raven_document_link_override hook applies —
	// that is what turns a shared Sales Order into an /erpbio-sales route instead
	// of /app/sales-order.
	//
	// Deliberately fetch rather than frappe-ui's `call`: document_link.get is
	// whitelisted GET-only, and `call` posts — which 405s. Falling back to the
	// Desk path keeps the card working if the request fails for any other reason,
	// rather than the click doing nothing at all.
	let path = `/app/${m.link_doctype.toLowerCase().replace(/\s+/g, "-")}/${encodeURIComponent(m.link_document)}`
	try {
		const qs = new URLSearchParams({
			doctype: m.link_doctype,
			docname: String(m.link_document),
			with_site_url: "0",
		})
		const res = await fetch(`/api/method/raven.api.document_link.get?${qs}`, {
			headers: { Accept: "application/json" },
		})
		if (res.ok) {
			const body = await res.json()
			if (body?.message) path = body.message
		}
	} catch (e) {}

	// The hook returns an absolute path including the target app's base
	// (/erpbio-sales/go/...). vue-router matches app-RELATIVE paths — the history
	// base is only applied to the URL — so a link into this same app has to have
	// that base stripped before resolve(), or it never matches and every link
	// becomes a full page load. A link into a different app legitimately is one.
	const base = router.options?.history?.base || ""
	if (base && path.startsWith(base + "/")) {
		const relative = path.slice(base.length)
		if (router.resolve(relative)?.matched?.length) {
			router.push(relative)
			return
		}
	}
	window.location.href = path
}

// --- Mentions -------------------------------------------------------------
function onDraftInput() {
	const el = input.value
	const upto = draft.value.slice(0, el?.selectionStart ?? draft.value.length)
	const match = /@([^\s@]*)$/.exec(upto)
	if (match) {
		mentionQuery.value = match[1]
		mentionIndex.value = 0
		mentionOpen.value = true
		ensureRavenUsersLoaded()
	} else {
		mentionOpen.value = false
	}
}

function applyMention(u) {
	const label = u.full_name || u.name
	const el = input.value
	const caret = el?.selectionStart ?? draft.value.length
	const before = draft.value.slice(0, caret).replace(/@([^\s@]*)$/, `@${label} `)
	draft.value = before + draft.value.slice(caret)
	if (!pendingMentions.value.some((m) => m.id === u.name)) pendingMentions.value.push({ label, id: u.name })
	mentionOpen.value = false
	nextTick(() => el?.focus())
}

function onKeydown(e) {
	if (mentionOpen.value && mentionMatches.value.length) {
		if (e.key === "ArrowDown") {
			e.preventDefault()
			mentionIndex.value = (mentionIndex.value + 1) % mentionMatches.value.length
			return
		}
		if (e.key === "ArrowUp") {
			e.preventDefault()
			mentionIndex.value = (mentionIndex.value - 1 + mentionMatches.value.length) % mentionMatches.value.length
			return
		}
		if (e.key === "Enter" || e.key === "Tab") {
			e.preventDefault()
			applyMention(mentionMatches.value[mentionIndex.value])
			return
		}
		if (e.key === "Escape") {
			mentionOpen.value = false
			return
		}
	}
	if (e.key === "Enter" && !e.shiftKey) {
		e.preventDefault()
		send()
	}
}

function escapeHtml(s) {
	return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
}

// Raven extracts mentions by walking the message HTML for
// span[data-type="userMention"] and reading data-id, so a mention only notifies
// if we emit that exact shape. Escape first, then substitute, so user text can
// never inject markup of its own.
function buildMessageHtml(plain) {
	let html = escapeHtml(plain)
	for (const m of pendingMentions.value) {
		if (!plain.includes(`@${m.label}`)) continue
		const needle = escapeHtml(`@${m.label}`)
		const span = `<span data-type="userMention" data-id="${escapeHtml(m.id)}">@${escapeHtml(m.label)}</span>`
		html = html.split(needle).join(span)
	}
	return `<p>${html.replace(/\n/g, "<br>")}</p>`
}

// --- Sending --------------------------------------------------------------
function onFilePicked(e) {
	const f = e.target.files?.[0]
	if (f) attachment.value = f
	e.target.value = ""
}

async function send() {
	if (sending.value) return
	const plain = draft.value.trim()
	if (!plain && !attachment.value) return
	sending.value = true
	sendError.value = ""
	try {
		if (attachment.value) await uploadFile(plain)
		else await call("raven.api.raven_message.send_message", { channel_id: activeChannel.value, text: buildMessageHtml(plain) })
		draft.value = ""
		pendingMentions.value = []
		attachment.value = null
		await loadMessages()
	} catch (e) {
		sendError.value = e?.messages?.[0] || e?.message || __("Could not send the message.")
	}
	sending.value = false
}

// The upload endpoint takes multipart form-data and creates the Raven Message
// itself, so it cannot go through frappe-ui's `call`.
async function uploadFile(caption) {
	const form = new FormData()
	form.append("file", attachment.value)
	form.append("channelID", activeChannel.value)
	form.append("caption", caption ? buildMessageHtml(caption) : "")
	form.append("compressImages", "1")
	const res = await fetch("/api/method/raven.api.upload_file.upload_file_with_message", {
		method: "POST",
		headers: { "X-Frappe-CSRF-Token": window.csrf_token || "" },
		body: form,
	})
	if (!res.ok) throw new Error(await res.text())
}

// --- Dragging -------------------------------------------------------------
// Inline left/top override the docked `bottom-0 right-4` classes once the user
// has moved the window; `right/bottom: auto` is what actually releases it from
// the corner, since those classes still apply.
// Matches Tailwind's `sm` breakpoint, which the class list above keys off.
const isMobile = ref(typeof window !== "undefined" && window.innerWidth < 640)

// A position dragged out on a desktop is meaningless on a phone — applying it
// there would drag the sheet off-screen with no way to grab it back, so the
// stored value is ignored below `sm` rather than cleared (rotate back to a wide
// window and the desktop position is still there).
const windowStyle = computed(() =>
	chatPos.value && !isMobile.value
		? { left: `${chatPos.value.x}px`, top: `${chatPos.value.y}px`, right: "auto", bottom: "auto" }
		: {}
)

const MARGIN = 8
let dragOffset = null
let dragMoved = false

function clampToViewport(x, y) {
	const el = windowEl.value
	const w = el?.offsetWidth || 352
	const h = el?.offsetHeight || 0
	return {
		x: Math.min(Math.max(x, MARGIN), Math.max(MARGIN, window.innerWidth - w - MARGIN)),
		// Keep at least the header reachable: a window dragged past the bottom
		// edge would otherwise be impossible to grab again.
		y: Math.min(Math.max(y, MARGIN), Math.max(MARGIN, window.innerHeight - Math.min(h, 40) - MARGIN)),
	}
}

function onHeaderPointerDown(e) {
	// Buttons and links in the header keep their own behaviour.
	if (e.target.closest("button, a")) return
	if (e.button !== 0) return
	// The phone sheet is pinned; dragging it would only break the layout, and a
	// touch-drag on the header should scroll/do nothing rather than move it.
	if (isMobile.value) return
	const r = windowEl.value?.getBoundingClientRect()
	if (!r) return
	dragOffset = { x: e.clientX - r.left, y: e.clientY - r.top }
	dragMoved = false
	window.addEventListener("pointermove", onPointerMove)
	window.addEventListener("pointerup", onPointerUp, { once: true })
}

function onPointerMove(e) {
	if (!dragOffset) return
	dragMoved = true
	setChatPos(clampToViewport(e.clientX - dragOffset.x, e.clientY - dragOffset.y))
}

function onPointerUp() {
	dragOffset = null
	window.removeEventListener("pointermove", onPointerMove)
}

// The header also restores a minimised window. Suppressed after a drag, so
// letting go of the mouse doesn't count as a click.
function onHeaderClick() {
	if (dragMoved) {
		dragMoved = false
		return
	}
	if (chatMinimized.value) chatMinimized.value = false
}

// Double-click the header to dock back bottom-right. Clearing the stored
// position (rather than writing the corner's coordinates) is what puts the
// window back on the `bottom-0 right-4` classes, so it stays pinned to the
// corner as the viewport resizes instead of drifting.
function resetPosition() {
	setChatPos(null)
}

// Re-clamp when the viewport shrinks or the window changes height, so a window
// parked near an edge cannot end up off-screen with no way back.
function reclamp() {
	isMobile.value = window.innerWidth < 640
	// Nothing to clamp on the phone sheet — it is pinned by class, not by style.
	if (isMobile.value || !chatPos.value || !windowEl.value) return
	setChatPos(clampToViewport(chatPos.value.x, chatPos.value.y))
}
watch([chatMinimized, chatOpen], () => nextTick(reclamp))
onMounted(() => {
	window.addEventListener("resize", reclamp)
	// Load users up front, not just on open: an incoming-message toast needs a
	// name and a face, and it can fire long before anyone opens the window.
	ensureRavenUsersLoaded()
})
onUnmounted(() => {
	window.removeEventListener("resize", reclamp)
	window.removeEventListener("pointermove", onPointerMove)
})

// --- Wiring ---------------------------------------------------------------
watch(chatOpen, (open) => {
	if (!open) return
	loadChannels()
	ensureRavenUsersLoaded()
	// Opening chat is a real user gesture, which is what browsers require before
	// they will show the permission prompt. Asking on page load gets denied by
	// reflex and can never be asked again.
	requestNotificationPermission()
	if (activeChannel.value) loadMessages()
})

// Raven publishes message_updated into the Raven Channel doc room on insert and
// edit, so we join that room for whichever conversation is on screen and leave
// it again on switch. Without the explicit doc_subscribe the event never reaches
// this socket.
let subscribedTo = null
let subscribedThreads = []

function onChannelActivity(data) {
	if (!data) return
	// Accept the conversation itself and any thread hanging off it — a bot reply
	// only ever publishes to the thread's room.
	if (data.channel_id !== activeChannel.value && !subscribedThreads.includes(data.channel_id)) return
	loadMessages()
}

// Join the room of each thread on screen. Idempotent: re-called on every load,
// so it only subscribes to rooms it has not already joined and drops the rest.
function subscribeThreads(parents) {
	if (!socket) return
	for (const id of subscribedThreads) {
		if (!parents.includes(id)) socket.emit("doc_unsubscribe", "Raven Channel", id)
	}
	for (const id of parents) {
		if (!subscribedThreads.includes(id)) socket.emit("doc_subscribe", "Raven Channel", id)
	}
	subscribedThreads = [...parents]
}

function leaveRoom() {
	if (socket && subscribedTo) {
		socket.emit("doc_unsubscribe", "Raven Channel", subscribedTo)
		socket.off("message_updated", onChannelActivity)
		socket.off("message_deleted", onChannelActivity)
	}
	if (socket) {
		for (const id of subscribedThreads) socket.emit("doc_unsubscribe", "Raven Channel", id)
	}
	subscribedThreads = []
	threadReplies.value = {}
	subscribedTo = null
}
watch(activeChannel, (id) => {
	leaveRoom()
	if (!id) return
	loadMessages()
	if (socket) {
		socket.emit("doc_subscribe", "Raven Channel", id)
		socket.on("message_updated", onChannelActivity)
		socket.on("message_deleted", onChannelActivity)
		subscribedTo = id
	}
})
</script>
