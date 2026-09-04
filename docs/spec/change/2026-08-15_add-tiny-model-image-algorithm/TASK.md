# 轻量终端 AI 对象选择与插画像素化任务清单

## 阶段 1：规格与契约

- [x] 确认上传后立即分析、前端显示 bbox、用户勾选实例、Generate 后继续处理的两阶段交互。
- [x] 确认移除 Subject Prompt 和 CLIP 图片区域匹配路线。
- [x] 确认首选 YOLOE-26M Prompt-free + SAM2.1-S，运行模型目标不超过 200 MiB。
- [x] 更新 SPEC、PLAN、TASK。
- [x] 定义分析输入、候选对象、bbox 和 token 数据契约。
- [x] 定义 Tiny Model 生成参数中的 `analysis_token` 与 `selected_object_ids`。

## 阶段 2：后端对象分析

- [x] 增加 YOLOE 和 SAM2.1 工件的大小、SHA-256、下载与校验。
- [x] 实现 Prompt-free 对象分析运行时和候选过滤、去重、排序、限量。
- [x] 使用 YOLOE 原始英文类型并实现同类型实例稳定编号。
- [x] 实现 HMAC 分析 token 的签发、过期和图片摘要验证。
- [x] 新增 `/api/v1/analyze`、标准响应信封和错误处理。
- [x] 增加分析成功、空结果、超限、模型不可用和 token 篡改测试。

## 阶段 3：精细分割和生成

- [x] 修改 Tiny Model 参数解析，移除 Prompt 并要求 token 与非空实例 ID。
- [x] 使用 SAM2.1-S 对选中 bbox 分别生成并修复 Mask。
- [x] 保持多实例相对位置、透明边裁切和主体等比放大。
- [x] 增加 Cartoonizer 接口并以可替换的边缘感知基线打通链路。
- [x] 接入 AnimeGANv2 PyTorch `celeba_distill` 评估权重并保持 Mask 外像素和最终 Alpha 不变。
- [x] 保持边缘、`max_colors`、像素化和 RGBA 输出契约。
- [x] 增加选中单实例、多实例、未知 ID、不同图片、过期 token 和空 Mask 测试。

## 阶段 4：前端交互

- [x] 增加 analyze 客户端、严格响应解析和自动取消。
- [x] Tiny Model 上传或切换后自动进入 analyzing。
- [x] 在原图上叠加可点击 bbox、原始英文类型和实例编号。
- [x] 增加实例复选列表、默认显著主体和至少一项校验。
- [x] 移除 Tiny Model Subject Prompt 控件。
- [x] 将选择变化接入 Generate/Download 状态机且不重复分析。
- [x] 分析或生成失败时保持浏览器回退与 5 秒通知。

## 阶段 5：工件与验收

- [x] 下载并验证 YOLOE-26M Prompt-free 和 SAM2.1-S 工件。
- [x] 更新 `data/model/download.md`、后端 README、`.env.example` 和许可证说明。
- [x] 使用 `007-src.jpg` 验证对象类型、bbox、选择和精细 Mask。
- [x] 比较 AnimeGANv2 `celeba_distill`、`face_paint_512_v2`、`paprika` 和权重插值效果，确定当前 POC 使用 `celeba_distill`。
- [x] 使用 `007-src.jpg` 完成 AnimeGAN 集成后的真实 CPU 接口与 Chrome 风格化生成测试，并记录扁平度改善和身份细节变化限制。
- [ ] 使用多人物、动物、台阶、边缘主体、重叠对象和无候选样本验收。
- [x] 运行 Ruff、pytest、Vitest、Astro check 和 build。
- [x] 真实 Chrome 验证分析、选择、Generate、等待、Download 和回退。
- [ ] 在 NVIDIA CUDA 环境记录显存、热请求时延和并发排队指标。
- [ ] 确认或替换 Cartoonizer 最终权重、训练来源和生产许可证，并完成扩展样本风格验收及身份细节可接受性评估。
