export function signOutCurrentDevice(
  beginRevocation: () => Promise<unknown>,
  clearLocalSession: () => void,
): Promise<void> {
  let revocation: Promise<unknown>
  try {
    // The API request captures the current bearer before local storage is
    // cleared. Attach both outcomes immediately so background failure is safe.
    revocation = Promise.resolve(beginRevocation())
  } catch {
    revocation = Promise.resolve()
  }
  const settled = revocation.then(() => undefined, () => undefined)
  clearLocalSession()
  return settled
}
