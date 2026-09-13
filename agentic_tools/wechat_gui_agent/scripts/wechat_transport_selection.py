"""Lightweight personal-WeChat transport choice shared by monitors and workers."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

SCRIPTS = Path(__file__).resolve().parent
PRIVATE = SCRIPTS.parent / '.private'
CONFIG = PRIVATE / 'wechat_tiny11.local.json'
STORE = PRIVATE / 'tiny11/message_999998.db'


def tiny11_enabled():
    if os.environ.get('WECHAT_TINY11_DISABLE') == '1':
        return False
    try:
        return json.loads(CONFIG.read_text()).get('enabled') is True
    except (OSError, ValueError):
        return False


def tiny11_health():
    try:
        config = json.loads(CONFIG.read_text())
        state = json.loads((STORE.parent / 'status.json').read_text())
    except (OSError, ValueError):
        config, state = {}, {}
    age = max(0, time.time() - state.get('last_sync_epoch', 0))
    ready = bool(state.get('ok') and age < 60 and config.get('delivery_verified')
                 and state.get('client_ready') is True)
    return {'ok': ready, 'available': ready, 'known': True, 'transport': 'wechat_tiny11',
            'status': 'unlocked' if ready else 'transport_unavailable',
            'reason': 'native_store_and_delivery_ready' if ready else 'native_transport_not_ready',
            'client_ready': state.get('client_ready') is True,
            'human_action_required': False, 'state_age_seconds': round(age),
            'binding_missing_chats': state.get('binding_missing_chats', []),
            'novnc_url': 'http://127.0.0.1:6143/'}


def send_tiny11(chat, *, message='', files=(), task_id):
    if not tiny11_enabled():
        raise RuntimeError('WECHAT_TINY11_NOT_READY: transport is disabled')
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w+', dir=PRIVATE, suffix='.json') as packet:
        json.dump({'chat': chat, 'message': message, 'files': [str(p) for p in files],
                   'task_id': task_id}, packet, ensure_ascii=False)
        packet.flush()
        try:
            proc = subprocess.run(
                [os.environ.get('WECHAT_TINY11_PYTHON', '/usr/bin/python3'),
                 str(SCRIPTS / 'wechat_tiny11_bridge.py'), 'send', '--request-file', packet.name],
                capture_output=True, text=True, timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            # The child may have submitted before its reply was lost. No
            # transport fallback or automatic resend after ambiguous input.
            raise RuntimeError('WECHAT_GUI_SEND_UNCERTAIN: sender timed out; reconcile native receipt') from exc
    try:
        result = json.loads(proc.stdout)
    except ValueError as exc:
        raise RuntimeError('WECHAT_GUI_SEND_UNCERTAIN: sender result unavailable') from exc
    if proc.returncode or not result.get('ok'):
        raise RuntimeError(str(result.get('error') or result.get('errors') or 'WeChat delivery failed'))
    return result
