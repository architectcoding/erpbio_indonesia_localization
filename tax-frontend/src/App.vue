<template>
	<AppShell v-if="session.isLoggedIn">
		<RouterView />
	</AppShell>
	<RouterView v-else />
</template>

<script setup>
import { inject } from "vue"
import { RouterView } from "vue-router"
import AppShell from "@/components/AppShell.vue"

const session = inject("$session")
</script>
