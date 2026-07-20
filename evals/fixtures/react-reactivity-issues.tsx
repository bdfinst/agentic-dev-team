// FAIL: stale closure (missing dep), setState during render, subscription leak

import { useEffect, useState } from "react";

interface Props {
  step: number;
}

export function Ticker({ step }: Props) {
  const [count, setCount] = useState(0);
  const [ready, setReady] = useState(false);

  // ISSUE: setState called directly in the render body, not inside a handler
  // or effect — triggers a synchronous re-render loop
  if (!ready) {
    setReady(true);
  }

  // ISSUE: `step` is read inside the effect but omitted from the dependency
  // array — the interval callback captures a stale `step` from the first render
  useEffect(() => {
    const id = setInterval(() => {
      setCount((c) => c + step);
    }, 1000);
    // ISSUE: no cleanup function returned — timer keeps running after unmount
  }, []);

  return (
    <div>
      {count} (step {step})
    </div>
  );
}
