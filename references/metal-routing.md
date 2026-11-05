# 金属线宽、焊盘靠近与短线扇出

用于新增或修改加热器馈线、移动焊盘、缩短既有金属走线；以用户当前接受的 GDS 为基线，不回放旧脚本覆盖后续光路或器件调整。

## 本用户当前布线约定

- 除非本次另有明确要求，外部金属主线与支线采用 20 μm；已明确保留的公共母线维持原线宽。固定 PDK 电极不随外部线宽要求改写。
- 采用 Diagonal 连接约束：金属主线路径中心线使用水平、垂直或 45° 斜线。编辑器对应 `Connections = Diagonal`、`Movements = Diagonal`；`edit-connect-angle-mode` 与 `edit-move-angle-mode` 的值均为 `diagonal`。GDS 本身不存储这些编辑器选项，路径角度验收与界面设置确认分开报告，不因几何正确就声称界面已设置。
- 焊盘 M2 金属到输出 EC/GC 最近物理边缘的水平净距至少 2.1 mm。使用真实物理边界，不以焊盘中心、开窗或端口坐标代替；右侧输出以其最近左边缘约束焊盘最右边缘。
- 暂不添加焊盘编号或可见标签；焊盘—电极对应关系写入属性或 CSV，保留器件端口元数据。

## 缩短引线

- 用户要求焊盘下移或靠近电极时，先保留指定的焊盘尺寸、排数、最小节距、控制顺序和网络分组。在允许调整横向位置时，优先让焊盘对齐各自电极的逃逸列；受输出退让约束的末端焊盘再按顺序收拢，减少为汇聚到中央而产生的长斜线。用户锁定的坐标和节距不得擅自变动。
- 依据电极、深槽和相邻金属的真实几何选择最小可用逃逸距离与扇出高度，避免保留没有用途的长垂直段或额外折返。在空闲区域用直线或一个 45° 过渡连接，不为视觉整齐添加迂回；按顺序扇出仍须验证实际跨网间距。
- 焊盘金属与开窗同步移动，重新连接至焊盘金属内部，保留正面积接触；导线在焊盘内延伸不必到中心。比较修改前后线长时采用一致端点，例如电极接触点到首次进入焊盘金属边缘，剔除焊盘内冗余线段；报告总长、缩短比例及是否每路均缩短，不把可行改进称作全局最优。

## 电极接入口与验收

- 加宽前先核对电极附近可用通道。若固定电极或深槽净距容不下主线宽度，只在必要的短距离保留匹配电极的窄接头，并在避让区外渐变到目标宽度；不得修改官方固定器件或降低 DRC 阈值。明确报告颈缩宽度和长度，不能把含窄接头的版本宣称为全程等宽。
- 短渐变后、转角前留足目标线宽需要的直段，检查接头与弯角的实体轮廓，避免形成小于金属间距要求的凹口。渐变边缘的角度与主线路径中心线约束分别处理。
- 从实际 M1 支路、M2 连通区域和焊盘开窗验收：每个控制端接到指定焊盘，同一加热器两端不同网，共地只按明确分组连接；原本未引出的支路保持原状态。对电极和焊盘检查正面积接触，不以包围框重合或网名代替导通。
- 另存递增版本，在完整 KLayout 环境中重读，核对线宽、路径角度、网络映射和非目标实例；光路、固定电极、深槽及 PCell 参数须按任务保护。修改金属后运行当前启用的原生 PDK DRC，自定义几何检查只作补充，已有违规与新增违规分别报告。

## 可复用脚本

`scripts/compact_metal_pads.py` 在完整 KLayout 中导入，依赖 `pya`，不绑定项目路径、cell 名、焊盘数量或 20 μm 固定值；不自动加载/保存 GDS，也不修改编辑器选项或 PDK。所有长度和坐标均为整数 DBU，返回的长度统计也为 DBU。

适用范围是同一坐标系内的一排同尺寸矩形金属焊盘及一一对应的独立馈线。原 Path 必须以竖直线进入焊盘，首点为保留的主线接入口，选定逃逸点与首点等 Y；两个容器和验收 root 的坐标系须由调用者确认。共地多端网络、阵列实例、非矩形焊盘或多排布局需先明确分组，不能静默套用。

- `collect_routes(...)`：从明确选择的金属 cell 和焊盘容器中收集 Path/实例，按线宽、可选网名白名单和 `expected_count` 验证目标；检查真实金属接触，拒绝重复网名、共享或歧义焊盘。`escape_index` 明确指定原 Path 的逃逸点；`fixed_lengths` 可传入不变颈缩/渐变段的中心线长度。
- `plan_compaction(...)`：在最小节距和可选左右金属边缘限制下保序就近拟合焊盘位置，使用水平、垂直、45° 路径；`fanout_y`、`pad_margin` 由实际避让空间确定，不会自动放宽 DRC。支持指定 `pad_center_y`，空间不够时拒绝；`direction=-1` 支持下侧镜像扇出。规划不改版图，不承诺全局最短线长。
- `apply_plan(plan)`：先确认所有目标未被并发修改，再仅更改选定主线和焊盘平移；保留线宽、属性、固定接头及焊盘自身几何。
- `check_pad_connections(...)`：从实际 M2 区域验证各选定起点到指定焊盘的连通、各网不同及开窗覆盖。可用 `terminal_regions` 提供真实电极区域；缺省只检验主线首点。完整 M1 支路/备用电极检查和原生 PDK DRC 仍由主脚本执行。

主脚本加载 PDK 和当前 GDS、确认目标 cell/网名及工艺净空后，可按下面方式调用。示例中的 cell 对象、基线、边缘和节距均来自本次实际测量，不是通用坐标：

```python
from compact_metal_pads import (
    collect_routes, plan_compaction, apply_plan, check_pad_connections,
)

def u(value_um):
    return round(value_um / layout.dbu)

routes = collect_routes(
    layout, selected_metal_cell, selected_pad_container,
    wire_width=u(20), expected_count=selected_count,
    net_ids=selected_net_ids, escape_index=1,
    fixed_lengths=unchanged_neck_and_taper_lengths,
)
plan = plan_compaction(
    routes, fanout_y=measured_fanout_baseline,
    pad_pitch=required_pitch, pad_margin=required_pad_margin,
    pad_overlap=u(10),
    pad_right_limit=output_physical_left_edge-u(2100),
)
apply_plan(plan)
checks = check_pad_connections(
    layout, common_coordinate_root, plan,
    terminal_regions=actual_electrode_regions_by_net,
)
# 继续运行非目标/PCell 不变量、原生重读与原生 PDK DRC，通过后另存版本。
```

验证记录：该工具在完整 KLayout 中从已接受的输入逐 cell 精确重现已验收的焊盘压缩结果，并通过独立重读、实际电极网络和原生 PDK DRC；另用不同 DBU、线宽及焊盘尺寸的上下两侧案例验证配置独立性，检查不可行边界与过期计划会在改动前被拒绝。
