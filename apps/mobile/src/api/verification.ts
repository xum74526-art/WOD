import { request, upload } from './request'

export type VerificationOcrStatus =
  | 'not_started'
  | 'processing'
  | 'matched'
  | 'review_required'
  | 'error'
  | 'unavailable'

export interface VerificationOcrSummary {
  name_match: boolean
  id_number_match: boolean
  birth_date_match: boolean
  gender_match: boolean
  validity_match: boolean
}

export interface VerificationOcrValidity {
  valid_from?: string | null
  valid_until?: string | null
  long_term?: boolean | null
}

export interface VerificationOcrFields {
  ocr_status?: VerificationOcrStatus | null
  ocr_summary?: Partial<VerificationOcrSummary> | null
  ocr_error_code?: string | null
  ocr_updated_at?: string | null
  ocr_message?: string | null
  ocr_validity?: VerificationOcrValidity | null
}

export interface VerificationInfo extends VerificationOcrFields {
  status: string  // unverified/pending/verified/rejected
  real_name?: string
  id_card_masked?: string
  consent_recorded?: boolean
  reject_reason?: string
  front_photo_uploaded?: boolean
  back_photo_uploaded?: boolean
}

export function getVerification() {
  return request<VerificationInfo>({ url: '/verification' })
}

export function submitVerification(real_name: string, id_card: string, sensitive_consent: boolean) {
  return request<VerificationInfo>({
    url: '/verification',
    method: 'POST',
    data: { real_name, id_card, sensitive_consent },
  })
}

export function uploadVerificationPhoto(filePath: string, side: 'front' | 'back') {
  return upload<VerificationInfo>({
    url: '/verification/upload',
    filePath,
    name: side,
    silent: true,
    timeout: 60000,
  })
}

export function uploadVerificationPhotos(frontFilePath: string, backFilePath: string) {
  return upload<VerificationInfo>({
    url: '/verification/upload',
    files: [
      { name: 'front', uri: frontFilePath },
      { name: 'back', uri: backFilePath },
    ],
    silent: true,
    timeout: 60000,
  })
}
