<!-- Copied from erpbio_general spa-shared, not imported: this app must build and
     install without erpbio_general present. Backend-agnostic (it calls whatever
     `method` you pass), so nothing here reaches into that app. Keep in sync by hand. -->
<template>
	<div class="flex h-full flex-col bg-surface-white">
		<!-- Header / toolbar -->
		<div class="border-b border-outline-gray-2 bg-surface-white px-3 py-2.5">
			<div class="flex flex-col gap-2">
				<!-- Buttons row. Mobile: Filter + actions left, New right (title
				     lives in the breadcrumb bar). Desktop: title left, buttons right. -->
				<div class="flex flex-wrap items-center gap-2">
					<h1 class="hidden text-base font-semibold text-ink-gray-9 md:block">{{ title }}</h1>
					<div class="hidden flex-1 md:block" />
					<FilterPanel
						v-if="filterableFields.length"
						:fields="filterableFields"
						@update:modelValue="onPanelFilters"
					/>
					<slot name="actions" />
					<div class="flex-1 md:hidden" />
					<Button v-if="createRoute" variant="solid" @click="router.push({ name: createRoute })">
						<template #prefix><FeatherIcon name="plus" class="h-4 w-4" /></template>
						{{ __("New") }}
					</Button>
				</div>

				<!-- Search: its own full row on mobile, inline with quick filters on desktop -->
				<div class="flex flex-col gap-2 md:flex-row md:flex-wrap md:items-center">
					<div v-if="searchFields.length || method" class="relative w-full md:min-w-[180px] md:max-w-xs md:flex-1">
						<FeatherIcon
							name="search"
							class="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-gray-4"
						/>
						<input
							type="text"
							class="h-8 w-full rounded-lg border-0 bg-surface-gray-2 pl-9 pr-3 text-sm focus:bg-surface-gray-1 focus:ring-1 focus:ring-gray-300"
							:placeholder="__('Search {0}…', [noun.toLowerCase()])"
							:value="searchQuery"
							@input="(e) => onSearch(e.target.value)"
						/>
					</div>
					<!-- Quick filters: equal-width pair on mobile, inline on desktop -->
					<div v-if="quickFilters.length" class="grid grid-cols-2 gap-2 md:flex md:flex-wrap md:items-center">
						<QuickFilter
							v-for="qf in quickFilters"
							:key="qf.fieldname"
							class="w-full md:w-auto"
							:label="qf.label"
							:fieldtype="qf.fieldtype"
							:options="qf.options"
							:doctype="qf.doctype"
							:modelValue="quickValues[qf.fieldname] || ''"
							@update:modelValue="(v) => onQuickFilter(qf, v)"
						/>
					</div>
				</div>
			</div>
		</div>

		<!-- Desk-style floating selection pill (bottom-center) -->
		<Teleport to="body">
			<div v-if="selectable && selectedNames.size" class="fixed bottom-6 left-1/2 z-40 w-max max-w-[95vw] -translate-x-1/2">
				<div class="flex flex-wrap items-center justify-center gap-2 rounded-xl border border-outline-gray-2 bg-surface-white px-3 py-2 shadow-2xl sm:gap-3 sm:px-4">
					<input type="checkbox" checked class="desk-checkbox" @click.prevent />
					<span class="whitespace-nowrap text-sm font-medium text-ink-gray-9">
						<!-- Two whole phrases rather than a stitched-on "s": Indonesian
						     doesn't pluralise, and other languages don't split this way. -->
						{{ selectedNames.size === 1 ? __("1 row selected") : __("{0} rows selected", [selectedNames.size]) }}
					</span>
					<div class="h-4 w-px bg-[color:var(--outline-gray-2)]" />
					<slot name="bulkActions" :selected="selectedRows" :clear="clearSelection" :reload="refresh" />
					<div class="h-4 w-px bg-[color:var(--outline-gray-2)]" />
					<button v-if="!allChecked" type="button" class="whitespace-nowrap text-sm text-ink-gray-6 hover:text-ink-gray-9" @click="toggleAll">
						{{ __("Select all") }}
					</button>
					<button type="button" class="p-0.5 text-ink-gray-5 hover:text-ink-gray-9" :title="__('Clear selection')" @click="clearSelection">
						<FeatherIcon name="x" class="h-4 w-4" />
					</button>
				</div>
			</div>
		</Teleport>

		<!-- Body -->
		<!-- Desktop: tighten the left/right/bottom padding so the table's thin
		     horizontal scrollbar sits close to the card edges (mobile cards keep
		     the roomier p-3). -->
		<div class="flex flex-1 flex-col overflow-y-auto p-3 md:px-1.5 md:pb-1.5">
			<!-- Loading (first page) -->
			<div v-if="loading && !rows.length" class="flex justify-center py-16">
				<LoadingIndicator class="h-6 w-6 text-ink-gray-5" />
			</div>

			<!-- Empty -->
			<div
				v-else-if="!rows.length"
				class="flex flex-col items-center justify-center gap-2 py-16 text-center text-ink-gray-5"
			>
				<FeatherIcon name="inbox" class="h-8 w-8" />
				<span class="text-sm">{{ __("No {0} found", [noun.toLowerCase()]) }}</span>
			</div>

			<template v-else>
				<!-- Desktop table: borderless body + a rounded, lighter header bar.
				     md:flex-auto lets it fill the list area so its (thin) horizontal
				     scrollbar sits at the bottom rather than under a short table. -->
				<div class="list-hscroll hidden overflow-x-auto bg-surface-white md:block md:flex-auto">
					<table class="w-full text-sm">
						<!-- Column width presets: a column may set `width` (any CSS
						     length or %), applied here as a global default for every
						     user. Columns without one size to their content. -->
						<colgroup>
							<col v-if="selectable" style="width: 2.5rem" />
							<col v-for="col in columns" :key="col.key" :style="col.width ? { width: col.width } : undefined" />
						</colgroup>
						<thead>
							<tr class="text-left text-[13px] font-medium text-ink-gray-9">
								<th v-if="selectable" class="w-8 rounded-l-lg bg-surface-gray-3 px-3 py-2.5">
									<input type="checkbox" :checked="allChecked" class="desk-checkbox" @change="toggleAll" />
								</th>
								<th
									v-for="(col, ci) in columns"
									:key="col.key"
									class="select-none whitespace-nowrap bg-surface-gray-3 px-4 py-2.5"
									:class="[
										col.headerClass,
										'cursor-pointer hover:text-ink-gray-7',
										ci === 0 && !selectable ? 'rounded-l-lg' : '',
										ci === columns.length - 1 ? 'rounded-r-lg' : '',
									]"
									@click="onSort(col)"
								>
									<span class="inline-flex items-center gap-1">
										{{ col.label }}
										<FeatherIcon
											v-if="sortField === (col.sortKey || col.key)"
											:name="sortDir === 'asc' ? 'chevron-up' : 'chevron-down'"
											class="h-3 w-3"
										/>
									</span>
								</th>
							</tr>
						</thead>
						<tbody>
							<tr
								v-for="row in displayRows"
								:key="row.name"
								class="group border-b border-outline-gray-1 last:border-0"
								:class="rowTo ? 'cursor-pointer' : ''"
								@click="onRowClick(row)"
							>
								<td v-if="selectable"
									class="w-8 rounded-l-lg px-3 py-2.5 transition-colors group-hover:bg-surface-gray-2"
									@click.stop
								>
									<input type="checkbox" :checked="selectedNames.has(row.name)" class="desk-checkbox" @change="toggleRow(row)" />
								</td>
								<td
									v-for="(col, ci) in columns"
									:key="col.key"
									v-doc-preview="col.preview ? col.preview(row) : undefined"
									class="px-4 py-2.5 text-ink-gray-8 transition-colors group-hover:bg-surface-gray-2"
									:class="[
										col.cellClass,
										ci === 0 && !selectable ? 'rounded-l-lg' : '',
										ci === columns.length - 1 ? 'rounded-r-lg' : '',
									]"
								>
									<component
										:is="col.component"
										v-if="col.component"
										:value="row[col.key]"
										:row="row"
									/>
									<span v-else-if="searchQuery" v-html="highlightText(formatCell(row, col))" />
									<template v-else>{{ formatCell(row, col) }}</template>
								</td>
							</tr>
						</tbody>
					</table>
				</div>

				<!-- Mobile cards. Selection is gallery-style: long-press a card to
					enter selection mode (checkboxes appear), tap to toggle, clear
					the selection to leave the mode. -->
				<div class="flex flex-col gap-2 md:hidden">
					<div
						v-for="row in displayRows"
						:key="row.name"
						class="flex items-start gap-2 transition-opacity duration-300"
						:class="[selectable ? 'select-none' : '', pressingRow === row.name ? 'opacity-50' : '']"
						@pointerdown="onCardPress(row, $event)"
						@pointerup="cancelPress"
						@pointercancel="cancelPress"
						@pointermove="onPressMove"
						@contextmenu="selectable && $event.preventDefault()"
					>
						<input
							v-if="selectable && mobileSelectMode"
							type="checkbox"
							:checked="selectedNames.has(row.name)"
							class="desk-checkbox mt-4 shrink-0"
							@click.stop
							@change="toggleRow(row)"
						/>
						<!-- Custom per-page card (e.g. Opportunities) -->
						<div
							v-if="$slots.mobileCard"
							class="min-w-0 flex-1"
							:class="rowTo ? 'cursor-pointer active:opacity-90' : ''"
							@click="onCardClick(row)"
						>
							<slot name="mobileCard" :row="row" :meta="meta" :highlight="highlightText" :search="searchQuery" />
						</div>
						<!-- Default generic label:value card -->
						<div
							v-else
							class="min-w-0 flex-1 rounded-lg border bg-surface-white p-3"
							:class="rowTo ? 'cursor-pointer active:bg-surface-gray-1' : ''"
							@click="onCardClick(row)"
						>
							<div
								v-for="(col, i) in columns"
								:key="col.key"
								class="flex justify-between gap-3 py-0.5"
								:class="i === 0 ? 'text-sm font-medium text-ink-gray-9' : 'text-xs text-ink-gray-5'"
							>
								<span v-if="i !== 0" class="shrink-0">{{ col.label }}</span>
								<component
									:is="col.component"
									v-if="col.component"
									:value="row[col.key]"
									:row="row"
								/>
								<span v-else :class="i === 0 ? '' : 'text-right text-ink-gray-7'">
									{{ formatCell(row, col) }}
								</span>
							</div>
						</div>
					</div>
				</div>

			</template>
		</div>

		<!-- Footer (permanent bottom bar, outside the scroll area): count ·
		     rows-per-page · load more -->
		<div v-if="rows.length" class="flex flex-wrap items-center justify-between gap-2 border-t bg-surface-white px-3 py-2 text-xs text-ink-gray-5">
			<div class="flex items-center gap-3">
				<span class="tabular-nums">{{ totalLabel }}</span>
				<div class="flex items-center gap-1">
					<button
						v-for="n in PAGE_SIZES"
						:key="n"
						type="button"
						class="rounded border px-2 py-0.5 tabular-nums"
						:class="pageSize === n ? 'bg-surface-gray-3 text-ink-gray-8' : 'text-ink-gray-5 hover:bg-surface-gray-2'"
						@click="setPageSize(n)"
					>
						{{ n }}
					</button>
				</div>
			</div>
			<Button v-if="hasNextPage" variant="outline" :loading="loading" @click="next">{{ __("Load more") }}</Button>
		</div>
	</div>
</template>

<script setup>
import { computed, inject, reactive, ref, watch } from "vue"
import { useRouter } from "vue-router"
import {
	Button,
	FeatherIcon,
	LoadingIndicator,
	createListResource,
	createResource,
	debounce,
} from "frappe-ui"
import FilterPanel from "./FilterPanel.vue"
import QuickFilter from "./QuickFilter.vue"

const __ = inject("$translate")

const props = defineProps({
	doctype: { type: String, default: "" },
	// Already-translated by the caller (pages pass __("Opportunities")); it is
	// interpolated into "Search {0}…" / "No {0} found" rather than re-wrapped.
	title: { type: String, required: true },
	// Noun for those two sentences when the title itself reads badly in them
	// (e.g. title "Items Price List" would give "No items price list found").
	// Also already-translated; defaults to the title.
	searchNoun: { type: String, default: "" },
	columns: { type: Array, required: true },
	fields: { type: Array, default: () => ["name"] },
	searchFields: { type: Array, default: () => [] },
	filters: { type: Object, default: () => ({}) },
	orderBy: { type: String, default: "modified desc" },
	// Method mode: data from a whitelisted method receiving { txt, start,
	// page_length, filters } and returning { items, has_next, ...meta }.
	method: { type: String, default: "" },
	// Advanced Filter panel fields: [{ fieldname, label, fieldtype, options? }].
	filterableFields: { type: Array, default: () => [] },
	// Inline quick-filter shortcuts: [{ fieldname, label, fieldtype, options?,
	// doctype? }]. Data -> contains; Select/Link -> equals.
	quickFilters: { type: Array, default: () => [] },
	rowTo: { type: Function, default: null },
	createRoute: { type: String, default: "" },
	pageLength: { type: Number, default: 50 },
	// Adds a checkbox column + select-all; pages provide bulk actions via the
	// #bulkActions slot ({ selected, clear, reload }).
	selectable: { type: Boolean, default: false },
})

// Falls back to the title so the other 96 call sites are unaffected.
const noun = computed(() => props.searchNoun || props.title)

const router = useRouter()
const searchQuery = ref("")
const panelFilters = ref([])
const quickValues = reactive({})

const PAGE_SIZES = [20, 100, 500, 2500]
const pageSize = ref(PAGE_SIZES.includes(props.pageLength) ? props.pageLength : 20)
const sortField = ref("")
const sortDir = ref("desc")
// the active column's data key, for the client-side sort layer (see displayRows)
const sortColKey = ref("")

function currentOrderBy() {
	return sortField.value ? `${sortField.value} ${sortDir.value}` : ""
}

/* ---- generic get_list mode ---- */
const listResource = props.method
	? null
	: createListResource({
			doctype: props.doctype,
			fields: props.fields,
			filters: props.filters,
			orderBy: props.orderBy,
			pageLength: props.pageLength,
			auto: true,
	  })

/* ---- custom method mode ---- */
const methodRows = ref([])
const methodMeta = ref({})
const methodHasNext = ref(false)
const methodStart = ref(0)

const methodResource = props.method
	? createResource({
			url: props.method,
			onSuccess(data) {
				const items = Array.isArray(data) ? data : data.items || []
				methodRows.value = methodStart.value === 0 ? items : methodRows.value.concat(items)
				methodMeta.value = Array.isArray(data) ? {} : data
				methodHasNext.value = Array.isArray(data) ? false : !!data.has_next
			},
	  })
	: null

// Quick filters + advanced panel filters both feed the same backend `filters`.
const combinedFilters = computed(() => {
	const quick = props.quickFilters
		.filter((qf) => quickValues[qf.fieldname])
		.map((qf) => ({
			field: qf.fieldname,
			operator: qf.fieldtype === "Data" ? "like" : "=",
			value: quickValues[qf.fieldname],
		}))
	return [...panelFilters.value, ...quick]
})

function fetchMethod() {
	methodResource.submit({
		txt: searchQuery.value,
		start: methodStart.value,
		page_length: pageSize.value,
		filters: JSON.stringify(combinedFilters.value),
		order_by: currentOrderBy(),
	})
}

if (props.method) fetchMethod()

/* ---- unified surface ---- */
const loading = computed(() => (props.method ? methodResource.loading : listResource.list.loading))
const rows = computed(() => (props.method ? methodRows.value : listResource.data || []))
const hasNextPage = computed(() => (props.method ? methodHasNext.value : listResource.hasNextPage))
const meta = computed(() => (props.method ? methodMeta.value : {}))

// Client-side sort layer: makes EVERY column sortable by header click —
// including derived columns (status/party/type) the backend can't order by.
// Server-side order_by still runs for real fields (full-dataset sort); this
// reorders the loaded rows on top so a click always visibly sorts. Empty
// values sink to the bottom in either direction.
const displayRows = computed(() => {
	if (!sortColKey.value) return rows.value
	const key = sortColKey.value
	const dir = sortDir.value === "asc" ? 1 : -1
	return [...rows.value].sort((x, y) => {
		const a = x[key]
		const b = y[key]
		const aEmpty = a === null || a === undefined || a === ""
		const bEmpty = b === null || b === undefined || b === ""
		if (aEmpty && bEmpty) return 0
		if (aEmpty) return 1
		if (bEmpty) return -1
		if (typeof a === "number" && typeof b === "number") return (a - b) * dir
		return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" }) * dir
	})
})

function next() {
	if (props.method) {
		methodStart.value += pageSize.value
		fetchMethod()
	} else {
		listResource.next()
	}
}

// "X of Y+" — total (capped at 1000 by the backend) surfaces via meta.total.
const totalLabel = computed(() => {
	const t = meta.value?.total
	const shown = rows.value.length
	if (t == null) return shown === 1 ? __("1 row") : __("{0} rows", [shown])
	return __("{0} of {1}", [shown, t > 1000 ? "1000+" : t])
})

function onSort(col) {
	const field = col.sortKey || col.key
	if (!field) return
	sortColKey.value = col.key
	if (sortField.value === field) {
		sortDir.value = sortDir.value === "asc" ? "desc" : "asc"
	} else {
		sortField.value = field
		sortDir.value = "asc"
	}
	if (props.method) {
		reloadFirstPage()
	} else {
		listResource.orderBy = currentOrderBy() || props.orderBy
		listResource.start = 0
		listResource.reload()
	}
}

function setPageSize(n) {
	if (pageSize.value === n) return
	pageSize.value = n
	if (props.method) {
		reloadFirstPage()
	} else {
		listResource.pageLength = n
		listResource.start = 0
		listResource.reload()
	}
}

function reloadFirstPage() {
	methodStart.value = 0
	fetchMethod()
}

const onSearch = debounce((value) => {
	searchQuery.value = value
	if (props.method) {
		reloadFirstPage()
	} else {
		listResource.orFilters = value ? props.searchFields.map((f) => [f, "like", `%${value}%`]) : undefined
		listResource.start = 0
		listResource.reload()
	}
}, 300)

function onPanelFilters(filters) {
	panelFilters.value = filters
	reloadFirstPage()
}

function onQuickFilter(qf, value) {
	quickValues[qf.fieldname] = value
	reloadFirstPage()
}

const emit = defineEmits(["row-click"])
function onRowClick(row) {
	// Pages without a detail route can open a modal instead.
	if (props.rowTo) router.push(props.rowTo(row))
	else emit("row-click", row)
}

/* ---- row selection (bulk actions) ---- */
const selectedNames = ref(new Set())

/* Gallery-style selection on mobile: hold a card (~450ms) to enter selection
   mode; while active, taps toggle instead of navigating. Clearing the
   selection (pill ×, bulk action) exits the mode. */
const mobileSelectMode = ref(false)
const pressingRow = ref(null) // dims the held card so the press feels acknowledged
let pressTimer = null
let pressStart = null
let suppressClick = false
function onCardPress(row, e) {
	if (!props.selectable) return
	pressStart = { x: e.clientX, y: e.clientY }
	pressingRow.value = row.name
	clearTimeout(pressTimer)
	pressTimer = setTimeout(() => {
		mobileSelectMode.value = true
		toggleRow(row)
		// Swallow the click that follows the long press — but only briefly, as
		// some browsers never emit it and the flag must not eat the next tap.
		suppressClick = true
		setTimeout(() => (suppressClick = false), 500)
		pressingRow.value = null
		if (navigator.vibrate) navigator.vibrate(15)
	}, 450)
}
function cancelPress() {
	clearTimeout(pressTimer)
	pressTimer = null
	pressStart = null
	pressingRow.value = null
}
function onPressMove(e) {
	// A scroll is not a long press.
	if (!pressStart) return
	if (Math.abs(e.clientX - pressStart.x) > 10 || Math.abs(e.clientY - pressStart.y) > 10) cancelPress()
}
function onCardClick(row) {
	if (suppressClick) {
		suppressClick = false
		return
	}
	if (mobileSelectMode.value) {
		toggleRow(row)
		return
	}
	onRowClick(row)
}
watch(selectedNames, (s) => {
	if (!s.size) mobileSelectMode.value = false
})
const selectedRows = computed(() => rows.value.filter((r) => selectedNames.value.has(r.name)))
const allChecked = computed(
	() => rows.value.length > 0 && rows.value.every((r) => selectedNames.value.has(r.name))
)
function toggleRow(row) {
	const next = new Set(selectedNames.value)
	if (next.has(row.name)) next.delete(row.name)
	else next.add(row.name)
	selectedNames.value = next
}
function toggleAll() {
	selectedNames.value = allChecked.value ? new Set() : new Set(rows.value.map((r) => r.name))
}
function clearSelection() {
	selectedNames.value = new Set()
}
function refresh() {
	clearSelection()
	if (props.method) reloadFirstPage()
	else {
		listResource.start = 0
		listResource.reload()
	}
}
// Pages hold a ref to the list to refresh after modal-based creates.
defineExpose({ refresh })

function formatCell(row, col) {
	const value = row[col.key]
	if (col.format) return col.format(value, row, meta.value)
	return value ?? "—"
}

// Highlight the search term inside a text cell (used only while searching).
function escapeHtml(s) {
	return String(s ?? "").replace(
		/[&<>"']/g,
		(c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
	)
}
function highlightText(text) {
	const t = String(text ?? "")
	const q = searchQuery.value.trim()
	if (!q) return escapeHtml(t)
	const lower = t.toLowerCase()
	const ql = q.toLowerCase()
	let out = ""
	let i = 0
	while (true) {
		const idx = lower.indexOf(ql, i)
		if (idx === -1) {
			out += escapeHtml(t.slice(i))
			break
		}
		out += escapeHtml(t.slice(i, idx))
		out += `<mark class="rounded bg-amber-300 px-0.5 text-gray-900">${escapeHtml(t.slice(idx, idx + q.length))}</mark>`
		i = idx + q.length
	}
	return out
}

watch(
	() => props.filters,
	(f) => {
		if (props.method) return
		listResource.filters = f
		listResource.start = 0
		listResource.reload()
	}
)
</script>

<style scoped>
/* Thin, subtle horizontal scrollbar for the desktop table — matches the app's
   nav scrollbar instead of the browser's chunky default. */
.list-hscroll {
	scrollbar-width: thin;
	scrollbar-color: var(--surface-gray-3) transparent;
}
.list-hscroll::-webkit-scrollbar {
	height: 8px;
}
.list-hscroll::-webkit-scrollbar-thumb {
	background: var(--surface-gray-3);
	border-radius: 9999px;
}
.list-hscroll::-webkit-scrollbar-thumb:hover {
	background: var(--surface-gray-4);
}
.list-hscroll::-webkit-scrollbar-track {
	background: transparent;
}
</style>
