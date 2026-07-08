<!-- FAIL: Vue reactive() destructuring breaks reactivity, watchEffect self-write -->

<script setup lang="ts">
import { reactive, watchEffect, ref } from 'vue';

// ISSUE: Destructuring a reactive() object — `name` and `age` are now plain
// (non-reactive) variables. Changes to `state.name` or `state.age` will NOT
// be reflected in `name` / `age` after the initial destructure.
// Fix: use toRef(state, 'name') / toRefs(state) to keep reactivity.
const state = reactive({ name: 'Alice', age: 30 });
const { name, age } = state;

// ISSUE: watchEffect self-write — `counter` is read inside the effect and also
// written unconditionally, causing an infinite update loop.
// Fix: add a guard (only increment if a triggering condition is met), or
// restructure so the write is in a handler, not the same effect that reads it.
const counter = ref(0);
watchEffect(() => {
  console.log('counter is', counter.value);
  counter.value++; // unconditional write to a tracked dep → infinite loop
});
</script>

<template>
  <!-- `name` and `age` here are the destructured (stale) plain values -->
  <p>{{ name }}, {{ age }}</p>
</template>
