// FAIL: DOM access before mount, missing cleanup, $: with hidden deps

import { onMount } from "svelte";

let width = $state(0);
let scrollY = $state(0);
let data = $state<string[]>([]);

// ISSUE: DOM access before mount — querySelector runs at module scope,
// before the component is mounted in the DOM
const el = document.querySelector("#app");
width = el?.clientWidth ?? 0;

// ISSUE: Missing cleanup — event listener is added but never removed
// in onDestroy or via $effect cleanup return
onMount(() => {
  window.addEventListener("scroll", () => {
    scrollY = window.scrollY;
  });

  // ISSUE: setInterval without cleanup — timer continues after unmount
  setInterval(() => {
    data = [...data, new Date().toISOString()];
  }, 1000);
});

// ISSUE: $: reactive declaration with hidden dependency — `config` is read
// inside `processItems` but is not visible in the $: statement, so Svelte
// won't re-run this block when `config` changes
let items = $state<number[]>([1, 2, 3]);
let config = $state({ multiplier: 2 });
let processed = $state<number[]>([]);

function processItems(list: number[]): number[] {
  return list.map((n) => n * config.multiplier); // hidden dep on `config`
}

// Simulating Svelte 4 $: block as a comment — the pattern is the issue
// $: processed = processItems(items);
// In Svelte 5 equivalent:
$effect(() => {
  processed = processItems(items); // `config` is a hidden dependency
});

// ISSUE: ResizeObserver without cleanup
onMount(() => {
  const observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      width = entry.contentRect.width;
    }
  });
  const target = document.getElementById("main");
  if (target) observer.observe(target);
  // observer.disconnect() never called
});

export { width, scrollY, data, processed };
