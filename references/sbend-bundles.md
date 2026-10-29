# MMI、taper 与 S 弯阵列

用于压缩器件与 taper 阵列之间的 S 弯横向距离，同时保留各路纵向偏移、器件方向和外围连接。不把某个项目的器件数量、坐标、间距或半径固定为默认设计要求。

## 几何口径

- 分清移相器行距、taper 行距、MMI 端口 pitch 和波导长度。用户将“等长”更正为“等 Y 间距”时，应改变阵列位置约束，不启动等长补偿。
- taper 的等 Y 间距按实际光口/中心线的 Y 坐标计算；器件的 Y 中心与 `(y_min + y_max) / 2` 对齐。不要用 S 弯包围框中心代替 taper 阵列中心，也不要默认实例原点就是器件中心。
- 保留某一通道为直线、固定移相器行距、固定欧拉半径、固定 taper 行距可能相互约束。先检查完整弯曲的切入长度；容量不足时重新选允许改变的间距或位置，不暗中减小半径，也不只移动一只 taper 后仍称阵列等距。
- 500 nm 引出 S 弯与 2 µm 长走线分开处理。用户指定宽波导用欧拉转角时，不能将宽波导换成 Bezier S 弯；窄引出段可以独立使用其既有 S 弯参数。
- 缩短 S 弯时保留 `height`、`width`、`bend_type`、`bezier`，让 PDK `coerce_parameters` 重算曲率和采样数。约束 `Rmin > R_limit` 应使用未四舍五入的派生值；直线的显示半径可能为 0，应按无曲率处理。
- 器件沿 X 移动后，其公共端短引线、端部 taper 和长波导起点也要重连。共享 PCell 不直接修改几何，只创建新 variant 或改变选定实例的变换。

## 可复用脚本

`scripts/compact_sbend_bundle.py` 在完整 KLayout 环境读取 JSON job：

```powershell
& 'D:\KLayout\klayout_app.exe' -b -r '<skill>\scripts\compact_sbend_bundle.py' -rd 'job_file=<absolute-path-to-job.json>'
```

适用于 JNU 的 `JNULib/Pcell_S_Bend` Bezier variant。支持单位缩放、水平旋转/镜像的阵列；不支持垂直阵列、任意角度、其它 S 弯实现或自动识别无明确选择信息的器件。所有原文件路径、库加载路径和实例坐标由 job 提供。

Job 示意如下；名称、坐标、数量必须替换为当前 GDS 的实际值：

```json
{
  "input_file": "D:/layouts/input.gds",
  "output_file": "D:/layouts/compact.gds",
  "report_file": "D:/layouts/compact-report.json",
  "python_paths": ["D:/PDK/pymacros"],
  "parent_cell": "ASSEMBLY",
  "new_span_um": 60.0,
  "minimum_radius_um": 20.0,
  "groups": [{
    "id": "bank_A",
    "sbends": {"property": 125, "regex": "A[0-9]+_sbend", "expected_count": 4},
    "translate": [
      {"cell_name": "MMI_1xN", "origin_um": [1000.0, 0.0], "expected_count": 1},
      {"property": 125, "equals": "A_common_lead", "expected_count": 1},
      {"cell_name": "TAPER", "origin_um": [1100.0, 0.0], "expected_count": 1}
    ],
    "reconnect": [{
      "selector": {"property": 125, "equals": "A_output_route", "expected_count": 1},
      "point_indices": [0]
    }]
  }]
}
```

- `sbends` 选择同一方向、相同原横向长度的 S 弯；每条的起点固定，长度改为 `new_span_um`。按其真实变换计算器件需要平移的 X 距离，因此镜像两侧可用同一配置结构。
- `translate` 精确选择随器件一起平移的实例。每个 selector 必须有 `expected_count`；重复/重叠选择直接失败。
- `reconnect` 选择单宽 `Waveguide`，将指定的原始 Manhattan Path 控制点沿同一 X 距离移动，再用 PDK 正式入口创建本地 PCell。脚本拒绝对角段和放不下既有转弯半径的路径。
- 可选 `library_name`、`sbend_pcell`、`bootstrap_module` 默认分别为 `JNULib`、`Pcell_S_Bend`、`JNULib`。`si_layer`、`pin_layer` 默认 `[1,0]`、`[1,10]`，需要时在 job 中修改。
- 选择作用于 `parent_cell` 的直接子实例。若该父 cell 被多处引用，应先确认修改全部引用是否符合任务；脚本不自动复制共享父级。

## 验收和失败行为

脚本先解析全部显式目标、检查数量与半径，再实施修改。半径不大于阈值、选择不明确、输出已存在等情况会拒绝写出；不会自动增加长度、改变 Bezier 参数或放宽阈值。

输出先写入同目录候选文件，再原生重读核对 S 弯参数、非目标实例多重集合、非目标 cell 内容和顶层列表。`scripts/layout_checks.py` 提供可供其它脚本导入的实例/图形比较以及 PinRec、Si 端口连续性和非预期相交检查。端口豁免只作用于相关器件对的实际连接面。

端口验收需要包含相邻光学器件的闭合装配 cell。已有合法开放端口的单体应先选择适合的父级，或为该任务单独定义验收；脚本不会静默忽略开放端口。该验收不是完整工艺 DRC。

通过后才发布为独立新文件；候选文件在失败时清理，原文件保持不变。脚本不写入 PDK 默认参数，也不生成哈希清单。
