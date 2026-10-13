[English](../README.md) · [العربية](README.ar.md) · [Español](README.es.md) · [Français](README.fr.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Tiếng Việt](README.vi.md) · [中文 (简体)](README.zh-Hans.md) · [中文（繁體）](README.zh-Hant.md) · [Deutsch](README.de.md) · [Русский](README.ru.md)

[![LazyingArt banner](https://github.com/lachlanchen/lachlanchen/raw/main/figs/banner.png)](https://lazying.art)

<p align="center">
  <a href="https://lazying.art"><img alt="Homepage" src="https://img.shields.io/badge/home-lazying.art-111827?style=for-the-badge"></a>
  <a href="https://github.com/lachlanchen/AgInTi-LabCanvas/actions"><img alt="Tests" src="https://img.shields.io/github/actions/workflow/status/lachlanchen/AgInTi-LabCanvas/test.yml?branch=master&style=for-the-badge&label=tests"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge">
  <img alt="MCP" src="https://img.shields.io/badge/MCP-ready-0F766E?style=for-the-badge">
</p>

<h1 align="center">AgInTi LabCanvas</h1>

<p align="center">
  Blender、BioRender、Unity、Unreal、研究・制作ツールへエージェントをルーティングする制御面です。
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="V-SPICE タスクと Blender/OpenSCAD アーティファクトを表示する AgInTi LabCanvas Studio" width="1100">
</p>

## このプロジェクトの目的

AgInTi LabCanvas は Codex、AgInTiFlow、Claude、MCP 対応エージェントに、アプリ自動化のための実用的な制御面を提供します。ターゲットを明示的なレジストリで管理し、設定を検証し、確認しやすい JSON エンベロープを適切なアダプターへ送ります。

## クイックスタート

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

インストール後:

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## Paper Figure Studio

Web アプリにはチャット、アーティファクトキャンバス、JSON シーンエディタ、バックエンド設定があります。正確な `NxM` SVG グリッド、AgInTi 画像リクエスト、秘密情報を保存しない BioRender 設定、OpenSCAD エクスポート、Blender レンダリングを扱えます。

[PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md)、[STUDIO_CLI.md](../docs/STUDIO_CLI.md)、[WEBAPP.md](../docs/WEBAPP.md) を参照してください。

## 3D 実験デザイン

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

信頼できるソースは JSON のシーン仕様です。Blender はヘッドレスで実行され、`.png` プレビューと `.blend` シーンを出力します。[paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json) から始められます。

## ターゲット

| ターゲット | アダプター | 主な用途 |
| --- | --- | --- |
| Blender | `http_json` またはローカルコマンド | シーン、素材、レンダー、エクスポート。 |
| AgInTi | ローカルコマンド | 図版用の画像コンセプト。 |
| BioRender | ブラウザと MCP | 公式フローでの学術図作成。 |
| Unity | `http_json` | シーン、アセット、スクリプト、テスト。 |
| Unreal | `http_json` | 明示的な権限でのエディタ制御。 |

## 開発

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

貢献ルールは [AGENTS.md](../AGENTS.md)、セキュリティモデルは [SECURITY.md](../SECURITY.md) を読んでください。

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
