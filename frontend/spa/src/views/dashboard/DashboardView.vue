<template>
  <section class="dashboard-view">
    <header class="dashboard-view__heading">
      <div>
        <h1 class="dashboard-view__title">Welcome back, {{ headlineName }}</h1>
        <p class="dashboard-view__subtitle">
          Monitor system health, track job throughput, and triage alerts without leaving
          the browser.
        </p>
      </div>
      <button
        class="dashboard-view__cta"
        type="button"
        @click="refreshNow"
        :disabled="isRefreshing"
      >
        {{ isRefreshing ? "Refreshing…" : "Refresh session" }}
      </button>
    </header>

    <div class="dashboard-grid">
      <section class="dashboard-card dashboard-card--span-2">
        <header class="dashboard-card__header">
          <h2>Environment snapshot</h2>
          <span class="dashboard-chip" :class="`dashboard-chip--${environmentVariant}`">
            {{ environmentLabel }}
          </span>
        </header>
        <dl class="snapshot">
          <div class="snapshot__item">
            <dt>Active session</dt>
            <dd>{{ sessionSummary }}</dd>
          </div>
          <div class="snapshot__item">
            <dt>Access token expires in</dt>
            <dd>{{ accessExpiryMessage }}</dd>
          </div>
          <div class="snapshot__item">
            <dt>API origin</dt>
            <dd>{{ apiBaseUrl }}</dd>
          </div>
        </dl>
      </section>

      <section class="dashboard-card">
        <header class="dashboard-card__header">
          <h2>Task throughput</h2>
        </header>
        <p class="dashboard-card__metric">
          128<span class="dashboard-card__suffix">/min</span>
        </p>
        <p class="dashboard-card__legend">Average computed over the last 15 minutes</p>
      </section>

      <section class="dashboard-card">
        <header class="dashboard-card__header">
          <h2>Queue depth</h2>
        </header>
        <p class="dashboard-card__metric">
          42<span class="dashboard-card__suffix">jobs</span>
        </p>
        <p class="dashboard-card__legend">
          Waiting tasks across high and default priorities
        </p>
      </section>

      <section class="dashboard-card">
        <header class="dashboard-card__header">
          <h2>Alerts</h2>
        </header>
        <ul class="dashboard-list">
          <li>
            <span class="dashboard-dot dashboard-dot--success"></span>
            Worker latency within SLO
          </li>
          <li>
            <span class="dashboard-dot dashboard-dot--warning"></span>
            RabbitMQ nearing memory watermark
          </li>
          <li>
            <span class="dashboard-dot dashboard-dot--error"></span>
            Investigate spike in failed sessions
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import { useAuthStore } from "@/stores/auth";

const auth = useAuthStore();
const isRefreshing = ref(false);

const headlineName = computed(() => auth.user?.email?.split("@")[0] ?? "operator");
const environmentLabel = computed(() => import.meta.env.MODE);
const environmentVariant = computed(() =>
  environmentLabel.value === "production" ? "danger" : "success",
);
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? "/api";

const sessionSummary = computed(() => {
  if (!auth.user) return "Not signed in";
  return `${auth.user.email} · session ${auth.sessionId ?? "unknown"}`;
});

const accessExpiryMessage = computed(() => {
  const seconds = auth.accessTokenRemaining;
  if (seconds <= 0) return "expired";
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes}m ${seconds % 60}s`;
});

const refreshNow = async () => {
  if (isRefreshing.value) return;
  isRefreshing.value = true;
  try {
    await auth.refreshTokens();
  } finally {
    isRefreshing.value = false;
  }
};

onMounted(async () => {
  if (!auth.user) {
    try {
      await auth.fetchCurrentUser();
    } catch (error) {
      console.error("Failed to load user", error);
    }
  }
});
</script>

<style scoped>
.dashboard-view {
  display: grid;
  gap: var(--space-6);
}

.dashboard-view__heading {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  align-items: flex-start;
}

.dashboard-view__title {
  font-size: clamp(1.75rem, 3vw, 2.1rem);
  font-weight: 600;
  letter-spacing: -0.015em;
}

.dashboard-view__subtitle {
  color: var(--text-muted);
  max-inline-size: 52ch;
}

.dashboard-view__cta {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  border-radius: var(--radius-md);
  border: 1px solid var(--accent-base);
  background: var(--accent-subtle);
  color: var(--accent-emphasis);
  font-weight: 600;
  cursor: pointer;
  transition:
    transform 160ms ease,
    box-shadow 160ms ease;
}

.dashboard-view__cta:disabled {
  opacity: 0.6;
  cursor: progress;
}

.dashboard-view__cta:not(:disabled):hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.dashboard-grid {
  display: grid;
  gap: var(--space-5);
}

.dashboard-card {
  background: var(--surface-base);
  border-radius: var(--radius-xl);
  padding: var(--space-5);
  border: 1px solid var(--border-subtle);
  box-shadow: var(--shadow-xs);
  display: grid;
  gap: var(--space-4);
}

.dashboard-card--span-2 {
  grid-column: span 1;
}

.dashboard-card__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dashboard-chip {
  padding: 0.25rem 0.65rem;
  border-radius: 999px;
  font-size: 0.8rem;
  font-weight: 600;
  border: 1px solid transparent;
}

.dashboard-chip--success {
  background: var(--success-subtle);
  color: var(--success-emphasis);
  border-color: var(--success-base);
}

.dashboard-chip--danger {
  background: var(--danger-subtle);
  color: var(--danger-emphasis);
  border-color: var(--danger-base);
}

.snapshot {
  display: grid;
  gap: var(--space-3);
}

.snapshot__item dt {
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.14em;
  color: var(--text-muted);
}

.snapshot__item dd {
  font-size: 1rem;
  font-weight: 600;
}

.dashboard-card__metric {
  font-size: clamp(2.25rem, 8vw, 3.25rem);
  font-weight: 700;
  line-height: 1;
}

.dashboard-card__suffix {
  font-size: 1rem;
  font-weight: 500;
  margin-left: 0.5rem;
  color: var(--text-muted);
}

.dashboard-card__legend {
  color: var(--text-muted);
  font-size: 0.9rem;
}

.dashboard-list {
  display: grid;
  gap: var(--space-3);
  list-style: none;
  padding: 0;
  margin: 0;
}

.dashboard-dot {
  inline-size: 0.75rem;
  block-size: 0.75rem;
  border-radius: 999px;
  display: inline-block;
  margin-inline-end: 0.65rem;
}

.dashboard-dot--success {
  background: var(--success-base);
}

.dashboard-dot--warning {
  background: var(--warning-base);
}

.dashboard-dot--error {
  background: var(--danger-base);
}

@media (min-width: 768px) {
  .dashboard-view__heading {
    flex-direction: row;
    align-items: center;
  }

  .dashboard-grid {
    grid-template-columns: repeat(12, minmax(0, 1fr));
  }

  .dashboard-card--span-2 {
    grid-column: span 8;
  }

  .dashboard-card:nth-of-type(2),
  .dashboard-card:nth-of-type(3),
  .dashboard-card:nth-of-type(4) {
    grid-column: span 4;
  }
}

@media (min-width: 1200px) {
  .dashboard-card--span-2 {
    grid-column: span 6;
  }

  .dashboard-card:nth-of-type(2),
  .dashboard-card:nth-of-type(3),
  .dashboard-card:nth-of-type(4) {
    grid-column: span 3;
  }
}
</style>
