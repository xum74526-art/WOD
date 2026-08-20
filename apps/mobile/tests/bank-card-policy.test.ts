import assert from 'node:assert/strict'
import test from 'node:test'

import {
  AMBIGUOUS_BANK_BIN_PREFIXES,
  bankNameSuggestion,
  isRegisteredBankCardStatus,
  luhnCheckCardNumber,
} from '../src/utils/bank-card.ts'

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
