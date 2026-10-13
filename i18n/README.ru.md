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
  Маршрутизация агентов для Blender, BioRender, Unity, Unreal и творческих или научных инструментов.
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="Студия AgInTi LabCanvas с задачей V-SPICE и артефактами Blender/OpenSCAD" width="1100">
</p>

## Зачем Нужен Проект

AgInTi LabCanvas дает Codex, AgInTiFlow, Claude и другим MCP-совместимым агентам практическую панель управления автоматизацией приложений. Цели хранятся в явном реестре, конфигурация проверяется, а команды отправляются в адаптеры как проверяемые JSON-конверты.

## Быстрый Старт

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

После установки:

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## Студия Фигур

Веб-приложение содержит чат, холст артефактов, JSON-редактор сцены и настройки бэкендов. Оно создает точные SVG-сетки `NxM`, готовит запросы изображений для AgInTi, хранит настройки BioRender без секретов, экспортирует OpenSCAD и рендерит сцены через Blender.

См. [PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md), [STUDIO_CLI.md](../docs/STUDIO_CLI.md) и [WEBAPP.md](../docs/WEBAPP.md).

## 3D-Дизайн Экспериментов

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

Источник истины - JSON-спецификация сцены. Blender запускается без интерфейса и создает `.png`-превью и `.blend`-сцену. Начните с [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json).

## Цели

| Цель | Адаптер | Основное назначение |
| --- | --- | --- |
| Blender | `http_json` или локальная команда | Сцены, материалы, рендеринг и экспорт. |
| AgInTi | локальная команда | Концепты изображений для фигур. |
| BioRender | браузер и MCP | Академические диаграммы через официальный поток. |
| Unity | `http_json` | Сцены, ассеты, скрипты и тесты. |
| Unreal | `http_json` | Управление редактором с явными правами. |

## Разработка

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

См. [AGENTS.md](../AGENTS.md) для правил участия и [SECURITY.md](../SECURITY.md) для модели безопасности.

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
