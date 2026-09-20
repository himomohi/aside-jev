import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { selectedLocales, mediaBase } from '../video/scripts/locales.mjs';

test('English is the default and unsupported locales are rejected', () => {
  assert.deepEqual(selectedLocales([]), ['en']);
  assert.deepEqual(selectedLocales(['--locale', 'ko']), ['ko']);
  assert.deepEqual(selectedLocales(['--locale', 'all']), ['en', 'ko']);
  assert.throws(() => selectedLocales(['--locale', 'ja']));
  assert.throws(() => selectedLocales(['--locale']));
});

test('Korean has the same non-empty video messages as English', () => {
  const read = locale => JSON.parse(readFileSync(new URL(`../video/src/locales/${locale}.json`, import.meta.url)));
  const en = read('en'); const ko = read('ko');
  assert.deepEqual(Object.keys(en).sort(), Object.keys(ko).sort());
  for (const dictionary of [en, ko]) for (const value of Object.values(dictionary)) assert.equal(typeof value === 'string' && value.trim().length > 0, true);
});

test('Default assets keep stable names and Korean assets cannot overwrite them', () => {
  assert.equal(mediaBase('en'), 'jev-speed-duel');
  assert.equal(mediaBase('ko'), 'jev-speed-duel.ko');
});
