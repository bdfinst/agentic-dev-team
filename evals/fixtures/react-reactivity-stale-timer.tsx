import { useEffect, useMemo, useState } from "react";

interface WorkoutTimerProps {
  readonly exerciseName: string;
  readonly targetSeconds: number;
  readonly onComplete: (elapsedSeconds: number) => void;
}

function formatDuration(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function WorkoutTimer({
  exerciseName,
  targetSeconds,
  onComplete,
}: WorkoutTimerProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [isRunning, setIsRunning] = useState(false);

  useEffect(() => {
    if (!isRunning) return undefined;
    const timerId = setInterval(() => {
      setElapsedSeconds(elapsedSeconds + 1);
    }, 1000);
    return () => clearInterval(timerId);
  }, [isRunning]);

  useEffect(() => {
    if (elapsedSeconds >= targetSeconds) {
      setIsRunning(false);
      onComplete(elapsedSeconds);
    }
  }, [elapsedSeconds, targetSeconds, onComplete]);

  const progressPercent = useMemo(
    () => Math.min(100, Math.round((elapsedSeconds / targetSeconds) * 100)),
    [elapsedSeconds, targetSeconds],
  );

  return (
    <section aria-label={`${exerciseName} timer`}>
      <h2>{exerciseName}</h2>
      <p>
        {formatDuration(elapsedSeconds)} / {formatDuration(targetSeconds)}
      </p>
      <progress value={progressPercent} max={100} />
      <button type="button" onClick={() => setIsRunning((running) => !running)}>
        {isRunning ? "Pause" : "Start"}
      </button>
      <button
        type="button"
        onClick={() => {
          setIsRunning(false);
          setElapsedSeconds(0);
        }}
      >
        Reset
      </button>
    </section>
  );
}
