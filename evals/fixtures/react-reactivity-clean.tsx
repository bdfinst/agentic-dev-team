// PASS: correct dependency arrays, cleanup functions, no setState-during-render

import { useCallback, useEffect, useRef, useState } from "react";

interface Props {
  userId: string;
  onLoaded?: (name: string) => void;
}

export function UserStatus({ userId, onLoaded }: Props) {
  const [name, setName] = useState("");
  const [online, setOnline] = useState(false);

  // Correct: onLoaded is a dep, guards against stale closure
  const notify = useCallback(
    (value: string) => {
      onLoaded?.(value);
    },
    [onLoaded],
  );

  // Correct: full dependency array, cleanup returned
  useEffect(() => {
    let cancelled = false;
    fetch(`/api/users/${userId}`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) {
          setName(data.name);
          notify(data.name);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [userId, notify]);

  // Correct: subscription cleaned up in the returned teardown function
  useEffect(() => {
    const handleOnline = () => setOnline(true);
    const handleOffline = () => setOnline(false);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  // Correct: ref used for a mutable value that shouldn't trigger re-render
  const renderCount = useRef(0);
  renderCount.current += 1;

  return (
    <div>
      {name} — {online ? "online" : "offline"}
    </div>
  );
}
