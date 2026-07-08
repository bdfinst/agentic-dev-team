// PASS: React component with correct effect dependencies and cleanup

import React, { useState, useEffect, useCallback } from 'react';

export function AutoIncrement() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const id = setInterval(() => {
      // Functional updater avoids stale closure — no dep array entry needed
      setCount(prev => prev + 1);
    }, 1000);

    // Proper cleanup prevents leak
    return () => clearInterval(id);
  }, []);

  return <div>Count: {count}</div>;
}

export function FetchOnId({ id }: { id: number }) {
  const [data, setData] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/items/${id}`)
      .then(r => r.json())
      .then(result => {
        if (!cancelled) setData(result);
      });
    // Cleanup prevents setState after unmount / after id change
    return () => { cancelled = true; };
  }, [id]); // id correctly listed as dep

  return <div>{data}</div>;
}
