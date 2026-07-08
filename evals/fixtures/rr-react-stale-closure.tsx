// FAIL: Classic stale-closure bug in useEffect — counter never increments past 1

import React, { useState, useEffect } from 'react';

export function AutoIncrement() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      // ISSUE: Stale closure — `count` is captured at mount time (0).
      // Every tick sets count to 0 + 1 = 1 forever.
      // Fix: use functional updater `setCount(prev => prev + 1)` or add
      // `count` to the dependency array (and clear/restart the interval).
      setCount(count + 1);
    }, 1000);

    // ISSUE: Missing cleanup — interval runs after component unmounts,
    // causing a memory leak and a setState-on-unmounted-component warning.
    // Fix: return () => clearInterval(id);
  }, []); // empty dep array intentional to show the stale-closure trap

  return <div>Count: {count}</div>;
}

export function FetchOnId({ id }: { id: number }) {
  const [data, setData] = useState<string | null>(null);

  useEffect(() => {
    fetch(`/api/items/${id}`)
      .then(r => r.json())
      .then(setData);
    // ISSUE: Missing `id` in dependency array — if `id` changes the fetch
    // won't re-run and `data` reflects the first `id` forever.
  }, []); // should be [id]

  return <div>{data}</div>;
}
