import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import {
  AMBIGUOUS_BANK_BIN_PREFIXES,
  bankNameSuggestion,
  isRegisteredBankCardStatus,
  luhnCheckCardNumber,
} from '../src/utils/bank-card.ts'

const bankCardPage = readFileSync(new URL('../src/pages/bank-cards/index.vue', import.meta.url), 'utf8')

test('registered and historical safe states remain usable without claiming bank verification', () => {
  for (const status of ['registered', 'pending_review', 'active']) {
    assert.equal(isRegisteredBankCardStatus(status), true)
  }
  for (const status of ['rejected', 'disabled', 'verified']) {
    assert.equal(isRegisteredBankCardStatus(status), false)
  }
})

test('Luhn validation rejects malformed card numbers before registration', () => {
  assert.equal(luhnCheckCardNumber('4539 5787 6362 1486'), true)
  assert.equal(luhnCheckCardNumber('4539578763621487'), false)
  assert.equal(luhnCheckCardNumber('1234'), false)
})

test('conflicting BIN prefixes never produce a bank-name suggestion', () => {
  for (const prefix of AMBIGUOUS_BANK_BIN_PREFIXES) {
    assert.equal(bankNameSuggestion(`${prefix}0000000000`), '')
  }
  assert.equal(bankNameSuggestion('6222020000000000'), '中国工商银行')
})

test('unverified users see only the real-name verification card after loading', () => {
  assert.match(bankCardPage, /v-else-if="verification && verification\.status !== 'verified'" class="verify-card"/)
  assert.match(bankCardPage, /v-else-if="!verification \|\| loadError" class="load-error"/)
  assert.match(bankCardPage, /<template v-else>[\s\S]*?<view v-if="!list\.length" class="card empty-card"/)
  assert.match(bankCardPage, /@tap="goVerification"/)

  assert.doesNotMatch(bankCardPage, /class="notice-card"/)
  assert.doesNotMatch(bankCardPage, /class="service-warning"/)
  assert.doesNotMatch(bankCardPage, /bankCardRegistrationTitle|bankCardRegistrationNotice/)
})
