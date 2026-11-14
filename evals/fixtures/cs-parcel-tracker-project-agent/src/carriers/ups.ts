export interface TrackingResult {
  status: "in_transit" | "delivered" | "unknown";
  checkedAt: string;
}

export async function trackUps(trackingNumber: string): Promise<TrackingResult> {
  try {
    const response = await fetch(`https://carrier.example/ups/${trackingNumber}`);
    const body = (await response.json()) as { status?: TrackingResult["status"] };
    return { status: body.status ?? "unknown", checkedAt: new Date().toISOString() };
  } catch {
    return { status: "unknown", checkedAt: new Date().toISOString() };
  }
}
