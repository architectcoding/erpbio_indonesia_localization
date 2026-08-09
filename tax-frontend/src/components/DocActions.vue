<!-- Copied from erpbio_general spa-shared, not imported: this app must build and
     install without erpbio_general present. Its backend module is a prop/config,
     so it points at this app's own api. Keep in sync by hand. -->
<template>
	<div class="flex items-center gap-1.5">
		<!-- Each button is a fixed 32px square on mobile (icon centred), expanding
		     to icon+label on sm+ — so Print/Share/Email are visually identical. -->
		<!-- Print: a dropdown of formats (View | Save). Teleported to <body> and
		     positioned beneath the button on desktop (never clipped by the
		     sidebar), centered below the top bar on mobile. -->
		<Button variant="subtle" class="!h-8 !w-8 justify-center !px-0 sm:!w-auto sm:!px-2.5" @click="openPrint">
			<span class="flex items-center justify-center gap-1.5 whitespace-nowrap">
				<FeatherIcon name="printer" class="h-4 w-4" />
				<span class="hidden sm:inline">{{ __("Print") }}</span>
			</span>
		</Button>
		<Button variant="subtle" :disabled="sharing" class="!h-8 !w-8 justify-center !px-0 sm:!w-auto sm:!px-2.5" @click="share">
			<span class="flex items-center justify-center gap-1.5 whitespace-nowrap">
				<LoadingIndicator v-if="sharing" class="h-4 w-4" />
				<FeatherIcon v-else name="share-2" class="h-4 w-4" />
				<span class="hidden sm:inline">{{ __("Share") }}</span>
			</span>
		</Button>
		<!-- Send the document itself to a colleague in Raven. Separate from Share
		     because Share here goes straight to the OS share sheet with a PDF —
		     erpbio_general's copy has a routes panel this fork never gained, so
		     there is no menu to add an entry to. -->
		<Button variant="subtle" class="!h-8 !w-8 justify-center !px-0 sm:!w-auto sm:!px-2.5" @click="shareToChatOpen = true">
			<span class="flex items-center justify-center gap-1.5 whitespace-nowrap">
				<FeatherIcon name="message-square" class="h-4 w-4" />
				<span class="hidden sm:inline">{{ __("Chat") }}</span>
			</span>
		</Button>
		<Dropdown :options="emailOptions">
			<Button variant="subtle" class="!h-8 !w-8 justify-center !px-0 sm:!w-auto sm:!px-2.5">
				<span class="flex items-center justify-center gap-1.5 whitespace-nowrap">
					<FeatherIcon name="mail" class="h-4 w-4" />
					<span class="hidden sm:inline">{{ __("Email") }}</span>
				</span>
			</Button>
		</Dropdown>
	</div>

	<ShareToRavenDialog v-model="shareToChatOpen" :doctype="doctype" :name="name" :label="label" />

	<!-- Compose email (system send) -->
	<div v-if="showEmail" class="fixed inset-0 z-50 flex items-start justify-center bg-black/40 p-4 pt-16 sm:pt-24"
		@click.self="showEmail = false">
		<div class="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-lg border bg-surface-white shadow-xl">
			<div class="flex items-center justify-between border-b px-4 py-3">
				<h3 class="text-sm font-semibold text-ink-gray-9">{{ __("Email") }} {{ label }} {{ name }}</h3>
				<button class="p-1 text-ink-gray-5 hover:text-ink-gray-8" @click="showEmail = false">
					<FeatherIcon name="x" class="h-4 w-4" />
				</button>
			</div>
			<div class="flex flex-col gap-3 overflow-y-auto p-4">
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("To") }}</label>
					<input v-model="emailTo" type="email" class="form-input h-8 text-sm" :placeholder="__('recipient@example.com')" />
				</div>
				<div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Subject") }}</label>
						<input v-model="emailSubject" class="form-input h-8 text-sm" />
					</div>
					<div class="flex flex-col gap-1">
						<label class="text-xs text-ink-gray-5">{{ __("Attachment (print format)") }}</label>
						<select v-model="emailFormat" class="form-select h-8 text-sm">
							<option v-for="f in formats" :key="f" :value="f">{{ f }}</option>
						</select>
					</div>
				</div>
				<div class="flex flex-col gap-1">
					<label class="text-xs text-ink-gray-5">{{ __("Message") }}</label>
					<div class="rounded-md border bg-surface-white">
						<TextEditor :key="editorKey" :content="emailBody" :placeholder="__('Write your message…')"
							:fixedMenu="toolbar" editor-class="prose-sm max-w-none p-2 min-h-[8rem] text-ink-gray-8"
							@change="(v) => (emailBody = v)" />
					</div>
					<p class="text-[11px] text-ink-gray-4">{{ __("The {0} PDF is attached automatically.", [label]) }}</p>
				</div>
			</div>
			<div class="flex justify-end gap-2 border-t px-4 py-3">
				<Button variant="ghost" @click="showEmail = false">{{ __("Cancel") }}</Button>
				<Button variant="solid" :loading="sending" :disabled="!emailTo.trim()" @click="sendEmail">
					<template #prefix><FeatherIcon name="send" class="h-4 w-4" /></template>
					{{ __("Send") }}
				</Button>
			</div>
		</div>
	</div>

	<!-- Print: format dropdown, teleported so it can't be clipped -->
	<Teleport to="body">
		<div v-if="printOpen" class="fixed inset-0 z-40 bg-black/40 sm:bg-transparent" @click="printOpen = false" />
		<Transition
			enter-active-class="transition duration-150 ease-out"
			enter-from-class="opacity-0 translate-y-1"
			enter-to-class="opacity-100 translate-y-0"
			leave-active-class="transition duration-100 ease-in"
			leave-from-class="opacity-100 translate-y-0"
			leave-to-class="opacity-0 translate-y-1"
		>
			<div
				v-if="printOpen"
				class="fixed z-50 flex max-h-[70vh] w-[calc(100vw-2rem)] max-w-[32rem] flex-col overflow-hidden rounded-lg border bg-surface-white shadow-xl sm:w-[32rem]"
				:style="printStyle"
			>
				<div class="flex items-center justify-between border-b px-4 py-3">
					<h3 class="text-sm font-semibold text-ink-gray-9">{{ __("Print") }} {{ label }}</h3>
					<button class="p-1 text-ink-gray-5 hover:text-ink-gray-8" @click="printOpen = false"><FeatherIcon name="x" class="h-4 w-4" /></button>
				</div>
				<div class="overflow-y-auto p-2">
					<div v-for="f in formats" :key="f" class="flex items-start gap-3 rounded-md px-2 py-1.5 hover:bg-surface-gray-2">
						<span class="min-w-0 flex-1 break-words text-sm text-ink-gray-8" :title="f">{{ f }}</span>
						<button class="flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs font-medium text-ink-gray-7 hover:bg-surface-gray-3" @click="viewPdf(f)">
							<FeatherIcon name="eye" class="h-3.5 w-3.5" /> {{ __("View") }}
						</button>
						<button class="flex shrink-0 items-center gap-1 rounded px-2 py-1 text-xs font-medium text-ink-gray-7 hover:bg-surface-gray-3" @click="downloadPdf(f); printOpen = false">
							<FeatherIcon name="download" class="h-3.5 w-3.5" /> {{ __("Save") }}
						</button>
					</div>
				</div>
			</div>
		</Transition>
	</Teleport>
</template>

<script setup>
import { computed, inject, ref } from "vue"
import { Button, Dropdown, FeatherIcon, LoadingIndicator, TextEditor, call } from "frappe-ui"
import ShareToRavenDialog from "@/components/ShareToRavenDialog.vue"
const __ = inject("$translate")

const props = defineProps({
	doctype: { type: String, required: true }, // "Quotation" | "Purchase Order" | …
	name: { type: String, required: true },
	// One-line summary used in share/email bodies, e.g. "Quotation Q26.. for X — IDR …"
	shareText: { type: String, default: "" },
	contactEmail: { type: String, default: "" },
	// Backend module exposing get_print_formats / email_document (+ optionally
	// get_email_template) for this app's doctypes — each app whitelists its own.
	apiModule: { type: String, default: "erpbio_general.api.sales_app" },
	// Display name for the doc in panel titles / email subject. Defaults to the
	// doctype, with the ERPbio convention that a Sales Order reads "Confirmation
	// Order"; any caller can override.
	label: { type: String, default: "" },
})

const label = computed(() => props.label || (props.doctype === "Sales Order" ? "Confirmation Order" : props.doctype))

const formats = ref(["Standard"])
call(`${props.apiModule}.get_print_formats`, { doctype: props.doctype })
	.then((r) => {
		formats.value = r || ["Standard"]
		if (!emailFormat.value) emailFormat.value = formats.value[0]
	})
	.catch(() => {})

function pdfUrl(format) {
	const params = new URLSearchParams({
		doctype: props.doctype,
		name: props.name,
		format: format || formats.value[0] || "Standard",
		no_letterhead: "0",
	})
	return `/api/method/frappe.utils.print_format.download_pdf?${params.toString()}`
}

// Force a real download (mobile in-browser PDF viewers often show the file
// with no save option). Fetch the blob and trigger an <a download>; fall back
// to opening in a new tab if the fetch fails.
async function downloadPdf(format) {
	try {
		const blob = await fetch(pdfUrl(format)).then((r) => {
			if (!r.ok) throw new Error("pdf failed")
			return r.blob()
		})
		const url = URL.createObjectURL(blob)
		const a = document.createElement("a")
		a.href = url
		a.download = `${props.name}.pdf`
		document.body.appendChild(a)
		a.click()
		a.remove()
		setTimeout(() => URL.revokeObjectURL(url), 2000)
	} catch (e) {
		window.open(pdfUrl(format), "_blank")
	}
}

// get_print_formats returns the default first, so formats[0] is the default.
// The print panel offers View (opens the PDF) and Save (downloads) per format.
const printOpen = ref(false)
const printAnchor = ref(null) // the Print button's viewport rect, for positioning
function openPrint(e) {
	printAnchor.value = e.currentTarget.getBoundingClientRect()
	printOpen.value = true
}
// Always drop beneath the Print button, left-aligned to it so it opens
// rightward and stays clear of the left sidebar; only nudged left if it would
// overflow the right edge. Same on mobile (full-ish width, below the button).
const printStyle = computed(() => {
	const a = printAnchor.value
	if (!a) return { top: "4rem", left: "1rem" }
	const vw = window.innerWidth
	const mobile = vw < 640
	const width = mobile ? Math.min(vw - 32, 512) : 512 // matches sm:w-[32rem]
	let left = a.left
	if (left + width > vw - 8) left = vw - width - 8
	left = Math.max(left, 8)
	return { top: `${a.bottom + 6}px`, left: `${left}px` }
})
function viewPdf(format) {
	window.open(pdfUrl(format), "_blank")
	printOpen.value = false
}

// Share: use the native share sheet with the PDF attached when the browser
// supports it (mobile). Once we go native, a cancel/error must NOT also pop a
// WhatsApp tab — that double behaviour looked broken on mobile. Only fall back
// to WhatsApp when there's no native share at all (typical desktop).
const sharing = ref(false)
const shareToChatOpen = ref(false)
async function share() {
	sharing.value = true
	try {
		let file = null
		try {
			const blob = await fetch(pdfUrl(formats.value[0])).then((r) => {
				if (!r.ok) throw new Error("pdf failed")
				return r.blob()
			})
			file = new File([blob], `${props.name}.pdf`, { type: "application/pdf" })
		} catch (e) {
			file = null // couldn't build the PDF — share text only below
		}

		const canShareFile = file && navigator.canShare && navigator.canShare({ files: [file] })
		if (canShareFile || navigator.share) {
			try {
				await navigator.share(
					canShareFile
						? { files: [file], title: props.name, text: props.shareText }
						: { title: props.name, text: props.shareText }
				)
			} catch (e) {
				// user cancelled or the sheet failed — stop here, no WhatsApp tab
			}
			return
		}

		// No native share (desktop) → WhatsApp text.
		window.open(`https://wa.me/?text=${encodeURIComponent(props.shareText || props.name)}`, "_blank")
	} finally {
		sharing.value = false
	}
}

const emailOptions = computed(() => [
	{
		label: __("Compose & send (PDF attached)"),
		icon: "send",
		onClick: openCompose,
	},
	{
		// mailto: can't carry attachments — the app-composed send (above) is the
		// way to attach the PDF. This just opens the user's mail app with text.
		label: __("Open in mail app (no attachment)"),
		icon: "external-link",
		onClick: () => {
			const subject = encodeURIComponent(`${label.value} ${props.name}`)
			const body = encodeURIComponent(props.shareText || props.name)
			window.location.href = `mailto:${props.contactEmail || ""}?subject=${subject}&body=${body}`
		},
	},
])

/* ---- compose modal ---- */
const showEmail = ref(false)
const sending = ref(false)
const emailTo = ref("")
const emailSubject = ref("")
const emailFormat = ref("")
const emailBody = ref("")
const editorKey = ref(0)

async function openCompose() {
	emailTo.value = props.contactEmail || ""
	emailSubject.value = `${label.value} ${props.name}`
	emailFormat.value = formats.value[0] || "Standard"
	emailBody.value = `<p>Dear Customer,</p><p>${props.shareText || `Please find attached ${label.value} ${props.name}.`}</p><p>Best regards.</p>`
	editorKey.value++ // remount so the editor picks up the fresh content
	showEmail.value = true
	// Prefill from the configured email template (ERPbio Settings), with the
	// doc's own values substituted server-side. Only sales_app exposes this; on
	// the other apps the call 404s and we keep the default body above.
	try {
		const t = await call(`${props.apiModule}.get_email_template`, {
			doctype: props.doctype,
			name: props.name,
		})
		if (t && (t.subject || t.body)) {
			if (t.subject) emailSubject.value = t.subject
			if (t.body) emailBody.value = t.body
			editorKey.value++ // remount with the template body
		}
	} catch (e) {
		/* no template configured / method — keep the default */
	}
}

async function sendEmail() {
	if (!emailTo.value.trim()) return
	sending.value = true
	try {
		const args = {
			doctype: props.doctype,
			name: props.name,
			recipient: emailTo.value.trim(),
			print_format: emailFormat.value || null,
			message: emailBody.value || null,
		}
		// purchasing.masters.email_document (a do-not-edit module) has no `subject`
		// param and would reject it; its backend derives the subject itself.
		if (!props.apiModule.endsWith("purchasing.masters")) args.subject = emailSubject.value || null
		await call(`${props.apiModule}.email_document`, args)
		showEmail.value = false
		window.alert(__("Sent to {0}.", [emailTo.value.trim()]))
	} catch (e) {
		window.alert(e?.messages?.[0] || __("Could not send the email."))
	} finally {
		sending.value = false
	}
}

const toolbar = ["Paragraph", "Bold", "Italic", "Separator", "Bullet List", "Numbered List", "Separator", "Link", "Separator", "Undo", "Redo"]
</script>
