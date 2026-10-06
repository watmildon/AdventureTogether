<script setup lang="ts">
/**
 * One header for both surfaces. Participant routes get the brand plus a small "Back office"
 * link; back-office routes get a "Back office" title and a link back to the participant side.
 */
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

const route = useRoute()
const isBackoffice = computed(() => route.path.startsWith('/backoffice'))
</script>

<template>
  <header :class="['app-header', { backoffice: isBackoffice }]">
    <div class="header-container">
      <template v-if="isBackoffice">
        <RouterLink to="/backoffice" class="brand-link">
          <span class="brand-logo">🗺️</span>
          <span class="brand-title">AdventureTogether</span>
          <span class="area-title">Back office</span>
        </RouterLink>

        <nav class="header-nav">
          <RouterLink to="/backoffice" class="nav-item">Events</RouterLink>
          <RouterLink to="/" class="nav-item">Participants</RouterLink>
        </nav>
      </template>

      <template v-else>
        <RouterLink to="/" class="brand-link">
          <span class="brand-logo">🗺️</span>
          <span class="brand-title">AdventureTogether</span>
        </RouterLink>

        <nav class="header-nav">
          <RouterLink to="/" class="nav-item">Events</RouterLink>
          <RouterLink to="/backoffice" class="nav-item nav-item-small">Back office</RouterLink>
        </nav>
      </template>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  height: var(--header-height);
  background-color: var(--color-bg-surface);
  border-bottom: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  position: sticky;
  top: 0;
  /* Above Leaflet's panes and controls (z-index up to 1000) so maps scroll under the header */
  z-index: 1100;
}

.header-container {
  width: 100%;
  max-width: var(--max-content-width);
  margin: 0 auto;
  padding: 0 var(--space-4);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.brand-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-lg);
  font-weight: var(--font-weight-bold);
  color: var(--color-text-main);
  text-decoration: none;
}

.brand-logo {
  font-size: 1.5rem;
}

.header-nav {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

/* Back office: a tinted bar so hosts can tell at a glance which side they are on */
.app-header.backoffice {
  background-color: var(--color-text-main);
  border-bottom-color: var(--color-text-main);
}

/* Back-office pages (builder, manage tabs) are 1400px wide; line the header up with them */
.backoffice .header-container {
  max-width: 1400px;
}

.backoffice .brand-link,
.backoffice .nav-item {
  color: var(--color-text-inverse);
}

.backoffice .nav-item:hover,
.backoffice .nav-item.router-link-exact-active {
  color: var(--color-primary-border);
}

.area-title {
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.1rem var(--space-2);
  border: 1px solid currentColor;
  border-radius: var(--radius-full);
}

.nav-item-small {
  font-size: var(--font-size-xs);
  color: var(--color-text-subtle);
}

/* Phone width: the "Back office" pill identifies the app well enough on its own */
@media (max-width: 480px) {
  .backoffice .brand-title {
    display: none;
  }
}

.nav-item {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  transition: color 0.15s ease;
}

.nav-item:hover, .nav-item.router-link-exact-active {
  color: var(--color-primary);
  text-decoration: none;
}
</style>
