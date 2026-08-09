// Copied from erpbio_general spa-shared, not imported: this app must build
// standalone (its vite config has no shared alias, and erpbio_general is not a
// declared dependency). Keep in step with the original when changing it.
import { computed, ref } from "vue"
import { call } from "frappe-ui"

// Shared chat state. The open flag and the unread badge live here rather than in
// either component because the button and the panel are mounted in different
// places — the button sits in SidebarUserFooter (inside the sidebar column), the
// panel is teleported to <body> from AppShell — so there is no prop path between
// them.
//
// Chat is backed entirely by Raven; erpbio adds no doctypes of its own. Raven is
// installed on every site that runs these SPAs.

export const chatOpen = ref(false)

// Odoo-style: the window collapses to its header bar rather than closing, so a
// conversation stays live (and scrolled) while you go do something else.
export const chatMinimized = ref(false)

// Where the user dragged the window to, as viewport pixels from the top-left.
// null means "docked bottom-right", the default. Persisted so the window comes
// back where it was left — a window that resets position on every navigation is
// worse than one that cannot move at all.
const POS_KEY = "erpbio-chat-position"

function loadPos() {
	try {
		const raw = localStorage.getItem(POS_KEY)
		const p = raw ? JSON.parse(raw) : null
		return p && typeof p.x === "number" && typeof p.y === "number" ? p : null
	} catch (e) {
		return null
	}
}

export const chatPos = ref(loadPos())

export function setChatPos(p) {
	chatPos.value = p
	try {
		if (p) localStorage.setItem(POS_KEY, JSON.stringify(p))
		else localStorage.removeItem(POS_KEY)
	} catch (e) {
		// private mode / quota — dragging still works for this session
	}
}

// channel_id -> unread count, from raven.api.raven_message.get_unread_count_for_channels
// which returns [{ name, is_direct_message, unread_count }].
export const unreadByChannel = ref({})

// The channel the panel should show when it opens. Set by openChat(id) so
// "reply to this DM" from a notification can deep-link straight into a thread.
export const activeChannel = ref(null)

// Raven is a hard dependency, but a *user* can exist without a Raven User
// record (Raven Settings → "Automatically add system users" governs this). Such
// a user gets empty lists rather than an error, so we detect the state and show
// an explanatory empty state instead of a silently dead panel.
export const ravenAvailable = ref(true)

export const unreadTotal = computed(() =>
	Object.values(unreadByChannel.value).reduce((sum, n) => sum + (n || 0), 0)
)

export function openChat(channelId = null) {
	if (channelId) activeChannel.value = channelId
	chatOpen.value = true
	chatMinimized.value = false
}

export function closeChat() {
	chatOpen.value = false
	chatMinimized.value = false
}

// From the sidebar button: if the window is sitting minimized, the click that
// "opens" chat should restore it rather than close it outright.
export function toggleChat() {
	if (chatOpen.value && chatMinimized.value) {
		chatMinimized.value = false
		return
	}
	chatOpen.value ? closeChat() : openChat()
}

export function toggleMinimized() {
	chatMinimized.value = !chatMinimized.value
}

// Raven users, shared rather than per-component: the panel needs them for the
// mention list and avatars, and the unread subscription needs them to turn a
// message's `owner` (an email) into a name and a face for the notification.
export const ravenUsers = ref([])
let usersRequested = false

export async function ensureRavenUsersLoaded() {
	if (usersRequested) return
	usersRequested = true
	try {
		ravenUsers.value = (await call("raven.api.raven_users.get_list")) || []
	} catch (e) {
		ravenUsers.value = []
		usersRequested = false // let a later open retry
	}
}

export function ravenUser(id) {
	return ravenUsers.value.find((u) => u.name === id) || null
}

export function userLabel(id) {
	return ravenUser(id)?.full_name || id || ""
}

// --- Notifications --------------------------------------------------------
// In-app toasts. Deliberately not alertDialog(): a modal in the middle of the
// screen for an incoming chat message would interrupt whatever the person is
// actually doing.
export const toasts = ref([])
let toastSeq = 0

export function pushToast(t) {
	const id = ++toastSeq
	// Cap the stack — a burst of messages should not paper over the page.
	toasts.value = [...toasts.value, { id, ...t }].slice(-3)
	setTimeout(() => dismissToast(id), 6000)
	return id
}

export function dismissToast(id) {
	toasts.value = toasts.value.filter((t) => t.id !== id)
}

// Desktop notifications only make sense when the tab is not the thing being
// looked at; the in-app toast covers the visible case. Permission is requested
// on a real user gesture (opening chat), never on page load.
export function requestNotificationPermission() {
	try {
		if (typeof Notification === "undefined") return
		if (Notification.permission === "default") Notification.requestPermission()
	} catch (e) {}
}

function notifyDesktop(title, body) {
	try {
		if (typeof Notification === "undefined" || Notification.permission !== "granted") return
		if (!document.hidden) return
		new Notification(title, { body, tag: "erpbio-chat" })
	} catch (e) {}
}

export async function refreshUnread() {
	try {
		const rows = await call("raven.api.raven_message.get_unread_count_for_channels")
		const next = {}
		for (const row of rows || []) {
			if (row?.name && row.unread_count) next[row.name] = row.unread_count
		}
		unreadByChannel.value = next
		ravenAvailable.value = true
	} catch (e) {
		// A permission error here means no Raven User record (or Raven disabled).
		// Zero the badge rather than leaving a stale count on screen.
		unreadByChannel.value = {}
		ravenAvailable.value = false
	}
}

// Clear locally the moment a channel is opened, so the badge responds to the
// click instead of waiting for the server round-trip to come back.
export function clearUnreadFor(channelId) {
	if (!channelId || !unreadByChannel.value[channelId]) return
	const next = { ...unreadByChannel.value }
	delete next[channelId]
	unreadByChannel.value = next
}

// Raven publishes this to every member on each new message (see
// raven_message.py — it fires for DMs, channels and threads alike). Refetching
// the counts is one cheap query and avoids trying to mirror Raven's own
// last_visit bookkeeping on the client.
export function subscribeUnread(socket) {
	if (!socket) return () => {}
	const handler = (data) => {
		refreshUnread()
		announce(data)
	}
	socket.on("raven:unread_channel_count_updated", handler)
	return () => socket.off("raven:unread_channel_count_updated", handler)
}

// Turn an incoming-message event into a toast (and a desktop notification when
// the tab is in the background). Stays quiet when the message is already on
// screen, so reading a conversation doesn't toast every reply into it.
function announce(data) {
	if (!data?.channel_id) return

	const me = window.frappe?.session?.user
	if (me && data.sent_by === me) return

	const lookingAtIt =
		chatOpen.value && !chatMinimized.value && activeChannel.value === data.channel_id
	if (lookingAtIt) return

	// last_message_details is json.dumps'd server-side, so it arrives as a string
	// over socketio on some paths and as an object on others.
	let details = data.last_message_details
	if (typeof details === "string") {
		try {
			details = JSON.parse(details)
		} catch (e) {
			details = null
		}
	}

	const senderId = details?.owner || data.sent_by
	const title = details?.is_bot_message && details?.bot ? details.bot : userLabel(senderId)
	const body = details?.content || (details?.message_type === "File" ? "Sent a file" : "New message")

	pushToast({ title, body, channelId: data.channel_id, userId: senderId })
	notifyDesktop(title, body)
}
