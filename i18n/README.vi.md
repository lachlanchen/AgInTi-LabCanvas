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
  Định tuyến agent tới Blender, BioRender, Unity, Unreal và các công cụ sáng tạo hoặc nghiên cứu.
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="AgInTi LabCanvas Studio với tác vụ V-SPICE và artifact Blender/OpenSCAD" width="1100">
</p>

## Vì Sao Có Dự Án Này

AgInTi LabCanvas cung cấp cho Codex, AgInTiFlow, Claude và các agent hỗ trợ MCP một mặt phẳng điều khiển thực dụng cho tự động hóa ứng dụng. Mỗi mục tiêu nằm trong registry rõ ràng, cấu hình được kiểm tra, và lệnh được gửi dưới dạng JSON có thể xem lại.

## Bắt Đầu Nhanh

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

Sau khi cài đặt:

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## Paper Figure Studio

Webapp có chat, canvas artifact, trình sửa JSON scene và thiết lập backend. Nó có thể tạo lưới SVG `NxM`, chuẩn bị yêu cầu ảnh AgInTi, lưu thiết lập BioRender không chứa secret, xuất OpenSCAD và render scene bằng Blender.

Xem [PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md), [STUDIO_CLI.md](../docs/STUDIO_CLI.md) và [WEBAPP.md](../docs/WEBAPP.md).

## Thiết Kế Thí Nghiệm 3D

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

Nguồn sự thật là đặc tả scene bằng JSON. Blender chạy headless và tạo bản xem trước `.png` cùng scene `.blend`. Bắt đầu từ [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json).

## Mục Tiêu

| Mục tiêu | Adapter | Cách dùng chính |
| --- | --- | --- |
| Blender | `http_json` hoặc lệnh local | Scene, vật liệu, render và export. |
| AgInTi | lệnh local | Ý tưởng ảnh cho hình minh họa. |
| BioRender | trình duyệt và MCP | Sơ đồ học thuật theo luồng chính thức. |
| Unity | `http_json` | Scene, asset, script và test. |
| Unreal | `http_json` | Điều khiển editor với quyền rõ ràng. |

## Phát Triển

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

Đọc [AGENTS.md](../AGENTS.md) cho quy tắc đóng góp và [SECURITY.md](../SECURITY.md) cho mô hình bảo mật.

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
