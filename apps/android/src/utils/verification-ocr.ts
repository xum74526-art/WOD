import type {
  VerificationOcrFields,
  VerificationOcrStatus,
  VerificationOcrSummary,
} from '@/api/verification'

export const OCR_SUMMARY_FIELDS: ReadonlyArray<{
  key: keyof VerificationOcrSummary
  label: string
  resultType?: 'match' | 'validity'
}> = [
  { key: 'name_match', label: 'ocrFieldName' },
  { key: 'id_number_match', label: 'ocrFieldIdNumber' },
  { key: 'birth_date_match', label: 'ocrFieldBirthDate' },
  { key: 'gender_match', label: 'ocrFieldGender' },
  { key: 'validity_match', label: 'ocrFieldValidity', resultType: 'validity' },
]

const OCR_STATUSES = new Set<VerificationOcrStatus>([
  'not_started',
  'processing',
  'matched',
  'review_required',
  'error',
  'unavailable',
])

export function normalizeOcrStatus(value: unknown): VerificationOcrStatus | null {
  return typeof value === 'string' && OCR_STATUSES.has(value as VerificationOcrStatus)
    ? value as VerificationOcrStatus
    : null
}

export function hasOcrResult(value: VerificationOcrFields | null | undefined): boolean {
  const status = normalizeOcrStatus(value?.ocr_status)
  return Boolean(status && status !== 'not_started')
}

export function ocrSummaryValue(
  summary: Partial<VerificationOcrSummary> | null | undefined,
  key: keyof VerificationOcrSummary,
): boolean | null {
  return typeof summary?.[key] === 'boolean' ? summary[key] as boolean : null
}

export function isOcrRetryable(status: VerificationOcrStatus | null): boolean {
  return status === 'review_required' || status === 'error' || status === 'unavailable'
}

export function shouldPollOcr(status: VerificationOcrStatus | null): boolean {
  return status === 'processing'
}
