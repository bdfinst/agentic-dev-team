<script setup lang="ts">
import {
  computed,
  onMounted,
  onUnmounted,
  reactive,
  ref,
  toRaw,
  toRefs,
  watch,
  watchEffect,
} from "vue";

import { profileApi, type Profile } from "../api/profile";

const props = defineProps<{ userId: string }>();
const emit = defineEmits<{ saved: [profile: Profile] }>();

const form = reactive({
  displayName: "",
  email: "",
  timezone: "UTC",
  marketingOptIn: false,
});
const { displayName, email } = toRefs(form);

const isSaving = ref(false);
const loadError = ref<string | null>(null);
const isOnline = ref(navigator.onLine);

const canSave = computed(
  () => !isSaving.value && isOnline.value && displayName.value.trim().length > 0,
);

watch(
  () => props.userId,
  async (userId, _previous, onCleanup) => {
    let cancelled = false;
    onCleanup(() => {
      cancelled = true;
    });
    loadError.value = null;
    try {
      const profile = await profileApi.load(userId);
      if (cancelled) return;
      Object.assign(form, {
        displayName: profile.displayName,
        email: profile.email,
        timezone: profile.timezone,
        marketingOptIn: profile.marketingOptIn,
      });
    } catch (error) {
      if (!cancelled) loadError.value = String(error);
    }
  },
  { immediate: true },
);

watchEffect(() => {
  document.title = displayName.value ? `${displayName.value} · Profile` : "Profile";
});

function updateOnlineStatus(): void {
  isOnline.value = navigator.onLine;
}

onMounted(() => {
  window.addEventListener("online", updateOnlineStatus);
  window.addEventListener("offline", updateOnlineStatus);
});

onUnmounted(() => {
  window.removeEventListener("online", updateOnlineStatus);
  window.removeEventListener("offline", updateOnlineStatus);
});

async function save(): Promise<void> {
  isSaving.value = true;
  try {
    const saved = await profileApi.save(props.userId, { ...toRaw(form) });
    emit("saved", saved);
  } finally {
    isSaving.value = false;
  }
}
</script>

<template>
  <form @submit.prevent="save">
    <p v-if="loadError" role="alert">{{ loadError }}</p>
    <label>Display name <input v-model="displayName" /></label>
    <label>Email <input v-model="email" type="email" /></label>
    <label>
      Timezone
      <select v-model="form.timezone">
        <option>UTC</option>
        <option>America/New_York</option>
        <option>Europe/Berlin</option>
      </select>
    </label>
    <label><input v-model="form.marketingOptIn" type="checkbox" /> Product news</label>
    <button type="submit" :disabled="!canSave">Save</button>
  </form>
</template>
