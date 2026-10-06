<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <header class="app-header">
    <div class="header-container">
      <RouterLink to="/" class="brand-link">
        <span class="brand-logo">🗺️</span>
        <span class="brand-title">AdventureTogether</span>
      </RouterLink>

      <nav class="header-nav">
        <RouterLink to="/" class="nav-item">Events</RouterLink>
      </nav>
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
  gap: var(--space-4);
}

.nav-item {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-muted);
  transition: color 0.15s ease;
}

.nav-item:hover, .nav-item.router-link-active {
  color: var(--color-primary);
  text-decoration: none;
}
</style>
