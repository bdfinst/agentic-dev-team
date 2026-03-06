// PASS: Proper onMount/onDestroy pairing, $effect cleanup returns

import { onMount, onDestroy } from "svelte";

let width = $state(0);
let isOnline = $state(navigator.onLine);
let mousePos = $state({ x: 0, y: 0 });

// Correct: onMount with returned cleanup function
onMount(() => {
  const handleResize = () => {
    width = window.innerWidth;
  };
  window.addEventListener("resize", handleResize);
  handleResize(); // initial value

  return () => {
    window.removeEventListener("resize", handleResize);
  };
});

// Correct: onMount + onDestroy pairing for multiple listeners
let cleanupFns: (() => void)[] = [];

onMount(() => {
  const handleOnline = () => {
    isOnline = true;
  };
  const handleOffline = () => {
    isOnline = false;
  };

  window.addEventListener("online", handleOnline);
  window.addEventListener("offline", handleOffline);

  cleanupFns.push(
    () => window.removeEventListener("online", handleOnline),
    () => window.removeEventListener("offline", handleOffline),
  );
});

onDestroy(() => {
  cleanupFns.forEach((fn) => fn());
});

// Correct: $effect with cleanup return for event listener
$effect(() => {
  const handleMouseMove = (e: MouseEvent) => {
    mousePos = { x: e.clientX, y: e.clientY };
  };
  window.addEventListener("mousemove", handleMouseMove);
  return () => {
    window.removeEventListener("mousemove", handleMouseMove);
  };
});

// Correct: $effect with cleanup for timer
let elapsed = $state(0);
$effect(() => {
  const interval = setInterval(() => {
    elapsed += 1;
  }, 1000);
  return () => {
    clearInterval(interval);
  };
});

// Correct: $effect with cleanup for ResizeObserver
let containerWidth = $state(0);
$effect(() => {
  const target = document.getElementById("container");
  if (!target) return;

  const observer = new ResizeObserver((entries) => {
    for (const entry of entries) {
      containerWidth = entry.contentRect.width;
    }
  });
  observer.observe(target);

  return () => {
    observer.disconnect();
  };
});

export { width, isOnline, mousePos, elapsed, containerWidth };
