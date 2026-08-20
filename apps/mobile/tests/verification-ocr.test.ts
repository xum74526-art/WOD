import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  OCR_SUMMARY_FIELDS,
  hasOcrResult,
  isOcrRetryable,
  normalizeOcrStatus,
  ocrSummaryValue,
  shouldPollOcr,
} from '../src/utils/verification-ocr.ts'

test('OCR contract accepts only documented status values', () => {
  for (const status of ['not_started', 'processing', 'matched', 'review_required', 'error', 'unavailable']) {
    assert.equal(normalizeOcrStatus(status), status)
  }
  assert.equal(normalizeOcrStatus('verified'), null)
  assert.equal(normalizeOcrStatus(undefined), null)
})

test('legacy responses without OCR fields remain compatible', () => {
  assert.equal(hasOcrResult({}), false)
  assert.equal(hasOcrResult({ ocr_status: 'not_started' }), false)
  assert.equal(hasOcrResult({ ocr_status: 'processing' }), true)
})

test('summary exposes exactly the five privacy-safe comparison results', () => {
  assert.deepEqual(OCR_SUMMARY_FIELDS.map((field) => field.key), [
    'name_match',
    'id_number_match',
    'birth_date_match',
    'gender_match',
    'validity_match',
  ])
  assert.equal(OCR_SUMMARY_FIELDS.at(-1)?.resultType, 'validity')
  assert.equal(ocrSummaryValue({ name_match: true }, 'name_match'), true)
  assert.equal(ocrSummaryValue({ name_match: false }, 'name_match'), false)
  assert.equal(ocrSummaryValue({}, 'name_match'), null)
})

test('processing polls while failure and manual-review states allow retry', () => {
  assert.equal(shouldPollOcr('processing'), true)
  assert.equal(shouldPollOcr('matched'), false)
  assert.equal(isOcrRetryable('review_required'), true)
  assert.equal(isOcrRetryable('error'), true)
  assert.equal(isOcrRetryable('unavailable'), true)
  assert.equal(isOcrRetryable('matched'), false)
})

test('user and finance views never render OCR text or raw validity values', () => {
  for (const page of ['../src/pages/verification/index.vue', '../src/pages/finance/index.vue']) {
    const source = readFileSync(new URL(page, import.meta.url), 'utf8')
    assert.equal(source.includes('ocr_message'), false)
    assert.equal(source.includes('ocr_validity'), false)
    assert.equal(source.includes('id_number_match'), false)
  }
})

test('identity submission carries explicit consent into the canonical manual KYC contract', () => {
  const source = readFileSync(new URL('../src/pages/verification/index.vue', import.meta.url), 'utf8')
  const apiSource = readFileSync(new URL('../src/api/verification.ts', import.meta.url), 'utf8')
  assert.match(source, /const ocrConsent = ref\(false\)/)
  assert.match(source, /if \(!ocrConsent\.value\)/)
  assert.match(source, /localOcrConsentRequired/)
  assert.match(source, /submitVerification\(form\.real_name, id, true\)/)
  assert.match(source, /async function retryOcr\(\)[\s\S]*?await onSubmit\(\)/)
  assert.match(apiSource, /url: '\/account\/kyc\/manual'/)
  assert.match(apiSource, /legal_name: real_name/)
  assert.match(apiSource, /identifier_number: id_card/)
  assert.match(apiSource, /declaration_accepted: sensitive_consent/)
})

test('finance review never invents a legacy photo endpoint for manual approval', () => {
  const source = readFileSync(new URL('../src/pages/finance/index.vue', import.meta.url), 'utf8')
  const apiSource = readFileSync(new URL('../src/api/finance.ts', import.meta.url), 'utf8')
  assert.match(source, /if \(!item\.front_photo_uploaded \|\| !item\.back_photo_uploaded\) return false/)
  assert.match(source, /return isOcrMatched\(item\) \|\| hasViewedBothPhotos\(item\)/)
  assert.match(source, /requiresManualOverride \? 'approveAfterManualCheckConfirm' : 'approveIdentityConfirm'/)
  assert.match(source, /isOcrMatched\(item\) \? 'oneClickApproveIdentity' : 'approveAfterManualCheck'/)
  assert.match(apiSource, /front_photo_uploaded: false/)
  assert.match(apiSource, /back_photo_uploaded: false/)
  assert.doesNotMatch(source, /uni\.downloadFile/)
  assert.doesNotMatch(source, /finance\/verifications\/.*\/photo/)
  assert.doesNotMatch(source, /status === null \|\| status === 'matched'/)
})
