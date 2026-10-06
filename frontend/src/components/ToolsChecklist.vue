<script setup lang="ts">
/**
 * "Tools I have" on the landing page. Ticked tools are saved to localStorage
 * (`participant_tools`); the map's quest panel then hides quests none of them can do.
 */
import { ref, watch } from 'vue'
import { TOOLS, type ToolId } from '../composables/useQuestTypes'
import { readTools, saveTools } from '../composables/participantProfile'

const emit = defineEmits<{ (e: 'change', tools: ToolId[]): void }>()

const selected = ref<ToolId[]>(readTools())

watch(selected, (tools) => {
  saveTools(tools)
  emit('change', [...tools])
})
</script>

<template>
  <ul class="tools-list">
    <li v-for="tool in TOOLS" :key="tool.id" class="tool" :class="{ ticked: selected.includes(tool.id) }">
      <label class="tool-label">
        <input v-model="selected" type="checkbox" :value="tool.id" :data-tool="tool.id" />
        <span class="tool-name">{{ tool.label }}</span>
      </label>
      <p class="tool-desc">{{ tool.description }}</p>
      <p class="tool-links">
        <a v-for="link in tool.links" :key="link.url" :href="link.url" target="_blank" rel="noopener">{{ link.label }} ↗</a>
      </p>
    </li>
  </ul>
</template>

<style scoped>
.tools-list {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-3);
}

.tool {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3);
  background-color: var(--color-bg-surface);
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.tool.ticked {
  border-color: var(--color-primary-border);
  background-color: var(--color-primary-light);
}

.tool-label {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
}

.tool-label input {
  width: 1.1rem;
  height: 1.1rem;
  flex-shrink: 0;
}

.tool-name {
  font-weight: var(--font-weight-semibold);
  font-size: var(--font-size-sm);
}

.tool-desc {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  flex-grow: 1;
}

.tool-links {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-3);
  font-size: var(--font-size-xs);
}
</style>
