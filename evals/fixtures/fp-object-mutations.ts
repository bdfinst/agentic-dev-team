// FAIL: Object mutations — param mutation, Object.assign on existing objects, delete

interface UserProfile {
  id: string;
  name: string;
  email: string;
  metadata: Record<string, string>;
  role?: string;
  legacyField?: string;
}

function normalizeProfile(profile: UserProfile): UserProfile {
  profile.name = profile.name.trim(); // mutation: param property assignment
  profile.email = profile.email.toLowerCase(); // mutation: param property assignment
  return profile;
}

function mergeMetadata(
  profile: UserProfile,
  extra: Record<string, string>,
): UserProfile {
  Object.assign(profile.metadata, extra); // mutation: Object.assign to existing object
  return profile;
}

function applyDefaults(profile: UserProfile): UserProfile {
  Object.assign(profile, { // mutation: Object.assign to param
    role: profile.role ?? "viewer",
    metadata: profile.metadata ?? {},
  });
  return profile;
}

function stripLegacyFields(profile: UserProfile): UserProfile {
  delete profile.legacyField; // mutation: delete on param
  return profile;
}

function setMetadataEntry(
  profile: UserProfile,
  key: string,
  value: string,
): void {
  profile.metadata[key] = value; // mutation: nested param property assignment
}

function promoteToAdmin(profile: UserProfile): UserProfile {
  profile.role = "admin"; // mutation: param property assignment
  return profile;
}

function cleanProfile(profile: UserProfile): UserProfile {
  normalizeProfile(profile);
  applyDefaults(profile);
  stripLegacyFields(profile);
  return profile;
}

export {
  normalizeProfile,
  mergeMetadata,
  applyDefaults,
  stripLegacyFields,
  setMetadataEntry,
  promoteToAdmin,
  cleanProfile,
};
