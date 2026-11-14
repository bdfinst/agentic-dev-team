<script setup lang="ts">
import {
  computed,
  onBeforeUnmount,
  onMounted,
  reactive,
  ref,
  toRef,
  watch,
} from "vue";

import { settingsApi, type NotificationChannel, type UserSettings } from "../api/settings";
import { useToast } from "../composables/useToast";
import { useDebouncedRef } from "../composables/useDebouncedRef";

type Theme = "light" | "dark" | "system";
type Density = "comfortable" | "compact";
type SectionId = "appearance" | "notifications" | "privacy" | "shortcuts";

interface Shortcut {
  readonly action: string;
  readonly keys: string;
}

const props = defineProps<{
  readonly userId: string;
  readonly initialSection?: SectionId;
}>();

const emit = defineEmits<{
  saved: [settings: UserSettings];
  close: [];
}>();

const SECTIONS: ReadonlyArray<{ id: SectionId; label: string }> = [
  { id: "appearance", label: "Appearance" },
  { id: "notifications", label: "Notifications" },
  { id: "privacy", label: "Privacy" },
  { id: "shortcuts", label: "Keyboard shortcuts" },
];

const DEFAULT_SHORTCUTS: readonly Shortcut[] = [
  { action: "Open search", keys: "Ctrl+K" },
  { action: "New document", keys: "Ctrl+N" },
  { action: "Toggle sidebar", keys: "Ctrl+B" },
];

const toast = useToast();

const activeSection = ref<SectionId>(props.initialSection ?? "appearance");
const isLoading = ref(true);
const isSaving = ref(false);
const loadError = ref<string | null>(null);

const preferences = reactive({
  theme: "system" as Theme,
  density: "comfortable" as Density,
  fontScale: 100,
  reduceMotion: false,
});

const notifications = reactive({
  channels: [] as NotificationChannel[],
  digestHour: 9,
  mutedUntil: null as string | null,
});

const privacy = reactive({
  shareUsageData: false,
  showOnlineStatus: true,
});

const shortcuts = ref<Shortcut[]>([...DEFAULT_SHORTCUTS]);
const shortcutFilter = ref("");
const debouncedFilter = useDebouncedRef(shortcutFilter, 200);

const savedSnapshot = ref<string>("");

const currentSnapshot = computed(() =>
  JSON.stringify({ preferences, notifications, privacy, shortcuts: shortcuts.value }),
);

const isDirty = computed(() => savedSnapshot.value !== currentSnapshot.value);

const filteredShortcuts = computed(() => {
  const term = debouncedFilter.value.trim().toLowerCase();
  if (term === "") return shortcuts.value;
  return shortcuts.value.filter((shortcut) => shortcut.action.toLowerCase().includes(term));
});

const fontScaleLabel = computed(() => `${preferences.fontScale}%`);

const prefersDark = window.matchMedia("(prefers-color-scheme: dark)");
const systemIsDark = ref(prefersDark.matches);

function onSystemThemeChange(event: MediaQueryListEvent): void {
  systemIsDark.value = event.matches;
}

const effectiveTheme = computed<"light" | "dark">(() => {
  if (preferences.theme === "system") return systemIsDark.value ? "dark" : "light";
  return preferences.theme;
});

function applyTheme(theme: "light" | "dark"): void {
  document.documentElement.dataset.theme = theme;
}

watch(effectiveTheme, (theme) => applyTheme(theme), { immediate: true });

watch(preferences.theme, (theme) => {
  settingsApi.trackThemeChange(props.userId, theme);
});

watch(
  () => preferences.fontScale,
  (scale) => {
    document.documentElement.style.setProperty("--font-scale", String(scale / 100));
  },
  { immediate: true },
);

watch(
  toRef(props, "userId"),
  (userId) => {
    void load(userId);
  },
  { immediate: true },
);

async function load(userId: string): Promise<void> {
  isLoading.value = true;
  loadError.value = null;
  try {
    const settings = await settingsApi.load(userId);
    Object.assign(preferences, settings.preferences);
    Object.assign(notifications, settings.notifications);
    Object.assign(privacy, settings.privacy);
    shortcuts.value = [...settings.shortcuts];
    savedSnapshot.value = currentSnapshot.value;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  } finally {
    isLoading.value = false;
  }
}

async function save(): Promise<void> {
  isSaving.value = true;
  try {
    const saved = await settingsApi.save(props.userId, {
      preferences: { ...preferences },
      notifications: { ...notifications, channels: [...notifications.channels] },
      privacy: { ...privacy },
      shortcuts: [...shortcuts.value],
    });
    savedSnapshot.value = currentSnapshot.value;
    toast.success("Settings saved");
    emit("saved", saved);
  } catch (error) {
    toast.error(error instanceof Error ? error.message : "Could not save settings");
  } finally {
    isSaving.value = false;
  }
}

function toggleChannel(channel: NotificationChannel): void {
  notifications.channels = notifications.channels.includes(channel)
    ? notifications.channels.filter((existing) => existing !== channel)
    : [...notifications.channels, channel];
}

function resetShortcuts(): void {
  shortcuts.value = [...DEFAULT_SHORTCUTS];
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") emit("close");
  if ((event.ctrlKey || event.metaKey) && event.key === "s") {
    event.preventDefault();
    if (isDirty.value) void save();
  }
}

onMounted(() => {
  prefersDark.addEventListener("change", onSystemThemeChange);
  window.addEventListener("keydown", onKeydown);
});

onBeforeUnmount(() => {
  prefersDark.removeEventListener("change", onSystemThemeChange);
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="settings-panel" role="dialog" aria-labelledby="settings-title">
    <h1 id="settings-title">Settings</h1>
    <p v-if="loadError" role="alert">{{ loadError }}</p>
    <nav>
      <button
        v-for="section in SECTIONS"
        :key="section.id"
        type="button"
        :aria-current="activeSection === section.id ? 'page' : undefined"
        @click="activeSection = section.id"
      >
        {{ section.label }}
      </button>
    </nav>

    <section v-if="activeSection === 'appearance'" :aria-busy="isLoading">
      <fieldset>
        <legend>Theme</legend>
        <label><input v-model="preferences.theme" type="radio" value="light" /> Light</label>
        <label><input v-model="preferences.theme" type="radio" value="dark" /> Dark</label>
        <label><input v-model="preferences.theme" type="radio" value="system" /> System</label>
      </fieldset>
      <label>
        Density
        <select v-model="preferences.density">
          <option value="comfortable">Comfortable</option>
          <option value="compact">Compact</option>
        </select>
      </label>
      <label>
        Font size {{ fontScaleLabel }}
        <input v-model.number="preferences.fontScale" type="range" min="80" max="150" step="10" />
      </label>
      <label><input v-model="preferences.reduceMotion" type="checkbox" /> Reduce motion</label>
    </section>

    <section v-else-if="activeSection === 'notifications'">
      <label v-for="channel in ['email', 'push', 'sms']" :key="channel">
        <input
          type="checkbox"
          :checked="notifications.channels.includes(channel as NotificationChannel)"
          @change="toggleChannel(channel as NotificationChannel)"
        />
        {{ channel }}
      </label>
      <label>
        Daily digest hour
        <input v-model.number="notifications.digestHour" type="number" min="0" max="23" />
      </label>
    </section>

    <section v-else-if="activeSection === 'privacy'">
      <label><input v-model="privacy.shareUsageData" type="checkbox" /> Share usage data</label>
      <label><input v-model="privacy.showOnlineStatus" type="checkbox" /> Show online status</label>
    </section>

    <section v-else>
      <input v-model="shortcutFilter" type="search" placeholder="Filter shortcuts" />
      <ul>
        <li v-for="shortcut in filteredShortcuts" :key="shortcut.action">
          {{ shortcut.action }} <kbd>{{ shortcut.keys }}</kbd>
        </li>
      </ul>
      <button type="button" @click="resetShortcuts">Restore defaults</button>
    </section>

    <footer>
      <button type="button" @click="emit('close')">Close</button>
      <button type="button" :disabled="!isDirty || isSaving" @click="save">Save</button>
    </footer>
  </div>
</template>
