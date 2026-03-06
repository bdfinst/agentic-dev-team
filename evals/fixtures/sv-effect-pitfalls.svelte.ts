// FAIL: $effect writing to own deps, side effects in $derived, $effect for derived state

let count = $state(0);
let doubled = $state(0);
let label = $state("");

// ISSUE: $effect writes to its own dependency — `count` is read and written
// in the same effect, risking an infinite loop
$effect(() => {
  if (count > 10) {
    count = 0; // writing to `count` re-triggers this effect
  }
});

// ISSUE: $effect used for synchronous derived state — `doubled` is simply
// `count * 2` and should use $derived instead
$effect(() => {
  doubled = count * 2;
});

// ISSUE: Side effect inside $derived — fetching or logging should live in
// $effect, not $derived
const summary = $derived(() => {
  console.log("Computing summary (side effect in $derived)");
  fetch("/api/track?count=" + count); // side effect!
  return `Count is ${count}`;
});

// ISSUE: $effect that computes a derived value — should be $derived
$effect(() => {
  label = count > 5 ? "high" : "low";
});

// ISSUE: $effect writing to a dependency it reads (different pattern)
let items = $state<string[]>([]);
let filteredCount = $state(0);

$effect(() => {
  filteredCount = items.filter((i) => i.length > 3).length;
  if (filteredCount === 0) {
    items = ["default"]; // writes to `items`, which is also read above
  }
});

export { count, doubled, label, summary, items, filteredCount };
