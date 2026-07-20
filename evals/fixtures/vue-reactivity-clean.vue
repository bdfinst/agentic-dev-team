<!-- PASS: correct ref/reactive usage, tracked watchEffect deps, cleanup on unmount -->
<script setup lang="ts">
import { computed, onUnmounted, ref, watchEffect } from "vue";

const props = defineProps<{ multiplier: number }>();

// Correct: primitive wrapped in ref, accessed via .value in script
const count = ref(0);
const doubled = computed(() => count.value * props.multiplier);

// Correct: watchEffect reads `count.value` directly inside the effect body,
// so the dependency is tracked
let intervalId: ReturnType<typeof setInterval> | undefined;
watchEffect((onCleanup) => {
  intervalId = setInterval(() => {
    count.value += 1;
  }, 1000);
  onCleanup(() => clearInterval(intervalId));
});

// Correct: whole reactive object passed through, not destructured or spread
const state = ref({ x: 0, y: 0 });
function updatePosition(e: MouseEvent) {
  state.value = { x: e.clientX, y: e.clientY };
}

window.addEventListener("mousemove", updatePosition);
onUnmounted(() => {
  window.removeEventListener("mousemove", updatePosition);
});

defineExpose({ count, doubled, state });
</script>

<template>
  <div>{{ doubled }} — {{ state.x }},{{ state.y }}</div>
</template>
