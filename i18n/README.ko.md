[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner — apps and four buddies](https://lazying.art/media/brand/lazyingart-intro.gif)](https://lazying.art)

<p align="center">
  <a href="https://lazying.art"><img alt="Homepage" src="https://img.shields.io/badge/home-lazying.art-111827?style=for-the-badge"></a>
  <a href="https://github.com/lachlanchen/AgInTi-LabCanvas/actions"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/lachlanchen/AgInTi-LabCanvas/test.yml?branch=master&style=for-the-badge&label=tests"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-ready-0F766E?style=for-the-badge">
</p>

<h1 align="center">AgInTi LabCanvas</h1>

<p align="center">
  Blender, BioRender, Unity, Unreal 및 창작·연구 도구로 에이전트를 라우팅하는 제어 계층입니다.
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="V-SPICE 작업과 Blender/OpenSCAD 아티팩트를 보여주는 AgInTi LabCanvas Studio" width="1100">
</p>

## 프로젝트 목적

AgInTi LabCanvas은 Codex, AgInTiFlow, Claude 및 MCP 호환 에이전트가 앱 자동화를 다룰 수 있는 실용적인 제어면을 제공합니다. 대상은 명시적인 레지스트리에 보관되고, 설정은 검증되며, 검토 가능한 JSON 봉투가 적절한 어댑터로 전달됩니다.

## 빠른 시작

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

설치 후:

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## 논문 그림 스튜디오

웹앱은 채팅, 아티팩트 캔버스, JSON 장면 편집기, 백엔드 설정을 제공합니다. 정확한 `NxM` SVG 그리드, AgInTi 이미지 요청 준비, 비밀을 저장하지 않는 BioRender 설정, OpenSCAD 내보내기, Blender 렌더링을 지원합니다.

[PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md), [STUDIO_CLI.md](../docs/STUDIO_CLI.md), [WEBAPP.md](../docs/WEBAPP.md)를 참고하세요.

## 3D 실험 설계

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

신뢰할 수 있는 원본은 JSON 장면 사양입니다. Blender는 헤드리스로 실행되어 `.png` 미리보기와 `.blend` 장면을 만듭니다. [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json)에서 시작하세요.

## 대상

| 대상 | 어댑터 | 주요 용도 |
| --- | --- | --- |
| Blender | `http_json` 또는 로컬 명령 | 장면, 재질, 렌더링, 내보내기. |
| AgInTi | 로컬 명령 | 그림용 이미지 콘셉트. |
| BioRender | 브라우저 및 MCP | 공식 흐름을 통한 학술 다이어그램. |
| Unity | `http_json` | 장면, 에셋, 스크립트, 테스트. |
| Unreal | `http_json` | 명시적 권한 기반 에디터 제어. |

## 개발

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

기여 규칙은 [AGENTS.md](../AGENTS.md), 보안 모델은 [SECURITY.md](../SECURITY.md)를 확인하세요.

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
