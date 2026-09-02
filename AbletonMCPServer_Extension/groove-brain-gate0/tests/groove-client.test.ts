import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseGrooveResponse, parseSearchResponse } from '../src/groove-client.js';

test('a search response becomes typed hits', () => {
  const parsed = parseSearchResponse(
    JSON.stringify({
      total: 103,
      returned: 1,
      items: [
        {
          id: 'a1',
          genre: ['metal'],
          bpm: ['bpm_140_159'],
          kit: ['kick'],
          bars: 4,
          meter: '4/4',
          note_count: 12,
        },
      ],
    }),
  );
  assert.equal(parsed.total, 103);
  assert.equal(parsed.items[0].id, 'a1');
  assert.equal(parsed.items[0].noteCount, 12);
});

test('a groove response becomes a writable groove', () => {
  const parsed = parseGrooveResponse(
    JSON.stringify({ id: 'a1', bars: 2, meter: '4/4', ppq: 480, notes: [[36, 0, 120, 100]] }),
  );
  assert.equal(parsed.ppq, 480);
  assert.equal(parsed.notes.length, 1);
});

test('a malformed payload is refused rather than half-read', () => {
  assert.throws(() => parseSearchResponse('not json'), /INVALID_SEARCH_RESPONSE/);
  assert.throws(() => parseSearchResponse('{"total":1}'), /INVALID_SEARCH_RESPONSE/);
  assert.throws(() => parseGrooveResponse('{"id":"a1"}'), /INVALID_GROOVE_RESPONSE/);
});

test('a note that is not four numbers is refused', () => {
  // The notes go straight into Live. A short tuple would write a NaN start.
  assert.throws(
    () => parseGrooveResponse('{"id":"a1","bars":1,"meter":"4/4","ppq":480,"notes":[[36,0]]}'),
    /INVALID_GROOVE_RESPONSE/,
  );
});
