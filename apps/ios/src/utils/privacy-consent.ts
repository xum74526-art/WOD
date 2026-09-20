import { LEGAL_VERSION } from '../config/legal-documents.ts'
import type { AppLanguage } from './language.ts'

export const PRIVACY_CONSENT_STORAGE_KEY = 'kai_privacy_consent_receipt'
export const PRIVACY_CONSENT_EVENT = 'kai-privacy-consent-granted'
export const PRIVACY_CONSENT_REVOKED_EVENT = 'kai-privacy-consent-revoked'
export const PRIVACY_CONSENT_SCHEMA_VERSION = 2
export const HONG_KONG_PROCESSING_CONSENT_VERSION = '1.0'

export type PrivacyConsentPlatform = 'ios' | 'android'
export type PrivacyRegionScope = 'mainland-china' | 'other'

export interface PrivacyConsentReceipt {
  schemaVersion: number
  legalVersion: string
  acceptedAt: number
  language: AppLanguage
  platform: PrivacyConsentPlatform
  regionScope: PrivacyRegionScope
  agreementAndPrivacyAccepted: true
  hongKongProcessingAccepted: true
  hongKongProcessingConsentVersion: string
}

export interface PrivacyConsentStorage {
  getStorageSync(key: string): unknown
  setStorageSync(key: string, value: unknown): void
  removeStorageSync?(key: string): void
}

export interface AcceptPrivacyConsentInput {
  language: AppLanguage
  platform: PrivacyConsentPlatform
  regionScope: PrivacyRegionScope
  agreementAndPrivacyAccepted: boolean
  hongKongProcessingAccepted: boolean
}

function runtimeStorage(): PrivacyConsentStorage {
  return uni
}

function isLanguage(value: unknown): value is AppLanguage {
  return value === 'zh-Hant' || value === 'zh-Hans' || value === 'en'
}

function isPlatform(value: unknown): value is PrivacyConsentPlatform {
  return value === 'ios' || value === 'android'
}

function isRegionScope(value: unknown): value is PrivacyRegionScope {
  return value === 'mainland-china' || value === 'other'
}

export function isCurrentPrivacyConsentReceipt(value: unknown): value is PrivacyConsentReceipt {
  if (!value || typeof value !== 'object') return false
  const receipt = value as Partial<PrivacyConsentReceipt>
  if (receipt.schemaVersion !== PRIVACY_CONSENT_SCHEMA_VERSION) return false
  if (receipt.legalVersion !== LEGAL_VERSION) return false
  if (receipt.agreementAndPrivacyAccepted !== true) return false
  if (!Number.isFinite(receipt.acceptedAt) || Number(receipt.acceptedAt) <= 0) return false
  if (!isLanguage(receipt.language) || !isPlatform(receipt.platform) || !isRegionScope(receipt.regionScope)) return false
  return receipt.hongKongProcessingAccepted === true
    && receipt.hongKongProcessingConsentVersion === HONG_KONG_PROCESSING_CONSENT_VERSION
}

export function readPrivacyConsent(
  storage: PrivacyConsentStorage = runtimeStorage(),
): PrivacyConsentReceipt | null {
  try {
    const value = storage.getStorageSync(PRIVACY_CONSENT_STORAGE_KEY)
    return isCurrentPrivacyConsentReceipt(value) ? value : null
  } catch {
    return null
  }
}

export function hasCurrentPrivacyConsent(
  storage: PrivacyConsentStorage = runtimeStorage(),
): boolean {
  return readPrivacyConsent(storage) !== null
}

export function acceptPrivacyConsent(
  input: AcceptPrivacyConsentInput,
  storage: PrivacyConsentStorage = runtimeStorage(),
  acceptedAt = Date.now(),
): PrivacyConsentReceipt {
  if (!input.agreementAndPrivacyAccepted) {
    throw new Error('The User Agreement and Privacy Policy must be accepted')
  }
  if (!isRegionScope(input.regionScope)) throw new Error('A service region must be selected')
  if (!input.hongKongProcessingAccepted) {
    throw new Error('Separate consent is required for Hong Kong storage and processing')
  }
  if (!Number.isFinite(acceptedAt) || acceptedAt <= 0) throw new Error('Invalid consent timestamp')

  const receipt: PrivacyConsentReceipt = {
    schemaVersion: PRIVACY_CONSENT_SCHEMA_VERSION,
    legalVersion: LEGAL_VERSION,
    acceptedAt,
    language: input.language,
    platform: input.platform,
    regionScope: input.regionScope,
    agreementAndPrivacyAccepted: true,
    hongKongProcessingAccepted: true,
    hongKongProcessingConsentVersion: HONG_KONG_PROCESSING_CONSENT_VERSION,
  }
  storage.setStorageSync(PRIVACY_CONSENT_STORAGE_KEY, receipt)
  return receipt
}

export function clearPrivacyConsent(
  storage: PrivacyConsentStorage = runtimeStorage(),
): boolean {
  try {
    // Invalidate first so a remove failure can never leave a usable receipt.
    storage.setStorageSync(PRIVACY_CONSENT_STORAGE_KEY, null)
  } catch {
    return false
  }
  try {
    storage.removeStorageSync?.(PRIVACY_CONSENT_STORAGE_KEY)
  } catch {
    // The invalid marker already closed the gate; physical cleanup can wait.
  }
  return !hasCurrentPrivacyConsent(storage)
}

export class PrivacyConsentRequiredError extends Error {
  readonly code = 'PRIVACY_CONSENT_REQUIRED'

  constructor() {
    super('Privacy consent is required before business network access')
    this.name = 'PrivacyConsentRequiredError'
  }
}

export function requirePrivacyConsent(
  storage: PrivacyConsentStorage = runtimeStorage(),
): void {
  if (!hasCurrentPrivacyConsent(storage)) throw new PrivacyConsentRequiredError()
}
