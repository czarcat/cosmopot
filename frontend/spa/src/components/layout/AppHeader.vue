<template>
  <div class="app-header">
    <RouterLink class="app-header__brand" to="/">
      <span class="app-header__logo" aria-hidden="true">⚡</span>
      <span class="app-header__title">Platform Control Center</span>
    </RouterLink>

    <nav class="app-header__nav" aria-label="Primary navigation">
      <RouterLink class="app-header__nav-link" to="/">Dashboard</RouterLink>
      <RouterLink class="app-header__nav-link" to="/settings">Settings</RouterLink>
    </nav>

    <div class="app-header__actions">
      <div v-if="isAuthenticated" class="app-header__user">
        <span class="app-header__avatar" aria-hidden="true">
          {{ displayInitials }}
        </span>
        <div class="app-header__user-details">
          <span class="app-header__user-name">{{ auth.user?.email }}</span>
          <small class="app-header__user-role">Active session</small>
        </div>
        <button class="app-header__signout" type="button" @click="handleLogout">
          Sign out
        </button>
      </div>
      <RouterLink v-else class="app-header__signin" to="/auth/login"
        >Sign in</RouterLink
      >
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";

const router = useRouter();
const auth = useAuthStore();

const isAuthenticated = computed(() => auth.isAuthenticated);

const displayInitials = computed(() => {
  const email = auth.user?.email ?? "";
  return email.slice(0, 2).toUpperCase() || "US";
});

const handleLogout = async () => {
  await auth.logout();
  await router.push({ name: "login" });
};
</script>

<style scoped>
.app-header {
  margin: 0 auto;
  max-width: var(--layout-max-width);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  padding: var(--space-4) clamp(var(--space-4), 4vw, var(--space-10));
}

.app-header__brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: 600;
  text-decoration: none;
  color: inherit;
}

.app-header__logo {
  display: grid;
  place-content: center;
  inline-size: 2.4rem;
  block-size: 2.4rem;
  border-radius: 0.8rem;
  background: linear-gradient(135deg, var(--accent-emphasis), var(--accent-base));
  color: var(--surface-base);
}

.app-header__title {
  font-size: 1.1rem;
  letter-spacing: -0.01em;
}

.app-header__nav {
  display: none;
  align-items: center;
  gap: var(--space-4);
  margin-left: auto;
}

.app-header__nav-link {
  font-weight: 500;
  color: var(--text-muted);
  text-decoration: none;
  transition: color 160ms ease;
}

.app-header__nav-link.router-link-exact-active,
.app-header__nav-link:hover {
  color: var(--text-primary);
}

.app-header__actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.app-header__user {
  display: inline-flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-lg);
  background: var(--surface-base);
  border: 1px solid var(--border-subtle);
}

.app-header__avatar {
  inline-size: 2.25rem;
  block-size: 2.25rem;
  border-radius: 999px;
  background: var(--accent-subtle);
  display: grid;
  place-content: center;
  font-weight: 600;
  color: var(--accent-emphasis);
}

.app-header__user-details {
  display: none;
  flex-direction: column;
}

.app-header__user-name {
  font-size: 0.95rem;
  font-weight: 600;
}

.app-header__user-role {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.app-header__signout,
.app-header__signin {
  font-weight: 600;
  border: none;
  cursor: pointer;
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  background: var(--surface-strong);
  color: var(--text-primary);
  text-decoration: none;
  transition: background 160ms ease;
}

.app-header__signout:hover,
.app-header__signin:hover {
  background: var(--surface-highlight);
}

@media (min-width: 768px) {
  .app-header__nav {
    display: inline-flex;
  }

  .app-header__user-details {
    display: inline-flex;
  }
}
</style>
