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
  面向 Blender、BioRender、Unity、Unreal 以及科研/创作工具的智能体路由控制面。
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="AgInTi LabCanvas Studio 展示 V-SPICE 任务以及 Blender/OpenSCAD 产物" width="1100">
</p>

## 项目用途

AgInTi LabCanvas 为 Codex、AgInTiFlow、Claude 和其他 MCP 感知智能体提供一个实用的应用自动化控制面。它把目标工具放入清晰的注册表，验证配置，并把可审查的 JSON 信封发送给正确的适配器。

## 快速开始

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

安装后也可以使用：

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## 论文图形工作室

Web 应用包含聊天、产物画布、场景 JSON 编辑器和后端设置。它可以生成精确的 `NxM` SVG 网格，准备 AgInTi 图像请求，保存不含密钥的 BioRender 设置，导出 OpenSCAD，并通过 Blender 渲染场景。

参见 [PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md)、[STUDIO_CLI.md](../docs/STUDIO_CLI.md) 和 [WEBAPP.md](../docs/WEBAPP.md)。

## 3D 实验设计

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

唯一可信来源是 JSON 场景规格。Blender 以 headless 模式运行，生成 `.png` 预览和 `.blend` 场景。可以从 [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json) 开始。

## 目标工具

| 目标 | 适配器 | 主要用途 |
| --- | --- | --- |
| Blender | `http_json` 或本地命令 | 场景、材质、渲染和导出。 |
| AgInTi | 本地命令 | 论文图形的图像概念。 |
| BioRender | 浏览器和 MCP | 通过官方流程绘制学术图。 |
| Unity | `http_json` | 场景、资源、脚本和测试。 |
| Unreal | `http_json` | 使用明确权限控制编辑器。 |

## 开发

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

贡献规范见 [AGENTS.md](../AGENTS.md)，编辑器自动化安全模型见 [SECURITY.md](../SECURITY.md)。

<!-- support:start -->
[![GitHub Sponsors](https://img.shields.io/badge/GitHub-Sponsors-EA4AAA?style=for-the-badge&logo=githubsponsors&logoColor=white)](https://github.com/sponsors/lachlanchen)
[![LazyingArt Support](https://img.shields.io/badge/LazyingArt-Support-0EA5E9?style=for-the-badge)](https://chat.lazying.art/donate)
[![PayPal Support](https://img.shields.io/badge/PayPal-Support-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen)
[![Stripe Support](https://img.shields.io/badge/Stripe-Support-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400)
<!-- support:end -->
