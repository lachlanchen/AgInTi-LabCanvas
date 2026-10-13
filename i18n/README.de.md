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
  Agenten-Routing für Blender, BioRender, Unity, Unreal und kreative oder wissenschaftliche Werkzeuge.
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="AgInTi LabCanvas Studio mit V-SPICE-Aufgabe und Blender/OpenSCAD-Artefakten" width="1100">
</p>

## Warum Es Dieses Projekt Gibt

AgInTi LabCanvas gibt Codex, AgInTiFlow, Claude und anderen MCP-fähigen Agenten eine praktische Steuerzentrale für App-Automatisierung. Ziele werden in einem expliziten Register verwaltet, Konfigurationen validiert und überprüfbare JSON-Umschläge an den passenden Adapter gesendet.

## Schnellstart

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

Nach der Installation:

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## Paper Figure Studio

Die Webapp bietet Chat, Artefakt-Canvas, JSON-Szeneneditor und Backend-Einstellungen. Sie erzeugt exakte `NxM`-SVG-Raster, vorbereitet AgInTi-Bildanfragen, speichert BioRender-Einstellungen ohne Geheimnisse, exportiert OpenSCAD und rendert Szenen mit Blender.

Siehe [PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md), [STUDIO_CLI.md](../docs/STUDIO_CLI.md) und [WEBAPP.md](../docs/WEBAPP.md).

## 3D-Experimentdesign

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

Die Quelle der Wahrheit ist eine JSON-Szenenspezifikation. Blender läuft headless und erzeugt eine `.png`-Vorschau sowie eine `.blend`-Szene. Starte mit [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json).

## Ziele

| Ziel | Adapter | Hauptnutzung |
| --- | --- | --- |
| Blender | `http_json` oder lokaler Befehl | Szenen, Materialien, Rendering und Export. |
| AgInTi | lokaler Befehl | Bildkonzepte für Figuren. |
| BioRender | Browser und MCP | Wissenschaftliche Diagramme über den offiziellen Ablauf. |
| Unity | `http_json` | Szenen, Assets, Skripte und Tests. |
| Unreal | `http_json` | Editor-Steuerung mit expliziten Rechten. |

## Entwicklung

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

Lies [AGENTS.md](../AGENTS.md) für Beitragsregeln und [SECURITY.md](../SECURITY.md) für das Sicherheitsmodell.

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
