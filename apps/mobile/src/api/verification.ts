import { request } from './request'

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

function toVerification(result: any): VerificationInfo {
  const application = result.application || result
  const status = result.status || application.status || 'unverified'
  return {
    status: status === 'approved' ? 'verified' : status,
    real_name: application.subject?.legal_name,
    id_card_masked: application.subject?.identifier_number,
    consent_recorded: Boolean(application.declaration_accepted_at),
    reject_reason: application.review_note,
    front_photo_uploaded: false,
    back_photo_uploaded: false,
    ocr_status: 'unavailable',
    ocr_message: '统一后端使用加密资料人工审核，不执行本地 OCR',
  }
}

export function getVerification() {
  return request<any>({ url: '/account/kyc' }).then(toVerification)
}

export function submitVerification(real_name: string, id_card: string, sensitive_consent: boolean) {
  return request<any>({
    url: '/account/kyc/manual',
    method: 'POST',
    data: {
      verification_type: 'individual',
      country_code: 'CN',
      legal_name: real_name,
      identifier_type: 'national_id',
      identifier_number: id_card,
      declaration_accepted: sensitive_consent,
    },
  }).then(toVerification)
}

export function uploadVerificationPhoto(filePath: string, side: 'front' | 'back') {
  void filePath
  void side
  return Promise.reject<VerificationInfo>(new Error('证件照片对象存储尚未配置，请直接提交加密文字资料审核'))
}

export function uploadVerificationPhotos(frontFilePath: string, backFilePath: string) {
  void frontFilePath
  void backFilePath
  return Promise.reject<VerificationInfo>(new Error('证件照片对象存储尚未配置，请直接提交加密文字资料审核'))
}
