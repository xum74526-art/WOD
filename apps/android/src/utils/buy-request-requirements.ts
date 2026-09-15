export function buyRequestAdditionalRequirements(
  requirements: Readonly<Record<string, unknown>> | null | undefined,
) {
  const note = typeof requirements?.note === 'string' ? requirements.note.trim() : ''
  if (note) return note
  return typeof requirements?.remark === 'string' ? requirements.remark.trim() : ''
}
