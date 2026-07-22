import assert from 'node:assert/strict';
import test from 'node:test';

import {
  chunkUtf8,
  decideInboundAuthorization,
  inboundAttachmentPayloads,
  inferExtension,
  mediaTypeForPath,
  sanitizeFilename,
} from '../src/protocol.mjs';

test('sanitizeFilename removes traversal and control characters', () => {
  assert.equal(sanitizeFilename('../../bad\u0000:name.pdf'), 'bad_name.pdf');
});

test('inferExtension recognizes common inbound media', () => {
  assert.equal(inferExtension(Buffer.from([0xff, 0xd8, 0xff, 0xe0])), '.jpg');
  assert.equal(inferExtension(Buffer.from('%PDF-1.7')), '.pdf');
  assert.equal(inferExtension(Buffer.from('#!AMR\nvoice')), '.amr');
  assert.equal(inferExtension(Buffer.from('OggSvoice')), '.ogg');
  assert.equal(inferExtension(Buffer.from('RIFF0000WAVEfmt ')), '.wav');
});

test('inboundAttachmentPayloads includes exact WeCom voice and media URLs', () => {
  const payloads = inboundAttachmentPayloads({
    image: { url: 'image-url' },
    voice: { url: 'voice-url', aeskey: 'private' },
    text: { content: 'hello' },
  });

  assert.deepEqual(payloads.map(({ kind }) => kind), ['image', 'voice']);
  assert.equal(payloads[1].payload.url, 'voice-url');
});

test('chunkUtf8 enforces byte limits without splitting characters', () => {
  assert.deepEqual(chunkUtf8('甲乙丙', 6), ['甲乙', '丙']);
});

test('mediaTypeForPath uses conservative WeCom upload types', () => {
  assert.equal(mediaTypeForPath('/tmp/render.png'), 'image');
  assert.equal(mediaTypeForPath('/tmp/result.mp4'), 'video');
  assert.equal(mediaTypeForPath('/tmp/report.pdf'), 'file');
});

test('owner enrollment trusts one group without opening unrelated groups or DMs', () => {
  const paired = decideInboundAuthorization({
    accessMode: 'owner',
    userId: 'owner',
    chatId: 'lab-agent',
    chatType: 'group',
    pairFirstUser: true,
  });
  assert.equal(paired.allowed, true);
  assert.equal(paired.pairOwner, true);
  assert.equal(paired.trustGroup, true);

  const member = decideInboundAuthorization({
    accessMode: 'owner',
    userId: 'researcher',
    chatId: 'lab-agent',
    chatType: 'group',
    ownerUserId: 'owner',
    trustedGroupIds: new Set(['lab-agent']),
  });
  assert.deepEqual(member, { allowed: true, role: 'group_member', reason: 'trusted_group' });

  const unrelated = decideInboundAuthorization({
    accessMode: 'owner',
    userId: 'researcher',
    chatId: 'other-group',
    chatType: 'group',
    ownerUserId: 'owner',
    trustedGroupIds: new Set(['lab-agent']),
  });
  assert.equal(unrelated.allowed, false);

  const dm = decideInboundAuthorization({
    accessMode: 'owner',
    userId: 'researcher',
    chatId: 'researcher',
    chatType: 'single',
    ownerUserId: 'owner',
    trustedGroupIds: new Set(['lab-agent']),
  });
  assert.equal(dm.allowed, false);
});
