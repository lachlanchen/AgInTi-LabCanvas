import path from 'node:path';

const IMAGE_SUFFIXES = new Set(['.jpg', '.jpeg', '.png', '.gif', '.webp']);
const VIDEO_SUFFIXES = new Set(['.mp4', '.mov', '.m4v']);

export function sanitizeFilename(value, fallback = 'attachment') {
  const base = path.basename(String(value || '').replaceAll('\\', '/'));
  const clean = base
    .normalize('NFKC')
    .replace(/[\u0000-\u001f\u007f]/g, '')
    .replace(/[<>:"/\\|?*]/g, '_')
    .replace(/^\.+/, '')
    .trim();
  return (clean || fallback).slice(0, 180);
}

export function inferExtension(buffer, fallback = '.bin') {
  if (!Buffer.isBuffer(buffer) || buffer.length < 4) return fallback;
  if (buffer[0] === 0xff && buffer[1] === 0xd8 && buffer[2] === 0xff) return '.jpg';
  if (buffer.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) return '.png';
  if (buffer.subarray(0, 4).toString('ascii') === 'GIF8') return '.gif';
  if (buffer.subarray(0, 4).toString('ascii') === '%PDF') return '.pdf';
  if (buffer.subarray(0, 4).toString('hex') === '504b0304') return '.zip';
  if (buffer.length >= 12 && buffer.subarray(4, 8).toString('ascii') === 'ftyp') return '.mp4';
  if (buffer.length >= 12 && buffer.subarray(0, 4).toString('ascii') === 'RIFF' && buffer.subarray(8, 12).toString('ascii') === 'WEBP') return '.webp';
  return fallback;
}

export function chunkUtf8(value, maxBytes = 18000) {
  const text = String(value || '');
  if (!text) return [];
  const chunks = [];
  let current = '';
  let currentBytes = 0;
  for (const character of text) {
    const size = Buffer.byteLength(character, 'utf8');
    if (current && currentBytes + size > maxBytes) {
      chunks.push(current);
      current = '';
      currentBytes = 0;
    }
    current += character;
    currentBytes += size;
  }
  if (current) chunks.push(current);
  return chunks;
}

export function mediaTypeForPath(filePath) {
  const suffix = path.extname(String(filePath || '')).toLowerCase();
  if (IMAGE_SUFFIXES.has(suffix)) return 'image';
  if (VIDEO_SUFFIXES.has(suffix)) return 'video';
  return 'file';
}

export function canonicalChatLabel(accountId, chatType, chatId, digest) {
  const account = String(accountId || 'default').replace(/[^0-9A-Za-z_.-]+/g, '-').slice(0, 32) || 'default';
  const kind = chatType === 'group' ? 'group' : 'dm';
  return `wecom:${account}:${kind}:${String(digest || chatId || '').slice(0, 16)}`;
}
