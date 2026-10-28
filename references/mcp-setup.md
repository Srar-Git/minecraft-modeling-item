# MCP 接入与恢复

## 先发现现有安装

优先用已连接的 Blockbench MCP 调 `get_capabilities(include_tools=true)`、`get_project_info`。记录编辑器、插件版本/build_id、当前项目 UUID/格式和模式。不打开新项目也能探测能力。不要把仓库 package.json 当作运行中插件版本。

本地历史：2026-08 安装服务为 1.6.1；旧源码 package.json 为 1.6.0；2026-10-27 只读复核运行环境为 Blockbench 5.2.2 / MCP 1.10.1。这些是证据日期，不是要求安装的全局最新版。

## 没有安装时

1. 使用桌面版 Blockbench。官方插件项目安装说明提供 File → Plugins → Load Plugin from URL，地址为 `https://jasonjgardner.github.io/blockbench-mcp-plugin/mcp.js`；安装前核对 [插件项目](https://github.com/jasonjgardner/blockbench-mcp-plugin) 的当前说明与来源。不要用旧 Hytale 技能的商店菜单步骤推断当前发行方式。
2. 若用户指定本地源码，先查实际 AGENTS/README/package scripts，再构建并加载产物，记录版本和哈希。不要用旧源码静默降级一个工作的运行实例。安装或替换前保存项目并保留旧插件的恢复路径。
3. Blockbench 设置中的 MCP Server Port / Endpoint 决定监听位置；常见默认是 `http://localhost:3000/bb-mcp`。先检查端口占用与插件日志，不能结束无关服务。远程 Codex 的 localhost 指的是它自己的主机，不能假定指向用户桌面。
4. Codex 使用当前作用域的配置，保留其他条目。示例只展示需要合并的部分：

```toml
[mcp_servers.blockbench]
url = "http://localhost:3000/bb-mcp"
```

标准用户目录为 `~/.codex/config.toml`，也可有项目作用域配置；有自定义 Codex home 时按实际环境定位。[官方 MCP 配置](https://learn.chatgpt.com/docs/extend/mcp#configure-with-configtoml)。本技能不改认证或工具审批设置。

5. 让工具目录刷新后先做只读调用，确认服务版本与项目。只有明确需要创建模型时才新建项目。MCP 配置安装成功不等于 Hytale/GeckoLib 等格式插件也已安装。

## 排错顺序

|表现|检查与处理|
|---|---|
|Connection refused|应用/插件是否运行、实际端口、主机归属；不要先重装|
|404|端点是否一致；不是所有服务器都叫 `/mcp`|
|初始化/会话错误|initialize → initialized 通知 → 工具调用，保留会话与协议头；不要拿普通 GET 页面当握手测试|
|工具名不见了|刷新 tools/list；检查模式、项目格式和版本，不调用历史假想名称|
|工具存在但 disabled|读 list_modes 和 capabilities；在任务需要时切换模式后重试|
|无当前项目|连接可能正常；不是重启理由|
|截图输出过大|使用 `capture_screenshot(max_size=...)` 或离屏尺寸；大批图片写磁盘，只展示必要局部|
|透明、发光或动画不对|先分辨编辑预览与游戏格式，再查材质/驱动，不把问题都归因 MCP|

备用 `bb_doctor.py` 是 loopback HTTP 的只读诊断。Python 标准库即可完成协议通信；整个工具集因复用审计模块需 Pillow。它支持 JSON 与有限 SSE 响应、会话关闭、超时和大小限制，不支持远程、OAuth、无限 SSE 流或带认证头连接。此类连接继续使用已有 MCP 工具，不复制凭据进脚本。

不强制安装 ImageMagick；当前 MCP 原生有缩略截图和离屏视图。旧 `bb_screenshot.py` 只作历史参考，不是必需依赖。

## 已复现的版本差异（2026-10-27）

- Blockbench 5.2.2 / MCP 1.10.1 的 `delete_offscreen_view` 可在已删除视图和释放 renderer 后，于 controls.dispose 报 `onContextMenu is not defined`。`bb_capture.py` 只针对这个具体错误再查 `list_views` 和 `Preview.all`；两处都无本次视图才保留截图并写 `cleanup_warning`。它不证明所有 controls listener 已释放，不修改共享全局函数；其他错误仍失败。持续报错应检查后续官方修复，不静默改插件。
- 当前 `risky_eval` 输入校验拒绝包含注释或 `console.` 的代码。发送无注释代码并返回结构化数据；配套预览文件已符合这一约束。
- 自定义 bbmodel 根字段可能在 codec 重开/保存后丢失。映射、生成配置和自定义预览需要独立文件或明确注册的插件属性；不能只验证离线 JSON 连续执行。
