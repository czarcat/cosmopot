import type { RouteRecordRaw } from "vue-router";

export const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "dashboard",
    component: () => import("@/views/dashboard/DashboardView.vue"),
    meta: {
      requiresAuth: true,
      title: "Dashboard",
    },
  },
  {
    path: "/settings",
    name: "settings",
    component: () => import("@/views/dashboard/SettingsView.vue"),
    meta: {
      requiresAuth: true,
      title: "Settings",
    },
  },
  {
    path: "/auth/login",
    name: "login",
    component: () => import("@/views/auth/LoginView.vue"),
    meta: {
      guestOnly: true,
      title: "Sign In",
    },
  },
  {
    path: "/:pathMatch(.*)*",
    name: "not-found",
    component: () => import("@/views/errors/NotFoundView.vue"),
    meta: {
      title: "Page not found",
    },
  },
];

export default routes;
