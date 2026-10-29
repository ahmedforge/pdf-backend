import test from 'node:test'
import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { isGuestToken } from '../src/lib/guest-session.js'
const token = claims => `header.${Buffer.from(JSON.stringify(claims)).toString('base64url')}.signature`
test('only an explicit guest claim enables the demo UI', () => {
  assert.equal(isGuestToken(token({ sub: '20', guest: true })), true)
  assert.equal(isGuestToken(token({ sub: '20' })), false)
  assert.equal(isGuestToken(token({ guest: 'true' })), false)
  assert.equal(isGuestToken(token({ guest: false })), false)
})
test('missing or corrupt tokens never enable guest UI', () => {
  for (const value of ['', null, undefined, 'invalid', 'a.not-json.b']) assert.equal(isGuestToken(value), false)
})
