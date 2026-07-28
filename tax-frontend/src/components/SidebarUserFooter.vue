<template>
	<div class="border-t p-3">
		<div class="flex items-center gap-1">
			<div class="min-w-0 flex-1">
				<Dropdown :options="userMenu" placement="top-start">
					<button class="flex w-full items-center gap-2 rounded-md p-1 hover:bg-surface-gray-2">
						<img
							v-if="user?.user_image"
							:src="user.user_image"
							class="h-8 w-8 shrink-0 rounded-full object-cover"
						/>
						<div
							v-else
							class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-xs font-medium text-ink-gray-7"
						>
							{{ initials }}
						</div>
						<div class="min-w-0 flex-1 text-left">
							<div class="truncate text-sm font-medium text-ink-gray-9">{{ displayName }}</div>
						</div>
						<FeatherIcon name="chevron-up" class="h-4 w-4 shrink-0 text-ink-gray-4" />
					</button>
				</Dropdown>
			</div>
			<button
				type="button"
				class="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-ink-gray-6 hover:bg-surface-gray-2 hover:text-ink-gray-9"
				:title="theme === 'dark' ? __('Switch to light mode') : __('Switch to dark mode')"
				:aria-label="theme === 'dark' ? __('Switch to light mode') : __('Switch to dark mode')"
				@click="toggleTheme"
			>
				<FeatherIcon :name="theme === 'dark' ? 'sun' : 'moon'" class="h-4 w-4" />
			</button>
		</div>

		<!-- Language (per-user; the server writes User.language, then we reload) -->
		<Dialog v-model="showLanguage" :options="{ title: __('Language'), size: 'sm' }">
			<template #body-content>
				<div class="flex flex-col gap-1 py-1">
					<button
						v-for="lang in languages"
						:key="lang.value"
						type="button"
						class="flex items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors"
						:class="
							lang.value === currentLang
								? 'bg-surface-gray-2 font-medium text-ink-gray-9'
								: 'text-ink-gray-7 hover:bg-surface-gray-1'
						"
						:disabled="!!languageSaving"
						@click="chooseLanguage(lang.value)"
					>
						<FeatherIcon
							:name="languageSaving === lang.value ? 'loader' : 'check'"
							class="h-4 w-4 shrink-0"
							:class="[
								languageSaving === lang.value ? 'animate-spin text-ink-gray-5' : '',
								lang.value === currentLang && !languageSaving ? 'text-ink-gray-7' : '',
								lang.value !== currentLang && languageSaving !== lang.value ? 'invisible' : '',
							]"
						/>
						<span class="min-w-0 flex-1 truncate">{{ lang.label }}</span>
					</button>
					<div v-if="languageError" class="px-3 pt-1 text-xs text-ink-red-3">{{ languageError }}</div>
					<div class="px-3 pt-2 text-xs text-ink-gray-4">
						{{ __("The page reloads to apply the language. It also applies in Desk.") }}
					</div>
				</div>
			</template>
		</Dialog>

		<AboutDialog v-model="aboutOpen" />
	</div>
</template>

<script setup>
// The sidebar account menu + light/dark toggle, matching the other ERPbio SPAs'
// footer (avatar → name → chevron, theme toggle on the right).
//
// Modelled on erpbio_general's accounting-frontend/SidebarUserFooter.vue but
// deliberately NOT a copy of it: most of that menu is erpbio_general-coupled and
// cannot work in a standalone install of this app —
//   * the Apps launcher flyout reads erpbio_general's launcherApps resource,
//   * Send Feedback posts to erpbio_general.api.feedback,
//   * "Open ERPbio Mobile" is an erpbio_general route,
//   * "Customize Sidebar" drives a per-workspace nav-layout system this app has
//     no equivalent of (7 nav items in 4 groups, no rail, nothing to customize),
//   * "Install as app" needs a PWA manifest this app doesn't ship.
// What remains is what works on core alone: Desk, language, about, log out.
import { computed, inject, ref } from "vue"
import { Dialog, Dropdown, FeatherIcon, call } from "frappe-ui"
import { useTheme } from "@/composables/useTheme"
import AboutDialog from "@/components/AboutDialog.vue"

const __ = inject("$translate")
const session = inject("$session")
const user = inject("$user", null)
const { theme, toggleTheme } = useTheme()

const displayName = computed(() => user?.full_name || user?.name || session?.user || "")
const initials = computed(() =>
	displayName.value
		.split(" ")
		.map((w) => w[0])
		.slice(0, 2)
		.join("")
		.toUpperCase()
)

const aboutOpen = ref(false)

const userMenu = computed(() => [
	{ label: __("Switch to Desk"), icon: "monitor", onClick: () => (window.location.href = "/app") },
	{ label: languageMenuLabel.value, icon: "globe", onClick: openLanguage },
	{ label: __("About"), icon: "info", onClick: () => (aboutOpen.value = true) },
	{ label: __("Log out"), icon: "log-out", onClick: () => session.logout() },
])

// --- Language switcher (api.tax sets User.language server-side; we reload
// because the catalog is baked into the server-rendered boot).
const showLanguage = ref(false)
const languages = ref([])
const languageSaving = ref("")
const languageError = ref("")
const currentLang = computed(() => window.frappe?.boot?.lang || "en")
const LANGUAGE_NAMES = { en: "English", id: "Indonesia" }
const languageMenuLabel = computed(() => {
	const name =
		languages.value.find((l) => l.value === currentLang.value)?.label || LANGUAGE_NAMES[currentLang.value]
	return name ? `${__("Language")} · ${name}` : __("Language")
})

async function openLanguage() {
	showLanguage.value = true
	languageError.value = ""
	if (languages.value.length) return
	try {
		languages.value = await call("erpbio_indonesia_localization.api.tax.get_languages")
	} catch (e) {
		languageError.value = e?.messages?.[0] || e?.message || __("Could not load languages.")
	}
}

async function chooseLanguage(code) {
	if (code === currentLang.value) {
		showLanguage.value = false
		return
	}
	languageSaving.value = code
	languageError.value = ""
	try {
		await call("erpbio_indonesia_localization.api.tax.set_language", { lang: code })
		window.location.reload()
	} catch (e) {
		languageError.value = e?.messages?.[0] || e?.message || __("Could not change the language.")
		languageSaving.value = ""
	}
}
</script>
