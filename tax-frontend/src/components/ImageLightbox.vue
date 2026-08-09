<template>
	<!-- In-app image gallery. Teleported so it can't be trapped (or clipped) by
	     whatever card the thumbnail sits in — opening a photo shouldn't kick you
	     out to the raw file URL and lose the page you were reading. -->
	<Teleport to="body">
		<div v-if="modelValue !== null && images.length" class="fixed inset-0 flex flex-col bg-black/90" :class="zClass"
			@click.self="close">
			<div class="flex items-center justify-between p-3 text-white">
				<span class="text-sm tabular-nums">{{ modelValue + 1 }} / {{ images.length }}</span>
				<div class="flex items-center gap-4">
					<a :href="current" :download="downloadName" class="inline-flex items-center gap-1 text-sm hover:underline">
						<FeatherIcon name="download" class="h-4 w-4" /> {{ __("Download") }}
					</a>
					<button type="button" :title="__('Close')" @click="close">
						<FeatherIcon name="x" class="h-6 w-6" />
					</button>
				</div>
			</div>

			<div class="flex flex-1 items-center justify-center overflow-hidden p-2">
				<button v-if="images.length > 1" type="button" class="shrink-0 p-2 text-white/80 hover:text-white"
					:title="__('Previous')" @click.stop="step(-1)">
					<FeatherIcon name="chevron-left" class="h-8 w-8" />
				</button>
				<img :src="current" class="max-h-full max-w-full object-contain" @click.stop />
				<button v-if="images.length > 1" type="button" class="shrink-0 p-2 text-white/80 hover:text-white"
					:title="__('Next')" @click.stop="step(1)">
					<FeatherIcon name="chevron-right" class="h-8 w-8" />
				</button>
			</div>

			<!-- filmstrip: jump straight to a photo when there are several -->
			<div v-if="images.length > 1" class="flex justify-center gap-1.5 overflow-x-auto p-3">
				<button v-for="(img, i) in images" :key="i" type="button" @click.stop="emit('update:modelValue', i)">
					<img :src="img" loading="lazy" class="h-12 w-12 rounded object-cover ring-2 transition"
						:class="i === modelValue ? 'ring-white' : 'opacity-60 ring-transparent hover:opacity-100'" />
				</button>
			</div>
		</div>
	</Teleport>
</template>

<script setup>
import { computed, inject, onMounted, onUnmounted } from "vue"
import { FeatherIcon } from "frappe-ui"

const props = defineProps({
	// index of the open image, or null when closed
	modelValue: { type: Number, default: null },
	images: { type: Array, default: () => [] }, // image urls
	downloadPrefix: { type: String, default: "image" },
	// Callers that live above z-60 themselves must raise this, or the viewer
	// opens behind whatever opened it. Kept a class rather than a number so it
	// stays in Tailwind's z-scale with the rest of the app's layering.
	zClass: { type: String, default: "z-[60]" },
})
const emit = defineEmits(["update:modelValue"])
const __ = inject("$translate", (s) => s)

const current = computed(() => props.images[props.modelValue] || "")
const downloadName = computed(() => `${props.downloadPrefix}-${(props.modelValue ?? 0) + 1}.jpg`)

function close() {
	emit("update:modelValue", null)
}
function step(dir) {
	const n = props.images.length
	if (!n) return
	emit("update:modelValue", (props.modelValue + dir + n) % n)
}

function onKeydown(e) {
	if (props.modelValue === null) return
	if (e.key === "Escape") close()
	else if (e.key === "ArrowLeft") step(-1)
	else if (e.key === "ArrowRight") step(1)
}
onMounted(() => window.addEventListener("keydown", onKeydown))
onUnmounted(() => window.removeEventListener("keydown", onKeydown))
</script>
