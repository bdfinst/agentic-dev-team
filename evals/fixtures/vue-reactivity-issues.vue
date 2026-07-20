<!-- FAIL: destructured reactive(), untracked watchEffect dep, missing cleanup -->
<script setup lang="ts">
import { reactive, watchEffect } from "vue";

// ISSUE: destructuring a reactive() object breaks reactivity — `x` and `y`
// become plain, non-reactive copies
const state = reactive({ x: 0, y: 0, multiplier: 2 });
const { x, y } = state;

// ISSUE: watchEffect calls a plain function that reads `state.multiplier`
// internally instead of accessing it directly inside the effect body — the
// dependency is never tracked, so the effect won't re-run when it changes
function computeArea() {
  return x * y * getMultiplier();
}
function getMultiplier() {
  return state.multiplier;
}

let area = 0;
watchEffect(() => {
  area = computeArea();
});

// ISSUE: event listener added with no onUnmounted/cleanup teardown
function handleResize() {
  state.x = window.innerWidth;
}
window.addEventListener("resize", handleResize);

defineExpose({ state, area });
</script>

<template>
  <div>{{ area }}</div>
</template>
