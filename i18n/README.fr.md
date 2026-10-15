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
  Routage d'agents pour Blender, BioRender, Unity, Unreal et les outils de création ou de recherche.
</p>

<p align="center">
  <img src="../docs/assets/aginti-labcanvas-vspice-studio.png" alt="Studio AgInTi LabCanvas avec une tâche V-SPICE et des artefacts Blender/OpenSCAD" width="1100">
</p>

## Pourquoi Ce Projet Existe

AgInTi LabCanvas donne à Codex, AgInTiFlow, Claude et aux autres agents compatibles MCP un plan de contrôle simple pour piloter des applications. Le projet garde les cibles dans un registre explicite, valide la configuration et envoie des enveloppes JSON vérifiables à l'adaptateur approprié.

## Démarrage Rapide

```bash
PYTHONPATH=src python -m agenticapp list
PYTHONPATH=src python -m agenticapp doctor
PYTHONPATH=src python -m agenticapp dispatch blender "Create a red cube at the origin" --dry-run
PYTHONPATH=src python -m agenticapp studio status
PYTHONPATH=src python -m unittest discover -s tests
```

Après installation :

```bash
labcanvas studio figure-grid "optical device icons 2x3" --rows 2 --cols 3
labcanvas webapp start --port 19473
```

## Studio de Figures

Le webapp fournit un chat, un canevas d'artefacts, un éditeur JSON de scène et des réglages de backend. Il peut créer des grilles SVG `NxM`, préparer des requêtes d'image AgInTi, conserver les réglages BioRender sans secrets, exporter OpenSCAD et rendre les scènes avec Blender.

Voir [PAPER_FIGURE_STUDIO.md](../docs/PAPER_FIGURE_STUDIO.md), [STUDIO_CLI.md](../docs/STUDIO_CLI.md) et [WEBAPP.md](../docs/WEBAPP.md).

## Conception 3D d'Expériences

```bash
labcanvas scene-template experiment-setup --output my-setup.scene.json
labcanvas render-scene my-setup.scene.json --dry-run
labcanvas render-scene my-setup.scene.json --output-dir output/scenes
```

La source de vérité est une spécification JSON. Blender s'exécute en mode headless et produit une image `.png` ainsi qu'une scène `.blend`. Commence par [paper-optics-setup.scene.json](../examples/paper-optics-setup.scene.json).

## Cibles

| Cible | Adaptateur | Usage principal |
| --- | --- | --- |
| Blender | `http_json` ou commande locale | Scènes, matériaux, rendu et export. |
| AgInTi | commande locale | Concepts d'images pour figures. |
| BioRender | navigateur et MCP | Diagrammes académiques via le flux officiel. |
| Unity | `http_json` | Scènes, assets, scripts et tests. |
| Unreal | `http_json` | Contrôle éditeur avec permissions explicites. |

## Développement

```bash
PYTHONPATH=src python -m unittest discover -s tests
PYTHONPATH=src python -m agenticapp doctor
```

Lis [AGENTS.md](../AGENTS.md) pour les consignes de contribution et [SECURITY.md](../SECURITY.md) pour le modèle de sécurité.

| Donate | PayPal | Stripe |
| --- | --- | --- |
| [![Donate](https://img.shields.io/badge/Donate-LazyingArt-0EA5E9?style=for-the-badge&logo=kofi&logoColor=white)](https://chat.lazying.art/donate) | [![PayPal](https://img.shields.io/badge/PayPal-RongzhouChen-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/RongzhouChen) | [![Stripe](https://img.shields.io/badge/Stripe-Donate-635BFF?style=for-the-badge&logo=stripe&logoColor=white)](https://buy.stripe.com/aFadR8gIaflgfQV6T4fw400) |
