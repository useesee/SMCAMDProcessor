#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 useesee/SMCAMDProcessor 的菜单栏添加 CPU/GPU 监控并调整内存提示框。

用法：
  cd /path/to/SMCAMDProcessor
  python3 patch_statusbar_cpu_gpu.py

可先只检查锚点和最终源码结构：
  python3 patch_statusbar_cpu_gpu.py --dry-run

本脚本仅修改 AMD Power Gadget/StatusbarController.swift；正式运行前自动备份。
不在非 macOS 环境中声称已完成 Xcode 编译或实机验证。
"""
from __future__ import annotations

from pathlib import Path
import shutil
import sys

ROOT = Path.cwd()
SOURCE_PATH = ROOT / "AMD Power Gadget" / "StatusbarController.swift"
BACKUP_PATH = SOURCE_PATH.with_suffix(SOURCE_PATH.suffix + ".before-cpu-gpu.bak")
DRY_RUN = "--dry-run" in sys.argv[1:]


def fail(message: str) -> "NoReturn":
    print("ERROR:", message, file=sys.stderr)
    raise SystemExit(1)


def anchor(source: str, needle: str, label: str) -> int:
    """校验一个锚点严格出现一次并返回偏移。"""
    count = source.count(needle)
    if count != 1:
        fail(f"功能{label}：锚点应出现 1 次，实际 {count} 次；未写入源文件。")
    print(f"anchor OK: 功能{label}")
    return source.index(needle)


def replace(source: str, old: str, new: str, label: str) -> str:
    """校验锚点后只替换一次，失败即停止。"""
    index = anchor(source, old, label)
    result = source[:index] + new + source[index + len(old):]
    if new and new not in result:
        fail(f"功能{label}：替换后校验失败。")
    print(f"check OK: 功能{label}")
    return result


def replacement(source: str, old: str, new: str, label: str) -> str:
    """与项目中补丁习惯一致的 replacement 包装。"""
    return replace(source, old, new, label)


def addition(source: str, needle: str, extra: str, label: str, *, before: bool = False) -> str:
    """校验锚点后插入代码；before=True 时插到锚点之前。"""
    index = anchor(source, needle, label)
    if before:
        result = source[:index] + extra + source[index:]
    else:
        end = index + len(needle)
        result = source[:end] + extra + source[end:]
    print(f"check OK: 功能{label}")
    return result


def replace_between(source: str, start: str, end: str, new_body: str, label: str) -> str:
    """同时校验首尾锚点，仅替换两个锚点之间的内容。"""
    start_index = anchor(source, start, label + "起点")
    end_index = anchor(source, end, label + "终点")
    if end_index <= start_index:
        fail(f"功能{label}：结束锚点出现在起点之前。")
    result = source[:start_index] + new_body.rstrip() + "\n\n" + source[end_index:]
    print(f"check OK: 功能{label}")
    return result


def apply_patch(source: str) -> str:
    if "BEGIN statusbar-cpu-gpu-tooltip patch" in source:
        fail("检测到本功能补丁标记；拒绝重复应用。若需重做，请先恢复备份并确认源码版本。")

    # 1. 增加 IOKit 导入（GPU 统计来自 IOAccelerator 的 PerformanceStatistics）。
    source = addition(
        source,
        "import Darwin.Mach\n",
        "import Darwin\nimport IOKit\n",
        "IOKit GPU 采样依赖",
    )

    # 2. 集中调整布局：功率/温度两行，间距 4 pt；内存/CPU 饼图与数值间距集中管理。
    source = replacement(
        source,
        "    static let temperatureX: CGFloat = 45\n",
        "    // 功率在上、温度在下；两行复用 CPU 频率紧凑字形。\n"
        "    static let powerTemperatureX: CGFloat = 48\n"
        "    static let powerTemperatureValueWidth: CGFloat = 26\n",
        "温度功率双行布局参数",
    )
    source = replacement(
        source,
        "    static let powerX: CGFloat = 78\n",
        "",
        "移除独立功率标签坐标",
    )
    source = replacement(
        source,
        "    static let powerValueWidth: CGFloat = 20\n"
        "    static let powerToMemoryPieGap: CGFloat = 8\n"
        "    static var memoryPieX: CGFloat {\n"
        "        powerX + metricValueOffsetX + powerValueWidth + powerToMemoryPieGap\n"
        "    }\n",
        "    static var memoryPieX: CGFloat {\n"
        "        powerTemperatureX + powerTemperatureValueWidth + 4\n"
        "    }\n",
        "温度功率到内存饼图 4pt 间距",
    )
    source = replacement(
        source,
        "    static let memoryPieToValueGap: CGFloat = 6\n",
        "    static let memoryPieToValueGap: CGFloat = 6\n"
        "    static let cpuPieSize: CGFloat = 16\n"
        "    static let cpuPieRingInset: CGFloat = 1.5\n"
        "    static let cpuPieRingWidth: CGFloat = 1.5\n"
        "    static let cpuPieToValueGap: CGFloat = 4\n",
        "CPU 饼图尺寸与间距参数",
    )
    source = replacement(
        source,
        "    static let memoryValueWidth: CGFloat = 28\n"
        "    static var itemWidth: CGFloat { memoryValueX + memoryValueWidth + 2 }\n",
        "    static let memoryValueWidth: CGFloat = 28\n"
        "    static var cpuPieX: CGFloat { memoryValueX + memoryValueWidth + 4 }\n"
        "    static var cpuValueX: CGFloat { cpuPieX + cpuPieSize + cpuPieToValueGap }\n"
        "    static let cpuValueWidth: CGFloat = 34\n"
        "    static var itemWidth: CGFloat { cpuValueX + cpuValueWidth + 2 }\n",
        "CPU 饼图与右侧双行数值布局",
    )
    source = addition(
        source,
        "    static let frequencyThreshold: Float = 3.2\n",
        "    static let cpuUsageThreshold: Double = 50.0\n"
        "    static let gpuUsageThreshold: Double = 50.0\n",
        "CPU GPU 使用率阈值",
    )
    source = addition(
        source,
        "    static let compressedColor = NSColor(calibratedRed: 0.98, green: 0.3, blue: 0.55, alpha: 1)\n",
        "    static let cpuSystemColor = NSColor(calibratedRed: 0.94, green: 0.20, blue: 0.28, alpha: 1)\n"
        "    static let cacheMemoryColor = NSColor(calibratedWhite: 0.60, alpha: 1)\n",
        "CPU 系统与缓存颜色",
    )
    source = addition(
        source,
        "// BEGIN statusbar-fan-memory patch (2026-10-22)\n",
        "// BEGIN statusbar-cpu-gpu-tooltip patch (2026-10-29)\n",
        "新功能补丁标记",
    )

    # 3. 内存快照增加文件缓存估算值；它只用于提示，不重复加入饼图总量。
    source = replacement(
        source,
        "    let compressedBytes: UInt64\n",
        "    let compressedBytes: UInt64\n"
        "    /// File-backed pages (external_page_count), used as a cache-memory estimate.\n"
        "    let cachedBytes: UInt64\n",
        "内存快照缓存字段",
    )
    source = replacement(
        source,
        "    var compressedGB: Double { Double(compressedBytes) / 1_073_741_824.0 }\n",
        "    var compressedGB: Double { Double(compressedBytes) / 1_073_741_824.0 }\n"
        "    var cachedGB: Double { Double(cachedBytes) / 1_073_741_824.0 }\n",
        "缓存内存 GB 换算",
    )
    source = replacement(
        source,
        "    static let zero = MemorySnapshot(availableBytes: 0, appBytes: 0, wiredBytes: 0, compressedBytes: 0, pressurePercent: nil)\n",
        "    static let zero = MemorySnapshot(availableBytes: 0, appBytes: 0, wiredBytes: 0, compressedBytes: 0, cachedBytes: 0, pressurePercent: nil)\n",
        "内存零值初始化",
    )
    source = replacement(
        source,
        "        let rawCompressed = UInt64(statistics.compressor_page_count) * pageBytes\n",
        "        let rawCompressed = UInt64(statistics.compressor_page_count) * pageBytes\n"
        "        let rawCached = UInt64(statistics.external_page_count) * pageBytes\n",
        "读取文件缓存页数",
    )
    source = replacement(
        source,
        "            compressedBytes: compressed,\n"
        "            pressurePercent: MemoryPressureSampler.samplePercent()\n",
        "            compressedBytes: compressed,\n"
        "            cachedBytes: min(rawCached, total),\n"
        "            pressurePercent: MemoryPressureSampler.samplePercent()\n",
        "写入缓存快照",
    )

    # 4. CPU 采用 HOST_CPU_LOAD_INFO 的相邻采样差值；GPU 读取可用驱动公开在 IORegistry 的统计。
    samplers = r'''/// Menu-bar CPU/GPU values sampled from the existing one-second status-bar update.
/// CPU percentages are calculated from cumulative Mach ticks, not process enumeration.
private struct CPUSnapshot {
    let systemPercent: Double
    let userPercent: Double
    let idlePercent: Double
    let gpuPercent: Double?
    let load1: Double
    let load5: Double
    let load15: Double

    static let zero = CPUSnapshot(
        systemPercent: 0, userPercent: 0, idlePercent: 100,
        gpuPercent: nil, load1: 0, load5: 0, load15: 0
    )
}

private enum GPUSampler {
    /// IOAccelerator keys differ by GPU/driver. Missing keys mean unavailable, not 0%.
    static func samplePercent() -> Double? {
        var iterator: io_iterator_t = 0
        let matching = IOServiceMatching("IOAccelerator")
        guard IOServiceGetMatchingServices(kIOMasterPortDefault, matching, &iterator) == KERN_SUCCESS else {
            return nil
        }
        defer { IOObjectRelease(iterator) }

        var maximum: Double?
        while true {
            let service = IOIteratorNext(iterator)
            if service == 0 { break }
            if let property = IORegistryEntryCreateCFProperty(
                service, "PerformanceStatistics" as CFString, kCFAllocatorDefault, 0
            )?.takeRetainedValue(), let statistics = property as? NSDictionary {
                let keys = ["Device Utilization %", "GPU Activity (%)", "Renderer Utilization %"]
                for key in keys {
                    if let number = statistics[key] as? NSNumber {
                        let value = number.doubleValue
                        if value.isFinite, value >= 0 {
                            let bounded = min(100.0, value)
                            maximum = max(maximum ?? bounded, bounded)
                            break
                        }
                    }
                }
            }
            IOObjectRelease(service)
        }
        return maximum
    }
}

private enum CPUUsageSampler {
    private static var previousTicks: [UInt32]?

    static func sample() -> CPUSnapshot {
        let gpu = GPUSampler.samplePercent()
        var averages = [Double](repeating: 0, count: 3)
        let averageCount = averages.withUnsafeMutableBufferPointer { buffer -> Int32 in
            guard let base = buffer.baseAddress else { return 0 }
            return getloadavg(base, 3)
        }

        var info = host_cpu_load_info_data_t()
        var count = mach_msg_type_number_t(
            MemoryLayout<host_cpu_load_info_data_t>.size / MemoryLayout<integer_t>.size
        )
        let host = mach_host_self()
        defer { mach_port_deallocate(mach_task_self_, host) }
        let result = withUnsafeMutablePointer(to: &info) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: Int(count)) {
                host_statistics(host, HOST_CPU_LOAD_INFO, $0, &count)
            }
        }
        guard result == KERN_SUCCESS else {
            return CPUSnapshot(
                systemPercent: 0, userPercent: 0, idlePercent: 100, gpuPercent: gpu,
                load1: averageCount > 0 ? averages[0] : 0,
                load5: averageCount > 1 ? averages[1] : 0,
                load15: averageCount > 2 ? averages[2] : 0
            )
        }

        // cpu_ticks order is USER, SYSTEM, IDLE, NICE in mach/host_info.h.
        let current = [info.cpu_ticks.0, info.cpu_ticks.1, info.cpu_ticks.2, info.cpu_ticks.3]
        let percentages: (Double, Double, Double)
        if let previous = previousTicks, previous.count == current.count {
            let deltas = zip(previous, current).map { Double($1 &- $0) }
            let total = deltas.reduce(0, +)
            if total > 0 {
                let user = (deltas[0] + deltas[3]) / total * 100.0
                let system = deltas[1] / total * 100.0
                let idle = deltas[2] / total * 100.0
                percentages = (system, user, idle)
            } else {
                percentages = (0, 0, 100)
            }
        } else {
            percentages = (0, 0, 100)
        }
        previousTicks = current

        return CPUSnapshot(
            systemPercent: percentages.0,
            userPercent: percentages.1,
            idlePercent: percentages.2,
            gpuPercent: gpu,
            load1: averageCount > 0 ? averages[0] : 0,
            load5: averageCount > 1 ? averages[1] : 0,
            load15: averageCount > 2 ? averages[2] : 0
        )
    }
}
'''
    source = addition(
        source,
        "private final class MemoryColorDotView: NSView {",
        "\n" + samplers + "\n",
        "CPU GPU 采样器",
        before=True,
    )

    # 5. 重建两个固定 128pt 的提示框；标签/数值列分别左、右对齐。
    tooltip_controllers = r'''private final class MemoryTooltipViewController: NSViewController {
    private var labelFields: [NSTextField] = []
    private var valueFields: [NSTextField] = []
    private var pressureValueField: NSTextField?
    private let rowLabels = ["可用内存", "App 内存", "联动内存", "压缩内存", "缓存内存"]
    private let rowColors = [
        StatusbarLayout.availableColor,
        StatusbarLayout.appMemoryColor,
        StatusbarLayout.wiredColor,
        StatusbarLayout.compressedColor,
        StatusbarLayout.cacheMemoryColor
    ]

    override func loadView() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 128, height: 142))
        let pressureDot = MemoryColorDotView(frame: NSRect(x: 8, y: 124, width: 7, height: 7))
        pressureDot.color = StatusbarLayout.memoryPressureDotColor
        content.addSubview(pressureDot)

        let pressureLabel = NSTextField(labelWithString: "内存压力")
        pressureLabel.frame = NSRect(x: 20, y: 120, width: 50, height: 16)
        pressureLabel.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        pressureLabel.textColor = NSColor.labelColor
        pressureLabel.alignment = .left
        content.addSubview(pressureLabel)

        let pressureValue = NSTextField(labelWithString: "--%")
        pressureValue.frame = NSRect(x: 72, y: 120, width: 48, height: 16)
        pressureValue.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        pressureValue.textColor = NSColor.labelColor
        pressureValue.alignment = .right
        content.addSubview(pressureValue)
        pressureValueField = pressureValue

        for index in 0..<rowLabels.count {
            let rowY = CGFloat(100 - index * 20)
            let dot = MemoryColorDotView(frame: NSRect(x: 8, y: rowY + 4, width: 7, height: 7))
            dot.color = rowColors[index]
            content.addSubview(dot)

            let label = NSTextField(labelWithString: rowLabels[index])
            label.frame = NSRect(x: 20, y: rowY, width: 50, height: 16)
            label.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            label.textColor = NSColor.labelColor
            label.alignment = .left
            label.lineBreakMode = .byTruncatingTail
            content.addSubview(label)
            labelFields.append(label)

            let value = NSTextField(labelWithString: "--.-G")
            value.frame = NSRect(x: 72, y: rowY, width: 48, height: 16)
            value.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            value.textColor = NSColor.labelColor
            value.alignment = .right
            value.lineBreakMode = .byTruncatingTail
            content.addSubview(value)
            valueFields.append(value)
        }
        view = content
    }

    func update(snapshot: MemorySnapshot) {
        _ = self.view
        let pressure = snapshot.pressurePercent.map { "\($0)%" } ?? "--%"
        if pressureValueField?.stringValue != pressure { pressureValueField?.stringValue = pressure }
        let values = [snapshot.availableGB, snapshot.appGB, snapshot.wiredGB,
                      snapshot.compressedGB, snapshot.cachedGB]
        for index in 0..<min(valueFields.count, values.count) {
            let text = String(format: "%.1fG", values[index])
            if valueFields[index].stringValue != text { valueFields[index].stringValue = text }
        }
    }
}

private final class CPUTooltipViewController: NSViewController {
    private var valueFields: [NSTextField] = []
    private let rowLabels = ["系统", "用户", "闲置", "GPU", "负载"]
    private let rowColors = [
        StatusbarLayout.cpuSystemColor,
        StatusbarLayout.wiredColor,
        StatusbarLayout.availableColor,
        StatusbarLayout.compressedColor,
        StatusbarLayout.memoryPressureDotColor
    ]

    override func loadView() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 128, height: 124))
        for index in 0..<rowLabels.count {
            let rowY = CGFloat(96 - index * 21)
            let dot = MemoryColorDotView(frame: NSRect(x: 8, y: rowY + 4, width: 7, height: 7))
            dot.color = rowColors[index]
            content.addSubview(dot)

            let label = NSTextField(labelWithString: rowLabels[index])
            label.frame = NSRect(x: 20, y: rowY, width: 40, height: 16)
            label.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            label.textColor = NSColor.labelColor
            label.alignment = .left
            content.addSubview(label)

            let value = NSTextField(labelWithString: "--.-%")
            value.frame = NSRect(x: 60, y: rowY, width: 60, height: 16)
            value.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            value.textColor = NSColor.labelColor
            value.alignment = .right
            value.lineBreakMode = .byTruncatingTail
            content.addSubview(value)
            valueFields.append(value)
        }
        view = content
    }

    func update(snapshot: CPUSnapshot) {
        _ = self.view
        let gpuText = snapshot.gpuPercent.map { String(format: "%.1f%%", $0) } ?? "--.-%"
        let values = [
            String(format: "%.1f%%", snapshot.systemPercent),
            String(format: "%.1f%%", snapshot.userPercent),
            String(format: "%.1f%%", snapshot.idlePercent),
            gpuText,
            String(format: "%.1f  %.1f  %.1f", snapshot.load1, snapshot.load5, snapshot.load15)
        ]
        for index in 0..<min(valueFields.count, values.count) {
            if valueFields[index].stringValue != values[index] {
                valueFields[index].stringValue = values[index]
            }
        }
    }
}
'''
    source = replace_between(
        source,
        "private final class MemoryTooltipViewController: NSViewController {",
        "// END statusbar-fan-memory patch (2026-10-22)",
        tooltip_controllers,
        "内存与 CPU 提示框",
    )

    # 6. 给 StatusbarView 加 CPU 状态、第二个饼图/提示框及短时位置检测器。
    source = replacement(
        source,
        "    private var memorySnapshot = MemorySnapshot.zero\n",
        "    private var memorySnapshot = MemorySnapshot.zero\n"
        "    private var cpuSnapshot = CPUSnapshot.zero\n",
        "菜单栏 CPU 快照字段",
    )
    source = replacement(
        source,
        "    private var memoryPopover: NSPopover?\n"
        "    private var memoryTooltipController: MemoryTooltipViewController?\n"
        "    private var memoryTrackingArea: NSTrackingArea?\n"
        "    private var hoveringMemoryPie = false\n"
        "    private var previousFanTemperature: Float?\n",
        "    private var memoryPopover: NSPopover?\n"
        "    private var memoryTooltipController: MemoryTooltipViewController?\n"
        "    private var memoryTrackingArea: NSTrackingArea?\n"
        "    private var cpuPopover: NSPopover?\n"
        "    private var cpuTooltipController: CPUTooltipViewController?\n"
        "    private var cpuTrackingArea: NSTrackingArea?\n"
        "    private enum TooltipKind: Equatable { case memory, cpu }\n"
        "    private var activeTooltipKind: TooltipKind?\n"
        "    private var activeTooltipPopover: NSPopover?\n"
        "    private var tooltipPositionTimer: Timer?\n"
        "    private var tooltipOutsideSince: TimeInterval?\n"
        "    private var previousFanTemperature: Float?\n",
        "菜单栏提示框生命周期字段",
    )

    setup_old = '''        let tooltipController = MemoryTooltipViewController(nibName: nil, bundle: nil)
        let popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 128, height: 108)
        popover.contentViewController = tooltipController
        memoryTooltipController = tooltipController
        memoryPopover = popover
        tooltipController.update(snapshot: memorySnapshot)'''
    setup_new = '''        let memoryController = MemoryTooltipViewController(nibName: nil, bundle: nil)
        let memoryPopover = NSPopover()
        memoryPopover.behavior = .transient
        memoryPopover.contentSize = NSSize(width: 128, height: 142)
        memoryPopover.contentViewController = memoryController
        self.memoryTooltipController = memoryController
        self.memoryPopover = memoryPopover
        memoryController.update(snapshot: memorySnapshot)

        let cpuController = CPUTooltipViewController(nibName: nil, bundle: nil)
        let cpuPopover = NSPopover()
        cpuPopover.behavior = .transient
        cpuPopover.contentSize = NSSize(width: 128, height: 124)
        cpuPopover.contentViewController = cpuController
        self.cpuTooltipController = cpuController
        self.cpuPopover = cpuPopover
        cpuController.update(snapshot: cpuSnapshot)'''
    source = replacement(source, setup_old, setup_new, "创建内存和 CPU 提示框")

    source = replacement(
        source,
        "        fanIndicatorView?.needsLayout = true\n"
        "        refreshMemoryTrackingArea()\n",
        "        fanIndicatorView?.needsLayout = true\n"
        "        refreshMemoryTrackingArea()\n"
        "        refreshCPUTrackingArea()\n",
        "布局变更时刷新 CPU 追踪区域",
    )
    source = replacement(
        source,
        "    override func viewDidMoveToWindow() {\n"
        "        super.viewDidMoveToWindow()\n"
        "        refreshMemoryTrackingArea()\n"
        "    }\n",
        "    override func viewDidMoveToWindow() {\n"
        "        super.viewDidMoveToWindow()\n"
        "        refreshMemoryTrackingArea()\n"
        "        refreshCPUTrackingArea()\n"
        "    }\n",
        "窗口变化时刷新 CPU 追踪区域",
    )
    # 7. 替换两个追踪区及弹窗自动关闭逻辑。位置轮询只在弹窗打开时创建。
    tracking_block = r'''    private var cpuPieRect: NSRect {
        NSRect(
            x: StatusbarLayout.cpuPieX,
            y: max(0, (bounds.height - StatusbarLayout.cpuPieSize) / 2.0),
            width: StatusbarLayout.cpuPieSize,
            height: StatusbarLayout.cpuPieSize
        )
    }

    private func refreshMemoryTrackingArea() {
        if let oldArea = memoryTrackingArea {
            removeTrackingArea(oldArea)
            memoryTrackingArea = nil
        }
        guard bounds.height >= StatusbarLayout.memoryPieSize else { return }
        let area = NSTrackingArea(
            rect: memoryPieRect.insetBy(dx: -2, dy: -2),
            options: [.mouseEnteredAndExited, .activeAlways],
            owner: self,
            userInfo: nil
        )
        memoryTrackingArea = area
        addTrackingArea(area)
    }

    private func refreshCPUTrackingArea() {
        if let oldArea = cpuTrackingArea {
            removeTrackingArea(oldArea)
            cpuTrackingArea = nil
        }
        guard bounds.height >= StatusbarLayout.cpuPieSize else { return }
        let area = NSTrackingArea(
            rect: cpuPieRect.insetBy(dx: -2, dy: -2),
            options: [.mouseEnteredAndExited, .activeAlways],
            owner: self,
            userInfo: nil
        )
        cpuTrackingArea = area
        addTrackingArea(area)
    }

    override func mouseEntered(with event: NSEvent) {
        if let area = memoryTrackingArea, event.trackingArea === area {
            memoryTooltipController?.update(snapshot: memorySnapshot)
            showTooltip(kind: .memory)
            return
        }
        if let area = cpuTrackingArea, event.trackingArea === area {
            cpuTooltipController?.update(snapshot: cpuSnapshot)
            showTooltip(kind: .cpu)
            return
        }
        super.mouseEntered(with: event)
    }

    override func mouseExited(with event: NSEvent) {
        // Hover state is determined by screen position, so moving from the icon into
        // its popover does not close it prematurely.
        super.mouseExited(with: event)
    }

    private func showTooltip(kind: TooltipKind) {
        let targetPopover: NSPopover
        let anchorRect: NSRect
        switch kind {
        case .memory:
            guard let popover = memoryPopover else { return }
            targetPopover = popover
            anchorRect = memoryPieRect
        case .cpu:
            guard let popover = cpuPopover else { return }
            targetPopover = popover
            anchorRect = cpuPieRect
        }

        if let current = activeTooltipPopover, current !== targetPopover, current.isShown {
            current.performClose(nil)
        }
        activeTooltipKind = kind
        activeTooltipPopover = targetPopover
        tooltipOutsideSince = nil
        if !targetPopover.isShown {
            targetPopover.show(relativeTo: anchorRect, of: self, preferredEdge: .minY)
        }
        startTooltipPositionMonitorIfNeeded()
    }

    private func startTooltipPositionMonitorIfNeeded() {
        guard activeTooltipPopover?.isShown == true else { return }
        tooltipPositionTimer?.invalidate()
        tooltipOutsideSince = nil
        let timer = Timer(timeInterval: 0.20, repeats: true) { [weak self] _ in
            self?.checkTooltipPosition()
        }
        tooltipPositionTimer = timer
        RunLoop.main.add(timer, forMode: .common)
    }

    private func checkTooltipPosition() {
        guard let popover = activeTooltipPopover, popover.isShown else {
            stopTooltipPositionMonitor()
            return
        }
        guard let window = self.window, let kind = activeTooltipKind else { return }
        let anchorRect = (kind == .memory) ? memoryPieRect : cpuPieRect
        let anchorInWindow = convert(anchorRect, to: nil)
        let anchorOnScreen = window.convertToScreen(anchorInWindow).insetBy(dx: -4, dy: -4)
        let mouse = NSEvent.mouseLocation
        let popoverOnScreen = popover.contentViewController?.view.window?.frame
            .insetBy(dx: -4, dy: -4)
        if anchorOnScreen.contains(mouse) || (popoverOnScreen?.contains(mouse) ?? false) {
            tooltipOutsideSince = nil
            return
        }

        let now = ProcessInfo.processInfo.systemUptime
        if tooltipOutsideSince == nil {
            tooltipOutsideSince = now
        } else if let outsideSince = tooltipOutsideSince, now - outsideSince >= 0.65 {
            popover.performClose(nil)
            stopTooltipPositionMonitor()
        }
    }

    private func stopTooltipPositionMonitor() {
        tooltipPositionTimer?.invalidate()
        tooltipPositionTimer = nil
        tooltipOutsideSince = nil
        activeTooltipPopover = nil
        activeTooltipKind = nil
    }

    func closeMemoryTooltip() {
        if let popover = memoryPopover, popover.isShown { popover.performClose(nil) }
        if let popover = cpuPopover, popover.isShown { popover.performClose(nil) }
        stopTooltipPositionMonitor()
    }

'''
    source = replace_between(
        source,
        "    private func refreshMemoryTrackingArea() {",
        "    func updateMetrics(",
        tracking_block,
        "提示框位置检测与生命周期",
    )

    # 8. 更新指标函数签名和提示框快照；仍由 controller 的原有 1 秒 timer 调用。
    source = replacement(
        source,
        "    func updateMetrics(meanFreq: Float, maxFreq: Float, temperature: Float, power: Float,\n"
        "                       memory: MemorySnapshot?) {",
        "    func updateMetrics(meanFreq: Float, maxFreq: Float, temperature: Float, power: Float,\n"
        "                       memory: MemorySnapshot?, cpu: CPUSnapshot) {",
        "更新菜单栏指标签名",
    )
    source = replacement(
        source,
        "        if let memory = memory {\n"
        "            memorySnapshot = memory\n"
        "            memoryTooltipController?.update(snapshot: memory)\n"
        "        }\n",
        "        if let memory = memory {\n"
        "            memorySnapshot = memory\n"
        "            memoryTooltipController?.update(snapshot: memory)\n"
        "        }\n"
        "        cpuSnapshot = cpu\n"
        "        cpuTooltipController?.update(snapshot: cpu)\n",
        "更新 CPU tooltip 快照",
    )

    # 9. 删除 TMP/PWR 标签调用，保留阈值颜色，改为上功率下温度并右对齐。
    draw_start = "    override func draw(_ dirtyRect: NSRect) {"
    memory_pie_start = "    private func drawMemoryPie() {"
    section_start = source.index("fileprivate class StatusbarView: NSView {")
    draw_start_index = source.find(draw_start, section_start)
    pie_start_index = source.find(memory_pie_start, draw_start_index)
    if draw_start_index < 0 or pie_start_index <= draw_start_index:
        fail("功能菜单栏重绘：找不到 StatusbarView.draw 与 drawMemoryPie 的边界锚点。")
    old_draw_region = source[draw_start_index:pie_start_index]
    if old_draw_region.count("drawCompactSingle(") != 2 or "drawMemoryValues()" not in old_draw_region:
        fail("功能菜单栏重绘：原绘图块结构与预期不符。")
    print("anchor OK: 功能菜单栏重绘起点/终点")
    new_draw = r'''    override func draw(_ dirtyRect: NSRect) {
        guard NSGraphicsContext.current?.cgContext != nil else { return }

        let averageFrequencyGHz = meanFreq * 0.001
        let maximumFrequencyGHz = maxFreq * 0.001
        let averageFrequency = String(format: "%.1f", averageFrequencyGHz)
        let maximumFrequency = String(format: "%.1f", maximumFrequencyGHz)

        drawDoubleCompactValue(
            up: "\(maximumFrequency)ᴳ",
            down: "\(averageFrequency)ᴳ",
            x: StatusbarLayout.frequencyValueX,
            upColor: maximumFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor,
            downColor: averageFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor
        )

        drawDoubleCompactValue(
            up: "\(Int(round(pwr)))ᵂ",
            down: "\(Int(round(temp)))º",
            x: StatusbarLayout.powerTemperatureX,
            upColor: pwr > StatusbarLayout.powerThreshold ? StatusbarLayout.highlightColor : .labelColor,
            downColor: temp > StatusbarLayout.temperatureThreshold ? StatusbarLayout.highlightColor : .labelColor,
            rightAligned: true,
            valueWidth: StatusbarLayout.powerTemperatureValueWidth
        )

        drawMemoryPie()
        drawMemoryValues()
        drawCPUPie()
        drawCPUValues()
    }

'''
    source = source[:draw_start_index] + new_draw + source[pie_start_index:]
    print("check OK: 功能温度功率双行绘制、保留阈值色")

    # 10. 增加 CPU 饼图（系统/用户/闲置）和 GPU 使用率外围进度圈。
    cpu_drawing = r'''    private func drawCPUPie() {
        let rect = cpuPieRect
        let center = NSPoint(x: rect.midX, y: rect.midY)
        let radius = min(rect.width, rect.height) / 2.0
        let total = max(0.0001, cpuSnapshot.systemPercent + cpuSnapshot.userPercent + cpuSnapshot.idlePercent)
        let pieces: [(Double, NSColor)] = [
            (cpuSnapshot.systemPercent, StatusbarLayout.cpuSystemColor),
            (cpuSnapshot.userPercent, StatusbarLayout.wiredColor),
            (cpuSnapshot.idlePercent, StatusbarLayout.availableColor)
        ]

        var startAngle: CGFloat = 90.0
        for (percentage, color) in pieces where percentage > 0 {
            let sweep = CGFloat(percentage / total * 360.0)
            let endAngle = startAngle - sweep
            let startRadians = startAngle * CGFloat.pi / 180.0
            let path = NSBezierPath()
            path.move(to: center)
            path.line(to: NSPoint(
                x: center.x + cos(startRadians) * radius,
                y: center.y + sin(startRadians) * radius
            ))
            path.appendArc(
                withCenter: center,
                radius: radius,
                startAngle: startAngle,
                endAngle: endAngle,
                clockwise: true
            )
            path.close()
            color.setFill()
            path.fill()
            startAngle = endAngle
        }

        let ringRect = rect.insetBy(dx: -StatusbarLayout.cpuPieRingInset,
                                    dy: -StatusbarLayout.cpuPieRingInset)
        let track = NSBezierPath(ovalIn: ringRect)
        track.lineWidth = StatusbarLayout.cpuPieRingWidth
        StatusbarLayout.memoryPressureTrackColor.setStroke()
        track.stroke()

        if let gpu = cpuSnapshot.gpuPercent, gpu > 0 {
            let arc = NSBezierPath()
            arc.lineWidth = StatusbarLayout.cpuPieRingWidth
            arc.lineCapStyle = .round
            let endAngle = CGFloat(90.0 - 360.0 * min(100.0, max(0.0, gpu)) / 100.0)
            arc.appendArc(
                withCenter: center,
                radius: radius + StatusbarLayout.cpuPieRingInset,
                startAngle: 90,
                endAngle: endAngle,
                clockwise: true
            )
            let color = gpu > StatusbarLayout.gpuUsageThreshold
                ? StatusbarLayout.highlightColor
                : StatusbarLayout.compressedColor
            color.setStroke()
            arc.stroke()
        }
    }

    private func drawCPUValues() {
        var attributes = compactValue ?? [:]
        attributes[.foregroundColor] = NSColor.labelColor
        let systemColor = cpuSnapshot.systemPercent > StatusbarLayout.cpuUsageThreshold
            ? StatusbarLayout.highlightColor : NSColor.labelColor
        let userColor = cpuSnapshot.userPercent > StatusbarLayout.cpuUsageThreshold
            ? StatusbarLayout.highlightColor : NSColor.labelColor

        var systemAttributes = attributes
        systemAttributes[.foregroundColor] = systemColor
        drawRightAlignedValue(
            String(format: "%.1f%%", cpuSnapshot.systemPercent),
            x: StatusbarLayout.cpuValueX,
            y: StatusbarLayout.frequencyTopY,
            width: StatusbarLayout.cpuValueWidth,
            attributes: systemAttributes
        )
        var userAttributes = attributes
        userAttributes[.foregroundColor] = userColor
        drawRightAlignedValue(
            String(format: "%.1f%%", cpuSnapshot.userPercent),
            x: StatusbarLayout.cpuValueX,
            y: StatusbarLayout.frequencyBottomY,
            width: StatusbarLayout.cpuValueWidth,
            attributes: userAttributes
        )
    }

'''
    source = addition(
        source,
        "    private func drawRightAlignedValue(",
        cpu_drawing,
        "绘制 CPU 饼图 GPU 外圈和双行百分比",
        before=True,
    )

    # 11. 让双行紧凑绘制函数支持右对齐；频率原有的左对齐方式保持默认。
    old_double = r'''    private func drawDoubleCompactValue(up: String, down: String, x: CGFloat,
                                        upColor: NSColor = .labelColor,
                                        downColor: NSColor = .labelColor) {
        var upperAttributes = compactValue ?? [:]
        upperAttributes[.foregroundColor] = upColor
        NSAttributedString(string: up, attributes: upperAttributes).draw(
            at: NSPoint(x: x, y: StatusbarLayout.frequencyTopY)
        )
        var lowerAttributes = compactValue ?? [:]
        lowerAttributes[.foregroundColor] = downColor
        NSAttributedString(string: down, attributes: lowerAttributes).draw(
            at: NSPoint(x: x, y: StatusbarLayout.frequencyBottomY)
        )
    }
'''
    new_double = r'''    private func drawDoubleCompactValue(up: String, down: String, x: CGFloat,
                                        upColor: NSColor = .labelColor,
                                        downColor: NSColor = .labelColor,
                                        rightAligned: Bool = false,
                                        valueWidth: CGFloat = 0) {
        var upperAttributes = compactValue ?? [:]
        upperAttributes[.foregroundColor] = upColor
        var lowerAttributes = compactValue ?? [:]
        lowerAttributes[.foregroundColor] = downColor
        if rightAligned {
            drawRightAlignedValue(up, x: x, y: StatusbarLayout.frequencyTopY,
                                  width: valueWidth, attributes: upperAttributes)
            drawRightAlignedValue(down, x: x, y: StatusbarLayout.frequencyBottomY,
                                  width: valueWidth, attributes: lowerAttributes)
        } else {
            NSAttributedString(string: up, attributes: upperAttributes).draw(
                at: NSPoint(x: x, y: StatusbarLayout.frequencyTopY)
            )
            NSAttributedString(string: down, attributes: lowerAttributes).draw(
                at: NSPoint(x: x, y: StatusbarLayout.frequencyBottomY)
            )
        }
    }
'''
    source = replacement(source, old_double, new_double, "双行数值右对齐能力")

    # 12. 通过现有 controller 的 1 秒周期同时采 CPU/GPU 快照。
    source = replacement(
        source,
        "        // Exactly one memory sample per existing one-second update; no second timer.\n"
        "        let memory = MemorySampler.sample()\n"
        "        view?.updateMetrics(\n"
        "            meanFreq: mean,\n"
        "            maxFreq: maximum,\n"
        "            temperature: temperature,\n"
        "            power: power,\n"
        "            memory: memory\n"
        "        )\n",
        "        // Memory, CPU, GPU and load averages reuse this existing one-second update.\n"
        "        let memory = MemorySampler.sample()\n"
        "        let cpu = CPUUsageSampler.sample()\n"
        "        view?.updateMetrics(\n"
        "            meanFreq: mean,\n"
        "            maxFreq: maximum,\n"
        "            temperature: temperature,\n"
        "            power: power,\n"
        "            memory: memory,\n"
        "            cpu: cpu\n"
        "        )\n",
        "复用现有刷新周期采样",
    )

    return source


def verify_result(source: str) -> None:
    checks = {
        "patch marker": "BEGIN statusbar-cpu-gpu-tooltip patch",
        "cache value": "snapshot.cachedGB",
        "CPU sampler": "private enum CPUUsageSampler",
        "GPU sampler": "private enum GPUSampler",
        "CPU tooltip": "private final class CPUTooltipViewController",
        "GPU threshold": "gpuUsageThreshold: Double = 50.0",
        "CPU threshold": "cpuUsageThreshold: Double = 50.0",
        "position timer": "startTooltipPositionMonitorIfNeeded",
        "one-second sampling call": "let cpu = CPUUsageSampler.sample()",
        "CPU pie draw": "drawCPUPie()",
        "GPU ring": "StatusbarLayout.compressedColor",
    }
    for label, needle in checks.items():
        if needle not in source:
            fail(f"最终校验失败：缺少 {label}（{needle}）。")
        print(f"check OK: 功能最终验证-{label}")

    if 'label: "TMP"' in source or 'label: "PWR"' in source:
        fail("最终校验失败：仍存在旧 TMP/PWR 菜单栏标签调用。")
    if source.count("BEGIN statusbar-cpu-gpu-tooltip patch") != 1:
        fail("最终校验失败：补丁标记数量异常。")
    # 防止引入额外的周期性采样 Timer；唯一新增 Timer 必须是弹窗可见期的局部位置监测器。
    if source.count("Timer(timeInterval: 0.20, repeats: true)") != 1:
        fail("最终校验失败：提示框位置检测器数量不是 1。")
    print("check OK: 功能最终验证-无重复常驻采样定时器")


def main() -> None:
    if not SOURCE_PATH.is_file():
        fail("未找到 AMD Power Gadget/StatusbarController.swift。请在 useesee/SMCAMDProcessor 仓库根目录运行脚本。")
    original = SOURCE_PATH.read_text(encoding="utf-8")
    if DRY_RUN:
        print("模式：dry-run，只检查锚点并在内存中模拟修改，不写入、不备份源文件。")
    elif BACKUP_PATH.exists():
        fail(f"备份已存在：{BACKUP_PATH}。拒绝覆盖；请先确认并移走旧备份。")

    patched = apply_patch(original)
    verify_result(patched)

    if DRY_RUN:
        print("DRY-RUN OK: 所有锚点及最终结构校验通过；源文件未改变。")
        return

    # 仅在所有锚点和内存中的后置检查通过后创建备份并写入文件。
    shutil.copy2(SOURCE_PATH, BACKUP_PATH)
    try:
        SOURCE_PATH.write_text(patched, encoding="utf-8")
        written = SOURCE_PATH.read_text(encoding="utf-8")
        verify_result(written)
    except Exception as exc:
        shutil.copy2(BACKUP_PATH, SOURCE_PATH)
        fail(f"写入或回读校验失败，已从备份恢复源文件：{exc}")

    print("PATCH OK: 已应用菜单栏温度/功率重绘、缓存内存、CPU/GPU 饼图与提示框位置检测。")
    print(f"BACKUP: {BACKUP_PATH}")
    print("注意：脚本静态校验不等同于 Xcode 编译或 macOS 10.13 实机运行验证。")


if __name__ == "__main__":
    main()
