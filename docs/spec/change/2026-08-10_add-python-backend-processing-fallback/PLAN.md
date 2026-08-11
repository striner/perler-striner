# Python 后端图片处理与前端回退技术计划

## 文档状态

- 状态：已确认
- 上游文档：[SPEC.md](SPEC.md)

## 总体设计

仓库调整为两个应用子项目：

```text
frontend/  Astro + React 静态前端
backend/   Python 图片处理 HTTP 服务
```

前端将图片处理拆为独立的“成品格子图获取”阶段。该阶段优先请求后端算法，失败或未注册算法时调用迁移后的原有 Canvas 降采样与背景移除算法。两条路径都输出 alpha 已标记好空格的 `ImageData`，再统一进入收窄后的 `generatePattern()` 完成色板匹配、抖动和统计。本次后端不提供生产算法，因此真实联调默认验证后端返回未实现、前端完成本地回退。

HTTP 接口使用版本化路径和 multipart 请求。响应使用统一 JSON 信封，`data` 内使用 Base64 编码 RGBA 字节，既保持精确字节语义，也避免大整数数组造成明显传输膨胀。

后端采用 FastAPI + BentoML：FastAPI 负责 HTTP 接入、参数校验、统一信封、中间件和异常映射；BentoML 负责未来 GPU 模型服务的 worker 隔离、资源声明、并发控制、自适应批处理和扩展边界。生产算法通过独立包和注册配置接入，两层之间只使用统一 `AlgorithmInput` / `AlgorithmOutput` 协议，Web 事件循环不直接执行 GPU 推理。

## P1：整理双子项目结构

### 回应目标

G1、G6；AC1。

### 实现动作

- 新建 `frontend/`，将现有 Astro 源码、公共资源、Node 依赖清单、TypeScript/Astro 配置和前端说明迁入该目录。
- 保留仓库级 `.github/`、`docs/`、`AGENTS.md` 和根 README；根 README 改为双子项目入口说明。
- 更新 `.gitignore`，覆盖前端构建产物、Python 虚拟环境、缓存和测试产物。
- 更新 GitHub Pages 工作流：Node 依赖缓存、安装、构建和产物上传均指向 `frontend/`。

### 期望结果

前端和后端具备清晰边界，可分别安装与运行，现有静态站点仍可构建部署。

## P2：定义版本化网格接口

### 回应目标

G2、G3、G5；AC2、AC4、AC5。

### 实现动作

- 提供 `POST /api/v1/process`，使用 multipart 表单接收：
  - `image`：用户原始图片文件；
  - `width`、`height`：目标网格尺寸；
  - `algorithm`：必填的稳定算法标识；
  - `algorithm_version`：可选算法版本；
  - `algorithm_params`：可选的 JSON 编码对象字符串，承载算法专属参数，省略时按空对象处理。
- 成功响应定义为：

```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "version": 1,
    "width": 87,
    "height": 64,
    "rgba_base64": "...",
    "algorithm": {
      "id": "subject-grid",
      "version": "1.0.0"
    }
  },
  "exec": null,
  "meta": {
    "accept_id": "2e093fb4-0ddb-4b09-b814-6bb61745c16e",
    "perf_time_use": 12.34
  }
}
```

- `data.rgba_base64` 解码后必须是按行排列的 RGBA 字节，长度严格等于 `data.width * data.height * 4`。
- `algorithm_params` 必须解析为 JSON 对象，并限制编码长度、嵌套深度和字段数量；数组、标量或超限内容在分发前拒绝。
- Web 层将 multipart 字段和上传内容归一化为唯一的 `AlgorithmInput`；HTTP 输入编码不得渗透到算法接口。
- `meta.accept_id` 由后端为每次请求生成，贯穿响应和安全日志；`meta.perf_time_use` 使用毫秒并包含从进入应用到形成响应的后端耗时。
- 失败使用明确的 4xx/5xx HTTP 状态，同时仍返回相同信封：非 `200` 的 `code`、安全的 `msg`、`data: null`、异常类名字符串或 `null` 的 `exec` 及完整 `meta`；不使用部分成功或空成功体。
- `exec` 由捕获到的 Python Exception Class 生成时只序列化 `exception.__class__.__name__`，不得序列化类对象、模块路径、异常消息或堆栈；没有异常对象的受控失败使用 `null`。
- 为请求参数校验、上传限制、上传读取、HTTP 异常和未处理异常设置统一响应构造与异常处理器，避免泄漏 FastAPI 默认或堆栈格式。
- 提供 `GET /health` 供本地运行和部署探测，其状态载荷也放入同一信封的 `data`。
- 提供 `GET /api/v1/algorithms` 返回已注册算法的标识、版本和参数能力；本次生产注册表返回空列表。

### 期望结果

接口与拼豆品牌无关，能够稳定选择算法和传递隔离的算法参数；响应格式统一，并能从未来成功信封的 `data` 精确还原已完成背景处理的前端 `ImageData`。

## P3：实现 Python Web 与 GPU 模型服务框架

### 回应目标

G1、G2、G5、G7；AC2、AC6、AC7、AC8。

### 实现动作

- 使用 FastAPI 建立 ASGI Web 接入，使用 BentoML 建立未来 GPU 推理服务层和部署入口；固定兼容版本，提供 CPU 环境可启动的空框架。
- 按以下职责分包，具体包名可在实现时遵循 Python 命名规范微调：

```text
backend/src/python_backend/
  web/          # FastAPI app、路由、中间件、异常处理
  schemas/      # HTTP 信封、请求和响应模型
  core/         # 配置、日志、常量、请求上下文
  services/     # 用例编排，不包含算法实现
  algorithms/   # 协议、描述符、注册表、分发异常
  serving/      # BentoML gateway、资源/并发/批处理配置边界
```

- 定义与 Web 无关的算法协议，至少包含算法标识、版本、能力/参数描述、输入图片字节、目标尺寸、算法参数和异步处理结果；背景移除不作为输入字段，而是所有算法输出必须满足的固定后置条件。
- 在 `algorithms/contracts.py`（名称可按实现微调）定义唯一规范结构：

```text
AlgorithmInput
  schema_version
  image.bytes / image.media_type / image.filename
  target.width / target.height
  algorithm.id / algorithm.version / algorithm.params

AlgorithmOutput
  schema_version
  algorithm.id / algorithm.version
  grid.width / grid.height / grid.rgba
```

- FastAPI 路由、业务服务、注册算法、BentoML gateway 和测试假算法均复用上述类型，不为不同算法复制 DTO。
- 通用参数校验明确拒绝通过 `algorithm.params` 传入 `remove_background` 或其他关闭背景移除的等价开关；新增算法的能力说明必须声明其输出已完成背景移除。
- 实现可依赖注入的算法注册表，以 `(algorithm, version)` 查找算法服务；未指定版本时按注册规则解析默认版本，歧义或不存在时返回结构化错误。
- 生产装配不注册任何算法；调用处理接口时返回 HTTP/业务码 `501`、`data: null`、`exec: "AlgorithmNotImplementedError"`。
- 仅在测试目录提供确定性假算法，用于验证注册、版本选择、参数透传、成功响应和前端消费，不将其加入生产包或默认装配。
- 实现算法能力查询服务；空注册表返回空列表，未来算法可声明参数 schema、是否需要 GPU、并发和批处理能力。
- 在算法返回后集中校验 `AlgorithmOutput` 的协议版本、算法身份、目标尺寸、RGBA 字节类型和长度；不合法结果转换为统一 `AlgorithmContractError`，不得进入成功信封。
- `serving/` 定义 BentoML 服务句柄/网关抽象和配置结构，为每算法独立 worker、GPU 资源数、最大并发、自适应批处理、队列超时和副本扩展预留配置；本次不加载模型、不分配 GPU、不执行推理。
- Web 层保持异步，只负责有限上传读取、校验和服务调用；未来 GPU 工作必须通过 BentoML 服务句柄执行，不允许直接在事件循环内调用同步模型代码。
- 上传内容只在请求内存中传递，不写入仓库、临时目录、数据库或对象存储；限制上传体积、内容类型、目标网格范围以及算法参数规模。
- 通过环境变量配置允许的 CORS 来源、请求超时、并发准入和模型服务连接信息，默认覆盖本地 Astro 开发地址。
- 提供固定依赖、独立启动说明和未来新增算法包的接入模板文档，但不提供模板算法实现。

### 期望结果

后端空框架可独立启动，健康检查和算法能力查询可用，处理接口稳定返回未实现信封；不同测试假算法通过同一输入输出结构证明多算法分发、参数透传、输出校验与未来成功契约，生产包不包含任何图片处理内容。

## P4：实现前端后端客户端与严格校验

### 回应目标

G2、G4、G5、G6；AC2、AC3、AC5。

### 实现动作

- 增加公开构建配置 `PUBLIC_PROCESSOR_API_URL`；未配置时不发请求，直接返回本地结果。
- 增加必填的 `PUBLIC_PROCESSOR_ALGORITHM`、可选 `PUBLIC_PROCESSOR_ALGORITHM_VERSION` 和受控算法参数配置；仅配置后端地址但没有算法标识时直接本地处理，前端不自行理解算法专属参数语义。
- 新建处理器客户端，发送原始 `File`、目标宽高、算法标识/版本和 JSON 算法参数，并设置有限超时和 `AbortSignal`；请求中不发送背景移除字段。
- 校验 HTTP 状态、信封全部字段及类型、`code === 200`、`exec` 为字符串或 `null`、非空 `data`、非空 `meta.accept_id`、非负 `meta.perf_time_use`、协议版本、整数尺寸、请求/响应尺寸一致性、Base64 合法性及解码字节长度。
- 仅在所有校验通过后构造 `ImageData`；任何异常统一返回失败信号，由调用层执行本地处理。
- 不在界面或生产日志暴露响应原文、图片内容或冗长堆栈。

### 期望结果

前端只消费可信的后端网格；配置缺失或服务异常不会影响现有功能。

## P5：重构前端处理流水线

### 回应目标

G2、G3、G4、G5；AC2、AC3、AC4、AC5。

### 实现动作

- 保留用户上传的原始 `File`，同时保留现有浏览器解码对象用于预览和回退。
- 将原 `downsample()` 与 `generatePattern()` 内的背景移除能力提取到本地格子图处理器，保持当前浏览器回退算法不变，始终执行背景移除，并通过 alpha 输出实体格/空格。
- 从 `PatternOptions` 和 `generatePattern()` 移除背景处理职责，使其只消费已经完成背景处理的格子图。
- 从 React 状态和页面控件中移除背景移除开关，避免后端优先路径和回退路径出现不同语义。
- 将处理拆为两个阶段：
  1. 当图片或目标尺寸变化时，异步获取后端成品格子图，失败则在本地强制完成缩放和背景移除；
  2. 当格子图、品牌或抖动选项变化时，调用收窄后的 `generatePattern()`。
- 使用请求序号和 `AbortController` 取消/忽略过期请求；组件卸载或输入变化时清理请求。
- 内置示例没有原始 `File`，固定走本地处理器。
- 保持现有界面、最终 `Pattern`、渲染和导出行为不变。

### 期望结果

后端成功与本地回退都在进入色板匹配前形成完整格子图，并共享完全相同的后续拼豆逻辑；控制项变化不会产生多余上传或旧响应覆盖。

## P6：文档、配置与隐私说明

### 回应目标

G1、G6；AC1、AC6。

### 实现动作

- 根 README 说明仓库结构、前后端职责和联调顺序。
- 前端 README 说明构建、GitHub Pages、后端 URL 配置、静态回退行为。
- 后端 README 说明 Python 版本、安装、启动、CORS、限制、API 示例、FastAPI/BentoML 职责边界和新增算法包流程。
- 更新产品描述中“完全本地、不上传”的旧承诺，明确启用后端地址后的上传行为和后端不可用时的回退。
- 提供不包含真实环境地址的 `.env.example`。

### 期望结果

开发者可复现在线/离线两种运行方式，用户不会被过时的隐私说明误导。

## P7：自动化验证与联调验收

### 回应目标

G1 至 G7；AC1 至 AC8。

### 实现动作

- 后端测试：健康检查、空算法列表、未实现信封、成功/失败信封、请求标识和耗时、算法标识/版本解析、参数约束、多个假算法共享契约、非法算法输出拒绝、错误上传、越界尺寸和不持久化行为。
- 前端测试：算法参数请求中不存在背景移除字段、测试假算法合法信封解码、信封缺失/类型/状态非法拒绝、后端 `501`、超时/网络/HTTP/空响应回退、本地强制背景移除、未配置直接回退、旧请求不覆盖新状态、品牌切换不重复请求。
- 执行前端类型检查和生产构建。
- 执行后端测试和基础静态/导入检查。
- 本地后台启动两个服务，人工验证：后端在线但无算法时返回 `501` 并回退；停止后端后上传和调整尺寸仍正常生成及导出。成功路径由自动化测试注入假算法验证。

### 期望结果

关键成功、未实现回退、失败和竞态路径均有可重复证据，双子项目可以独立及联合运行；框架扩展点可测试，但不把无模型环境的结果表述为 GPU 性能验证。

## 风险与处理

### 静态站点跨域

GitHub Pages 与 Python 服务一定是跨域部署。后端采用显式来源白名单；生产部署必须提供实际前端来源，否则前端会安全回退但不会使用后端。

### 图片上传隐私

新行为会把原图发送到配置服务。通过文档更新、不持久化、限制日志内容来降低风险，但传输安全仍依赖部署方提供 HTTPS。

### 网络延迟影响

后端优先意味着图案首次生成需要等待请求完成或超时。通过有限超时、取消旧请求和无后端配置时直接本地处理控制影响。

### GPU 并发能力尚未实测

选择 BentoML 并预留 worker、GPU 资源、并发和批处理配置只能证明架构具备接入点，不能证明特定模型的吞吐量或延迟。本次以接口、注册分发和配置测试验收；真实模型接入后必须使用目标 GPU、输入规模和并发曲线单独压测。

### 多算法参数演进

任意透传参数容易造成接口失控。通用接口只接受受限 JSON 对象，注册算法必须声明自己的参数 schema 并在进入模型服务前完成校验；通用 Web 层不加入算法专属字段。

### 输入输出契约漂移

如果算法包自行定义请求或结果类型，多算法会迅速产生兼容分支。统一结构放在无 Web/模型框架依赖的协议模块中，路由只做一次输入映射，结果只做一次集中校验；算法专属内容只能存在于 `algorithm.params`，不能扩展输出顶层结构。

## 验证命令草案

具体命令在实现时以实际依赖清单为准，目标入口如下：

```text
cd frontend && npm ci
cd frontend && npm run check
cd frontend && npm test
cd frontend && npm run build

cd backend && python -m pip install -r requirements-dev.txt
cd backend && python -m pytest
cd backend && python -m uvicorn python_backend.web.app:app
```
