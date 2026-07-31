// PASS: File name carries the *.adapter.ts dotted suffix - a declared effect boundary,
// so the console/fetch side effects here are expected and must not be flagged

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
