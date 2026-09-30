#!/usr/bin/env python3
"""Recover an exact Channels card link from the selected Windows WeChat app."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

from PIL import Image, ImageOps

from shipinhao_gui_audio_capture import exact_cover_candidates
from shipinhao_media_transcribe import (
    DEFAULT_CACHE_ROOT, download_media, extract_shipinhao_media_profile,
    normalize_identity, safe_component, resolve_sph_share_profile, merge_resolved_share_profile,
)
from shipinhao_share_link_resolver import extract_share_urls
from wechat_tiny11_bridge import Tiny11WeChatBridge, native_docked_pane as player_box
from wecom_gui_bridge import write_private_json


def card_candidates(screen, cover, region, output_dir):
    """Native Windows card thumbnails use centered 4:3/3:4 cover crops."""
    candidates = []
    with Image.open(cover) as source:
        for label, ratio in (('original', source.width / source.height), ('landscape', 4/3), ('portrait', 3/4)):
            width = min(source.width, round(source.height * ratio))
            height = min(source.height, round(source.width / ratio))
            crop = ImageOps.fit(source, (width, height))
            path = output_dir / f'cover-match-{label}.png'
            crop.save(path)
            path.chmod(0o600)
            candidates.extend(exact_cover_candidates(screen, path, region=region, min_confidence=.80))
    return sorted(candidates, key=lambda item: item['match_confidence'], reverse=True)


def exact_player_title(expected, observed):
    expected, observed = normalize_identity(expected), normalize_identity(observed)
    return len(expected) >= 4 and expected in observed


def verify_player_title(bridge, crop, expected):
    # The footer is a text block; sparse OCR can misread individual glyphs.
    # Require an exact normalized title in either reading, never fuzzy identity.
    return any(exact_player_title(expected, bridge.ocr_scaled(crop, scale=3, psm=psm))
               for psm in (6, 11))


def wait_copied_link(bridge, marker, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = bridge.get_clipboard()
        urls = extract_share_urls(value) if value != marker else []
        if len(urls) == 1:
            return urls[0]
        time.sleep(.2)
    raise RuntimeError('native_copy_link_clipboard_unavailable')


def verify_resolved_card(profile, url):
    resolved = resolve_sph_share_profile(url)
    for field in ('title', 'author'):
        if not resolved.get(field) or normalize_identity(resolved[field]) != normalize_identity(profile.get(field)):
            raise ValueError('native_link_resolved_' + field + '_mismatch')
    return merge_resolved_share_profile({**profile, 'share_token': url.rsplit('/', 1)[-1]}, resolved)


def menu_panel_boxes(path):
    """Isolate light native popups from a playing video's noisy background."""
    import cv2

    image = cv2.imread(str(path))
    if image is None:
        return []
    mask = cv2.inRange(image, (210, 210, 210), (255, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if (80 <= width <= 400 and 50 <= height <= 500
                and cv2.contourArea(contour) >= .85 * width * height):
            boxes.append((x, y, width, height))
    return sorted(boxes, key=lambda box: (box[1], box[0]))


def match_menu(bridge, screen, box, labels, output_dir, label):
    crop = bridge.crop(screen, box, output_dir / f'{label}.png')
    crops = [
        (bridge.crop(crop, panel, output_dir / f'{label}-panel-{index}.png'), panel[0], panel[1])
        for index, panel in enumerate(menu_panel_boxes(crop))
    ]
    crops.append((crop, 0, 0))
    if box[2] < 200:
        crops.append((bridge.crop(crop, (29, 0, box[2] - 29, box[3]),
                                  output_dir / f'{label}-text.png'), 29, 0))
    for candidate, inset_x, inset_y in crops:
        for text in labels:
            for native in (False, True):
                match = bridge.find_ocr_line(candidate, text, scale=3, native_pixels=native)
                if match and match.get('similarity') == 1:
                    return (box[0] + inset_x + int(match['center_x']),
                            box[1] + inset_y + int(match['center_y']))
    return None


def player_tab_close_point(screen, window, player):
    """Find the small X in the owned dock tab, never the app title bar."""
    import cv2
    import numpy as np

    left, top = player[0], window.y + 35
    with Image.open(screen).convert('RGB') as image:
        header = np.array(image.crop((left, top, left + min(player[2], 320), top + 40)))
    gray = cv2.cvtColor(header, cv2.COLOR_RGB2GRAY)
    mask = ((gray < 170) & ((header.max(axis=2).astype(int) - header.min(axis=2)) < 20)).astype('uint8')
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    points = []
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        if not (8 <= width <= 16 and 8 <= height <= 16 and abs(width - height) <= 1):
            continue
        rows, columns = np.nonzero(mask[y:y+height, x:x+width])
        distance = np.minimum(abs(rows - columns), abs(rows + columns - (width - 1)))
        if len(rows) >= 2 * width - 3 and np.mean(distance <= 1) >= .9:
            points.append((left + x + width//2, top + y + height//2))
    return points[0] if len(points) == 1 else None


def close_owned_player(bridge, window, player):
    # A popup consumes the first click; dismiss it before locating the tab X.
    bridge.click(window.x + 300, window.y + 40)
    time.sleep(.2)
    screen = bridge.capture_screen('channels-owned-tab-close')
    point = player_tab_close_point(screen, window, player)
    if point is None:
        raise RuntimeError('native_owned_tab_close_unavailable')
    bridge.click(*point)
    # Closing the dock shrinks the app. Its old bounds include the desktop,
    # whose dark background can otherwise be mistaken for a remaining player.
    for _ in range(8):
        time.sleep(.3)
        current_window = bridge.find_window()
        if not player_box(bridge.capture_screen('channels-owned-tab-closed'), current_window):
            return
    raise RuntimeError('native_owned_tab_close_not_confirmed')


def recover(chat, source_text, output_dir, *, bridge=None, max_scrolls=48):
    profile = extract_shipinhao_media_profile(source_text)
    if not profile.get('object_id') or not profile.get('title'):
        raise ValueError('exact_card_identity_missing')
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    output_dir.chmod(0o700)
    def stage(name, **fields):
        write_private_json(output_dir / 'stage.json', {
            'stage': name, 'object_id': profile['object_id'],
            'observed_at': datetime.now(timezone.utc).isoformat(), **fields})
    stage('source_preparation')
    saved = output_dir / 'native-share-link.json'
    if saved.is_file():
        try:
            prior = json.loads(saved.read_text())
            if (prior.get('source_chat') == chat and prior.get('object_id') == profile['object_id']
                    and prior.get('content_identity_verified') is True):
                verify_resolved_card(profile, prior['share_url'])
                stage('share_link_recovered', reused=True)
                return {**prior, 'reused': True}
        except (ValueError, OSError, KeyError, RuntimeError):
            pass
    candidate_path = output_dir / 'native-share-candidate.json'
    if candidate_path.is_file():
        try:
            candidate = json.loads(candidate_path.read_text())
        except (OSError, ValueError):
            candidate = {}
        if (candidate.get('source_chat') == chat and candidate.get('object_id') == profile['object_id']
                and candidate.get('title') == profile['title']
                and candidate.get('author') == profile.get('author', '') and candidate.get('share_url')):
            stage('verify_resolved_identity', reused_candidate=True)
            # A provider outage is not a reason to reopen the client or ask for
            # another card. This candidate is still unusable until verified.
            try:
                resolved = verify_resolved_card(profile, candidate['share_url'])
            except ValueError:
                pass  # A mismatched candidate must be reacquired, never trusted.
            else:
                result = {**candidate, 'status': 'share_link_recovered',
                          'content_identity_verified': True, 'reused': True,
                          'identity_method': 'exact_card_cover_and_resolved_title_author'}
                write_private_json(output_dir / 'resolved-profile.json', resolved)
                write_private_json(saved, result)
                stage('share_link_recovered', reused_candidate=True)
                return result
    cover = DEFAULT_CACHE_ROOT / safe_component(profile['object_id']) / 'card-cover.jpg'
    if not cover.is_file():
        cover.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        for url in profile.get('cover_urls', []):
            try:
                download_media(url, cover, max_bytes=8*1024*1024, timeout=20)
                with Image.open(cover) as image:
                    image.verify()
                break
            except Exception:
                cover.unlink(missing_ok=True)
    if not cover.is_file():
        raise RuntimeError('exact_card_cover_unavailable')
    # Fail clearly instead of silently getting no template candidates.
    import cv2  # noqa: F401
    b = bridge or Tiny11WeChatBridge()
    player = None
    opened = False
    menu_open = False
    cleanup_error = None
    with b.serialized_gui():
        try:
            w = b.ensure_chat(chat)
            screen = b.capture_screen('channels-before-open')
            if player_box(screen, w):
                raise RuntimeError('native_player_already_open_preserve_user_tab')
            b.scroll_chat_to_bottom(w)
            stage('find_card')
            found = None
            for scan in range(max_scrolls):
                screen = b.capture_screen(f'channels-card-scan-{scan}')
                left, top, width, height = b.history_surface(w)
                region = {'left': left, 'top': top, 'width': width, 'height': height}
                candidates = card_candidates(screen, cover, region, output_dir)
                if candidates:
                    found = candidates[0]
                    point = (left + int(found['center_x']), top + int(found['center_y']))
                    break
                b.tiny11.invoke({'action': 'macro', 'actions': [
                    {'action': 'wheel', 'x': left + 100, 'y': top + height//2, 'delta': 600}
                    for _ in range(4)]})
                time.sleep(.3)
            if found is None:
                raise RuntimeError('exact_card_not_visible')
            b.right_click(*point)
            menu_open = True
            time.sleep(.2)
            menu = b.capture_screen('channels-silent-play-menu')
            menu_left = min(point[0], w.x + w.width - 165)
            menu_top = min(point[1], w.y + w.height - 260)
            action = match_menu(b, menu, (menu_left, menu_top, 165, 260),
                                ('Silent Play', '静音播放'), output_dir, 'silent-play-menu')
            if action is None:
                action = match_menu(b, menu, (w.x, w.y, w.width, w.height),
                                    ('Silent Play', '静音播放'), output_dir, 'silent-play-menu-full')
            if action is None:
                raise RuntimeError('native_silent_play_action_unavailable')
            b.click(*action)
            menu_open = False
            opened = True
            stage('wait_player')
            deadline = time.monotonic() + 180
            title_ok = False
            activated = False
            while time.monotonic() < deadline:
                w = b.find_window()
                screen = b.capture_screen('channels-player-load')
                player = player_box(screen, w)
                if player:
                    stage('verify_player_title')
                    x, y, width, height = player
                    if not activated:
                        b.click(x + width//2, y + height//2)
                        activated = True
                        time.sleep(.5)
                        continue
                    footer = b.crop(screen, (x + 10, y + height - 110, width - 20, 100), output_dir / 'player-identity.png')
                    title_exact = verify_player_title(b, footer, profile['title'])
                    # OCR can misread classical text or a collapsed long title.
                    # Copying a candidate link is read-only; the resolver must
                    # independently match the full title AND author afterward.
                    if title_exact or b.ocr_scaled(footer, scale=2, psm=6).strip():
                        title_ok = True
                        # Silent Play starts playback. Pause it before reading
                        # menus so short clips cannot advance to another item.
                        b.click(x + width//2, y + height//2)
                        break
                time.sleep(.3)
            if not title_ok:
                raise RuntimeError('native_player_identity_unverified')
            marker = 'labcanvas-link-' + hashlib.sha256(str(time.time_ns()).encode()).hexdigest()
            b.set_clipboard(marker)
            if b.get_clipboard() != marker:
                raise RuntimeError('native_clipboard_unavailable')
            b.click(x + width - 151, y + height - 59)
            stage('copy_link')
            time.sleep(.3)
            menu = b.capture_screen('channels-copy-link-menu')
            action = match_menu(b, menu, (x, y + height - 320, width, 320),
                                ('复制链接', 'Copy Link', '複製連結'), output_dir, 'copy-link-menu')
            if action is None:
                raise RuntimeError('native_copy_link_action_unavailable')
            write_private_json(output_dir / 'copy-link-focus.json', {
                'point': action, 'helper': b.tiny11.health()})
            b.click(*action)
            try:
                url = wait_copied_link(b, marker)
            finally:
                b.capture_screen('channels-after-copy-link')
            # A clipboard update is not source identity; check the player
            # again, then let the existing resolver compare title and author.
            screen = b.capture_screen('channels-copied-link-identity')
            footer = b.crop(screen, (x + 10, y + height - 110, width - 20, 100), output_dir / 'copied-player-identity.png')
            if player_box(screen, w) != player:
                raise RuntimeError('native_player_changed_during_copy')
            result = {'status': 'share_link_recovered', 'transport': 'wechat_tiny11',
                      'read_only': True, 'public_actions': False, 'source_chat': chat,
                      'object_id': profile['object_id'], 'title': profile['title'], 'author': profile.get('author', ''),
                      'visual_identity_verified': title_exact, 'share_url': url,
                      'share_url_sha256': hashlib.sha256(url.encode()).hexdigest(),
                      'cover_sha256': hashlib.sha256(cover.read_bytes()).hexdigest(),
                      'cover_match_confidence': found['match_confidence'],
                      'observed_at': datetime.now(timezone.utc).isoformat()}
            write_private_json(candidate_path, {**result, 'status': 'identity_pending',
                                               'content_identity_verified': False})
        finally:
            try:
                if opened and not player:
                    w = b.find_window()
                    player = player_box(b.capture_screen('channels-final-state'), w)
                if opened and player:
                    # Close only the tab this invocation opened, not WeChat or
                    # its shared desktop. Escape can hide the logged-in app.
                    close_owned_player(b, w, player)
                elif menu_open:
                    b.dismiss_transient_overlays(b.find_window())
            except Exception as exc:
                cleanup_error = {'error_type': type(exc).__name__, 'error_code': str(exc)[:250]}
                write_private_json(output_dir / 'cleanup-error.json', cleanup_error)
                # Cleanup is separate from source recovery. Never mask the
                # original error or discard a copied link before identity checks.
    stage('verify_resolved_identity')
    resolved = verify_resolved_card(profile, url)
    result['content_identity_verified'] = True
    result['identity_method'] = 'exact_card_cover_and_resolved_title_author'
    if cleanup_error:
        result['cleanup_warning'] = cleanup_error
    write_private_json(output_dir / 'resolved-profile.json', resolved)
    write_private_json(output_dir / 'native-share-link.json', result)
    stage('share_link_recovered')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chat', required=True)
    parser.add_argument('--source-text-file', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = recover(args.chat, args.source_text_file.read_text(), args.output_dir)
    except Exception as exc:
        try:
            stage = json.loads((args.output_dir / 'stage.json').read_text()).get('stage')
        except (OSError, ValueError):
            stage = None
        resolver_failed = stage == 'verify_resolved_identity'
        result = {'status': 'failed', 'transport': 'wechat_tiny11',
                  'failure_stage': 'share_resolver' if resolver_failed else 'share_link',
                  'error_code': str(exc)[:250], 'error_type': type(exc).__name__}
        if resolver_failed:
            result['native_link_copied'] = True
            result['failure_origin'] = 'download_resolver_not_native_player'
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'share_link_recovered' else 2


if __name__ == '__main__':
    raise SystemExit(main())
