# 图片生成拼豆图工具技术方案

## 1. 技术目标

本方案目标是说明当前图片转拼豆图工具的技术实现方式，并为后续功能扩展提供结构参考。

当前工程包含静态前端和独立 Python 后端两个子项目：

- 前端在用户点击 Generate 后请求后端生成目标尺寸、已移除背景的 RGBA 格子图，失败时自动使用 Canvas 本地回退。
- 后端采用 FastAPI + BentoML，并注册 CPU-only `cv_native@1.0.0`；框架继续为后续多算法、高并发和 GPU 服务预留边界。
- 色板匹配、抖动、统计、渲染和导出仍由前端完成。
- 后端未配置或不可用时，静态前端仍可独立使用。

## 2. 技术选型

| 模块 | 技术 |
| --- | --- |
| 页面框架 | Astro |
| 交互组件 | React |
| 样式 | Tailwind CSS |
| UI 组件 | shadcn/ui 风格组件 |
| 图片处理 | Canvas / ImageData |
| 后端接入 | FastAPI |
| 模型服务边界 | BentoML |
| 颜色匹配 | CIE Lab + CIEDE2000 |
| 导出 | Canvas toBlob PNG |
| 部署形态 | 静态站点 |

## 3. 工程结构

```text
perler-striner/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── PerlerStudio.tsx
│   │   │   └── HomePage.astro
│   │   ├── i18n/
│   │   │   └── ui.ts
│   │   ├── lib/
│   │   │   ├── color.ts
│   │   │   ├── grid.ts
│   │   │   ├── palette.ts
│   │   │   ├── pattern.ts
│   │   │   ├── processor-client.ts
│   │   │   ├── render.ts
│   │   │   └── utils.ts
│   │   └── pages/
│   │       ├── index.astro
│   │       └── zh/index.astro
│   ├── package.json
│   └── astro.config.mjs
├── backend/
│   └── src/python_backend/
│       ├── web/
│       ├── schemas/
│       ├── core/
│       ├── services/
│       ├── algorithms/
│       └── serving/
├── docs/
│   ├── PRD.md
│   └── TECH_DESIGN.md
└── README.md
```

核心文件说明：

| 文件 | 职责 |
| --- | --- |
| `frontend/src/components/PerlerStudio.tsx` | 页面状态、图片上传、两阶段生成、下载交互 |
| `frontend/src/lib/grid.ts` | 浏览器本地缩放与强制背景移除 |
| `frontend/src/lib/processor-client.ts` | 后端请求、响应校验、超时取消与本地回退 |
| `frontend/src/lib/pattern.ts` | 将 RGBA 格子图转换成拼豆图数据 |
| `frontend/src/lib/color.ts` | RGB/Lab 转换、CIEDE2000、最近色匹配 |
| `frontend/src/lib/palette.ts` | 拼豆品牌与色卡数据 |
| `frontend/src/lib/render.ts` | 拼豆图渲染、网格线、拼板线、导出 PNG |
| `frontend/src/i18n/ui.ts` | 中英文文案 |

## 4. 核心数据流

```text
用户上传图片
→ createImageBitmap 解码图片
→ 保存 Source 到 React state
→ 上传、模式、宽度或 CV 超参数变化后标记为待生成
→ 用户点击 Generate
→ 根据宽度豆数计算目标网格尺寸
→ 后端生成 RGBA 格子图，失败则 Canvas 下采样并移除背景
→ generatePattern 执行色板匹配、抖动和统计
→ renderPattern 渲染到预览 Canvas
→ renderExport 生成带图例的导出 Canvas
→ canvas.toBlob 下载 PNG
```

## 5. 核心数据结构

### 5.1 Source

`Source` 表示用户上传或示例图片。

```ts
interface Source {
  image: CanvasImageSource;
  width: number;
  height: number;
  name: string;
  thumb: string;
  file: File | null;
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `image` | 可绘制到 Canvas 的图片源 |
| `width` | 原图宽度 |
| `height` | 原图高度 |
| `name` | 图片名称，用于导出文件名 |
| `thumb` | 缩略图 URL |
| `file` | 用户上传的原始文件；内置示例为 `null`，不会请求后端 |

### 5.2 RgbaGrid

图片算法与拼豆业务之间的固定数据切面：

```ts
interface RgbaGrid {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}
```

网格按行存储，每格 4 字节 RGBA；`data.length` 必须严格等于
`width * height * 4`，背景格通过 alpha 标记为空。此结构不包含品牌、
色板索引、颜色用量或拼豆总数。

### 5.3 Pattern

`Pattern` 是生成后的拼豆图数据。

```ts
interface Pattern {
  brand: BrandId;
  width: number;
  height: number;
  cells: Int16Array;
  used: { index: number; count: number }[];
  totalBeads: number;
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `brand` | 使用的拼豆品牌 |
| `width` | 图纸宽度，单位为颗豆 |
| `height` | 图纸高度，单位为颗豆 |
| `cells` | 每个格子的色卡索引，`-1` 表示空格 |
| `used` | 已使用颜色及数量，按数量倒序 |
| `totalBeads` | 总豆数 |

### 5.4 Palette / Brand

色卡结构由 `palette.ts` 管理。每个品牌包含颜色列表和豆子尺寸。

典型颜色字段包括：

```ts
{
  code: string;
  name: string;
  hex: string;
}
```

## 6. 图片处理流程

### 6.1 图片解码

上传图片后使用浏览器原生能力解码：

```ts
const bmp = await createImageBitmap(file, {
  imageOrientation: "from-image",
});
```

优点：

- 原生支持图片方向修正。
- 可直接作为 Canvas 绘制源。
- 不需要额外图片处理依赖。

### 6.2 目标尺寸计算

当前通过“宽度豆数”控制输出尺寸：

```ts
const w = Math.min(beadsAcross, MAX_BEADS);
const h = Math.max(
  1,
  Math.min(MAX_BEADS, Math.round((w * source.height) / source.width))
);
```

当前限制：

- 最大边不超过 `MAX_BEADS = 150`。
- 高度按原图比例自动计算。
- 暂不支持手动固定宽高。

### 6.3 后端优先与本地回退

用户上传的原始 `File`、目标宽高、算法标识、可选版本和 JSON 参数通过
multipart 发送到 `/api/v1/process`。请求不包含 `remove_background`；所有
后端算法必须输出已移除背景的格子图。

选择 `cv_native` 时，Hyperparameters 面板把支持的参数统一映射为 snake_case
`algorithm_params`。上传、模式、宽度或这些超参数变化只让结果失效，不立即发请求；
Generate 捕获当前输入快照后提交一次请求。处理期间相关控件锁定，完成色板匹配后主按钮
才从 Generating 变为 Download。品牌、抖动、网格和缩放只作用于当前结果，不重新上传原图。

前端仅接受 HTTP 成功、统一信封合法、算法身份和尺寸匹配、Base64 可解码且
RGBA 长度正确的结果。未配置、网络错误、超时、非成功状态、空响应和非法
响应都自动执行 `grid.ts` 中的本地处理。

本地 `downsample` 使用 Canvas 将原图缩放为目标网格大小：

处理策略：

1. 对大图进行多次减半缩放。
2. 最后绘制到目标宽高。
3. 读取目标 Canvas 的 ImageData。
4. 执行既有边缘连通背景移除，并以透明 alpha 标记空格。

这样比一次性缩小更能保留细节，减少锯齿和混色异常。

## 7. 颜色匹配方案

### 7.1 为什么不用 RGB 距离

直接计算 RGB 欧氏距离会出现人眼感知不一致的问题。例如两个颜色在 RGB 数值上接近，不代表视觉上接近。

因此当前采用：

```text
sRGB → CIE XYZ → CIE Lab → CIEDE2000 色差
```

### 7.2 最近色匹配

对每个目标格子的颜色，在指定品牌色卡中找到 CIEDE2000 色差最小的颜色。

```text
输入 RGB
→ 转 Lab
→ 遍历品牌色卡
→ 计算 ΔE00
→ 选择距离最小的色卡颜色
```

### 7.3 抖动

当前支持 Floyd–Steinberg dithering。

处理逻辑：

1. 当前格子匹配到最近拼豆色。
2. 计算原颜色与匹配颜色之间的误差。
3. 将误差按权重扩散到右侧和下一行邻居。

误差扩散权重：

```text
当前像素 X

      X   7/16
3/16 5/16 1/16
```

优点：

- 渐变和照片类图片更自然。
- 限色时能保留更多视觉层次。

缺点：

- 会产生更多散点。
- 对实际制作可能更复杂。

## 8. 空格与透明像素处理

当前透明度低于阈值的像素会被视为空格。

```ts
if (data[p + 3] >= 128) {
  solid[i] = 1;
}
```

效果：

- 透明 PNG 可以生成异形拼豆图。
- 空格不参与颜色匹配和误差扩散。

## 9. 渲染方案

### 9.1 预览渲染

`renderPattern` 负责绘制预览图：

- 背景色。
- 网格线。
- 10 格主参考线。
- 29 格拼板参考线。
- 圆形拼豆。
- 中心小孔阴影。
- 颜色高亮。

### 9.2 拼板参考线

标准拼板按 29×29 处理：

```ts
const PEGBOARD = 29;
```

当 x 或 y 坐标是 29 的倍数时绘制蓝色参考线。

### 9.3 导出渲染

`renderExport` 会创建新的 Canvas，内容包括：

- 高分辨率拼豆图。
- 网格线和拼板线。
- 配豆清单图例。

导出流程：

```ts
renderExport(pattern).toBlob((blob) => {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${source.name}-perler-pattern.png`;
  a.click();
});
```

## 10. 当前能力与限制

### 10.1 当前能力

- 图片上传。
- 后端优先、浏览器自动回退的格子图预处理。
- 强制背景移除，无关闭参数或页面开关。
- 多品牌色卡。
- CIEDE2000 颜色匹配。
- 抖动。
- 拼板参考线。
- 配豆清单。
- PNG 导出。
- 中文页面。

### 10.2 当前限制

- 只能按宽度控制尺寸，高度自动计算。
- 没有固定 29×29 / 58×58 等快捷尺寸。
- 没有 CSV 导出。
- 没有 PDF 导出。
- 没有手动编辑。
- 没有颜色数量上限。
- 当前生产后端注册 CPU-only `cv_native@1.0.0`，使用 GrabCut、Mask 修复、前景边缘
  视觉锐化和 Mask 感知采样生成 RGBA 格子；复杂场景仍可能失败并触发浏览器回退。
- 尚未在真实 GPU、真实模型和目标并发下进行性能验证。
- 没有作品保存。

## 11. 后续扩展设计

### 11.1 快捷尺寸

建议在 `PerlerStudio.tsx` 中增加尺寸 preset：

```ts
const sizePresets = [
  { label: "1 块板", width: 29 },
  { label: "2×2 块板", width: 58 },
  { label: "3×3 块板", width: 87 },
  { label: "4×4 块板", width: 116 },
];
```

当前尺寸逻辑只依赖 `beadsAcross`，因此快捷按钮可直接更新该 state。

如果要支持固定宽高，需要把 `beadsAcross` 拆成：

```ts
const [gridWidth, setGridWidth] = useState(58);
const [gridHeight, setGridHeight] = useState(58);
const [keepAspectRatio, setKeepAspectRatio] = useState(true);
```

### 11.2 CSV 配豆清单导出

可基于 `pattern.used` 和 `BRANDS[brand].colors` 生成 CSV。

字段建议：

```text
code,name,hex,count
```

实现位置建议：

- 在 `PerlerStudio.tsx` 增加 `downloadCsv`。
- 或在 `src/lib/export.ts` 新增导出工具函数。

### 11.3 PDF 导出

推荐方案：

- 轻量方案：先用 Canvas PNG 放入 PDF。
- 高质量方案：使用 jsPDF 绘制矢量圆点、网格和图例。

如果图纸很大，建议支持分页：

```text
每 29×29 或 58×58 作为一页
```

### 11.4 手动编辑

需要引入编辑状态：

```ts
selectedColorIndex
activeTool: "paint" | "erase" | "picker"
```

交互事件：

- Canvas pointer down。
- 根据鼠标坐标换算格子 x/y。
- 修改 `Pattern.cells[y * width + x]`。
- 重新统计 `used` 和 `totalBeads`。

建议新增模块：

```text
src/lib/pattern-edit.ts
```

### 11.5 颜色数量上限

可选方案：

1. 先生成完整色卡匹配结果，再合并低频颜色。
2. 生成前对图片做颜色量化，再映射色卡。
3. 在色卡中选出最接近图片主色的 N 个颜色，再做匹配。

个人使用优先推荐第 1 种，改动小。

## 12. 本地运行

### 12.1 安装依赖

```bash
npm install
```

### 12.2 开发服务

```bash
npm run dev
```

当前后台服务地址：

```text
http://127.0.0.1:4321/zh/
```

### 12.3 构建

```bash
npm run build
```

构建产物目录：

```text
dist/
```

## 13. 验证记录

当前已完成本地验证：

```text
npm install
npm run build
npx astro dev --background --host 127.0.0.1
```

构建结果：

- 生成静态页面成功。
- `/` 和 `/zh/` 页面构建成功。
- 本地开发服务可访问。

## 14. 风险与注意事项

### 14.1 大图性能

当输出豆数过大时，Canvas 渲染和 CIEDE2000 计算会明显变慢。当前通过 `MAX_BEADS = 150` 限制最大边。

后续如果需要更大图纸，可考虑：

- Web Worker 后台计算。
- 最近色缓存。
- 降低导出分辨率。
- 分块渲染。

### 14.2 色卡准确性

屏幕显示颜色、RGB 色值和真实拼豆颜色会存在差异。实际制作前最好参考实体色卡。

### 14.3 打印尺寸

当前 PNG 导出重点是可视图纸，不保证物理打印比例严格等于真实拼豆尺寸。若要精确打印，需要 PDF 或打印参数控制。

### 14.4 授权

当前工程来自开源仓库，本阶段仅用于个人本地试用。后续如需正式发布，应再次确认依赖和原项目授权。
