export function normalizeAdminReviewPrompt(value: string | null, reasonRequired: boolean) {
  if (value === null) return null;
  const normalized = value.trim();
  if (reasonRequired && !normalized) return null;
  return normalized || undefined;
}
