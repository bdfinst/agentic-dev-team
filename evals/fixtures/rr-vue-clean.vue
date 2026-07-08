<!-- PASS: Vue component with correct reactive usage and no watchEffect leaks -->

<script setup lang="ts">
import { reactive, toRefs, watchEffect, ref } from 'vue';

// toRefs preserves reactivity on each property after destructuring
const state = reactive({ name: 'Alice', age: 30 });
const { name, age } = toRefs(state);

// Guarded watchEffect — only writes when a condition changes, no infinite loop
const counter = ref(0);
const limit = ref(10);
watchEffect(() => {
  if (counter.value < limit.value) {
    // no write to counter here; just reads and logs
    console.log('counter below limit:', counter.value);
  }
});
</script>

<template>
  <!-- name and age are refs — template auto-unwraps .value -->
  <p>{{ name }}, {{ age }}</p>
</template>
