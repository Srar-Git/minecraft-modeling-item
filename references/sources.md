# 版本依据与调研来源

格式资料历史核查日期：2026-09-13；技能实现与本机 MCP 复核日期：2026-10-27。这里是特定版本的已核实事实，不替代将来的版本检查。优先看 Mojang 发布说明、Blockbench 自有文档/源码和目标运行时文档，不能因社区帖子在官方域名下就当作 Mojang 官方规则。

## 核心风格

[Blockbench Minecraft Style Guide](https://blockbench.net/wiki/guides/minecraft-style-guide/)：支持以少量有意义几何表达外形、旋转元素表达斜线、保持像素密度和有意识的色块/色阶。它偏原版风格；本技能还兼顾用户指定的精细自定义武器，所以不把其中所有比例和简化例子强制套到任何模型。

[Blockbench Overview & Tips](https://blockbench.net/wiki/guides/blockbench-overview-tips/)：用于核查 per-face/box UV、枢轴、父子关系、顶点吸附、共面冲突和预览工具。编辑器的 Inflate 和模型负缩放不是同一概念，也不证明某效果能原版导出。

## Java 格式演进

[Mojang 25w16a](https://www.minecraft.net/en-us/article/minecraft-snapshot-25w16a)：旧的 22.5° 步进限制被放宽，单轴角度可在 −45° 到 +45° 内连续取值。其发布说明同时明确核心 shader 覆盖属于不受支持的内部接口，不能默认为通用长期方案。

[Mojang 25w46a](https://www.minecraft.net/en-us/article/minecraft-snapshot-25w46a)：元素支持 `rotation.x/y/z`，应用顺序 X→Y→Z；旧的 `axis/angle` 仍可用，混写时旧写法优先。旧的 ±45° 范围限制也被移除。不要把老版本规则误用于 Java 26.1；不要混淆 blockstate 的离散旋转规则与元素旋转。

[Mojang Java 26.1](https://www.minecraft.net/en-us/article/minecraft-java-edition-26-1)：资源包版本 84；模型 sprite 的 alpha 内容可影响 solid/cutout/translucent 通道。纹理引用支持字符串或包含 `sprite`、可选 `force_translucent` 的对象；物品子模型支持 `transformation`。这个字段本身不是任意动画时间轴，也不取消元素边界及格式约束。其他版本要重新核查 pack 元数据和透明行为。

[Fabric Item Models](https://docs.fabricmc.net/develop/items/item-models)：提供模型、面、UV、cullface 和 display 结构的开发者文档。网页随所选版本变化，应核对版本；与 Mojang 已更新的旋转说明冲突时，不把页面中的旧例子当作新限制。Java `from/to` 范围与 UV 约定可用于结构预检，但完整运行行为仍需客户端确认。

[Mojang 24w33a](https://www.minecraft.net/en-us/article/minecraft-snapshot-24w33a)：`light_emission` 为 0–15，控制元素最低受光等级。这不是环境光源或 bloom 的承诺。

[Blockbench Emissive Textures in Renders](https://blockbench.net/wiki/guides/emissive-textures-renders/)：区分编辑/渲染软件里的发光预览与目标游戏能力；不要把 Blender emission 或某插件预览当成原版 Java 特性。

## 本地证据的使用边界

本地成品及验证报告见 [local-examples.md](local-examples.md)。它们可说明实际制作方法和曾经的失败，但没有经过真实 Minecraft 客户端验证的项目不能作为兼容性的权威范本。现有倒置壳是本地实现经验，不能据此发明通用 `outline:-1` 字段。


## 本次技能实现的验证范围（2026-10-27）

- Python：既有结构/图像审计 12 个用例，新增工作流 21 个用例，全部通过。覆盖重复描边、sidecar 恢复、透明/倒置/旋转跳过、冻结遮挡、精确合并、外部 UUID 引用、无损帧装配、输出不覆盖、包依赖/哈希和 MCP 响应 ID。
- Node：9 项矩阵比较断言通过；上下文、时间、模式、元素和矩阵无效时拒绝比较，显式容差和真实差异分别报告。
- 运行中的 Blockbench 5.2.2 / MCP 1.10.1：只用临时自制 cuboid 项目验证实时快照、离屏截图、负尺寸单面描边、Edit/第三人称右手 Display 的真实矩阵、300 次手动采样后的循环回位，以及定时播放/停止/dispose。源可编辑数据未改变。测试后关闭临时项目、恢复原项目，比较其编译数据一致。
- 两个相邻不透明 cuboid 合并为一个后，在完整取景的正面和斜视各 384×384 样本上像素差为 0。仅证明这两个样本；早期过度放大的裁切视图曾有 2 像素差，不能用裁切样本认证全模型。优化器仍输出候选，不自动接受或覆盖。
- 原生 codec 重开后自定义根映射确实丢失；sidecar 流程已在实际重开/编译数据上复测，缺映射拒绝，提供映射时保持原 shell UUID 和 3 个组件。
- MCP 离屏清理的已知警告、控制监听器的验证边界见 [接入与恢复](mcp-setup.md)。未启动 Minecraft 客户端或服务端；未测游戏 FPS、26.3 格式、复杂凹形自动描边、任意骨骼或合批驱动。
