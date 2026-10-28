# 配套工具操作

所有命令中的 `SKILL` 是已定位的技能绝对目录。Python 3.10+、Pillow；Node.js 用于矩阵对照。不要在未知全局 Python 上擅自升级依赖；缺少 Pillow 时使用任务虚拟环境。无需 NumPy、ImageMagick 或额外 Node 包。

## 工具边界

|工具|读/写范围|运行方式|
|---|---|---|
|bb_doctor.py|读取 loopback MCP，输出诊断，可写新报告|Python CLI|
|bb_snapshot.py|编译当前工程，写新目录；不保存覆盖当前项目|Python CLI + MCP risky_eval|
|bb_capture.py|创建/销毁离屏相机，写新截图目录；不驱动时间/切 Display|Python CLI + MCP 原生工具|
|audit_model.py / audit_cost.py|读工程/实际导出，写报告|Python CLI|
|outline_builder.py|读取模型/spec，写新 bbmodel|Python CLI，导入后是普通可编辑元素|
|optimize_model.py|读取明确静态范围，写候选及报告|Python CLI，拒绝未知动画|
|texture_tools.py|读取自有色板/图块/帧，写新目录|Python CLI，不改模型 UV|
|preview_runtime.js|临时修改指定 Cube 的渲染矩阵，可恢复|在 Blockbench 中载入；不是 Node 或游戏脚本|
|validate_motion.js|读取实际采样的矩阵 JSON，比较并可写新报告|Node CLI|
|package_model.py|读取显式文件清单，写新 staging 包和 ZIP|Python CLI，不生成模型动画|

新增文件工具不覆盖现有输出；重新生成使用新路径。既有 `audit_model.py` / `compare_renders.py` 可覆盖指定报告文件，所以报告必须放在专用工作目录，不能指向资产。修改实时模型优先原生 MCP 可撤销工具；离线候选先预检，再用新标签打开，对照通过后再替换正式文件。

## 环境、快照和截图

```sh
python3 "$SKILL/scripts/bb_doctor.py" --output work/doctor.json
python3 "$SKILL/scripts/bb_snapshot.py" --project-id ACTUAL_PROJECT_UUID --output work/baseline
python3 "$SKILL/scripts/bb_capture.py" work/cameras.json --output work/before
```

三个工具可用 `--url` 指定实际 loopback 端点。UUID 来自实时 `get_capabilities`，不能使用历史名称替代。快照内含 `project.bbmodel` 和哈希清单；不会复制粒子、音频等外部依赖。它经过当前 codec 编译，不能保全未注册的自定义根字段或运行中全局变量；原文件、预览脚本及映射 sidecar 同时保留。

`cameras.json` 示例；替换真实 UUID，按模型范围设置 target/距离：

```json
{"project_id":"ACTUAL_PROJECT_UUID","width":768,"height":768,"pose_label":"manual t=0, frozen","views":[
  {"name":"front","position":[0,8,40],"target":[0,8,0],"projection":"orthographic","zoom":1},
  {"name":"oblique","position":[28,20,30],"target":[0,8,0],"projection":"perspective","fov":45}
]}
```

调用前暂停所有动画并明确保持的时刻。`pose_label` 是记录，不是时间锁；工具不自动控制未知预览插件。当前模式/灯光继承编辑器。输出同时记录请求与实际应用的相机；先看图确认完整取景，再做像素比较。过大的 zoom 会裁掉模型，不能把裁切图片当完整外观证据。需要 Display 的实际持握参考时，用原生 `enter_display_mode`/`get_display_transform`/`set_camera_angle` 并记录设置，不能宣称离屏普通模型视图等于真实手持场景。

## 成本预算与结构检查

```sh
python3 "$SKILL/scripts/audit_model.py" work/model.bbmodel --profile java-26.1 --output work/structure.json
python3 "$SKILL/scripts/audit_cost.py" work/model.bbmodel --profile java-26.1 --plan work/cost-plan.json --output work/cost.json
python3 "$SKILL/scripts/compare_renders.py" work/before work/after --strict --background 32,39,49 --output work/diff.json
```

成本计划示例：

```json
{"budgets":{"components":150,"declared_faces":700,"texture_pixels":65536,"estimated_baked_components":500},"lanes":[
  {"name":"core motion","element_ids":["CORE_UUID","SHELL_UUID"],"frames":16}
]}
```

预算数是该例的工程选择，不是技能默认上限。`lanes` 必须描述输入中的单套模板，成员互斥；不把已经展开的帧重新计为模板。它估算朴素展开量，不解析未知驱动。`within_declared_budgets=null` 表示没有预算，不能理解为通过。预算超限/结构错误退出码非零。

## 描边候选

先创建独立的单色描边材质，设置为 front-only；不要让脚本改变主体共用材质。spec：

```json
{"element_ids":["CORE_UUID"],"texture_uuid":"OUTLINE_TEXTURE_UUID","uv":[1,1,3,3],"thickness":0.15,"layer":"outer","light_emission":15}
```

```sh
python3 "$SKILL/scripts/outline_builder.py" work/source.bbmodel work/outline.json --output work/outlined.bbmodel
```

支持正尺寸、无 inflate/rescale 的 Java cuboid，继承 origin/rotation 和直接父组，生成普通负尺寸壳。`uv` 必须采样均匀色块；脚本检查边界但不证明其颜色或主体遮挡。正面纹理面与顶底面统一采样，不能用于自动复刻渐变。

工具同时输出 `候选.bbmodel.outline-map.json`，记录 `sourceUUID:layer → shellUUID`，必须作为工程依赖保留。文件内也写入 `minecraft_item_outline_v1`，但 Blockbench 5.2.2 实测会在重开/保存时丢弃该自定义根字段；因此经过编辑器后更新必须显式传 `--mapping 原候选.bbmodel.outline-map.json`。同一 layer 使用相同 shell UUID 更新。若缺映射且检测到描边命名则拒绝；这只是丢失提示，不能识别任意改名后的壳。不能因名称检测没有命中就省掉 sidecar。映射冲突、壳被移动/删除时拒绝，不盲目重建。自定义动画成员由调用方将新增 shell UUID 加到同一轨道；脚本不猜骨骼/运动协议。

## 保守优化候选

```json
{"static_scope":true,"element_ids":["BODY_A_UUID","BODY_B_UUID"],"merge_uniform":true,"remove_empty":true}
```

```sh
python3 "$SKILL/scripts/optimize_model.py" work/source.bbmodel work/optimize.json --output work/optimized.bbmodel
```

只有调用者明确确认选区没有动画或自定义语义依赖才可声明静态；未知项目字段不能由名字自动证明无运动。仅处理声明静态、同直接父组、未旋转、无 inflate/rescale、六面均为静态内嵌不透明贴图的 cuboid；最多 1200 个选定元素。全项目有已知动画/自定义运行数据时拒绝。被剔除的面从冻结源几何计算；薄片、负尺寸、透明贴图和其他不支持对象跳过并列明。

精确合并只支持竖向相邻、相同截面与其余属性、侧面 UV 一致且采样纯色的组件；不支持容差合并、图案 UV 重接或任意轴向并集。删除 UUID 有其他引用时拒绝。报告保存为 `候选.bbmodel.report.json`。这一工具不会复刻旧冰斧的有损切片重构；后者需专门候选与视觉验收。

## 纹理装配

```sh
python3 "$SKILL/scripts/texture_tools.py" work/texture-spec.json --output work/texture-result
```

三类 spec：

```json
{"mode":"palette","cell":4,"columns":4,"colors":{"metal":"#596677","highlight":"#ccddeb","energy":"#69e9ff"}}
```

```json
{"mode":"atlas","width":128,"padding":2,"files":["tiles/metal.png","tiles/rune.png"]}
```

```json
{"mode":"frames","files":["frames/0.png","frames/1.png"],"timeline":[{"index":0,"time":2},{"index":1,"time":1},{"index":0,"time":1}]}
```

输入图路径相对于 spec 所在目录，不能越界。atlas 只做完整图块、相同 RGBA 内容去重和无损排布，输出像素矩形；不自动裁原图、重采样或修改模型 UV。padding 为透明边距，不自动扩边；需要 mipmap/采样扩边时另做候选验证。frames 要求同尺寸，精确去重后保留原时间顺序和停留时间，生成 PNG 与 mcmeta。

这些工具用于确定性资产装配，不替代图像生成/编辑工具进行艺术重绘。16/32px 是制作起点，不能把现有大图直接缩小称作无损。

## 临时刚性预览与矩阵验证

先停止控制相同元素的旧驱动。读取 `assets/preview_runtime.js`，通过 `risky_eval` 执行文件内容；它只注册 factory，没有自动创建定时器。当前 MCP 会拒绝含注释或 `console.` 的代码，发送示例时不要添加注释。需要结构化回执可在文件内容后追加 `({loaded:true})`。再创建实例：

```js
globalThis.itemPreview = MinecraftItemPreviewFactory.create({
  project_id: Project.uuid,
  tracks: [{kind:'rotate',element_ids:['CORE_UUID','SHELL_UUID'],axis:[0,0,1],pivot:[8,16,8],period:2,amplitude:15,offset:0,phase:0}]
});
itemPreview.pose(0.5);
```

上例手动固定姿态，适合截图；播放调用 `itemPreview.start()`，停止恢复调用 `itemPreview.stop()`；完成或失败时执行 `itemPreview.dispose(); delete globalThis.itemPreview`。dispose 后实例不能重启，需要重新创建。

每帧从基准 model-space 矩阵计算，转换回实际父节点局部空间。模型数据不改写。选中元素、切出支持模式、切项目时播放停止；Undo 索引变化时停止并要求重建基线。模式切换重新绑定。它不自动导出、不驱动 PNG、没有通用 easing/mesh 合批；大模型的预览合批仍需按 [性能方法论](performance-methodology.md) 的材质/相位约束做专门实现。

`pose(time)` 返回实际渲染矩阵样本。在固定显示上下文记录：

```js
({context:{project:Project.uuid,slot:'edit',space:'model'},samples:[0,0.5,1,2].map(t=>itemPreview.pose(t))})
```

将基线与候选的返回值存成 JSON：

```sh
node "$SKILL/scripts/validate_motion.js" work/motion-before.json work/motion-after.json 0 work/motion-diff.json
```

默认容差 0；采用浮点容差时说明来源。周期检查可比较 `pose(t)` 与多轮后的同相位矩阵，但匹配标签应由采样脚本明确归一到同一相位，并另外保存真实采样时刻。矩阵通过不意味着 UV、颜色、形变顶点或游戏动画通过。

## 资源包交付

打包前用当前工程重新执行目标导出器。准备显式清单：

```json
{"profile":"java-26.1","pack_format":84,"verified_external_resources":[],"files":[
  {"path":"pack.mcmeta","sha256":"ACTUAL_FILE_SHA256"},
  {"path":"assets/example/models/item/weapon.json","sha256":"ACTUAL_FILE_SHA256"},
  {"path":"assets/example/textures/item/weapon.png","sha256":"ACTUAL_FILE_SHA256"}
]}
```

```sh
python3 "$SKILL/scripts/package_model.py" work/package.json --root work/export --output work/delivery
```

生成 `pack/`、`resourcepack.zip` 和报告。实际文件哈希必须匹配清单，防止过期或装错。模型 parent/texture 依赖与物品定义的 model 叶子引用需能解析；合法外部依赖先核对来源后逐条加入清单，不能批量忽略所有 minecraft 命名空间。mcmeta、物品条件/动画驱动等仍需要版本与客户端验证。它不是完整资源包 schema 认证器。

## 维护自检

```sh
python3 "$SKILL/scripts/selftest.py"
python3 "$SKILL/scripts/test_workflow.py"
node "$SKILL/scripts/test_motion.js"
```

测试使用临时目录和自制几何，不读取私人历史资产。运行中 Blockbench 的烟测是独立可选步骤，先快照用户现场，使用临时项目，最后恢复；不要让测试覆盖真实成品或启动 Minecraft。
