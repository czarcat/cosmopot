<template>
  <section class="login-view">
    <div class="login-view__card" role="form">
      <header class="login-view__header">
        <h1>Sign in</h1>
        <p>
          Authenticate to manage sessions, inspect metrics, and debug production
          traffic.
        </p>
      </header>

      <form @submit.prevent="handleSubmit" class="login-view__form">
        <label class="login-view__field">
          <span>Email</span>
          <input
            v-model="email"
            type="email"
            name="email"
            autocomplete="email"
            required
          >
        </label>

        <label class="login-view__field">
          <span>Password</span>
          <input
            v-model="password"
            type="password"
            name="password"
            autocomplete="current-password"
            required
          >
        </label>

        <button type="submit" class="login-view__submit" :disabled="isSubmitting">
          {{ isSubmitting ? "Signing in…" : "Sign in" }}
        </button>
      </form>

      <p class="login-view__hint">
        Need an account? API registration is available at
        <a
          :href="`${apiBaseUrl}/v1/auth/register`"
          target="_blank"
          rel="noreferrer noopener"
          >/api/v1/auth/register</a
        >
      </p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import { useAuthStore } from "@/stores/auth";
import { useNotificationsStore } from "@/stores/notifications";

const router = useRouter();
const route = useRoute();
const auth = useAuthStore();
const notifications = useNotificationsStore();

const email = ref("");
const password = ref("");
const isSubmitting = ref(false);
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

const handleSubmit = async () => {
  if (isSubmitting.value) return;
  isSubmitting.value = true;
  try {
    await auth.login({ email: email.value, password: password.value });
    notifications.push({
      message: "Signed in successfully",
      variant: "success",
      timeout: 4000,
    });
    const redirect = route.query.redirect;
    if (typeof redirect === "string") {
      await router.replace(redirect);
    } else {
      await router.replace({ name: "dashboard" });
    }
  } catch (error) {
    notifications.push({
      message: "Unable to sign in",
      variant: "error",
      detail: "Check your credentials and try again.",
    });
  } finally {
    isSubmitting.value = false;
  }
};
</script>

<style scoped>
.login-view {
  min-height: clamp(70vh, 80vh, 100%);
  display: grid;
  place-items: center;
  padding-block: var(--space-10);
}

.login-view__card {
  max-inline-size: 420px;
  width: min(100%, 420px);
  border-radius: var(--radius-2xl);
  border: 1px solid var(--border-subtle);
  padding: var(--space-10) clamp(var(--space-6), 5vw, var(--space-10));
  background: var(--surface-base);
  box-shadow: var(--shadow-md);
  display: grid;
  gap: var(--space-6);
}

.login-view__header h1 {
  font-size: 1.75rem;
  font-weight: 600;
}

.login-view__header p {
  color: var(--text-muted);
}

.login-view__form {
  display: grid;
  gap: var(--space-4);
}

.login-view__field {
  display: grid;
  gap: var(--space-2);
  font-weight: 500;
}

.login-view__field input {
  border-radius: var(--radius-lg);
  border: 1px solid var(--border-subtle);
  padding: var(--space-3);
  background: var(--surface-subtle);
}

.login-view__field input:focus-visible {
  outline: 2px solid var(--accent-base);
  outline-offset: 2px;
}

.login-view__submit {
  border: none;
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  background: linear-gradient(135deg, var(--accent-base), var(--accent-emphasis));
  color: var(--surface-base);
  font-weight: 600;
  cursor: pointer;
}

.login-view__submit:disabled {
  opacity: 0.65;
  cursor: progress;
}

.login-view__hint {
  color: var(--text-muted);
  font-size: 0.85rem;
}

.login-view__hint a {
  color: inherit;
}
</style>
