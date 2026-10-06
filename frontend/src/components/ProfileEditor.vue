<script setup lang="ts">
/**
 * "Your profile" on the landing page: display name, contributor usernames and the default
 * location-sharing tier. Saved to localStorage as the host types (no account, no Save button);
 * the join form and the map read the same keys.
 */
import { ref, watch } from 'vue'
import { readProfile, saveIdentity, saveVisibility, ensureParticipantId } from '../composables/participantProfile'
import type { VisibilityTier } from '../composables/useGeolocation'

// Generate the device's id up front so every later screen agrees on who this is
ensureParticipantId()

const initial = readProfile()
const displayName = ref(initial.displayName)
const osmUsername = ref(initial.usernames.osm_username)
const wikimediaUsername = ref(initial.usernames.wikimedia_username)
const githubUsername = ref(initial.usernames.github_username)
const visibility = ref<VisibilityTier>(initial.visibility)
const saved = ref(false)

let savedTimer: ReturnType<typeof setTimeout> | null = null
const flashSaved = () => {
  saved.value = true
  if (savedTimer) clearTimeout(savedTimer)
  savedTimer = setTimeout(() => (saved.value = false), 1500)
}

watch([displayName, osmUsername, wikimediaUsername, githubUsername], () => {
  saveIdentity(displayName.value, {
    osm_username: osmUsername.value,
    wikimedia_username: wikimediaUsername.value,
    github_username: githubUsername.value
  })
  flashSaved()
})

watch(visibility, (tier) => {
  saveVisibility(tier)
  flashSaved()
})

const tiers: { value: VisibilityTier; label: string; hint: string }[] = [
  { value: 'nobody', label: 'Nobody', hint: 'Check-ins still work' },
  { value: 'team', label: 'My team', hint: 'Default' },
  { value: 'quest', label: 'Everyone in the event', hint: '' }
]
</script>

<template>
  <div class="profile-editor">
    <div class="form-group">
      <label class="form-label" for="profileName">Display name</label>
      <input id="profileName" v-model="displayName" type="text" class="form-input" placeholder="e.g. Alex Cartographer" />
    </div>

    <fieldset class="usernames">
      <legend class="form-label">Contributor usernames <span class="optional">(optional)</span></legend>
      <p class="hint">So your edits are credited to your team.</p>
      <div class="username-grid">
        <div class="form-group">
          <label class="form-label" for="profileOsm">OpenStreetMap</label>
          <input id="profileOsm" v-model="osmUsername" type="text" class="form-input" placeholder="also OpenHistoricalMap" autocomplete="off" autocapitalize="off" />
        </div>
        <div class="form-group">
          <label class="form-label" for="profileWikimedia">Wikimedia</label>
          <input id="profileWikimedia" v-model="wikimediaUsername" type="text" class="form-input" placeholder="Commons and Wikidata" autocomplete="off" autocapitalize="off" />
        </div>
        <div class="form-group">
          <label class="form-label" for="profileGithub">GitHub</label>
          <input id="profileGithub" v-model="githubUsername" type="text" class="form-input" placeholder="code quests" autocomplete="off" autocapitalize="off" />
        </div>
      </div>
    </fieldset>

    <fieldset class="sharing">
      <legend class="form-label">Share my location on the map with</legend>
      <label v-for="tier in tiers" :key="tier.value" class="radio">
        <input v-model="visibility" type="radio" name="profileVisibility" :value="tier.value" />
        {{ tier.label }}
        <span v-if="tier.hint" class="hint-inline">({{ tier.hint }})</span>
      </label>
    </fieldset>

    <p class="saved-note" aria-live="polite">{{ saved ? 'Saved on this device' : 'Stored on this device only' }}</p>
  </div>
</template>

<style scoped>
.usernames,
.sharing {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: var(--space-3) var(--space-4);
  margin-bottom: var(--space-4);
}

legend {
  padding: 0 var(--space-1);
  margin-bottom: 0;
}

.optional,
.hint-inline {
  color: var(--color-text-muted);
  font-weight: var(--font-weight-normal);
}

.hint {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-bottom: var(--space-3);
}

.username-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0 var(--space-3);
}

.radio {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--font-size-sm);
  padding: var(--space-1) 0;
}

.hint-inline {
  font-size: var(--font-size-xs);
}

.saved-note {
  font-size: var(--font-size-xs);
  color: var(--color-text-subtle);
}
</style>
