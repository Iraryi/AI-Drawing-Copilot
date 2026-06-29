<div align="center">
  <a href="./README.md">简体中文</a> · <strong>English</strong>
</div>

# AI Drawing Copilot

> **Stop asking image models to guess your composition. Compute the spatial relationships first, then hand the scene to AI.**

[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-2563eb)](https://github.com/Iraryi/AI-Drawing-Copilot/releases/latest)
[![Release](https://img.shields.io/badge/download-latest%20installer-22c55e)](https://github.com/Iraryi/AI-Drawing-Copilot/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.10%2B-f5c542)](https://www.python.org/)

AI Drawing Copilot is not another image generator. It is a **composition constraint layer between a region sketch and an image model**. Draw semantic regions such as sky, river, castle, or wheat field on a canvas; the application computes their left/right and above/below relationships, adjacency, containment, overlap, layer order, distance, frame occupancy, and elongated routes. It then translates those geometric facts into explicit, inspectable natural-language constraints that are harder for an image model to ignore.

The problem is rarely that AI cannot render the requested subjects. The problem is that it moves them, swaps their sides, changes a river's route, or breaks the intended region structure. Current image models cannot reliably reproduce a composition from coordinates alone, so this project analyzes every region pair in code and delivers a human-readable composition brief alongside visual indexes.

`Region sketch → programmatic spatial analysis → mandatory brief and visual indexes → image model`

| Region composition | Result guided by relationship constraints |
| --- | --- |
| ![Region composition](docs/images/02-composition-map.png) | ![Result guided by relationship constraints](docs/images/03-coordinate-prompt-limit.png) |

In the example above, region 3 is a river and region 10 is a rice field. The application describes their frame occupancy, relative direction, adjacency, and the river's overall route instead of merely exporting coordinates.

## Download

Windows users can download `AIDrawingCopilot-Setup-0.2.0.exe` from [Releases](https://github.com/Iraryi/AI-Drawing-Copilot/releases/latest).

The installer supports Chinese and English as well as standard and portable installation modes. The application asks for the interface language on first launch, remembers the selection, and lets you change it later in Settings.

## How it works

### 1. Draw and describe semantic regions

Create a canvas or import a background image. Use the brush, add, and erase tools to define regions, then provide a region name and natural-language description. A normalized prompt and notes are optional.

![Region editor](docs/images/01-region-editor.png)

### 2. Choose an export for the target AI

![Export modes](docs/images/08-export-modes.png)

- **For AI · Indirect (default):** exports a mandatory composition brief, a uniquely indexed PNG, and an SVG. A code-capable AI must first create `texture_underpaint.png`, stop, and wait for a separate **Continue** message before generating the final image.
- **For AI · Direct:** allows immediate image generation while keeping every composition relationship mandatory.
- **Weak AI fallback:** exports only PNG and TXT. The TXT can use a compact direct, indirect, or full direct workflow for models with limited file or context capabilities.
- **Automation workflow:** adds machine-readable structural files for further processing.
- **Complete handoff package:** exports all visual, textual, and structural materials.
- **Visual reference only:** exports only the numbered PNG and SVG.

Colors in the visual index identify regions; they do not prescribe final materials. Even if every region uses the same reference color in the editor, the export assigns unique index colors.

### 3. Hand the export to a file-capable AI

The indirect workflow requires an AI that can read files and run local code. When submitting the export, avoid extra instructions that might trigger immediate image generation; let the exported brief control Stage 1.

![Indirect two-stage workflow](docs/images/06-indirect-workflow.png)

The direct workflow does not require code execution and allows the AI to generate an image immediately, but its composition is currently less stable and still needs broader validation.

![Direct workflow](docs/images/07-direct-workflow.png)

## Why a position map or coordinates are not enough

A position map can tell a model what belongs in each area, but it does not guarantee that the model will preserve large-scale occupancy, connected boundaries, or pairwise relationships. A wheat field intended to remain left of a river may move to the right, while water may incorrectly cover a region anchored to the top edge.

| Common drift | More severe structural failure |
| --- | --- |
| ![Composition drift despite a position guide](docs/images/04-relation-guided-result.png) | ![Severe structural failure](docs/images/05-coordinate-prompt-failure.png) |

AI Drawing Copilot cannot remove the image model's own limitations, but it makes the constraints explicit: do not swap left and right or top and bottom; do not remove adjacency, containment, or overlap; do not reverse layer order; do not move the main body to the opposite side of the frame; and do not arbitrarily straighten, shift, or reroute elongated regions such as rivers, roads, walls, and ridgelines.

## Current scope and limitations

- The workflow has currently been tested only with **ChatGPT 5.5**. File reading, code execution, and image-generation behavior may differ in other AI systems.
- The default indirect export is not suitable for a standalone image model because it includes code-based underpainting and a mandatory **Continue** gate.
- For standalone image models, experiment with the Weak AI fallback or manually provide its TXT and PNG together. Results are not guaranteed.
- The output is a clearer set of composition constraints, not a promise of pixel-perfect reproduction. Final results still depend on model capability and generation randomness.

## Default export

The default **For AI** preset produces only three files so technical material does not overwhelm the actual instructions:

- `*.mandatory-composition-brief.md`: the highest-priority natural-language composition brief.
- `*.guide.png`: a numbered raster index with a unique color for every region.
- `*.regions.svg`: a vector index for cross-checking boundaries and identities.

If a visual index and the written brief appear ambiguous, the mandatory composition brief takes precedence. The application analyzes all N×(N−1)/2 region pairs instead of selecting only a few relationships.

## Run from source

Python 3.10+ is required:

```powershell
py -3 -m pip install -r requirements.txt
py -3 main.py
py -3 tests\smoke_test.py
```

Build the standalone Windows application:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
```

Build the installer:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```
