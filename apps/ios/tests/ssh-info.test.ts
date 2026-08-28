import assert from 'node:assert/strict'
import test from 'node:test'

import { isValidSshInfo } from '../src/utils/ssh-info.ts'

test('accepts command and labelled SSH delivery formats', () => {
  assert.equal(isValidSshInfo('ssh root@gpu.example.com -p 2222\npassword: secret'), true)
  assert.equal(isValidSshInfo('主机：203.0.113.8\n用户名：ubuntu\n端口：22\n密码：secret'), true)
  assert.equal(isValidSshInfo('ssh admin@[2001:db8::1]'), true)
})

test('rejects notes, invalid hosts and invalid explicit ports', () => {
  assert.equal(isValidSshInfo('please contact me for access'), false)
  assert.equal(isValidSshInfo('ssh root@localhost -p 22'), false)
  assert.equal(isValidSshInfo('ssh root@bad..host -p 22'), false)
  assert.equal(isValidSshInfo('ssh root@gpu.example.com -p 0'), false)
  assert.equal(isValidSshInfo('ssh root@gpu.example.com -p 65536'), false)
})
