# Tiny Model Artifacts

Model binaries are local runtime artifacts and are not committed to Git. Download all
three files before enabling `tiny_model`; the service validates exact size and SHA-256
before loading any model.

The originally proposed `ultralytics/yolo-world-nano` artifact could not be verified in
the public Ultralytics or Hugging Face releases. The POC therefore uses the smallest
published Ultralytics YOLO-World v2 checkpoint, `yolov8s-worldv2.pt`.

## Locked Files

| Destination | Bytes | SHA-256 | Source |
| :-- | --: | :-- | :-- |
| `data/model/yolov8s-worldv2.pt` | `25,923,032` | `9b2c17ab6124a913e9b3a5c170617920d91b0f01111a8479da69f00e2cf27792` | [Ultralytics assets v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8s-worldv2.pt) |
| `data/model/mobile_sam.pt` | `40,728,226` | `6dbb90523a35330fedd7f1d3dfc66f995213d81b29a5ca8108dbcdd4e37d6c2f` | [Ultralytics assets v8.4.0](https://github.com/ultralytics/assets/releases/download/v8.4.0/mobile_sam.pt) |
| `data/model/clip/ViT-B-32.pt` | `353,976,522` | `40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af` | [OpenAI CLIP](https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt) |

Dynamic text prompts require the CLIP text encoder. The complete weight footprint is
`420,627,780` bytes (about `401 MiB`), not the original unverified 35 MB estimate.

## Download

The cross-platform prefetch command downloads to temporary files and validates the
locked size and SHA-256 before use:

```powershell
cd backend
.venv\Scripts\python -m python_backend.algorithms.tiny_model.prefetch
```

The equivalent manual PowerShell commands are:

Run from the repository root in PowerShell:

```powershell
New-Item -ItemType Directory -Force data/model/clip | Out-Null
Start-BitsTransfer `
  https://github.com/ultralytics/assets/releases/download/v8.4.0/yolov8s-worldv2.pt `
  data/model/yolov8s-worldv2.pt
Start-BitsTransfer `
  https://github.com/ultralytics/assets/releases/download/v8.4.0/mobile_sam.pt `
  data/model/mobile_sam.pt
Start-BitsTransfer `
  https://openaipublic.azureedge.net/clip/models/40d365715913c9da98579312b702a82c18be219cc2a73407c4526f58eba950af/ViT-B-32.pt `
  data/model/clip/ViT-B-32.pt
Get-FileHash data/model/yolov8s-worldv2.pt -Algorithm SHA256
Get-FileHash data/model/mobile_sam.pt -Algorithm SHA256
Get-FileHash data/model/clip/ViT-B-32.pt -Algorithm SHA256
```

Install the optional runtime from `backend/` after installing the PyTorch build for the
target CPU or CUDA platform:

```powershell
.venv\Scripts\python -m pip install -e ".[tiny-model,dev]"
```

The request path never downloads weights. A missing or mismatched file makes the
algorithm unavailable through the capability endpoint.

## Licenses

- Ultralytics `8.4.120` runtime and distributed YOLO-World checkpoint: AGPL-3.0.
- Original YOLO-World project: GPL-3.0.
- MobileSAM project: Apache-2.0.
- OpenAI CLIP code and checkpoint source: MIT.

The deployment owner must confirm that these licenses fit the distribution model before
shipping the POC beyond an evaluation environment.
