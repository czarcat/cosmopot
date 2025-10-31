<template>
  <div class="dashboard-shell">
    <header class="dashboard-shell__header">
      <slot name="header" />
    </header>

    <aside
      v-if="$slots.sidebar"
      class="dashboard-shell__sidebar"
      aria-label="Sidebar navigation"
    >
      <slot name="sidebar" />
    </aside>

    <main class="dashboard-shell__main" aria-live="polite">
      <slot />
    </main>

    <footer class="dashboard-shell__footer">
      <slot name="footer" />
    </footer>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped>
.dashboard-shell {
  min-height: 100vh;
  display: grid;
  grid-template-areas:
    "header"
    "main"
    "footer";
  grid-template-rows: auto 1fr auto;
  background: var(--surface-subtle);
  color: var(--text-primary);
}

.dashboard-shell__header {
  grid-area: header;
  backdrop-filter: blur(8px);
  background: var(--surface-elevated);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 10;
}

.dashboard-shell__sidebar {
  grid-area: sidebar;
  border-right: 1px solid var(--border-subtle);
  background: var(--surface-base);
  padding: var(--space-6) var(--space-4);
}

.dashboard-shell__main {
  grid-area: main;
  padding: var(--space-6) clamp(var(--space-4), 5vw, var(--space-10));
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.dashboard-shell__footer {
  grid-area: footer;
  border-top: 1px solid var(--border-subtle);
  background: var(--surface-elevated);
  padding: var(--space-4) clamp(var(--space-4), 5vw, var(--space-10));
}

@media (min-width: 992px) {
  .dashboard-shell {
    grid-template-columns: 260px 1fr;
    grid-template-areas:
      "sidebar header"
      "sidebar main"
      "sidebar footer";
  }

  .dashboard-shell__header {
    position: sticky;
    top: 0;
  }

  .dashboard-shell__sidebar {
    position: sticky;
    top: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
}
</style>
