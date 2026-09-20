/** Keep backend references intact while presenting the current application name. */
export function displayBusinessReference(value?: string | null): string {
  return String(value || '').replace(/^WOD(?=[A-Z0-9-])/i, 'KAI星算')
}
