# CV Native 后端算法与前端处理模式技术计划

## 文档状态

- 状态：已完成
- 上游文档：[SPEC.md](SPEC.md)

## 总体设计

前端把固定构建时算法标识升级为用户可选的处理模式。`browser_native` 直接调用现有
本地格子处理器；`cv_native` 使用现有 HTTP 契约请求后端，成功则消费后端 RGBA
格子，失败则返回带 `fell_back` 标记的本地格子并触发单例通知。

后端新增独立 `algorithms/cv_native/` 包，通过生产装配注册 `cv_native@1.0.0`。
同步 OpenCV 工作放入有界线程执行器，继续由通用处理服务负责超时和统一输出校验。
算法不实现真正语义识别，而是用透明度/空间先验初始化 GrabCut。初始背景分割和
Mask 修复完成后，再对保留前景及其轮廓邻域执行 Canny 边缘增强和视觉锐化。像素化采用掩码
感知的区域采样，采样颜色不在后端量化或聚类。

## 后端分包蓝图

后端沿现有 `python_backend` 分层扩展，统一协议不向算法包泄漏 FastAPI 或 BentoML
对象。建议的职责边界如下：

```text
backend/src/python_backend/
├─ algorithms/contracts.py       # AlgorithmInput/Output、Descriptor、Protocol
├─ algorithms/registry.py        # 生产/测试注册表与版本解析
├─ algorithms/cv_native/
│  ├─ __init__.py                # 对外导出 service/descriptor
│  ├─ descriptor.py              # cv_native@1.0.0 能力与参数 schema
│  ├─ params.py                  # 参数默认值、范围和不可变约束
│  ├─ service.py                 # AlgorithmService 适配器
│  ├─ pipeline.py                # 解码到 RGBA 的同步编排
│  ├─ segmentation.py            # Trimap、GrabCut、Mask 修复与置信度
│  ├─ edges.py                   # 前景限定 Canny、保护带和局部锐化
│  └─ pixelize.py                # Mask/边缘感知的目标网格采样
├─ services/processing.py        # 超时、并发边界、统一输出校验
├─ serving/*                     # 未来 GPU/批处理运行时适配边界
└─ web/routes/*                  # HTTP 参数解析和统一信封
```

`cv_native` 内部模块只能通过不可变的内部数据对象传递图像、Mask、边缘带和采样结果；
HTTP 路由只负责组装 `AlgorithmInput`，算法只返回 `AlgorithmOutput`。后续算法不得复制
一套新的图片或响应结构。

## 后端数据流与契约

请求仍使用 `POST /api/v1/process` 的 multipart 字段：`image`、`width`、`height`、
`algorithm=cv_native`、可选 `algorithm_version` 和 JSON `algorithm_params`。算法包接收：

```text
AlgorithmInput {
  schema_version,
  image: { data: bytes, media_type, filename },
  target: { width, height },
  algorithm: { algorithm_id, version },
  params: object
}
```

成功只返回统一 `AlgorithmOutput { schema_version, algorithm, width, height, rgba }`，
由 Web 层编码到既有 `code/msg/data/exec/meta` 信封，`data` 内为 RGBA Base64、尺寸和
算法身份。失败只返回统一错误信封；`exec` 可记录受控错误类型或 Exception Class，
不得将图片内容、堆栈或内部数组放入响应。

## CV Native 处理阶段

### B1：输入与工作图

- 在内存中解码 JPG/PNG，统一为 BGR/BGRA/灰度三类输入，校验通道、尺寸和解码后像素上限。
- 按长边上限缩放到工作图（默认 1024，可配置），但保留目标尺寸只用于最后采样；不得像
  浏览器基线一样先缩到最终格子再做背景判断。
- 使用小半径 Gaussian 或边缘保留降噪图进行分割估计；原始/轻锐化图保留给后续采样，
  避免降噪导致轮廓变软。

### B2：保守 Trimap 与 GrabCut

- 有 alpha 时，将透明区域作为高可信背景、不透明区域作为前景先验，并对不确定的 alpha
  边界保留 probable 状态。
- 无 alpha 时从边界颜色一致性、局部颜色新颖度、亮度/色度差、结构连续性和空间连通性
  生成四值 Trimap；边界像素默认只是 probable background，不得无条件标记 definite background。
- 前景种子必须包含非中心区域候选，以支持贴边主体；只有同时存在可信前景和背景样本时才
  调用 `cv2.grabCut(..., GC_INIT_WITH_MASK)`。
- GrabCut 迭代次数、工作边长和初始化阈值受参数 schema 限制；样本不足、Mask 全空/全满或
  结果置信度过低时抛出 `AlgorithmProcessingError`，交给前端回退。

### B3：Mask 修复与主体保守策略

- 对 GrabCut 结果执行 close/open、孔洞填充、小连通域过滤和必要的边界平滑。
- 连通域保留依据前景种子重叠、面积、结构连续性和边界接触情况，不使用“必须靠近中心”
  作为硬条件。
- 不确定区域优先保留为前景，只有高可信背景才转为透明；输出前检查主体占比、边界覆盖和
  前景/背景样本是否满足最小质量阈值。

### B4：前景边缘视觉增强

- 只在 B3 完成后，在前景 Mask 与其边界邻域上运行灰度 Canny/梯度检测。
- 对边缘图做小半径形态学膨胀，形成 `edge_band`；`edge_band` 与背景区域的交集必须被清除。
- 在前景和 `edge_band` 内执行上限受控的 Unsharp Mask/局部对比度增强，直接改善输出 RGB
  的边缘锐度；增强强度应随局部梯度和 JPEG 噪声自适应，禁止全图锐化。
- 可选叠加 1 个工作像素以内的轻度描边：描边颜色从边缘两侧局部颜色推导，使用有限透明度
  混合，不固定使用纯黑或纯白，不得形成明显光晕。
- 记录每个目标格是否穿过 `edge_band`，交给 B5 作为采样权重；该权重用于保留增强后的
  视觉边缘，不得替代前两项 RGB 增强。

### B5：Mask 感知像素化与输出

- 将工作图按目标 `width × height` 划分区域，先计算每格前景覆盖率，再仅用前景像素计算实体
  RGB；边界格使用 `edge_band` 权重避免轮廓被平均抹平。
- 透明背景不参与主体颜色平均；覆盖率低于 alpha 阈值的格子输出透明，高覆盖率格子输出实体
  alpha，阈值和抗锯齿策略固定并可测试。
- 直接输出区域采样得到的 RGB，绝不对输出执行 K-Means、颜色聚类、调色板压缩或拼豆
  颜色判断；仅允许在分割阶段聚类边框颜色样本，聚类中心不得进入输出。
- 组装 `uint8` RGBA，严格校验尺寸、字节长度、alpha 和算法身份后返回 `AlgorithmOutput`。

## 资源、并发与失败策略

- 路由层限制上传字节数、解码后像素数、目标网格尺寸和参数 JSON 深度/字段数。
- 同步 OpenCV 流水线进入有界线程池；请求协程只负责排队、超时和结果回收，OpenCV 内部
  线程数默认设为 1，避免 worker 乘线程造成 CPU/内存爆炸。
- 使用信号量限制同时处理数，队列满时返回 `BackendBusyError`；超时返回统一错误并在日志中
  记录耗时和阶段，不记录图片字节或 Base64。
- 解码失败、Mask 无效、OpenCV 异常、输出校验失败均映射为 `AlgorithmProcessingError`；
  `exec` 允许记录错误类别，前端只依据失败状态回退。
- 线程任务超时后不能强制杀死 Python/OpenCV 线程，需在计划和日志中保留该残余风险，并通过
  工作尺寸、并发上限和进程级部署策略控制影响。

## 相对浏览器基线的验证方案

建立一组固定 fixture，至少覆盖纯色背景、纹理背景、主体居中、主体贴左/右/上/下边界、
细长结构、低对比度主体、JPEG 压缩和透明 PNG。对每张图同时运行 `browser_native` 与
`cv_native`，记录：主体误删格数量、边界背景污染格数量、边缘断裂格数量、透明覆盖率和
处理耗时，并在前景边缘带内比较增强前后的局部梯度对比度。验收以“贴边主体不劣于基线，
边缘锐度高于未增强输出，至少一个边界/细节场景明显减少污染或断裂，无法判断时正确回退”
作为第一版最低标准；不承诺通用语义分割或高并发性能。

## 技术修正说明

用户建议的主流程合理，但需要以下修正：

- GrabCut 是前景/背景图割，不是语义分割。它不知道对象类别，复杂背景、贴边主体和
  前景背景近色场景仍可能失败，必须保留前端回退。
- 全图 Canny 会放大背景纹理并干扰前景判断，因此不在 GrabCut 前生成全图边缘保护
  Mask。先完成背景分割和 Mask 修复，再在前景内部与轮廓邻域提取结构边缘，用于
  视觉锐化、可选轻度描边、轮廓微调和像素采样保护。
- 对输出做 K-Means 会与前端真实拼豆色板量化形成双重量化，提前丢失可用于色板匹配的
  颜色信息。因此后端只允许为前景分割聚类边框背景样本，不得用聚类结果替换区域采样
  颜色；原始区域采样颜色直接输出给前端。
- 目标分辨率已由请求确定。“分区可控像素化”实现为掩码感知、边界感知的区域采样，
  避免普通整图缩放把背景色混进主体边缘，而不是再生成一套独立尺寸协议。

## P1：扩展前端处理模式和结果状态

### 回应目标

G1、G2、G4、G6；AC1、AC2、AC6。

### 实现动作

- 定义 `ProcessingMode = "cv_native" | "browser_native"` 及模式描述表。
- 将处理器配置拆为后端连接配置与模式对应算法配置；`browser_native` 不构造请求，
  `cv_native` 固定发送算法标识和版本。
- 将 `acquireGrid()` 返回值改为判别联合，包含 `grid`、实际来源、是否发生回退和
  受控失败分类，不向 UI 传递原始异常或响应内容。
- 保留 AbortSignal 和请求序号；只有当前请求可以更新格子和回退通知。
- 模式变化加入格子获取 effect 依赖，品牌、抖动、网格、缩放和高亮仍不加入。

### 期望结果

调用方可以区分后端成功、主动本地处理和后端失败后的本地回退，并保持竞态安全。

## P2：增加模式下拉框和回退通知

### 回应目标

G1、G2；AC1、AC2。

### 实现动作

- 在 Pattern settings 的 `CardContent` 首项增加 Radix Select，模式名称使用中英文词典。
- 后端 URL 有效时初始模式为 `cv_native`，否则为 `browser_native`；不持久化用户选择。
- 新增通知状态与 5 秒清理 effect；新事件更新事件编号并重置定时器。
- 通知采用固定视口位置的轻量提示，包含本地化文本和 lucide `X` 图标按钮；使用
  `role="status"` 或等价 live-region，并为关闭按钮提供可访问名称。
- 切换到本地模式、切换图片或后端成功时清除不再相关的旧通知。

### 期望结果

模式选择位于第一项；回退对用户可见但不阻断工作流，不发生通知堆叠或过期闪现。

## P3：建立 CV Native 算法包与生产装配

### 回应目标

G3、G4、G5；AC3、AC5。

### 实现动作

- 添加直接运行依赖 `opencv-python-headless` 和 `numpy`，固定兼容版本范围。
- 创建 `algorithms/cv_native/`，分离描述符、参数模型、同步流水线和异步服务适配器。
- 描述符使用 `cv_native@1.0.0`、默认版本、`requires_gpu=False`、
  `supports_batching=False`、`removes_background=True`，提供 JSON 参数 schema。
- 提供生产注册表构造函数并由 `create_app()` 默认装配；测试仍可注入自定义注册表。
- 为算法增加最大解码像素、最大工作边长、并发 worker、OpenCV 内部线程等配置。
- 使用专用有界执行器/信号量和 `asyncio` 线程桥接运行同步 OpenCV 流水线，避免阻塞
  ASGI 事件循环；记录 native 任务超时后不能强制中断线程的剩余风险。
- 增加安全的 `AlgorithmProcessingError`，将解码、掩码和 OpenCV 失败映射到统一信封。

### 期望结果

生产能力接口能发现首个真实算法，合法请求进入 CPU 执行边界，异常继续使用统一协议。

## P4：实现零模型 CV 流水线

### 回应目标

G3、G5；AC4、AC5。

### 实现动作

- 使用 `cv2.imdecode` 从内存解码，统一 BGR/BGRA/灰度输入并验证维度、通道和解码后
  像素上限；不写临时文件。
- 在受限工作尺寸上执行轻量降噪，降低颜色噪声对初始前景/背景估计的干扰。
- 输入有有效 alpha 时，将透明/不透明区域转换成 GrabCut 强先验；无 alpha 时使用
  留边矩形、中心区域和保守颜色先验构造 probable foreground/background mask。
- 使用 `GC_INIT_WITH_MASK` 执行有限轮 GrabCut；确认同时存在前景与背景样本，否则
  抛出受控算法错误。
- 对二值前景 mask 执行 close/open、孔洞修复和小连通域过滤。
- 在约两倍目标网格分辨率构造高召回主体保护 Mask，并与高分辨率 GrabCut Mask 融合；
  只恢复当前主体邻域内、受粗尺度主体支持且与背景色域距离足够大的像素，避免硬二值
  GrabCut 永久丢失低对比度主体，同时禁止保护 Mask 扩散到远处背景连通块。
- 将修复后的 mask 应用于工作图，仅在前景内部与轮廓邻域执行灰度 Canny 和轻量膨胀；
  使用结果微调轮廓并保护主体内部结构，不重新引入背景区域。
- 采用 mask 归一化的面积采样生成目标网格颜色和占用率，在边界格选择前景代表色，
  避免透明背景参与平均产生色边；按占用阈值写入 alpha。
- 保留区域采样得到的实体格 RGB，不对输出执行 K-Means、调色板压缩或其他颜色量化。
- 按行组装精确 `uint8` RGBA 并转换为 `bytes`，返回统一 `AlgorithmOutput`。

### 期望结果

合成前景、透明 PNG 和常见纯色背景图片可以得到边界较稳定的透明 RGBA 目标网格，
不包含模型、拼豆色板或 Web 类型。

## P5：补齐自动化测试

### 回应目标

G1 至 G6；AC1 至 AC7。

### 实现动作

- 后端参数测试：默认值、未知字段、类型、范围、非有限数和背景关闭字段。
- 后端流水线测试：透明输入、纯色背景主体、边界主体、灰度/RGB/RGBA、非法图片、
  过大解码、无有效前景、精确尺寸/长度/alpha、采样颜色保留和重复执行稳定性。
- 后端集成测试：生产能力列表、默认版本解析、真实算法 API 成功信封、算法错误信封、
  事件循环非阻塞边界和并发限制。
- 前端客户端测试：两种模式请求行为、成功来源、各类失败的 `fell_back` 结果、取消
  请求不产生过期回退事件。
- 使用 Testing Library + jsdom（或现有工具链可实现的等价方案）测试模式位置/切换、
  通知出现、5 秒关闭、手动关闭、连续事件重置和无障碍名称。
- 验证品牌/抖动/网格/缩放不重传，宽度和模式变化重传。

### 期望结果

CV 算法、HTTP 成功路径、模式 UI、通知生命周期、失败回退和竞态均有可重复证据。

## P6：文档、联调与验收

### 回应目标

G3 至 G6；AC3 至 AC7。

### 实现动作

- 更新根、前端和后端 README，说明两种模式、默认规则、回退通知、CV 能力和限制。
- 更新 `.env.example`、PRD 和技术方案；移除“生产注册表为空/只返回 501”的旧状态。
- 运行 Ruff、Pytest、前端测试、Astro check/build、`git diff --check`。
- 后台启动服务并验证能力接口只含 `cv_native`，处理真实受控图片返回合法成功信封。
- 浏览器验证 CV 成功、后端停止后的 5 秒通知回退、本地模式不发请求、设置依赖正确。
- 记录 GrabCut 非语义模型、CPU 超时线程不可强停、真实复杂图片效果和未进行负载压测
  的剩余风险。

### 期望结果

首个生产算法和用户可见模式选择可联合运行，成功与回退行为均可观察、可测试、可追踪。

## P7：CV 超参数与手动生成状态机

### 回应目标

G7；AC9，并替代 P1/P2 中模式和宽度变化自动请求的阶段性行为。

### 实现动作

- 扩展 `CvNativeParams` 和算法 descriptor，公开主体恢复背景距离、粗尺度主体数量、保护
  尺度、颜色差异种子、边缘/饱和度种子、保护膨胀、恢复邻域、锐化和描边强度；所有参数
  具有默认值、数值范围和未知字段拒绝规则。
- 将双尺度保护中的常量改为参数驱动，保持默认值等于已验收的主体召回优先档；透明 alpha
  输入继续跳过无 alpha 图片使用的恢复启发式。
- 前端定义同构超参数状态和 snake_case 请求映射，在 CV Native 模式下于 Pattern settings
  下方渲染独立 Hyperparameters 面板，使用稳定尺寸的滑块和值标签。
- 删除图片、宽度和模式依赖的自动获取 effect，建立 `empty/dirty/generating/ready` 状态：
  输入变化使结果失效并进入 dirty；Generate 捕获最新输入快照并发起一次处理；形成 Pattern
  后进入 ready；只有 ready 显示 Download。
- 生成期间禁用上传、模式、宽度和超参数控件，主按钮显示等待且不可重复触发；继续使用请求
  序号与 AbortController 防御过期结果。
- 保留前端色板、抖动、网格、缩放和高亮的即时处理，它们不使后端格子失效。

### 期望结果

用户可以可控地调参并显式生成，不会因滑块连续变化重复上传；按钮和控件状态准确反映当前
结果是否可下载，后端仍使用统一契约。

## 验证命令草案

```text
backend/.venv/Scripts/python -m pip install -e "./backend[dev]"
backend/.venv/Scripts/python -m ruff check backend
backend/.venv/Scripts/python -m pytest backend

cd frontend && npm test
cd frontend && npm run check
cd frontend && npm run build

curl http://127.0.0.1:8000/api/v1/algorithms
curl -F image=@sample.png -F width=87 -F height=87 -F algorithm=cv_native \
  http://127.0.0.1:8000/api/v1/process
```
