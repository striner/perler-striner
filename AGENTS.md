# 仓库指南

## 项目定位

详见 [README.md HEAD](README.md)。

## 项目宪法

所有正式需求开发必须遵守 [项目宪法](docs/spec/CONSTITUTION.md)。

开始任何正式需求前，必须先阅读该文件，并按其中流程创建 SPEC 工作空间、形成 `SPEC.md`、`PLAN.md`  `TASK.md`。

如果要引用目录，也可以：

需求文档放在 [docs/spec/change/](docs/spec/change/)。
沉淀的 skill 放在 [docs/spec/skill/](docs/spec/skill/)。

## 开发指南

### Python 相关

使用 Python 3 风格和 4 空格缩进。
函数、变量和模块名使用 `snake_case`；
类名使用 `PascalCase`，例如 `TOSHook`、`TosUtil`；
固定配置使用清晰的常量名。修改 hook 逻辑时保持分发顺序明确，除非有明确行为变更需求，否则避免对 monkey patch 核心路径做大范围重构。

### 服务相关

启动开发服务器时，请使用后台模式：

```
astro dev --background
```

使用 `astro dev stop`、`astro dev status` 和 `astro dev logs` 管理后台服务器。

完整文档：https://docs.astro.build

处理相关任务前，请先查阅以下指南：

- [添加页面、动态路由或中间件](https://docs.astro.build/en/guides/routing/)
- [使用 Astro 组件](https://docs.astro.build/en/basics/astro-components/)
- [使用 React、Vue、Svelte 或其他框架组件](https://docs.astro.build/en/guides/framework-components/)
- [添加或管理内容](https://docs.astro.build/en/guides/content-collections/)
- [添加样式或使用 Tailwind](https://docs.astro.build/en/guides/styling/)
- [支持多语言](https://docs.astro.build/en/guides/internationalization/)
