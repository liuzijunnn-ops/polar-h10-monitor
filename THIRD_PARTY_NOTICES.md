# Third-party notices / 第三方来源说明

## 本项目的许可

Copyright (c) 2026 liuzijunnn-ops and contributors.

Polar H10 Monitor 的整体应用以 GNU General Public License version 3（SPDX: `GPL-3.0-only`）发布，完整文本见 [LICENSE](LICENSE)。第三方组件继续使用各自许可证。选择 GPLv3 是为了与开源版 PyQt6 的 GPLv3 许可兼容；本说明不声称持有 Riverbank 商业许可证。

## polar-python

- 作者 / 版权所有者：Zachary Liu（GitHub: zHElEARN）。
- 仓库：https://github.com/zHElEARN/polar-python
- 许可：MIT；原文见 [licenses/polar-python-MIT.txt](licenses/polar-python-MIT.txt)。
- 关系：早期版本直接依赖该包；当前运行依赖已经移除。`polar_ble.py` 的 PMD 常量、模型、帧解析与差分解码参考并改编了该项目相关实现；本地 BLE 连接、Windows 配对重试和标准 HR 标志处理由本项目集成调整。
- 本次核对版本：[`e5129c0bfa789044b29e8e1f1ba186912b23bf3a`](https://github.com/zHElEARN/polar-python/tree/e5129c0bfa789044b29e8e1f1ba186912b23bf3a)，核对日期 2026-10-19。该版本用于来源与许可核对，不声称是最初开发时使用的精确版本。

## polar-display

- 作者 / 版权所有者：Zachary Liu（GitHub: zHElEARN）。
- 仓库：https://github.com/zHElEARN/polar-display
- 许可：MIT；原文见 [licenses/polar-display-MIT.txt](licenses/polar-display-MIT.txt)。
- 关系：实时 ECG / ACC 展示、按会话录制和目录组织的参考。上游使用 WebSocket / 网页，本项目使用 PyQt6 桌面界面；当前没有包含其 Web 前端或 WebSocket 服务代码。
- 本次核对版本：[`7832c4869a2ff2a71acfa6487db30d435e92ecfc`](https://github.com/zHElEARN/polar-display/tree/7832c4869a2ff2a71acfa6487db30d435e92ecfc)，核对日期 2026-10-19。同样不据此推断最初参考版本。

以上两个上游的 MIT 原文均保留 `Copyright (c) 2024 Zachary Liu`。我们保留两份对应通知，以明确各自项目来源。

## 运行与构建依赖

| 组件 | 用途 | 许可 / 官方来源 |
| --- | --- | --- |
| Bleak | BLE 扫描、GATT 连接 | MIT；https://github.com/hbldh/bleak |
| NumPy | 数组与 NumPy 文件导出 | BSD-3-Clause；https://github.com/numpy/numpy |
| SciPy | Welch 频谱 | BSD-3-Clause；https://github.com/scipy/scipy |
| PyQt6 | Qt 桌面界面 | GPLv3 / 商业双许可，此项目使用 GPLv3；https://www.riverbankcomputing.com/software/pyqt/ |
| Qt | PyQt6 依赖的界面运行库 | 按所安装模块的 LGPL/GPL/商业许可及随包第三方通知；https://www.qt.io/licensing/open-source-lgpl-obligations |
| pyqtgraph | 波形绘制 | MIT；https://github.com/pyqtgraph/pyqtgraph |
| PyInstaller | 构建工具 | GPL-2.0-or-later，附打包例外；https://pyinstaller.org/en/stable/license.html |

实际版本及完整许可以安装的发行包为准。构建前的 `scripts/collect_licenses.py` 收集当前 Python 环境中发行包提供的许可证文件与元数据，随可执行程序放入 `dependency-licenses/`，其中 `INDEX.json` 记录包版本与来源信息。该清单包含构建环境中的工具包，不表示每个包都被可执行程序使用。PyInstaller 的 Qt hooks 负责随包 Qt 资源；分发者仍需检查实际打包结果中的 Qt 许可与第三方通知，保留依赖要求的完整文本。

## 品牌

Polar、H10 等名称仅用于说明设备兼容目标。本项目不是 Polar 官方软件，也不声称上游项目作者为本项目提供背书。
