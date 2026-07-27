<!-- Copied from erpbio_general's spa-shared rather than imported: this app is
     deliberately self-contained (clean-room MIT, installs without
     erpbio_general present), so it must not take a build-time dependency on
     it. Only needs $translate, which main.js provides. Keep in sync by hand
     if the shared one changes. -->
<template>
	<!-- Desk-style date picker: click the month name for a month grid, the year
	     for a year grid — no endless chevron-clicking to reach another year. -->
	<div ref="root" class="relative">
		<button type="button" class="form-input flex w-full items-center gap-1.5 text-left"
			:class="[
				size === 'sm' ? 'h-7 text-xs' : 'h-8 text-sm',
				disabled ? 'cursor-not-allowed opacity-60' : '',
			]"
			:disabled="disabled" @click="toggle">
			<FeatherIcon name="calendar" class="h-3.5 w-3.5 shrink-0 text-ink-gray-4" />
			<span class="truncate" :class="modelValue ? 'text-ink-gray-8' : 'text-ink-gray-4'">
				{{ modelValue || placeholder || __("Select date") }}
			</span>
		</button>

		<!-- Teleported and fixed-positioned rather than absolute inside this wrapper:
		     an absolute panel gets clipped by any scrolling/overflow ancestor — a
		     dialog body, a card, a table cell — and can't escape to flip when it
		     runs out of room. -->
		<Teleport to="body">
		<div v-if="open" ref="panel" :style="panelStyle"
			class="fixed z-50 w-64 rounded-lg border bg-surface-white p-2 shadow-xl">
			<!-- header: chevrons + drillable month/year -->
			<div class="mb-1 flex items-center">
				<button type="button" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2" @click="step(-1)">
					<FeatherIcon name="chevron-left" class="h-4 w-4" />
				</button>
				<div class="flex flex-1 items-center justify-center gap-1 text-sm font-medium text-ink-gray-8">
					<button v-if="view === 'days'" type="button" class="rounded px-1 hover:bg-surface-gray-2"
						@click="view = 'months'">{{ MONTHS[cursor.month] }},</button>
					<button type="button" class="rounded px-1 hover:bg-surface-gray-2"
						:class="view === 'days' ? 'text-ink-gray-5' : ''" @click="view = 'years'">{{ cursor.year }}</button>
				</div>
				<button type="button" class="rounded p-1 text-ink-gray-5 hover:bg-surface-gray-2" @click="step(1)">
					<FeatherIcon name="chevron-right" class="h-4 w-4" />
				</button>
			</div>

			<!-- days -->
			<template v-if="view === 'days'">
				<div class="grid grid-cols-7 text-center text-[10px] font-medium uppercase text-ink-gray-4">
					<span v-for="d in DOW" :key="d" class="py-1">{{ d }}</span>
				</div>
				<div class="grid grid-cols-7">
					<button v-for="d in days" :key="d.iso" type="button"
						class="rounded py-1 text-center text-sm"
						:class="[
							d.other ? 'text-ink-gray-3' : 'text-ink-gray-8',
							d.iso === modelValue ? 'bg-surface-gray-7 font-medium text-ink-white' : 'hover:bg-surface-gray-2',
							d.today && d.iso !== modelValue ? 'font-semibold text-ink-gray-9' : '',
						]"
						@click="pick(d.iso)">
						{{ d.day }}
					</button>
				</div>
				<!-- optional quick-duration shortcuts (e.g. valid-upto: +1w, +1mo…) -->
				<div v-if="shortcuts.length" class="mt-1 grid grid-cols-3 gap-1">
					<button v-for="s in shortcuts" :key="s.label" type="button"
						class="rounded-md border py-1 text-xs text-ink-gray-7 hover:bg-surface-gray-1"
						@click="pick(addToBase(s))">
						{{ s.label }}
					</button>
				</div>
				<div class="mt-1 flex gap-1">
					<button type="button" class="flex-1 rounded-md border py-1 text-sm text-ink-gray-7 hover:bg-surface-gray-1"
						@click="pick(todayIso())">{{ __("Today") }}</button>
					<button v-if="clearable && modelValue" type="button"
						class="flex-1 rounded-md border py-1 text-sm text-ink-gray-5 hover:bg-surface-gray-1"
						@click="pick('')">{{ __("Clear") }}</button>
				</div>
			</template>

			<!-- months -->
			<div v-else-if="view === 'months'" class="grid grid-cols-3 gap-1">
				<button v-for="(m, i) in MONTHS" :key="m" type="button"
					class="rounded py-2 text-sm"
					:class="i === cursor.month ? 'bg-surface-gray-7 text-ink-white' : 'text-ink-gray-8 hover:bg-surface-gray-2'"
					@click="cursor.month = i; view = 'days'">
					{{ m.slice(0, 3) }}
				</button>
			</div>

			<!-- years -->
			<div v-else class="grid grid-cols-3 gap-1">
				<button v-for="y in yearPage" :key="y" type="button"
					class="rounded py-2 text-sm"
					:class="y === cursor.year ? 'bg-surface-gray-7 text-ink-white' : 'text-ink-gray-8 hover:bg-surface-gray-2'"
					@click="cursor.year = y; view = 'months'">
					{{ y }}
				</button>
			</div>
		</div>
		</Teleport>
	</div>
</template>

<script setup>
import { computed, inject, onMounted, onUnmounted, reactive, ref } from "vue"
import { FeatherIcon } from "frappe-ui"

const props = defineProps({
	modelValue: { type: String, default: "" }, // YYYY-MM-DD
	placeholder: { type: String, default: "" },
	// quick-duration buttons: [{label, days?, months?, years?}] — relative to
	// shortcutBase (falls back to today)
	shortcuts: { type: Array, default: () => [] },
	shortcutBase: { type: String, default: "" },
	// offer a Clear button (emits "")
	clearable: { type: Boolean, default: false },
	// read-only (locked/submitted docs): the calendar can't be opened
	disabled: { type: Boolean, default: false },
	// "sm" matches the compact inputs used in dense grid rows
	size: { type: String, default: "" },
})
const emit = defineEmits(["update:modelValue"])
const __ = inject("$translate", (s) => s)

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
const DOW = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]

const root = ref(null)
const panel = ref(null)
const open = ref(false)
const view = ref("days")
const cursor = reactive({ year: 2026, month: 0 })

// --- placement -----------------------------------------------------------------
// The panel lives on <body>, so it has to be told where the trigger is, and it
// flips rather than spilling off-screen.
const PANEL_W = 256 // w-64
const PANEL_H = 320 // tallest view (days + Today/Clear); close enough to decide a flip
const GAP = 4
const pos = reactive({ top: 0, left: 0 })
const panelStyle = computed(() => ({ top: `${pos.top}px`, left: `${pos.left}px` }))

function place() {
	const el = root.value
	if (!el) return
	const r = el.getBoundingClientRect()
	// below the trigger unless that would run off the bottom
	pos.top = r.bottom + PANEL_H + GAP > window.innerHeight && r.top - PANEL_H - GAP > 0
		? r.top - PANEL_H - GAP
		: r.bottom + GAP
	// left-aligned unless that would run off the right
	let left = r.left
	if (left + PANEL_W > window.innerWidth - GAP) left = r.right - PANEL_W
	pos.left = Math.max(GAP, left)
}

function todayIso() {
	return new Date().toISOString().slice(0, 10)
}
function toggle() {
	if (props.disabled) return
	open.value = !open.value
	if (open.value) {
		const base = props.modelValue || todayIso()
		cursor.year = Number(base.slice(0, 4))
		cursor.month = Number(base.slice(5, 7)) - 1
		view.value = "days"
		place()
	}
}
function pick(iso) {
	emit("update:modelValue", iso)
	open.value = false
}
function addToBase(s) {
	const base = props.shortcutBase || todayIso()
	const d = new Date(base + "T00:00:00Z")
	if (s.days) d.setUTCDate(d.getUTCDate() + s.days)
	if (s.months) d.setUTCMonth(d.getUTCMonth() + s.months)
	if (s.years) d.setUTCFullYear(d.getUTCFullYear() + s.years)
	return d.toISOString().slice(0, 10)
}
function step(dir) {
	if (view.value === "days") {
		let m = cursor.month + dir
		if (m < 0) { m = 11; cursor.year -= 1 }
		if (m > 11) { m = 0; cursor.year += 1 }
		cursor.month = m
	} else if (view.value === "months") {
		cursor.year += dir
	} else {
		cursor.year += dir * 12
	}
}

const days = computed(() => {
	const first = new Date(Date.UTC(cursor.year, cursor.month, 1))
	const start = new Date(first)
	start.setUTCDate(1 - first.getUTCDay()) // back to Sunday
	const out = []
	const today = todayIso()
	for (let i = 0; i < 42; i++) {
		const d = new Date(start)
		d.setUTCDate(start.getUTCDate() + i)
		const iso = d.toISOString().slice(0, 10)
		out.push({
			iso,
			day: d.getUTCDate(),
			other: d.getUTCMonth() !== cursor.month,
			today: iso === today,
		})
	}
	return out
})
const yearPage = computed(() => {
	const base = cursor.year - (cursor.year % 12)
	return Array.from({ length: 12 }, (_, i) => base + i)
})

function onClickOutside(e) {
	if (!open.value) return
	// the panel is teleported, so it is NOT inside root — test it separately
	if (root.value?.contains(e.target) || panel.value?.contains(e.target)) return
	open.value = false
}
// Capture phase: the trigger may sit inside a scrolling dialog or card, and a
// fixed panel doesn't move with it on its own.
function onReflow() {
	if (open.value) place()
}
onMounted(() => {
	document.addEventListener("mousedown", onClickOutside)
	window.addEventListener("scroll", onReflow, true)
	window.addEventListener("resize", onReflow)
})
onUnmounted(() => {
	document.removeEventListener("mousedown", onClickOutside)
	window.removeEventListener("scroll", onReflow, true)
	window.removeEventListener("resize", onReflow)
})
</script>
