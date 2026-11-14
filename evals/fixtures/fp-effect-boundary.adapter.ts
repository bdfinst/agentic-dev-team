declare function fetch(url: string): Promise<{ json(): Promise<unknown> }>;

async function fetchUserScore(userId: string): Promise<number> {
  const res = await fetch(`/api/users/${encodeURIComponent(userId)}/score`);
  const data = (await res.json()) as { score: number };
  return data.score;
}

function logAudit(message: string): void {
  console.log(`[audit] ${message}`);
}

export { fetchUserScore, logAudit };
