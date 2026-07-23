<template>
	<div class="flex h-screen items-center justify-center bg-surface-gray-1 p-4">
		<div class="w-full max-w-sm rounded-lg border bg-surface-white p-6">
			<h1 class="mb-1 text-lg font-semibold text-ink-gray-9">{{ __("ERPbio Tax") }}</h1>
			<p class="mb-4 text-sm text-ink-gray-5">{{ __("Sign in to manage e-Faktur compliance.") }}</p>
			<form class="flex flex-col gap-3" @submit.prevent="submit">
				<FormControl type="email" :label="__('Email')" v-model="email" autocomplete="username" required />
				<FormControl type="password" :label="__('Password')" v-model="password" autocomplete="current-password" required />
				<Button variant="solid" :loading="busy" type="submit">{{ __("Log In") }}</Button>
				<p v-if="errorMessage" class="text-sm text-ink-red-3">{{ errorMessage }}</p>
			</form>
		</div>
	</div>
</template>

<script setup>
import { inject, ref } from "vue"

const session = inject("$session")
const __ = inject("$translate")

const email = ref("")
const password = ref("")
const busy = ref(false)
const errorMessage = ref("")

async function submit() {
	busy.value = true
	errorMessage.value = ""
	try {
		await session.login(email.value, password.value)
	} catch (e) {
		errorMessage.value = e?.messages?.[0] || __("Invalid login. Please try again.")
	} finally {
		busy.value = false
	}
}
</script>
