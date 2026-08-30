const test = require('node:test');
const assert = require('node:assert/strict');
const freshness = require('../js/freshness.js');

const now = new Date('2026-08-30T06:36:00Z');

test('current snapshots do not promise an exact future run', () => {
  const state = freshness.evaluate('2026-08-30T05:00:00Z', now, 120);
  assert.equal(state.level, 'current');
  assert.match(state.label, /^Current · /);
  assert.doesNotMatch(state.label, /2026|Next|due at/i);
});

test('past refresh targets become visibly delayed', () => {
  const state = freshness.evaluate('2026-08-30T03:00:00Z', now, 120);
  assert.equal(state.level, 'delayed');
  assert.equal(state.label, 'Refresh delayed · 3h 36m ago');
});

test('old and future-dated snapshots never appear current', () => {
  assert.equal(freshness.evaluate('2026-08-29T20:00:00Z', now, 120).level, 'stale');
  assert.equal(freshness.evaluate('2026-08-30T07:00:00Z', now, 120).level, 'unknown');
});
