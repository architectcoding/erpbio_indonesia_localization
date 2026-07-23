import { computed, reactive } from "vue"
import { call } from "frappe-ui"

export function sessionUser() {
	const cookies = new URLSearchParams(document.cookie.split("; ").join("&"))
	let user = cookies.get("user_id")
	if (user === "Guest") user = null
	return user
}

export const session = reactive({
	user: sessionUser(),
	isLoggedIn: computed(() => !!session.user),
	async login(email, password) {
		const response = await call("login", { usr: email, pwd: password })
		if (response.message === "Logged In") {
			session.user = sessionUser()
			window.location.reload()
		}
		return response
	},
	async logout() {
		await call("logout")
		session.user = sessionUser()
		window.location.reload()
	},
})
