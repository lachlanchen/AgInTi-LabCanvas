import assert from 'node:assert/strict';
import test from 'node:test';

import { chunkUtf8, inferExtension, mediaTypeForPath, sanitizeFilename } from '../src/protocol.mjs';

test('sanitizeFilename removes traversal and control characters', () => {
  assert.equal(sanitizeFilename('../../bad\u0000:name.pdf'), 'bad_name.pdf');
});

test('inferExtension recognizes common inbound media', () => {
  assert.equal(inferExtension(Buffer.from([0xff, 0xd8, 0xff, 0xe0])), '.jpg');
  assert.equal(inferExtension(Buffer.from('%PDF-1.7')), '.pdf');
});

test('chunkUtf8 enforces byte limits without splitting characters', () => {
  assert.deepEqual(chunkUtf8('甲乙丙', 6), ['甲乙', '丙']);
});

test('mediaTypeForPath uses conservative WeCom upload types', () => {
  assert.equal(mediaTypeForPath('/tmp/render.png'), 'image');
  assert.equal(mediaTypeForPath('/tmp/result.mp4'), 'video');
  assert.equal(mediaTypeForPath('/tmp/report.pdf'), 'file');
});
