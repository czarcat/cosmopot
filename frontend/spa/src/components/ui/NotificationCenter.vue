<template>
  <transition-group
    name="notification"
    tag="section"
    class="notification-center"
    aria-live="assertive"
  >
    <article
      v-for="notification in notifications"
      :key="notification.id"
      class="notification"
      :class="`notification--${notification.variant}`"
      role="status"
    >
      <div class="notification__content">
        <span class="notification__icon" aria-hidden="true">{{
          iconFor(notification.variant)
        }}</span>
        <div class="notification__body">
          <p class="notification__message">{{ notification.message }}</p>
          <p v-if="notification.detail" class="notification__detail">
            {{ notification.detail }}
          </p>
        </div>
      </div>
      <button
        class="notification__dismiss"
        type="button"
        @click="dismiss(notification.id)"
      >
        <span class="sr-only">Dismiss notification</span>
        ×
      </button>
    </article>
  </transition-group>
</template>

<script setup lang="ts">
import { storeToRefs } from "pinia";

import { NotificationVariant, useNotificationsStore } from "@/stores/notifications";

const store = useNotificationsStore();
const { active: notifications } = storeToRefs(store);

const dismiss = (id: string) => store.dismiss(id);

const iconFor = (variant: NotificationVariant) => {
  switch (variant) {
    case "success":
      return "✔";
    case "warning":
      return "⚠";
    case "error":
      return "⛔";
    default:
      return "ℹ";
  }
};
</script>

<style scoped>
.notification-center {
  position: fixed;
  inset-inline-end: var(--space-6);
  inset-block-start: var(--space-6);
  display: grid;
  gap: var(--space-3);
  z-index: 50;
  max-inline-size: min(360px, 90vw);
}

.notification {
  background: var(--surface-elevated);
  border: 1px solid var(--border-subtle);
  border-inline-start: 4px solid var(--accent-base);
  border-radius: var(--radius-lg);
  padding: var(--space-4);
  display: flex;
  align-items: center;
  gap: var(--space-4);
  box-shadow: var(--shadow-md);
  color: var(--text-primary);
}

.notification__content {
  display: flex;
  gap: var(--space-3);
  align-items: flex-start;
  flex: 1;
}

.notification__icon {
  font-size: 1.25rem;
}

.notification__body {
  display: grid;
  gap: var(--space-1);
}

.notification__message {
  font-weight: 600;
}

.notification__detail {
  font-size: 0.85rem;
  color: var(--text-muted);
}

.notification__dismiss {
  appearance: none;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font-size: 1.25rem;
  line-height: 1;
}

.notification--success {
  border-inline-start-color: var(--success-base);
}

.notification--warning {
  border-inline-start-color: var(--warning-base);
}

.notification--error {
  border-inline-start-color: var(--danger-base);
}

.notification-enter-active,
.notification-leave-active {
  transition: all 200ms ease;
}
.notification-enter-from,
.notification-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

@media (max-width: 480px) {
  .notification-center {
    inset-inline: var(--space-4);
    inset-block-start: var(--space-4);
  }
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
