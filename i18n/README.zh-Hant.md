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
  面向 Blender、BioRender、Unity、Unreal 以及科研/創作工具的智慧體路由控制面。
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="AgInTi LabCanvas Studio 展示 V-SPICE 任務以及 Blender/OpenSCAD 產物" width="1100">
</p>

## 專案用途

AgInTi LabCanvas 為 Codex、AgInTiFlow、Claude 和其他 MCP 感知智慧體提供一個實用的應用自動化控制面。它把目標工具放入清晰的註冊表，驗證設定，並把可審查的 JSON 信封送到正確的適配器。

## 快速開始

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

安裝後也可以使用：

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## 論文圖形工作室

Web 應用包含聊天、產物畫布、場景 JSON 編輯器和後端設定。它可以生成精確的 `NxM` SVG 網格，準備 AgInTi 圖像請求，保存不含密鑰的 BioRender 設定，匯出 OpenSCAD，並透過 Blender 渲染場景。

參見 [PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md)、[STUDIO_CLI.md](../docs/STUDIO_CLI.md) 和 [WEBAPP.md](../docs/WEBAPP.md)。

## 3D 實驗設計

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

唯一可信來源是 JSON 場景規格。Blender 以 headless 模式執行，生成 `.png` 預覽和 `.blend` 場景。可以從 [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json) 開始。

## 目標工具

| 目標 | 適配器 | 主要用途 |
| --- | --- | --- |
| Blender | `http_json` 或本地命令 | 場景、材質、渲染和匯出。 |
| AgInTi | 本地命令 | 論文圖形的圖像概念。 |
| BioRender | 瀏覽器和 MCP | 透過官方流程繪製學術圖。 |
| Unity | `http_json` | 場景、資源、腳本和測試。 |
| Unreal | `http_json` | 使用明確權限控制編輯器。 |

## 開發

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

貢獻規範見 [AGENTS.md](../AGENTS.md)，編輯器自動化安全模型見 [SECURITY.md](../SECURITY.md)。

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
