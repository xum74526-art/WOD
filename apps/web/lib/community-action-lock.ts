export function acquireCommunityAction(active: Set<string>, key: string): boolean {
  if (active.has(key)) return false;
  active.add(key);
  return true;
}

export function releaseCommunityAction(active: Set<string>, key: string): void {
  active.delete(key);
}
