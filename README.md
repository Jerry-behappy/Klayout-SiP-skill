# KLayout SiP Skill

## 中文说明

klayout-sip-skill 是一个面向硅光版图的 Codex skill。它支持在 KLayout 中安全地完成 GDS/OASIS 版图的设计、检查、修复、布线、标注、层级分析与验证，适用于使用 PCell、固定库器件或扁平化几何的硅光版图。

### 支持内容

- GDS/OASIS 的 cell、层级、图层、实例、阵列、端口和标记。
- PCell、固定库实例、波导、螺旋线、光栅耦合器和 Basic.Text 文字。
- 几何提取、实例替换、布线与版图标注。
- 安全的另存修改，或经用户明确要求后的原位覆盖修改。
- 使用 KLayout 批处理进行层级与几何验证。

### 职责边界

本 skill 用于使用和编辑硅光版图，不修改 PDK 源码、库注册、技术文件或封装实现。只有用户明确要求 PDK 开发时，才进入相应的 PDK 开发流程。

### 前置条件

- 已安装完整 KLayout，并使用已安装的 klayout_app.exe 批处理运行时验证版图输出。
- KLayout 可以访问当前项目所需的技术文件与版图库。
- 已明确源版图、目标对象和输出策略。默认另存；原位覆盖必须获得用户明确授权。

### 工作流程

1. 修改前检查源版图的 DBU、顶层 cell、图层、层级、PCell 和库状态、目标实例及端口。
2. 明确目标集合，并按任务记录父级关系、变换、阵列、关键几何和边界框；哈希仅在有明确需要时使用。
3. 先在同目录写入临时版图。
4. 使用完整 KLayout 运行时重新读取输出，验证目标对象与保留不变量。
5. 验证通过后再另存或替换原文件，并报告目标数量、输出路径、映射关系与重读结果。

### 仓库结构

- SKILL.md：权威工作流和按需读取说明。
- references/：通用版图约定、编辑流程、层级与选择指导，以及验证要求。
- references/routing-and-matching.md：复合波导容量、分宽度等长、弯曲数和阵列压缩。
- references/connection-repair.md：光电连接修复、回形针补偿与严格等长验收。
- scripts/inspect_layout.py：批处理版图检查脚本。
- scripts/compact_sbend_bundle.py：以 JSON job 缩短 S 弯阵列，严格检查 PDK 最小曲率半径并重连公共端。
- scripts/layout_checks.py：可复用的实例/图形比较、光端口连续性和硅层相交验收。
- references/sbend-bundles.md：S 弯压缩配置，以及 taper 等 Y 间距和 MMI 居中的口径。
- scripts/sync_skill_links.py：创建并检查指向本规范目录的 Codex 与 Claude skill 目录链接。
- agents/openai.yaml：agent 元数据。

### 维护本地 Skill 入口

修改 skill 后，在当前目录运行：

~~~powershell
python scripts/sync_skill_links.py sync
python scripts/sync_skill_links.py check
~~~

同步脚本会创建并验证固定的 klayout-sip-skill Codex 与 Claude 入口。

---

## English

klayout-sip-skill is a Codex skill for safe silicon-photonic layout work in KLayout. It covers design, inspection, repair, routing, annotation, hierarchy analysis, and verification for GDS and OASIS layouts using PCells, fixed-library devices, or flattened geometry.

### What It Handles

- GDS/OASIS cells, hierarchy, layers, instances, arrays, ports, and markers.
- PCells, fixed-library instances, waveguides, spirals, grating couplers, and Basic.Text labels.
- Geometry extraction, instance replacement, routing, and layout annotation.
- Safe copy-on-write or explicitly requested in-place layout modification.
- KLayout batch verification, including hierarchy and geometry checks.

### Scope

This skill consumes and edits silicon-photonic layouts. It does not change PDK source, library registration, technology files, or package implementation unless the user explicitly requests PDK development.

### Requirements

- A full KLayout installation. Use the installed klayout_app.exe batch runtime to verify layout output.
- The technology files and layout libraries required by the current project.
- A source layout, clearly defined target objects, and an output strategy. Saving to a new file is the default; in-place replacement needs explicit user approval.

### Working Model

1. Inspect the source layout before changing it: DBU, top cells, layers, hierarchy, PCell and library state, target instances, and ports.
2. Define the target set and relevant invariants: parent relationships, transforms, arrays, key geometry and bounding boxes. Use hashes only when explicitly needed.
3. Write modifications to a temporary layout in the same directory.
4. Reload the output with the full KLayout runtime and verify the requested targets and preserved invariants.
5. Only then save the result or replace the original file. Report the target count, output path, mappings, and reload result.

### Repository Layout

- SKILL.md: the authoritative workflow and routing instructions.
- references/: layout conventions, editing procedures, hierarchy and selection guidance, and verification requirements.
- references/routing-and-matching.md: composite-waveguide capacity, length matching by width, bend counts, and array compaction.
- references/connection-repair.md: optical and electrical connection repair, paperclip compensation, and strict length verification.
- scripts/inspect_layout.py: batch layout inspection helper.
- scripts/compact_sbend_bundle.py: JSON-configured S-bend bundle compaction with strict PDK minimum-radius checks and common-port reconnection.
- scripts/layout_checks.py: reusable instance/shape comparisons, optical continuity, and Si-intersection checks.
- references/sbend-bundles.md: compaction job configuration, taper Y pitch, and MMI centering conventions.
- scripts/sync_skill_links.py: creates and validates the Codex and Claude directory links that point to this canonical skill folder.
- agents/openai.yaml: agent metadata.

### Maintaining Local Skill Entries

Run the following commands from this directory after changing the skill:

~~~powershell
python scripts/sync_skill_links.py sync
python scripts/sync_skill_links.py check
~~~

The sync script creates and verifies the fixed klayout-sip-skill entries for Codex and Claude.
