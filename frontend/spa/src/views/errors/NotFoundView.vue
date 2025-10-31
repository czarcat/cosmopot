<template>
  <section class="not-found">
    <h1>Page not found</h1>
    <p>
      The resource you are looking for might have been removed or is temporarily
      unavailable.
    </p>
    <RouterLink class="not-found__cta" to="/">Return to dashboard</RouterLink>
  </section>
</template>

<script setup lang="ts">
import { RouterLink } from "vue-router";
</script>

<style scoped>
.not-found {
  text-align: center;
  padding: var(--space-16) var(--space-6);
  display: grid;
  gap: var(--space-4);
  justify-items: center;
}

.not-found h1 {
  font-size: clamp(2rem, 4vw, 2.6rem);
}

.not-found__cta {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-4);
  background: var(--surface-strong);
  border-radius: var(--radius-md);
  text-decoration: none;
  color: inherit;
  font-weight: 600;
}
</style>
