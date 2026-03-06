// FAIL: Manual .subscribe() without unsubscribe in onDestroy (Svelte 4)

import { writable, derived, type Writable } from "svelte/store";
import { onMount } from "svelte";

interface User {
  name: string;
  email: string;
}

const userStore: Writable<User | null> = writable(null);
const themeStore = writable("light");

let currentUser: User | null = null;
let currentTheme = "light";

// ISSUE: Manual .subscribe() with no unsubscribe — subscription is never
// cleaned up in onDestroy, causing a memory leak when the component unmounts
userStore.subscribe((value) => {
  currentUser = value;
  console.log("User updated:", value);
});

// ISSUE: Another subscription leak — stored in a variable but never called
const unsub = themeStore.subscribe((value) => {
  currentTheme = value;
});
// `unsub` is never invoked in onDestroy

// ISSUE: Derived store subscription also leaks
const displayName = derived(userStore, ($user) => $user?.name ?? "Anonymous");

let name = "";
displayName.subscribe((value) => {
  name = value;
});

onMount(() => {
  // ISSUE: Subscription created inside onMount but cleanup is not returned
  // or handled in onDestroy
  userStore.subscribe((value) => {
    if (value) {
      document.title = `Profile: ${value.name}`;
    }
  });
});

export { currentUser, currentTheme, name };
