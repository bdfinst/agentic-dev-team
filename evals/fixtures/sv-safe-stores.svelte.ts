// PASS: Svelte 4 — $store auto-subscription syntax and manual subscribe with proper cleanup

import { writable, derived, get } from "svelte/store";
import { onDestroy } from "svelte";

interface Settings {
  theme: "light" | "dark";
  fontSize: number;
}

// Store definitions
const settings = writable<Settings>({ theme: "light", fontSize: 14 });
const theme = derived(settings, ($s) => $s.theme);
const fontSize = derived(settings, ($s) => $s.fontSize);

// Safe: using $store auto-subscription syntax (compiler handles cleanup)
// In a .svelte file these would be $settings, $theme, $fontSize

// Safe: manual subscribe with cleanup in onDestroy
let currentTheme = "light";

const unsubTheme = theme.subscribe((value) => {
  currentTheme = value;
});

onDestroy(() => {
  unsubTheme();
});

// Safe: multiple subscriptions all cleaned up
const unsubscribers: (() => void)[] = [];

unsubscribers.push(
  settings.subscribe((value) => {
    document.documentElement.style.fontSize = `${value.fontSize}px`;
  }),
);

unsubscribers.push(
  theme.subscribe((value) => {
    document.documentElement.dataset.theme = value;
  }),
);

onDestroy(() => {
  unsubscribers.forEach((unsub) => unsub());
});

// Safe: one-time read with get() — no subscription to leak
function getCurrentSettings(): Settings {
  return get(settings);
}

// Safe: store update helpers
function toggleTheme() {
  settings.update((s) => ({
    ...s,
    theme: s.theme === "light" ? "dark" : "light",
  }));
}

function setFontSize(size: number) {
  settings.update((s) => ({ ...s, fontSize: size }));
}

export { settings, theme, fontSize, currentTheme, getCurrentSettings, toggleTheme, setFontSize };
