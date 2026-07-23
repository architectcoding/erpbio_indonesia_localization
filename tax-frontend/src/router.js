import { createRouter, createWebHistory } from "vue-router"
import { session } from "./session"

const routes = [
	{ path: "/", redirect: "/exports" },
	{ path: "/login", name: "Login", component: () => import("@/pages/Login.vue") },
	{ path: "/exports", name: "ExportList", component: () => import("@/pages/ExportList.vue") },
	{ path: "/exports/:name", name: "ExportDetail", component: () => import("@/pages/ExportDetail.vue"), props: true },
	{ path: "/imports", name: "ImportList", component: () => import("@/pages/ImportList.vue") },
	{ path: "/imports/:name", name: "ImportDetail", component: () => import("@/pages/ImportDetail.vue"), props: true },
	{ path: "/reports/ppn-keluaran", name: "PpnKeluaran", component: () => import("@/pages/PpnKeluaran.vue") },
	{ path: "/settings", name: "Settings", component: () => import("@/pages/Settings.vue") },
]

const router = createRouter({
	history: createWebHistory("/erpbio-tax"),
	routes,
})

router.beforeEach((to, _from, next) => {
	if (to.name !== "Login" && !session.isLoggedIn) {
		next({ name: "Login" })
	} else if (to.name === "Login" && session.isLoggedIn) {
		next({ path: "/" })
	} else {
		next()
	}
})

export default router
