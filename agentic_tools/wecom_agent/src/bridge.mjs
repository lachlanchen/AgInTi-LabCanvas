#!/usr/bin/env node

import { execFile } from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';

import AiBot, { generateReqId } from '@wecom/aibot-node-sdk';

import {
  chunkUtf8,
  decideInboundAuthorization,
  inferExtension,
  mediaTypeForPath,
  sanitizeFilename,
} from './protocol.mjs';

const execFileAsync = promisify(execFile);
const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const TOOL_ROOT = path.resolve(SCRIPT_DIR, '..');
const REPO_ROOT = path.resolve(TOOL_ROOT, '../..');
const PRIVATE_DIR = path.join(TOOL_ROOT, '.private');
const DEFAULT_ENV_FILE = path.join(PRIVATE_DIR, 'wecom.local.env');

loadEnvFile(process.env.WECOM_ENV_FILE || DEFAULT_ENV_FILE);

const BOT_ID = String(process.env.WECOM_BOT_ID || '').trim();
const BOT_SECRET = String(process.env.WECOM_BOT_SECRET || '').trim();
const ACCOUNT_ID = String(process.env.WECOM_ACCOUNT_ID || 'default').trim() || 'default';
const LOCAL_API_HOST = '127.0.0.1';
const LOCAL_API_PORT = boundedInteger(process.env.WECOM_LOCAL_API_PORT, 19578, 1024, 65535);
const LOCAL_API_TOKEN = String(process.env.WECOM_LOCAL_API_TOKEN || '').trim();
const PYTHON_BIN = String(process.env.WECOM_PYTHON || 'python3').trim();
const INGEST_SCRIPT = path.join(TOOL_ROOT, 'scripts', 'wecom_ingest.py');
const QUEUE_PATH = path.resolve(process.env.WECOM_TASK_QUEUE || path.join(PRIVATE_DIR, 'wecom_task_queue.jsonl'));
const OUTPUT_ROOT = path.resolve(process.env.WECOM_MEDIA_ROOT || path.join(REPO_ROOT, 'output', 'wecom', 'inbound'));
const ACCESS_MODE = String(process.env.WECOM_ACCESS_MODE || 'owner').trim().toLowerCase();
const PAIR_FIRST_USER = String(process.env.WECOM_PAIR_FIRST_USER || '1') !== '0';
const ALLOWED_USERIDS = new Set(splitList(process.env.WECOM_ALLOWED_USERIDS));
const GROUP_MEMBER_ACCESS = String(process.env.WECOM_GROUP_MEMBER_ACCESS || 'trusted').trim().toLowerCase();
const MAX_INBOUND_BYTES = boundedInteger(process.env.WECOM_MAX_INBOUND_BYTES, 100 * 1024 * 1024, 1024, 500 * 1024 * 1024);
const MAX_OUTBOUND_BYTES = boundedInteger(process.env.WECOM_MAX_OUTBOUND_BYTES, 49 * 1024 * 1024, 1024, 50 * 1024 * 1024);
const ROUTE_TIMEOUT_MS = boundedInteger(process.env.WECOM_INGEST_TIMEOUT_MS, 120000, 5000, 600000);
const OWNER_STATE_PATH = path.join(PRIVATE_DIR, 'owner.local.json');
const KNOWN_CHATS_PATH = path.join(PRIVATE_DIR, 'known_chats.local.json');
const TRUSTED_GROUPS_PATH = path.join(PRIVATE_DIR, 'trusted_groups.local.json');
const SEEN_PATH = path.join(PRIVATE_DIR, 'seen_messages.local.json');
const STATUS_PATH = path.join(PRIVATE_DIR, 'bridge_status.local.json');
const DELIVERY_PATH = path.join(PRIVATE_DIR, 'deliveries.local.json');

if (!BOT_ID || !BOT_SECRET) {
  fatal('WECOM_BOT_ID and WECOM_BOT_SECRET are required. Run `labcanvas wecom init-config`, then fill the ignored env file.');
}
if (!LOCAL_API_TOKEN) {
  fatal('WECOM_LOCAL_API_TOKEN is required. Re-run `labcanvas wecom init-config --force` if the private config is incomplete.');
}

fs.mkdirSync(PRIVATE_DIR, { recursive: true, mode: 0o700 });
fs.mkdirSync(OUTPUT_ROOT, { recursive: true, mode: 0o700 });
fs.mkdirSync(path.dirname(QUEUE_PATH), { recursive: true, mode: 0o700 });

const knownChats = Object.assign(Object.create(null), readJson(KNOWN_CHATS_PATH, {}));
const trustedGroups = new Set(Object.keys(readJson(TRUSTED_GROUPS_PATH, {})));
const seenMessages = new Map(Object.entries(readJson(SEEN_PATH, {})));
const inFlightMessages = new Set();
const deliveries = readJson(DELIVERY_PATH, {});
let authenticated = false;

const logger = {
  debug: (message, ...args) => log('debug', message, ...args),
  info: (message, ...args) => log('info', message, ...args),
  warn: (message, ...args) => log('warn', message, ...args),
  error: (message, ...args) => log('error', message, ...args),
};

const client = new AiBot.WSClient({
  botId: BOT_ID,
  secret: BOT_SECRET,
  wsUrl: process.env.WECOM_WS_URL || undefined,
  maxReconnectAttempts: -1,
  maxAuthFailureAttempts: 5,
  requestTimeout: 15000,
  logger,
});

client.on('connected', () => updateStatus({ connected: true, authenticated: false, event: 'connected' }));
client.on('authenticated', () => {
  authenticated = true;
  updateStatus({ connected: true, authenticated: true, event: 'authenticated' });
  log('info', `Authenticated WeCom bot ${redact(BOT_ID)}`);
});
client.on('disconnected', (reason) => {
  authenticated = false;
  updateStatus({ connected: false, authenticated: false, event: 'disconnected', reason: String(reason || '') });
});
client.on('reconnecting', (attempt) => updateStatus({ connected: false, authenticated: false, event: 'reconnecting', attempt }));
client.on('error', (error) => {
  updateStatus({ connected: client.isConnected, authenticated, event: 'error', error: safeError(error) });
  log('error', safeError(error));
});
client.on('message', (frame) => {
  void handleInbound(frame).catch(async (error) => {
    log('error', `Inbound handling failed: ${safeError(error)}`);
    try {
      const streamId = generateReqId('labcanvas_error');
      await client.replyStream(frame, streamId, 'LabCanvas 没有成功接收这条消息，请稍后重试。', true);
    } catch (replyError) {
      log('error', `Unable to return inbound error: ${safeError(replyError)}`);
    }
  });
});

const apiServer = http.createServer((request, response) => {
  void handleLocalApi(request, response).catch((error) => {
    writeJsonResponse(response, 500, { ok: false, error: safeError(error) });
  });
});

apiServer.listen(LOCAL_API_PORT, LOCAL_API_HOST, () => {
  updateStatus({ connected: false, authenticated: false, event: 'starting', local_api_port: LOCAL_API_PORT });
  log('info', `Local transport API listening on http://${LOCAL_API_HOST}:${LOCAL_API_PORT}`);
  client.connect();
});

async function handleInbound(frame) {
  const body = frame?.body || {};
  const messageId = String(body.msgid || '').trim();
  const senderUserId = String(body.from?.userid || '').trim();
  const chatType = body.chattype === 'group' ? 'group' : 'single';
  const chatId = String(chatType === 'group' ? body.chatid || '' : senderUserId).trim();
  if (!messageId || !senderUserId || !chatId) {
    throw new Error('WeCom frame is missing msgid, sender userid, or chat id.');
  }
  if (seenMessages.has(messageId)) {
    log('info', `Ignored duplicate message ${shortHash(messageId)}`);
    return;
  }
  if (inFlightMessages.has(messageId)) {
    log('info', `Ignored in-flight duplicate message ${shortHash(messageId)}`);
    return;
  }
  const authorization = authorizeInbound(senderUserId, chatId, chatType);
  if (!authorization.allowed) {
    log('warn', `Ignored sender ${shortHash(senderUserId)} under access mode ${ACCESS_MODE}: ${authorization.reason}`);
    return;
  }

  inFlightMessages.add(messageId);
  try {
    rememberChat(chatId, chatType, senderUserId, authorization.role);
    const streamId = generateReqId('labcanvas');
    await client.replyStream(frame, streamId, 'LabCanvas 正在处理。', false);

    const eventDir = inboundEventDir(chatId, messageId);
    fs.mkdirSync(eventDir, { recursive: true, mode: 0o700 });
    const normalized = await normalizeInboundMessage(body, eventDir, authorization);
    const eventPath = path.join(eventDir, 'event.json');
    writePrivateJson(eventPath, normalized);

    const result = await invokeIngest(eventPath);
    const finalReply = String(result.reply || result.ack || '').trim()
      || (result.queued ? '任务已进入 LabCanvas 队列，完成后会把结果发回这个会话。' : '消息已处理。');
    await client.replyStream(frame, streamId, finalReply, true);
    rememberSeen(messageId);
  } finally {
    inFlightMessages.delete(messageId);
  }
}

async function normalizeInboundMessage(body, eventDir, authorization) {
  const attachments = [];
  const textParts = [];
  if (body.text?.content) textParts.push(String(body.text.content));
  if (body.voice?.content) textParts.push(String(body.voice.content));
  if (Array.isArray(body.mixed?.msg_item)) {
    for (const item of body.mixed.msg_item) {
      if (item?.msgtype === 'text' && item.text?.content) textParts.push(String(item.text.content));
      if (item?.msgtype === 'image' && item.image?.url) {
        attachments.push(await downloadAttachment(item.image, 'image', eventDir, attachments.length + 1));
      }
    }
  }
  for (const kind of ['image', 'file', 'video']) {
    if (body[kind]?.url) attachments.push(await downloadAttachment(body[kind], kind, eventDir, attachments.length + 1));
  }

  const quote = normalizeQuote(body.quote);
  if (quote.attachment) {
    attachments.push(await downloadAttachment(quote.attachment.payload, quote.attachment.kind, eventDir, attachments.length + 1, 'quoted'));
  }
  return {
    schema_version: 1,
    transport: 'wecom',
    account_id: ACCOUNT_ID,
    message_id: String(body.msgid || ''),
    chat_id: String(body.chattype === 'group' ? body.chatid || '' : body.from?.userid || ''),
    chat_type: body.chattype === 'group' ? 'group' : 'single',
    sender_userid: String(body.from?.userid || ''),
    authorization_role: String(authorization?.role || 'rejected'),
    irreversible_actions_allowed: ['owner', 'allowlisted'].includes(String(authorization?.role || '')),
    create_time: Number(body.create_time || Math.floor(Date.now() / 1000)),
    msgtype: String(body.msgtype || 'unknown'),
    text: textParts.join('\n').trim(),
    quote_text: quote.text,
    attachments,
    received_at: new Date().toISOString(),
  };
}

function normalizeQuote(quote) {
  if (!quote || typeof quote !== 'object') return { text: '', attachment: null };
  const textParts = [];
  if (quote.text?.content) textParts.push(String(quote.text.content));
  if (quote.voice?.content) textParts.push(String(quote.voice.content));
  if (Array.isArray(quote.mixed?.msg_item)) {
    for (const item of quote.mixed.msg_item) {
      if (item?.msgtype === 'text' && item.text?.content) textParts.push(String(item.text.content));
    }
  }
  for (const kind of ['image', 'file']) {
    if (quote[kind]?.url) return { text: textParts.join('\n').trim(), attachment: { kind, payload: quote[kind] } };
  }
  return { text: textParts.join('\n').trim(), attachment: null };
}

async function downloadAttachment(payload, kind, eventDir, index, prefix = 'attachment') {
  const { buffer, filename } = await client.downloadFile(String(payload.url), payload.aeskey ? String(payload.aeskey) : undefined);
  if (!Buffer.isBuffer(buffer) || buffer.length === 0) throw new Error(`Downloaded ${kind} is empty.`);
  if (buffer.length > MAX_INBOUND_BYTES) throw new Error(`Inbound ${kind} exceeds ${MAX_INBOUND_BYTES} bytes.`);
  let cleanName = sanitizeFilename(filename, `${prefix}-${index}${inferExtension(buffer)}`);
  if (!path.extname(cleanName)) cleanName += inferExtension(buffer);
  const target = uniquePath(eventDir, cleanName);
  atomicWrite(target, buffer, 0o600);
  return { kind, filename: path.basename(target), path: target, size_bytes: buffer.length };
}

async function invokeIngest(eventPath) {
  const env = {
    ...process.env,
    PYTHONPATH: [path.join(REPO_ROOT, 'src'), process.env.PYTHONPATH || ''].filter(Boolean).join(path.delimiter),
  };
  const { stdout, stderr } = await execFileAsync(
    PYTHON_BIN,
    [INGEST_SCRIPT, '--event-file', eventPath, '--queue', QUEUE_PATH, '--json'],
    { cwd: REPO_ROOT, env, timeout: ROUTE_TIMEOUT_MS, maxBuffer: 4 * 1024 * 1024 },
  );
  if (stderr?.trim()) log('warn', `Ingress diagnostics: ${stderr.trim().slice(-1000)}`);
  const payload = parseLastJson(stdout);
  if (!payload?.ok) throw new Error(payload?.error || 'WeCom ingress returned no usable result.');
  return payload;
}

async function handleLocalApi(request, response) {
  const url = new URL(request.url || '/', `http://${LOCAL_API_HOST}:${LOCAL_API_PORT}`);
  if (request.method === 'GET' && url.pathname === '/health') {
    writeJsonResponse(response, 200, {
      ok: true,
      connected: client.isConnected,
      authenticated,
      account_id: ACCOUNT_ID,
      known_chat_count: Object.keys(knownChats).length,
    });
    return;
  }
  if (request.method !== 'POST' || url.pathname !== '/v1/send') {
    writeJsonResponse(response, 404, { ok: false, error: 'not found' });
    return;
  }
  const authorization = String(request.headers.authorization || '');
  if (!constantTimeEqual(authorization, `Bearer ${LOCAL_API_TOKEN}`)) {
    writeJsonResponse(response, 401, { ok: false, error: 'unauthorized' });
    return;
  }
  if (!client.isConnected || !authenticated) {
    writeJsonResponse(response, 503, { ok: false, error: 'WeCom WebSocket is not authenticated.' });
    return;
  }
  const payload = await readRequestJson(request, 1024 * 1024);
  const chatId = String(payload.chat_id || '').trim();
  if (!chatId || !Object.prototype.hasOwnProperty.call(knownChats, chatId)) {
    writeJsonResponse(response, 403, { ok: false, error: 'Refusing proactive send to an unseen WeCom chat.' });
    return;
  }
  const result = await sendOutbound(chatId, payload);
  // The request itself completed even if one attachment failed. Returning 200 lets
  // the worker persist successful deliveries before it decides whether to retry.
  writeJsonResponse(response, 200, { ok: result.errors.length === 0, ...result });
}

async function sendOutbound(chatId, payload) {
  const sentFiles = [];
  const errors = [];
  const sentMessages = [];
  const taskId = String(payload.task_id || '').trim() || `adhoc-${shortHash(`${chatId}:${payload.message || ''}`)}`;
  const ledger = deliveries[taskId] && deliveries[taskId].chat_hash === shortHash(chatId)
    ? deliveries[taskId]
    : { chat_hash: shortHash(chatId), message_chunks: [], file_keys: [], updated_at: new Date().toISOString() };
  const completedChunks = new Set(Array.isArray(ledger.message_chunks) ? ledger.message_chunks : []);
  const completedFiles = new Set(Array.isArray(ledger.file_keys) ? ledger.file_keys : []);
  const chunks = chunkUtf8(payload.message || '', 18000);
  for (const [index, chunk] of chunks.entries()) {
    const chunkKey = `${index}:${shortHash(chunk)}`;
    if (completedChunks.has(chunkKey)) continue;
    try {
      await client.sendMessage(chatId, { msgtype: 'markdown', markdown: { content: chunk } });
      sentMessages.push(Buffer.byteLength(chunk, 'utf8'));
      completedChunks.add(chunkKey);
      ledger.message_chunks = [...completedChunks];
      persistDelivery(taskId, ledger);
    } catch (error) {
      errors.push({ kind: 'message', error: safeError(error) });
      break;
    }
  }
  for (const rawPath of Array.isArray(payload.files) ? payload.files : []) {
    const resolved = path.resolve(String(rawPath || ''));
    try {
      const stat = fs.statSync(resolved);
      if (!stat.isFile()) throw new Error('not a regular file');
      if (stat.size > MAX_OUTBOUND_BYTES) throw new Error(`file exceeds ${MAX_OUTBOUND_BYTES} bytes`);
      const fileKey = shortHash(`${resolved}:${stat.size}:${stat.mtimeMs}`);
      if (completedFiles.has(fileKey)) {
        sentFiles.push(resolved);
        continue;
      }
      const type = mediaTypeForPath(resolved);
      const upload = await client.uploadMedia(fs.readFileSync(resolved), { type, filename: path.basename(resolved) });
      await client.sendMediaMessage(chatId, type, upload.media_id, type === 'video' ? { title: path.basename(resolved) } : undefined);
      sentFiles.push(resolved);
      completedFiles.add(fileKey);
      ledger.file_keys = [...completedFiles];
      persistDelivery(taskId, ledger);
    } catch (error) {
      errors.push({ kind: 'file', path: resolved, error: safeError(error) });
    }
  }
  return { task_id: taskId, sent_messages: sentMessages, sent_files: sentFiles, errors };
}

function persistDelivery(taskId, ledger) {
  ledger.updated_at = new Date().toISOString();
  deliveries[taskId] = ledger;
  const entries = Object.entries(deliveries).sort((left, right) => String(right[1]?.updated_at || '').localeCompare(String(left[1]?.updated_at || '')));
  for (const [oldTaskId] of entries.slice(2000)) delete deliveries[oldTaskId];
  writePrivateJson(DELIVERY_PATH, deliveries);
}

function authorizeInbound(userid, chatId, chatType) {
  const owner = readJson(OWNER_STATE_PATH, {});
  const decision = decideInboundAuthorization({
    accessMode: ACCESS_MODE,
    userId: userid,
    chatId,
    chatType,
    ownerUserId: owner.userid || '',
    pairFirstUser: PAIR_FIRST_USER,
    allowedUserIds: ALLOWED_USERIDS,
    trustedGroupIds: trustedGroups,
    groupMemberAccess: GROUP_MEMBER_ACCESS,
  });
  if (decision.pairOwner) {
    writePrivateJson(OWNER_STATE_PATH, { userid, paired_at: new Date().toISOString() });
    log('info', `Paired first owner ${shortHash(userid)}`);
  }
  if (decision.trustGroup && chatType === 'group' && chatId) {
    trustedGroups.add(chatId);
    writePrivateJson(
      TRUSTED_GROUPS_PATH,
      Object.fromEntries([...trustedGroups].map((id) => [id, { enrolled_at: new Date().toISOString() }])),
    );
    log('info', `Enrolled trusted group ${shortHash(chatId)}`);
  }
  return decision;
}

function rememberChat(chatId, chatType, senderUserId, authorizationRole) {
  knownChats[chatId] = {
    chat_type: chatType,
    last_sender_hash: shortHash(senderUserId),
    authorization_role: authorizationRole,
    trusted_group: chatType === 'group' && trustedGroups.has(chatId),
    last_seen_at: new Date().toISOString(),
  };
  writePrivateJson(KNOWN_CHATS_PATH, knownChats);
}

function rememberSeen(messageId) {
  seenMessages.set(messageId, new Date().toISOString());
  while (seenMessages.size > 5000) seenMessages.delete(seenMessages.keys().next().value);
  writePrivateJson(SEEN_PATH, Object.fromEntries(seenMessages));
}

function inboundEventDir(chatId, messageId) {
  const day = new Date().toISOString().slice(0, 10).replaceAll('-', '');
  return path.join(OUTPUT_ROOT, day, shortHash(chatId), sanitizeFilename(messageId, shortHash(messageId)));
}

function updateStatus(update) {
  writePrivateJson(STATUS_PATH, { ...readJson(STATUS_PATH, {}), ...update, pid: process.pid, updated_at: new Date().toISOString() });
}

function loadEnvFile(filePath) {
  if (!fs.existsSync(filePath)) return;
  for (const rawLine of fs.readFileSync(filePath, 'utf8').split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith('#')) continue;
    const index = line.indexOf('=');
    if (index < 1) continue;
    const key = line.slice(0, index).trim().replace(/^export\s+/, '');
    let value = line.slice(index + 1).trim();
    if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) value = value.slice(1, -1);
    if (!(key in process.env)) process.env[key] = value;
  }
}

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch {
    return fallback;
  }
}

function writePrivateJson(filePath, value) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true, mode: 0o700 });
  atomicWrite(filePath, Buffer.from(`${JSON.stringify(value, null, 2)}\n`), 0o600);
}

function atomicWrite(filePath, buffer, mode) {
  const temporary = `${filePath}.tmp-${process.pid}-${crypto.randomBytes(4).toString('hex')}`;
  fs.writeFileSync(temporary, buffer, { mode });
  fs.renameSync(temporary, filePath);
  fs.chmodSync(filePath, mode);
}

function uniquePath(directory, filename) {
  const parsed = path.parse(filename);
  let candidate = path.join(directory, filename);
  let index = 2;
  while (fs.existsSync(candidate)) {
    candidate = path.join(directory, `${parsed.name}-${index}${parsed.ext}`);
    index += 1;
  }
  return candidate;
}

function parseLastJson(stdout) {
  const lines = String(stdout || '').split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    try {
      return JSON.parse(lines[index]);
    } catch {
      // Keep scanning because backend diagnostics may precede the JSON line.
    }
  }
  return null;
}

async function readRequestJson(request, maxBytes) {
  const chunks = [];
  let total = 0;
  for await (const chunk of request) {
    total += chunk.length;
    if (total > maxBytes) throw new Error('request body too large');
    chunks.push(chunk);
  }
  return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
}

function writeJsonResponse(response, status, payload) {
  if (response.headersSent) return;
  const body = Buffer.from(`${JSON.stringify(payload)}\n`);
  response.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': body.length });
  response.end(body);
}

function splitList(value) {
  return String(value || '').split(/[\s,;]+/).map((item) => item.trim()).filter(Boolean);
}

function boundedInteger(value, fallback, minimum, maximum) {
  const parsed = Number.parseInt(String(value || ''), 10);
  return Number.isFinite(parsed) ? Math.min(maximum, Math.max(minimum, parsed)) : fallback;
}

function constantTimeEqual(left, right) {
  const a = Buffer.from(String(left || ''));
  const b = Buffer.from(String(right || ''));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function shortHash(value) {
  return crypto.createHash('sha256').update(String(value || '')).digest('hex').slice(0, 12);
}

function redact(value) {
  const text = String(value || '');
  return text.length <= 8 ? `${text.slice(0, 2)}...` : `${text.slice(0, 4)}...${text.slice(-4)}`;
}

function safeError(error) {
  return String(error?.message || error || 'unknown error').replaceAll(BOT_SECRET, '[redacted]').slice(0, 1000);
}

function log(level, message, ...args) {
  const suffix = args.length ? ` ${args.map((item) => safeError(item)).join(' ')}` : '';
  const safeMessage = String(message).replaceAll(BOT_SECRET, '[redacted]');
  process.stderr.write(`[${new Date().toISOString()}] [wecom:${level}] ${safeMessage}${suffix}\n`);
}

function fatal(message) {
  process.stderr.write(`${message}\n`);
  process.exit(1);
}

function shutdown(signal) {
  log('info', `Stopping on ${signal}`);
  updateStatus({ connected: false, authenticated: false, event: 'stopped', signal });
  client.disconnect();
  apiServer.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1500).unref();
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));
