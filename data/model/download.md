# Tiny Model Artifacts

Model binaries are local runtime artifacts and are not committed to Git. Download all three
files before enabling `tiny_model`; service startup validates
their exact byte size and SHA-256. Request handling never downloads weights.

## Locked Files

| Destination | Bytes | SHA-256 | Source |
| :-- | --: | :-- | :-- |
| `data/model/yoloe-26m-seg-pf.pt` | `72,857,475` | `4a03f83695314f2dfb5fd6ebc3866100af525645b6490907bde31e4c0e4ffbd5` | [Ultralytics assets v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-26m-seg-pf.pt) |
| `data/model/sam2.1_s.pt` | `92,319,866` | `60f9e43f1307be192eef341437e02c40f32cd61cf36a97a203a0998a2952873a` | [Ultralytics assets v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/sam2.1_s.pt) |
| `data/model/animegan2-celeba-distill.pt` | `8,603,556` | `a3740d98f99efe2ee6c332de2b800f542ddbb2d15e835c07e9bf667c29cef8a7` | [AnimeGANv2 PyTorch, commit `25d7b01`](https://raw.githubusercontent.com/bryandlee/animegan2-pytorch/25d7b017267208dfaf34026aa3425e518372aa2f/weights/celeba_distill.pt) |

The validated artifact footprint is `173,780,897` bytes, about `165.7 MiB`. YOLOE uses
its built-in Prompt-free vocabulary and original English names for type and bounding-box
analysis. SAM2.1-S refines only the boxes selected by the user. The `celeba_distill`
generator provides the evaluation-only flat portrait style.

## Download

The cross-platform prefetch command downloads to temporary files, verifies each file,
and atomically moves it into `data/model/`:

```powershell
cd backend
.venv\Scripts\python -m python_backend.algorithms.tiny_model.prefetch
```

Equivalent manual PowerShell commands, run from the repository root:

```powershell
New-Item -ItemType Directory -Force data/model | Out-Null
Start-BitsTransfer `
  https://github.com/ultralytics/assets/releases/download/v8.4.0/yoloe-26m-seg-pf.pt `
  data/model/yoloe-26m-seg-pf.pt
Start-BitsTransfer `
  https://github.com/ultralytics/assets/releases/download/v8.4.0/sam2.1_s.pt `
  data/model/sam2.1_s.pt
Start-BitsTransfer `
  https://raw.githubusercontent.com/bryandlee/animegan2-pytorch/25d7b017267208dfaf34026aa3425e518372aa2f/weights/celeba_distill.pt `
  data/model/animegan2-celeba-distill.pt
Get-FileHash data/model/yoloe-26m-seg-pf.pt -Algorithm SHA256
Get-FileHash data/model/sam2.1_s.pt -Algorithm SHA256
Get-FileHash data/model/animegan2-celeba-distill.pt -Algorithm SHA256
```

Install the optional runtime from `backend/` after installing the PyTorch build for the
target CPU or CUDA platform:

```powershell
.venv\Scripts\python -m pip install -e ".[tiny-model,dev]"
```

A missing or mismatched file makes Tiny Model unavailable through
`GET /api/v1/algorithms`; it does not silently download or substitute another model.

## Licenses

- Ultralytics `8.4.120` and the distributed YOLOE checkpoint: AGPL-3.0.
- SAM2.1 project and checkpoint: Apache-2.0.
- AnimeGANv2 PyTorch generator implementation: MIT, copyright 2021 Bryan Lee.

The deployment owner must confirm that these licenses fit the distribution model before
shipping beyond an evaluation environment. The converted `celeba_distill` weight is used
only for POC evaluation; its upstream training data and production distribution rights
remain to be confirmed before it can become the final Cartoonizer artifact.
