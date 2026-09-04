from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch
from torch import nn
from torch.nn import functional as functional

# Generator architecture adapted from bryandlee/animegan2-pytorch.
# Copyright (c) 2021 Bryan Lee, distributed under the MIT License.


class ConvNormLReLU(nn.Sequential):
    def __init__(
        self,
        input_channels: int,
        output_channels: int,
        kernel_size: int = 3,
        stride: int = 1,
        padding: int | tuple[int, int, int, int] = 1,
        groups: int = 1,
        bias: bool = False,
    ) -> None:
        super().__init__(
            nn.ReflectionPad2d(padding),
            nn.Conv2d(
                input_channels,
                output_channels,
                kernel_size=kernel_size,
                stride=stride,
                groups=groups,
                bias=bias,
            ),
            nn.GroupNorm(1, output_channels, affine=True),
            nn.LeakyReLU(0.2, inplace=True),
        )


class InvertedResBlock(nn.Module):
    def __init__(self, input_channels: int, output_channels: int) -> None:
        super().__init__()
        bottleneck = input_channels * 2
        self.use_residual = input_channels == output_channels
        self.layers = nn.Sequential(
            ConvNormLReLU(input_channels, bottleneck, kernel_size=1, padding=0),
            ConvNormLReLU(
                bottleneck,
                bottleneck,
                groups=bottleneck,
                bias=True,
            ),
            nn.Conv2d(bottleneck, output_channels, kernel_size=1, bias=False),
            nn.GroupNorm(1, output_channels, affine=True),
        )

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        output = self.layers(inputs)
        return inputs + output if self.use_residual else output


class AnimeGanGenerator(nn.Module):
    """AnimeGANv2 PyTorch generator architecture, adapted under the MIT license."""

    def __init__(self) -> None:
        super().__init__()
        self.block_a = nn.Sequential(
            ConvNormLReLU(3, 32, kernel_size=7, padding=3),
            ConvNormLReLU(32, 64, stride=2, padding=(0, 1, 0, 1)),
            ConvNormLReLU(64, 64),
        )
        self.block_b = nn.Sequential(
            ConvNormLReLU(64, 128, stride=2, padding=(0, 1, 0, 1)),
            ConvNormLReLU(128, 128),
        )
        self.block_c = nn.Sequential(
            ConvNormLReLU(128, 128),
            InvertedResBlock(128, 256),
            InvertedResBlock(256, 256),
            InvertedResBlock(256, 256),
            InvertedResBlock(256, 256),
            ConvNormLReLU(256, 128),
        )
        self.block_d = nn.Sequential(ConvNormLReLU(128, 128), ConvNormLReLU(128, 128))
        self.block_e = nn.Sequential(
            ConvNormLReLU(128, 64),
            ConvNormLReLU(64, 64),
            ConvNormLReLU(64, 32, kernel_size=7, padding=3),
        )
        self.out_layer = nn.Sequential(nn.Conv2d(32, 3, kernel_size=1, bias=False), nn.Tanh())

    def forward(self, inputs: torch.Tensor) -> torch.Tensor:
        output = self.block_a(inputs)
        half_size = output.shape[-2:]
        output = self.block_b(output)
        output = self.block_c(output)
        output = functional.interpolate(
            output,
            half_size,
            mode="bilinear",
            align_corners=True,
        )
        output = self.block_d(output)
        output = functional.interpolate(
            output,
            inputs.shape[-2:],
            mode="bilinear",
            align_corners=True,
        )
        return self.out_layer(self.block_e(output))


class AnimeGanCartoonizer:
    def __init__(self, model_path: Path, device: str, maximum_edge: int = 768) -> None:
        self.device = torch.device(device)
        self.maximum_edge = maximum_edge
        self.model = AnimeGanGenerator().to(self.device)
        state = torch.load(model_path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)
        self.model.eval()
        if device == "cuda":
            self.model.half()

    def stylize(self, image: np.ndarray, mask: np.ndarray) -> np.ndarray:
        if not np.any(mask > 0):
            return image.copy()
        height, width = image.shape[:2]
        scale = min(1.0, self.maximum_edge / max(height, width))
        target_width = max(4, round(width * scale / 4) * 4)
        target_height = max(4, round(height * scale / 4) * 4)
        resized = cv2.resize(
            image,
            (target_width, target_height),
            interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR,
        )
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = (
            torch.from_numpy(np.ascontiguousarray(rgb))
            .permute(2, 0, 1)
            .unsqueeze(0)
            .to(self.device)
        )
        tensor = tensor.half() if self.device.type == "cuda" else tensor.float()
        tensor = tensor / 127.5 - 1.0
        with torch.inference_mode():
            prediction = self.model(tensor)[0].float().permute(1, 2, 0).cpu().numpy()
        prediction = np.clip((prediction + 1.0) * 127.5, 0, 255).astype(np.uint8)
        stylized = cv2.cvtColor(prediction, cv2.COLOR_RGB2BGR)
        if stylized.shape[:2] != (height, width):
            stylized = cv2.resize(
                stylized,
                (width, height),
                interpolation=cv2.INTER_LANCZOS4,
            )
        output = image.copy()
        foreground = mask > 0
        output[foreground] = stylized[foreground]
        return output
