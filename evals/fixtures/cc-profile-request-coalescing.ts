export interface Profile {
  userId: string;
  displayName: string;
}

export interface ProfileClient {
  fetchProfile(userId: string): Promise<Profile>;
}

export class ProfileLoader {
  private readonly inFlight = new Map<string, Promise<Profile>>();

  constructor(private readonly client: ProfileClient) {}

  load(userId: string): Promise<Profile> {
    const pending = this.inFlight.get(userId);
    if (pending) {
      return pending;
    }
    const request = this.client.fetchProfile(userId).finally(() => {
      this.inFlight.delete(userId);
    });
    this.inFlight.set(userId, request);
    return request;
  }
}
