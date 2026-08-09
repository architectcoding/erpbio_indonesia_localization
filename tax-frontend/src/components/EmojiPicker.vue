<template>
	<div
		ref="rootEl"
		class="flex w-[17.5rem] max-w-[calc(100vw-2rem)] flex-col overflow-hidden rounded-lg border bg-surface-white shadow-lg"
	>
		<div class="shrink-0 border-b p-1.5">
			<input
				ref="searchEl"
				v-model="query"
				type="text"
				class="form-input h-7 w-full text-sm"
				:placeholder="__('Search emoji')"
				@keydown.esc.stop.prevent="emit('close')"
				@keydown.enter.prevent="pickFirst"
			/>
		</div>

		<!-- Category strip. Hidden while searching, because the results are drawn
		     from every category and highlighting one would be a lie. -->
		<div v-if="!query.trim()" class="flex shrink-0 items-center gap-0.5 border-b px-1.5 py-1">
			<button
				v-for="c in tabs"
				:key="c.key"
				type="button"
				class="flex h-6 w-6 items-center justify-center rounded"
				:class="c.key === activeTab ? 'bg-surface-gray-3 text-ink-gray-9' : 'text-ink-gray-5 hover:bg-surface-gray-2'"
				:title="__(c.label)"
				@click="activeTab = c.key"
			>
				<FeatherIcon :name="c.icon" class="h-3.5 w-3.5" />
			</button>
		</div>

		<!-- Fixed height, deliberately not flex-1: the picker sits above a composer
		     in a 32rem window, and a grid that sizes to its content grows tall
		     enough to cover the window's own header. -->
		<div class="h-52 overflow-y-auto p-1.5">
			<p v-if="visible.length === 0" class="py-8 text-center text-xs text-ink-gray-5">
				{{ __("No emoji found.") }}
			</p>
			<div v-else class="grid grid-cols-8 gap-0.5">
				<button
					v-for="e in visible"
					:key="e.char"
					type="button"
					class="flex h-7 w-7 items-center justify-center rounded text-lg leading-none hover:bg-surface-gray-2"
					:title="e.keywords"
					@click="pick(e)"
				>{{ e.char }}</button>
			</div>
		</div>
	</div>
</template>

<script setup>
// Emoji picker for the chat composer.
//
// Reaches for the curated set in data/emoji.js rather than emoji-mart, which
// Raven's own frontend uses — see the note there for why the dependency is not
// worth paying for eight times over in this shared component.
import { computed, inject, nextTick, onMounted, ref } from "vue"
import { FeatherIcon } from "frappe-ui"
import { EMOJI_CATEGORIES, ALL_EMOJI, searchEmoji } from "@/data/emoji"
import { useStoredRef } from "@/composables/useStoredRef"

const __ = inject("$translate")
const emit = defineEmits(["select", "close"])

const rootEl = ref(null)
const searchEl = ref(null)
const query = ref("")

// Characters, not objects: the stored shape then survives an edit to the emoji
// list, and a character that has since been dropped simply resolves to nothing.
const recent = useStoredRef("erpbio-chat-emoji-recent", [])
const RECENT_LIMIT = 24

const recentEmojis = computed(() =>
	recent.value.map((char) => ALL_EMOJI.find((e) => e.char === char)).filter(Boolean)
)

const tabs = computed(() => [
	// The recents tab only exists once there are recents — an empty first tab
	// that the picker also opens on would show a blank grid on first use.
	...(recentEmojis.value.length ? [{ key: "recent", label: "Recent", icon: "clock" }] : []),
	...EMOJI_CATEGORIES.map((c) => ({ key: c.key, label: c.label, icon: c.icon })),
])

const activeTab = ref(recent.value.length ? "recent" : EMOJI_CATEGORIES[0].key)

const visible = computed(() => {
	if (query.value.trim()) return searchEmoji(query.value)
	if (activeTab.value === "recent") return recentEmojis.value
	return EMOJI_CATEGORIES.find((c) => c.key === activeTab.value)?.emojis || []
})

function pick(e) {
	recent.value = [e.char, ...recent.value.filter((c) => c !== e.char)].slice(0, RECENT_LIMIT)
	emit("select", e.char)
}

function pickFirst() {
	if (visible.value.length) pick(visible.value[0])
}

onMounted(() => {
	// Type-to-search without a click first. nextTick because the popover is
	// mounted by a v-if in the same flush.
	nextTick(() => searchEl.value?.focus())
})
</script>
