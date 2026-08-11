# Python 后端图片处理与前端回退任务清单

## 文档状态

- 状态：实现完成，待人工浏览器交互验收
- 上游文档：[PLAN.md](PLAN.md)

## 阶段 1：建立子项目结构（P1）

- [x] 创建 `frontend/` 并迁移 `src/`、`public/`、`package.json`、锁文件、Astro/TypeScript/UI 配置及前端相关说明。
- [x] 检查所有路径别名、静态资源路径和 Astro `base` 在迁移后仍正确。
- [x] 创建 `backend/` Python 包结构、测试目录和项目说明入口。
- [x] 更新根 `.gitignore`，增加 Python `.venv/`、`__pycache__/`、`.pytest_cache/`、覆盖率文件，并适配 `frontend/dist/` 和 `frontend/.astro/`。
- [x] 更新 `.github/workflows/deploy.yml` 的 npm 缓存依赖路径、工作目录和上传目录。
- [x] 在迁移后先执行一次前端安装、类型检查和构建，确认纯目录调整没有破坏行为。

## 阶段 2：实现并测试 HTTP 契约（P2、P3）

- [x] 建立 `backend/src/python_backend/`，按 `web/`、`schemas/`、`core/`、`services/`、`algorithms/`、`serving/` 分包并保持单向职责依赖。
- [x] 增加 FastAPI Web 应用、CORS、中间件、健康检查、版本化处理路由和算法能力查询路由。
- [x] 增加 BentoML 模型服务层依赖、空服务装配和配置入口，确保无 GPU、无模型环境可启动基础框架。
- [x] 定义上传大小、内容类型、目标宽高、算法标识/版本格式、算法参数编码长度/深度/字段数等常量限制。
- [x] 定义统一响应信封模型：`code`、`msg`、`data`、`exec: string | null`、`meta.accept_id`、`meta.perf_time_use`；成功码固定为 `200`。
- [x] 实现请求标识生成、毫秒耗时采集和统一成功响应构造。
- [x] 实现 multipart 参数验证和统一的 4xx 错误信封。
- [x] 为 FastAPI 参数校验、HTTP 异常和未处理异常增加统一异常处理器，确保受控错误不逸出默认响应格式。
- [x] 错误响应的 `exec` 仅序列化 Exception Class 类名；无异常对象时返回 `null`，禁止返回模块路径、异常消息或堆栈。
- [x] 确保图片处理和健康检查端点都使用同一响应信封，仅 `data` 业务载荷不同。
- [x] 在独立协议模块定义唯一的 `AlgorithmInput`、`AlgorithmOutput`、算法描述符和异步算法服务协议，协议不依赖 FastAPI 或 BentoML 类型。
- [x] 统一输入包含协议版本、图片字节/媒体类型/文件名、目标尺寸、算法标识/版本/参数；统一输出包含协议版本、实际算法标识/版本和已移除背景的 RGBA 网格。
- [x] Web 层只执行一次 multipart 到 `AlgorithmInput` 的映射；业务服务、注册表、BentoML gateway 和测试假算法不得创建平行 DTO。
- [x] 实现以算法标识和版本索引、可依赖注入的注册表，以及默认版本、版本歧义和算法不存在的分发规则。
- [x] 定义算法参数 schema 声明与校验入口；通用 Web 层只解析受限 JSON 对象，不包含算法专属字段。
- [x] 拒绝在 `algorithm_params` 中使用 `remove_background` 或等价关闭项，算法能力说明固定声明输出已完成背景移除。
- [x] 实现集中 `AlgorithmOutput` 校验，拒绝协议版本、算法身份、尺寸、RGBA 类型或长度不合法的结果，并映射为 `AlgorithmContractError` 信封。
- [x] 定义 BentoML gateway/服务句柄抽象及 GPU 数量、worker、最大并发、自适应批处理、队列超时和副本配置模型，不加载或调用任何模型。
- [x] 保持生产注册表为空；处理请求统一返回 `501`、`data: null`、`exec: "AlgorithmNotImplementedError"`。
- [x] 实现算法能力查询，生产装配返回空列表。
- [x] 仅在后端测试目录实现至少两个标识或版本不同、但共享同一输入输出类型的确定性假算法并通过依赖注入注册；不得把假算法加入生产包或默认注册表。
- [x] 使用测试假算法验证版本、宽高、Base64 RGBA 和算法描述信息位于成功信封 `data`，且 RGBA 解码长度为 `width * height * 4`。
- [x] 确认处理路径不创建持久化文件，日志不记录图片内容。
- [x] 增加后端依赖清单、开发依赖和启动配置。
- [x] 编写成功/错误信封、请求标识、非负耗时、健康检查、空算法列表、未实现分发、算法版本、参数约束、多个假算法共享输入输出契约、非法算法输出、非法/空上传、越界尺寸和响应长度测试。
- [x] 运行后端测试并修复失败。

## 阶段 3：实现前端网格处理边界（P4、P5）

- [x] 将 `PerlerStudio.tsx` 中的 `downsample()` 和 `pattern.ts` 中的背景移除能力提取到 `frontend/src/lib/` 的本地格子图处理模块，保持当前回退算法不变。
- [x] 让本地处理器把移除的背景写为透明格，并从 `PatternOptions`、`generatePattern()` 中删除背景移除职责。
- [x] 定义后端响应 TypeScript 类型，但按运行时不可信数据进行解析。
- [x] 实现 `PUBLIC_PROCESSOR_API_URL`、`PUBLIC_PROCESSOR_ALGORITHM`、可选版本和受控算法参数配置读取。
- [x] 实现 URL 归一化、包含算法标识/版本/参数但不包含背景移除字段的 multipart 请求、超时和取消。
- [x] 实现信封字段与类型、成功状态、请求标识、非负耗时、版本、整数、目标尺寸、Base64、RGBA 长度与字节范围校验，并构造 `ImageData`。
- [x] 为后端客户端返回可区分的成功/失败结果，避免异常逃逸到 UI。
- [x] 扩展上传图片状态以保留原始 `File`；内置示例保持无文件状态。
- [x] 将 React 流程拆成“获得成品格子图”和“格子图转 Pattern”两个 effect/状态阶段。
- [x] 后端获取失败时调用本地网格处理模块；未配置地址或内置示例直接调用本地模块。
- [x] 加入 `AbortController` 与递增请求标识，在文件、尺寸变化和卸载时取消或忽略旧结果。
- [x] 删除 React 背景移除状态和页面开关；本地处理模块始终执行现有背景移除算法。
- [x] 保证品牌和抖动变化只重新执行 `generatePattern()`，不重新请求后端。
- [x] 保证加载新网格期间旧图案不会被错误标记为新图片结果。

## 阶段 4：补齐前端自动化验证（P4、P5、P7）

- [x] 配置与现有 Astro/TypeScript 兼容的前端测试入口。
- [x] 测试合法响应信封可以从 `data` 还原精确 RGBA `ImageData`。
- [x] 测试信封缺字段、字段类型错误、`code` 非 `200`、`exec` 类型非法、协议版本、宽高、Base64 和字节长度非法时拒绝结果。
- [x] 测试算法标识、可选版本和 JSON 参数被正确发送、请求不包含背景移除字段，前端不解释算法专属字段。
- [x] 测试生产后端 `501` 未实现、未配置、网络错误、超时、非 2xx、空响应和非法响应均调用本地处理器。
- [x] 测试最新请求获胜，已取消或较慢的旧请求不能覆盖结果。
- [x] 测试页面不再呈现背景移除开关、本地回退始终执行背景移除，品牌、抖动等后续选项变化不会产生新的 HTTP 请求。
- [x] 执行前端测试、类型检查和生产构建。

## 阶段 5：更新文档与环境示例（P6）

- [x] 重写根 README 的项目定位、目录结构和快速开始，链接到前后端说明。
- [x] 在 `frontend/README.md` 记录静态构建、`PUBLIC_PROCESSOR_API_URL`、本地回退和 GitHub Pages 配置。
- [x] 在 `backend/README.md` 记录 Python 环境、依赖安装、服务启动、环境变量、API 示例、输入限制、无持久化约束和当前无生产算法的行为。
- [x] 记录 FastAPI 与 BentoML 职责边界，以及新增算法包、参数 schema、注册、GPU 资源、并发、批处理和独立压测流程。
- [x] 添加前后端所需 `.env.example`，不写入真实凭证或生产 URL。
- [x] 更新所有“图片绝不上传”“没有后端”的旧描述，明确条件化行为。
- [x] 检查 README、PRD 和技术设计中是否还有与新行为冲突的内容；只修改本需求直接影响的段落。

## 阶段 6：全链路验收（P7）

- [x] 运行后端完整自动化测试并记录结果。
- [x] 运行前端完整自动化测试、类型检查和生产构建并记录结果。
- [x] 使用后台模式启动 Astro 前端和 Python 后端，确认健康检查正常。
- [x] 查询算法能力接口，确认生产注册表返回空列表。
- [ ] 上传受控测试图，确认后端返回 `501` 未实现信封且前端自动显示本地处理结果。
- [x] 通过自动化测试注入假算法，确认成功响应契约和多算法分发；不在生产服务注册假算法。
- [x] 确认页面无背景移除开关，后端请求无对应参数，本地结果仍始终完成背景移除。
- [ ] 切换品牌、抖动、预览缩放和高亮，确认不发生不必要的图片重传。
- [ ] 修改拼豆宽度，确认重新请求对应目标尺寸。
- [ ] 停止后端，再次上传并调整宽度，确认自动本地回退、预览和导出均可用。
- [x] 模拟空响应、非法响应和慢响应，确认本地回退及最新请求保护。
- [x] 检查后端生产包和依赖，确认不存在 Pillow、OpenCV、缩放、背景移除、模型加载或伪造结果实现。
- [x] 检查 BentoML 资源/并发/批处理配置入口可解析，并明确记录未执行真实 GPU 性能验证。
- [x] 检查 `git diff --check`、工作区变更范围和生成产物，避免提交依赖目录、缓存或用户文件。
- [x] 在本工作空间记录实际执行的验证命令、结果及任何未验证风险。

## 验证记录（2026-08-11）

### 自动化与静态检查

- `backend/.venv/Scripts/python -m ruff check backend`：通过，无问题。
- `backend/.venv/Scripts/python -m pytest backend`：14 项通过；存在 1 条 FastAPI
  `TestClient` 关于未来 `httpx2` 的上游弃用警告，不影响当前测试结果。
- `cd frontend && npm test`：24 项通过，覆盖合法/非法信封、`501`、网络错误、
  空响应、非法 JSON、超时、本地回退、取消保护及强制背景移除。
- `cd frontend && npm run check`：30 个文件，0 错误、0 警告、0 提示。
- `cd frontend && npm run build`：通过，生成 4 个静态页面。
- `git diff --check`：通过；仅报告 Windows 工作区预期的 LF/CRLF 转换提示。

### 服务联调

- Uvicorn 运行于 `http://127.0.0.1:8000`；`GET /health` 返回 `code: 200`，
  `registered_algorithms: 0`。
- `GET /api/v1/algorithms` 返回空 `items`；生产注册表未装配测试假算法。
- multipart 调用 `POST /api/v1/process` 返回 HTTP/业务码 `501`、`data: null`、
  `exec: "AlgorithmNotImplementedError"` 和完整请求元数据。
- 从 Astro 来源 `http://127.0.0.1:4321` 发起 CORS 预检返回 `200` 和正确的
  `access-control-allow-origin`。
- BentoML 入口在 `8001` 实际启动并成功响应统一健康信封，验证后已停止。
- Astro 按后台模式运行于 `http://127.0.0.1:4321/perler-striner/`，页面 HTTP
  响应为 `200`。

### 范围与剩余风险

- 生产依赖和 `python_backend` 源码中不存在 Pillow、OpenCV、PyTorch、
  TensorFlow、图片缩放、背景移除或伪造算法输出；图片算法仅有测试假实现。
- 未加载真实模型、未分配 GPU，也未执行 GPU 吞吐、批处理或并发性能测试；这些
  必须在接入具体算法后使用目标硬件单独验收。
- 当前执行环境禁止启动 Chrome 远程调试，未能自动执行页面内上传、切换品牌/
  抖动/缩放/高亮、修改宽度和停止后端后的预览导出操作。因此对应四项人工浏览器
  验收保持未勾选；其底层请求、回退、取消和 effect 依赖已由测试及代码审计覆盖。
