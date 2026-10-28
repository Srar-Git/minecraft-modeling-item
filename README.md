# minecraft-modeling-item

面向 Codex 的 Minecraft 物品建模技能，使用 Blockbench MCP 制作、修正和优化武器、工具与道具，重点支持 Java 物品。

## 内容

- MCP 安装、配置、能力检查和故障排查。
- 参考拆解、三维灰模、像素上色、UV 与参数控制。
- 倒置外壳描边、发光、动画预览和修正流程。
- 低组件建模与保真优化的 8 条硬规则。
- 快照、截图、纹理装配、保守几何优化、结构审计、图像/矩阵对照和资源包打包工具。

从 [SKILL.md](SKILL.md) 开始；脚本输入、运行方式和适用边界见 [工具说明](references/tools.md)。

## 安装与调用

将本仓库放入实际 Codex 技能目录下的 `minecraft-modeling-item/`。默认用户目录示例：

```sh
git clone https://github.com/Srar-Git/minecraft-modeling-item.git ~/.codex/skills/minecraft-modeling-item
```

如果该目录已存在，先检查已有版本，不要覆盖。使用自定义 Codex home 时调整路径。技能被加载后，通过 `$minecraft-modeling-item` 调用。

文件工具需要 Python 3.10+ 和 Pillow；矩阵比较需要 Node.js。实时工具需要运行中的 Blockbench MCP，配置见 [接入说明](references/mcp-setup.md)。

## 验证

```sh
python3 scripts/selftest.py
python3 scripts/test_workflow.py
node scripts/test_motion.js
```

本版通过 33 个 Python 用例、9 项矩阵比较断言，以及 Blockbench 5.2.2 / MCP 1.10.1 临时项目实测。详细范围和已知版本问题见 [验证依据](references/sources.md)。

编辑器预览不等于游戏动画支持；编辑组件减少不等于游戏 FPS 提升。本版没有 Minecraft 客户端性能或 26.3 格式认证。复杂凹形自动描边、任意骨骼和通用预览合批不在现有脚本的自动处理范围。

历史案例只保留方法与验证边界，不包含原始聊天记录、第三方模型或游戏贴图。脚本默认输出独立候选，正式替换前须完成对应校验。
