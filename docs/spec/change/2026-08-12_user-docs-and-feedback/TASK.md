# 用户说明文档与反馈入口接入任务清单

> 本任务清单基于 `PLAN.md` 当前版本形成。若 `SPEC.md` 或 `PLAN.md` 后续调整，本文件需要同步更新。

## 阶段 1：确认需求与渠道信息

1. 确认说明文档站内访问路径：
   - 中文：`/perler-striner/pages/guide/zh/`
   - 英文：`/perler-striner/pages/guide/en/`
2. 确认反馈入口首版方案：
   - 采用问卷反馈；
   - 问卷链接：`https://v.wjx.cn/vm/wFChGhh.aspx`；
   - 补充联系邮箱：`striner@foxmail.com`。
3. 确认版本更新记录维护规则：
   - 人工维护或 AI 总结；
   - 不展示提交链接；
   - 记录操作人；
   - 每次版本更新/合并 `master` 前检查说明文档更新记录。

## 阶段 2：实现入口配置

1. 修改 `src/i18n/ui.ts`：
   - 为 `en` 增加 `guideLabel`、`guideHref`、`feedbackLabel`、`feedbackHref`、`feedbackAriaLabel` 等字段。
   - 为 `zh` 增加对应中文文案。
   - 配置反馈链接为 `https://v.wjx.cn/vm/wFChGhh.aspx`。
   - 确保 `Dict` 类型推导不报错。
2. 检查站内说明文档链接：
   - 中文页面使用 `/perler-striner/pages/guide/zh/`；
   - 英文页面使用 `/perler-striner/pages/guide/en/`。

## 阶段 3：实现右上角说明文档入口

1. 修改 `src/components/HomePage.astro`：
   - 在 header 右侧语言切换按钮附近增加说明文档链接。
   - 使用 `t.guideLabel` 和 `t.guideHref`。
   - 保持现有语言切换入口。
2. 调整 header 布局：
   - 桌面端保持按钮横向排列。
   - 移动端空间不足时允许换行或压缩，不遮挡标题。

## 阶段 4：实现右下角反馈入口

1. 修改 `src/components/HomePage.astro`：
   - 在页面内增加右下角 fixed 圆角悬浮反馈链接。
   - 使用 `t.feedbackLabel`、`t.feedbackHref`、`t.feedbackAriaLabel`。
   - 设置新标签页打开问卷链接。
2. 调整样式：
   - 使用明显但不突兀的按钮样式。
   - 保证层级高于页面内容。
   - 移动端不遮挡主要按钮。

## 阶段 5：实现系统内置说明文档页面

1. 新增中文说明文档页面：
   - 文件：`src/pages/pages/guide/zh/index.astro`
   - 路径：`/perler-striner/pages/guide/zh/`
   - 内容为完整中文说明文档。
2. 新增英文说明文档页面：
   - 文件：`src/pages/pages/guide/en/index.astro`
   - 路径：`/perler-striner/pages/guide/en/`
   - 内容为英文说明文档。
3. 两个说明文档页面均包含：
   - 系统是什么；
   - 适合谁使用；
   - 使用前须知；
   - 新手上手指南；
   - 参数解释；
   - 常见问题；
   - 版本更新记录。
4. 在说明文档末尾加入版本更新记录，并强调维护规则：
   - 每次打版本更新都需要更新说明文档末尾的版本更新记录；
   - 合并 `master` 前检查该记录；
   - 记录时间、操作人、版本、更新内容、用户可感知变化。

## 阶段 6：验证

1. 运行构建：
   - `npm run build`
2. 如可用，运行类型/框架检查：
   - `npx astro check`
3. 启动本地服务：
   - `astro dev --background`
4. 人工检查中文主页面：
   - 右上角说明文档入口可见；
   - 点击后进入 `/perler-striner/pages/guide/zh/`；
   - 右下角反馈入口可见；
   - 点击后跳转到 `https://v.wjx.cn/vm/wFChGhh.aspx`；
   - 原有上传、示例、参数调整、下载入口仍可用。
5. 人工检查英文主页面：
   - 右上角说明文档入口可见；
   - 点击后进入 `/perler-striner/pages/guide/en/`；
   - 反馈入口英文文案可用。
6. 人工检查移动端布局：
   - header 不明显错位；
   - 反馈按钮不遮挡主流程关键操作。

## 阶段 7：复盘与交付说明

1. 记录实际运行过的验证命令和结果。
2. 说明未能验证的部分及原因。
3. 记录反馈问卷链接：`https://v.wjx.cn/vm/wFChGhh.aspx`。
