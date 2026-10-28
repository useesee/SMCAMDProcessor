#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Patch the current useesee/SMCAMDProcessor menu-bar source with fan + memory UI.

Run from the repository root:
    python3 patch_statusbar_fan_memory.py

Use --dry-run to inspect the proposed diff, --check to validate anchors without
writing, or --self-test to test patch transformation logic on a synthetic fixture.
This script does not claim to compile or execute AppKit/Core Animation on macOS.
"""
from __future__ import print_function

import argparse
import difflib
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import time

PATCH_MARKER = "// BEGIN statusbar-fan-memory patch (2026-10-22)"
TARGET_RELATIVE = Path("AMD Power Gadget") / "StatusbarController.swift"

NEW_LAYOUT_AND_HELPERS = r'''// BEGIN statusbar-fan-memory patch (2026-10-22)
/// All menu-bar geometry and thresholds are centralized here.
private enum StatusbarLayout {
    static let fanX: CGFloat = 0
    static let fanSize: CGFloat = 18
    static let frequencyValueOffsetX: CGFloat = 2
    static var cpuValueX: CGFloat { fanX + fanSize + frequencyValueOffsetX }
    static let temperatureX: CGFloat = 45
    static let powerX: CGFloat = 78
    static let labelWidth: CGFloat = 8
    static let labelOriginY: CGFloat = -4
    static let metricValueOffsetX: CGFloat = 7
    static let valueOriginY: CGFloat = 2.5
    static let frequencyTopY: CGFloat = 9
    static let frequencyBottomY: CGFloat = -1
    static let memoryPieSize: CGFloat = 16
    static let memoryPressureRingInset: CGFloat = 1.5
    static let memoryPressureRingWidth: CGFloat = 1.5
    static let memoryPressureThreshold: Int = 70
    static let memoryPressureRingColor = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 1) // #FFFFFF
    static let memoryPressureTrackColor = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 0.5) // #FFFFFF80
    static let memoryPressureDotColor = memoryPressureRingColor
    static let powerValueWidth: CGFloat = 20
    static let powerToMemoryPieGap: CGFloat = 8
    static var memoryPieX: CGFloat {
        powerX + metricValueOffsetX + powerValueWidth + powerToMemoryPieGap
    }
    static let memoryPieToValueGap: CGFloat = 6
    static var memoryValueX: CGFloat {
        memoryPieX + memoryPieSize + memoryPieToValueGap
    }
    static let memoryValueWidth: CGFloat = 28
    static var itemWidth: CGFloat { memoryValueX + memoryValueWidth + 2 }
    static let frequencyThreshold: Float = 3.2
    static let temperatureThreshold: Float = 70
    static let fanTemperatureThreshold: Float = 65
    static let fanMinimumTemperature: Double = 45.0
    static let fanMaximumTemperature: Double = 85.0
    static let fanBaseRevolutionPeriod: Double = 10.0
    static let powerThreshold: Float = 10
    // The fan hot state uses the exact same color as the highlighted CPU frequency.
    static let highlightColor = NSColor(
        calibratedRed: 1,
        green: 0.6,
        blue: 0,
        alpha: 1
    )
    static let fanNormalColor = NSColor.white
    static let availableColor = NSColor(calibratedRed: 0.20, green: 0.78, blue: 0.45, alpha: 1)
    static let appMemoryColor = NSColor(calibratedRed: 1, green: 0.6, blue: 0.00, alpha: 1)
    static let wiredColor = NSColor(calibratedRed: 0.28, green: 0.66, blue: 0.98, alpha: 1)
    static let compressedColor = NSColor(calibratedRed: 0.98, green: 0.3, blue: 0.55, alpha: 1)
}

/// Four curved swept blades. One Core Animation rotation is installed in init;
/// speed changes only remap layer time and therefore keep the current phase.
private final class FanIndicatorView: NSView {
    private let rotorLayer = CALayer()
    private let bladesLayer = CAShapeLayer()
    private let hubLayer = CAShapeLayer()
    private var currentLayerSpeed: Float = 1.0
    private var isHot = false

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        rotorLayer.anchorPoint = CGPoint(x: 0.5, y: 0.5)
        rotorLayer.bounds = bounds
        rotorLayer.position = CGPoint(x: bounds.midX, y: bounds.midY)
        rotorLayer.addSublayer(bladesLayer)
        rotorLayer.addSublayer(hubLayer)
        layer?.addSublayer(rotorLayer)
        configurePaths()
        installRotationAnimation()
        applyColor(isHot: false)
    }

    required init?(coder: NSCoder) {
        super.init(coder: coder)
        wantsLayer = true
        layer?.backgroundColor = NSColor.clear.cgColor
        rotorLayer.anchorPoint = CGPoint(x: 0.5, y: 0.5)
        rotorLayer.bounds = bounds
        rotorLayer.position = CGPoint(x: bounds.midX, y: bounds.midY)
        rotorLayer.addSublayer(bladesLayer)
        rotorLayer.addSublayer(hubLayer)
        layer?.addSublayer(rotorLayer)
        configurePaths()
        installRotationAnimation()
        applyColor(isHot: false)
    }

    private func installRotationAnimation() {
        let rotation = CABasicAnimation(keyPath: "transform.rotation.z")
        rotation.fromValue = 0.0
        rotation.toValue = -2.0 * Double.pi // negative angle is clockwise in layer coordinates
        rotation.duration = StatusbarLayout.fanBaseRevolutionPeriod // base revolution period
        rotation.repeatCount = .infinity
        rotation.timingFunction = CAMediaTimingFunction(name: .linear)
        rotorLayer.add(rotation, forKey: "fan.rotation")
    }

    override func layout() {
        super.layout()
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        rotorLayer.bounds = bounds
        rotorLayer.position = CGPoint(x: bounds.midX, y: bounds.midY)
        bladesLayer.frame = rotorLayer.bounds
        hubLayer.frame = rotorLayer.bounds
        configurePaths()
        CATransaction.commit()
    }

    func updateTemperature(_ temperature: Float, crossedThreshold: Bool) {
        guard temperature.isFinite else { return }
        updateRotationSpeed(forTemperature: temperature)
        if crossedThreshold {
            applyColor(isHot: temperature > StatusbarLayout.fanTemperatureThreshold)
        }
    }

    func setInitialTemperature(_ temperature: Float) {
        guard temperature.isFinite else { return }
        updateRotationSpeed(forTemperature: temperature)
        applyColor(isHot: temperature > StatusbarLayout.fanTemperatureThreshold)
    }

    private func applyColor(isHot newValue: Bool) {
        isHot = newValue
        let color = (newValue ? StatusbarLayout.highlightColor : StatusbarLayout.fanNormalColor).cgColor
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        bladesLayer.fillColor = color
        CATransaction.commit()
    }

    /// Returns the requested revolution period. The function is continuous at
    /// fanTemperatureThreshold, gentle below it, and substantially steeper above it.
    private func revolutionPeriod(forTemperature temperature: Float) -> Double {
        let minimum = StatusbarLayout.fanMinimumTemperature
        let maximum = StatusbarLayout.fanMaximumTemperature
        let threshold = Double(StatusbarLayout.fanTemperatureThreshold)
        let value = min(maximum, max(minimum, Double(temperature)))
        let rotationsPerSecond: Double
        if value <= threshold {
            let progress = (value - minimum) / (threshold - minimum)
            rotationsPerSecond = 0.1 + 0.4 * pow(progress, 1.7)
        } else {
            let progress = (value - threshold) / (maximum - threshold)
            rotationsPerSecond = 0.5 + ((1.0 / 0.3) - 0.5) * pow(progress, 0.9)
        }
        return 1.0 / rotationsPerSecond
    }

    private func updateRotationSpeed(forTemperature temperature: Float) {
        let period = revolutionPeriod(forTemperature: temperature)
        let newSpeed = Float(StatusbarLayout.fanBaseRevolutionPeriod / period) // one persistent base-period animation
        guard abs(newSpeed - currentLayerSpeed) > 0.0001 else { return }

        // Preserve the current layer-local time as the new speed takes effect.
        // Local time is the animation phase source; no animation is removed/re-added.
        let now = CACurrentMediaTime()
        let currentLocalTime = rotorLayer.convertTime(now, from: nil)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        rotorLayer.speed = newSpeed
        rotorLayer.beginTime = now
        rotorLayer.timeOffset = currentLocalTime
        CATransaction.commit()
        currentLayerSpeed = newSpeed
    }

    private func configurePaths() {
        let side = max(bounds.width, bounds.height)
        guard side > 0 else { return }
        let center = CGPoint(x: side / 2.0, y: side / 2.0)

        // REFERENCE_TRACE_POINTS: initial mockup contour traced from its blade silhouette.
        // Coordinates are normalized from the original four-lobed icon, rather than a generic fan glyph.
        // The contour is smoothed from the original image mask to retain a round outer cap and narrow swept root.
        let contourPoints: [CGPoint] = [
            CGPoint(x: side * 0.49518, y: side * 0.99508),
            CGPoint(x: side * 0.46909, y: side * 0.98574),
            CGPoint(x: side * 0.44274, y: side * 0.97778),
            CGPoint(x: side * 0.41687, y: side * 0.96582),
            CGPoint(x: side * 0.39465, y: side * 0.94588),
            CGPoint(x: side * 0.37605, y: side * 0.92223),
            CGPoint(x: side * 0.36100, y: side * 0.89875),
            CGPoint(x: side * 0.35032, y: side * 0.87304),
            CGPoint(x: side * 0.34583, y: side * 0.84411),
            CGPoint(x: side * 0.34702, y: side * 0.81426),
            CGPoint(x: side * 0.34740, y: side * 0.78354),
            CGPoint(x: side * 0.34578, y: side * 0.75285),
            CGPoint(x: side * 0.35022, y: side * 0.72483),
            CGPoint(x: side * 0.36331, y: side * 0.69988),
            CGPoint(x: side * 0.37153, y: side * 0.67257),
            CGPoint(x: side * 0.38611, y: side * 0.64960),
            CGPoint(x: side * 0.40286, y: side * 0.62351),
            CGPoint(x: side * 0.42378, y: side * 0.61909),
            CGPoint(x: side * 0.44925, y: side * 0.63243),
            CGPoint(x: side * 0.47396, y: side * 0.64545),
            CGPoint(x: side * 0.50264, y: side * 0.64703),
            CGPoint(x: side * 0.51464, y: side * 0.67107),
            CGPoint(x: side * 0.52779, y: side * 0.69578),
            CGPoint(x: side * 0.54239, y: side * 0.72039),
            CGPoint(x: side * 0.55953, y: side * 0.74304),
            CGPoint(x: side * 0.57741, y: side * 0.76541),
            CGPoint(x: side * 0.59418, y: side * 0.78953),
            CGPoint(x: side * 0.61215, y: side * 0.81301),
            CGPoint(x: side * 0.63407, y: side * 0.83292),
            CGPoint(x: side * 0.65977, y: side * 0.84906),
            CGPoint(x: side * 0.68288, y: side * 0.86686),
            CGPoint(x: side * 0.69663, y: side * 0.89162),
            CGPoint(x: side * 0.69800, y: side * 0.92043),
            CGPoint(x: side * 0.68602, y: side * 0.94574),
            CGPoint(x: side * 0.66222, y: side * 0.96290),
            CGPoint(x: side * 0.63429, y: side * 0.97447),
            CGPoint(x: side * 0.60904, y: side * 0.98333),
            CGPoint(x: side * 0.58095, y: side * 0.98727),
            CGPoint(x: side * 0.55215, y: side * 0.99294),
            CGPoint(x: side * 0.52537, y: side * 1.00008)
        ]

        // Mirror the traced blade horizontally around the rotor centre.
        // This reverses the blade sweep seen in the previous build, while preserving
        // the exact silhouette, fourfold layout, hub and clockwise rotor animation.
        let mirroredContourPoints = contourPoints.map {
            CGPoint(x: side - $0.x, y: $0.y)
        }

        let blade = CGMutablePath()
        let pointCount = mirroredContourPoints.count
        if pointCount > 2 {
            blade.move(to: mirroredContourPoints[0])
            // Smooth the mirrored screenshot-traced contour with closed Catmull-Rom-to-Bezier
            // segments. This avoids a polygonal appearance at the 16 pt menu-bar size.
            for index in 0..<pointCount {
                let p0 = mirroredContourPoints[(index - 1 + pointCount) % pointCount]
                let p1 = mirroredContourPoints[index]
                let p2 = mirroredContourPoints[(index + 1) % pointCount]
                let p3 = mirroredContourPoints[(index + 2) % pointCount]
                let control1 = CGPoint(
                    x: p1.x + (p2.x - p0.x) / 6.0,
                    y: p1.y + (p2.y - p0.y) / 6.0
                )
                let control2 = CGPoint(
                    x: p2.x - (p3.x - p1.x) / 6.0,
                    y: p2.y - (p3.y - p1.y) / 6.0
                )
                blade.addCurve(to: p2, control1: control1, control2: control2)
            }
            blade.closeSubpath()
        }

        // Rotate the traced lobe around the exact center four times. Keeping the gaps
        // and asymmetry of this contour is what makes it match the reference fan symbol.
        let allBlades = CGMutablePath()
        for index in 0..<4 {
            let angle = CGFloat(index) * CGFloat.pi / 2.0
            let cosine = cos(angle)
            let sine = sin(angle)
            let transform = CGAffineTransform(
                a: cosine,
                b: sine,
                c: -sine,
                d: cosine,
                tx: center.x - cosine * center.x + sine * center.y,
                ty: center.y - sine * center.x - cosine * center.y
            )
            allBlades.addPath(blade, transform: transform)
        }
        bladesLayer.path = allBlades
        bladesLayer.fillColor = (isHot ? StatusbarLayout.highlightColor : StatusbarLayout.fanNormalColor).cgColor

        // The reference uses a white circular hub with a narrow dark outline.
        // This stroke remains independent of the temperature-colored blades.
        let hubRadius = side * 0.090
        hubLayer.path = CGPath(
            ellipseIn: CGRect(x: center.x - hubRadius, y: center.y - hubRadius,
                             width: hubRadius * 2.0, height: hubRadius * 2.0),
            transform: nil
        )
        hubLayer.fillColor = NSColor.white.cgColor
        hubLayer.strokeColor = NSColor(calibratedWhite: 0.12, alpha: 1).cgColor
        hubLayer.lineWidth = 0.5
        hubLayer.lineJoin = .round
    }
}

/// Physical-memory snapshot; all values are byte counts and pie segments sum
/// to installed physical RAM. App memory follows the requested internal-purgeable estimate.
private struct MemorySnapshot {
    let availableBytes: UInt64
    let appBytes: UInt64
    let wiredBytes: UInt64
    let compressedBytes: UInt64
    /// Estimated pressure derived from memory_pressure's system-wide free percentage.
    /// nil means the command failed or its output could not be parsed.
    let pressurePercent: Int?

    var usedBytes: UInt64 { appBytes + wiredBytes + compressedBytes }
    var totalBytes: UInt64 { availableBytes + usedBytes }
    var availableGB: Double { Double(availableBytes) / 1_073_741_824.0 }
    var appGB: Double { Double(appBytes) / 1_073_741_824.0 }
    var wiredGB: Double { Double(wiredBytes) / 1_073_741_824.0 }
    var compressedGB: Double { Double(compressedBytes) / 1_073_741_824.0 }
    var usedGB: Double { Double(usedBytes) / 1_073_741_824.0 }

    static let zero = MemorySnapshot(availableBytes: 0, appBytes: 0, wiredBytes: 0, compressedBytes: 0, pressurePercent: nil)
}

/// memory_pressure reports system-wide free percentage, not Activity Monitor's private
/// pressure score. Convert free% to an approximate pressure estimate (100 - free%).
/// Sampled once per existing one-second update; no second timer is created.
private enum MemoryPressureSampler {
    static func samplePercent() -> Int? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/memory_pressure")
        process.arguments = ["-Q"]
        let output = Pipe()
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice
        do {
            try process.run()
            let data = output.fileHandleForReading.readDataToEndOfFile()
            process.waitUntilExit()
            guard process.terminationStatus == 0,
                  let text = String(data: data, encoding: .utf8) else { return nil }
            let pattern = #"(?i)System-wide memory free percentage:\s*(\d+(?:\.\d+)?)\s*%"#
            guard let range = text.range(of: pattern, options: .regularExpression),
                  let numberRange = text[range].range(of: #"\d+(?:\.\d+)?"#, options: .regularExpression),
                  let freePercent = Double(text[numberRange]), freePercent.isFinite else { return nil }
            return min(100, max(0, Int((100.0 - freePercent).rounded())))
        } catch {
            return nil
        }
    }
}

/// Sampled once per existing one-second status-bar update; no extra timer is created.
private enum MemorySampler {
    static func sample() -> MemorySnapshot? {
        var statistics = vm_statistics64_data_t()
        let capacity = MemoryLayout<vm_statistics64_data_t>.size / MemoryLayout<integer_t>.size
        var count = mach_msg_type_number_t(capacity)
        var pageSize: vm_size_t = 0

        let host = mach_host_self()
        defer { mach_port_deallocate(mach_task_self_, host) }

        guard host_page_size(host, &pageSize) == KERN_SUCCESS, pageSize > 0 else { return nil }
        let result = withUnsafeMutablePointer(to: &statistics) { pointer in
            pointer.withMemoryRebound(to: integer_t.self, capacity: capacity) {
                host_statistics64(host, HOST_VM_INFO64, $0, &count)
            }
        }
        guard result == KERN_SUCCESS else { return nil }

        let total = ProcessInfo.processInfo.physicalMemory
        guard total > 0 else { return nil }
        let pageBytes = UInt64(pageSize)
        let internalPages = UInt64(statistics.internal_page_count)
        let purgeablePages = UInt64(statistics.purgeable_count)
        let appPages = internalPages > purgeablePages ? internalPages - purgeablePages : 0

        let rawApp = appPages * pageBytes
        let rawWired = UInt64(statistics.wire_count) * pageBytes
        let rawCompressed = UInt64(statistics.compressor_page_count) * pageBytes

        // Clamp defensively so category totals cannot exceed physical RAM.
        var remaining = total
        let app = min(rawApp, remaining); remaining -= app
        let wired = min(rawWired, remaining); remaining -= wired
        let compressed = min(rawCompressed, remaining); remaining -= compressed
        let available = remaining
        return MemorySnapshot(
            availableBytes: available,
            appBytes: app,
            wiredBytes: wired,
            compressedBytes: compressed,
            pressurePercent: MemoryPressureSampler.samplePercent()
        )
    }
}

private final class MemoryColorDotView: NSView {
    var color: NSColor = .green { didSet { needsDisplay = true } }

    override func draw(_ dirtyRect: NSRect) {
        color.setFill()
        NSBezierPath(ovalIn: bounds.insetBy(dx: 0.25, dy: 0.25)).fill()
    }
}

/// Native popover tooltip with fixed 128-point width and four same-color dots.
private final class MemoryTooltipViewController: NSViewController {
    private var valueFields: [NSTextField] = []
    private var pressureField: NSTextField?
    private let rowLabels = ["可用内存：", "App 内存：", "联动内存：", "压缩内存："]
    private let rowColors = [
        StatusbarLayout.availableColor,
        StatusbarLayout.appMemoryColor,
        StatusbarLayout.wiredColor,
        StatusbarLayout.compressedColor
    ]

    override func loadView() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: 128, height: 108))
        let pressureDot = MemoryColorDotView(frame: NSRect(x: 8, y: 86, width: 7, height: 7))
        pressureDot.color = StatusbarLayout.memoryPressureDotColor
        content.addSubview(pressureDot)
        let pressure = NSTextField(labelWithString: "内存压力：--%")
        pressure.frame = NSRect(x: 20, y: 81, width: 100, height: 16)
        pressure.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        pressure.textColor = NSColor.labelColor
        content.addSubview(pressure)
        pressureField = pressure
        for index in 0..<4 {
            let rowY = CGFloat(65 - index * 19)
            let dot = MemoryColorDotView(frame: NSRect(x: 8, y: rowY + 1, width: 7, height: 7))
            dot.color = rowColors[index]
            content.addSubview(dot)

            let field = NSTextField(labelWithString: "")
            field.frame = NSRect(x: 20, y: rowY - 3, width: 101, height: 16)
            field.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            field.textColor = NSColor.labelColor
            field.lineBreakMode = .byTruncatingTail
            content.addSubview(field)
            valueFields.append(field)
        }
        view = content
    }

    func update(snapshot: MemorySnapshot) {
        // Accessing view triggers lazy loading and is compatible with macOS 10.13.
        _ = self.view
        let pressureText = snapshot.pressurePercent.map { "内存压力：\($0)%" } ?? "内存压力：--%"
        if pressureField?.stringValue != pressureText { pressureField?.stringValue = pressureText }
        let values = [snapshot.availableGB, snapshot.appGB, snapshot.wiredGB, snapshot.compressedGB]
        for index in 0..<min(valueFields.count, values.count) {
            let newText = rowLabels[index] + String(format: "%.1fG", values[index])
            if valueFields[index].stringValue != newText {
                valueFields[index].stringValue = newText
            }
        }
    }
}

// END statusbar-fan-memory patch (2026-10-22)
'''

NEW_STATUSBAR_VIEW = r'''fileprivate class StatusbarView: NSView {
    var meanFreq: Float = 0
    var maxFreq: Float = 0
    var temp: Float = 0
    var pwr: Float = 0
    private var memorySnapshot = MemorySnapshot.zero

    var normalLabel: [NSAttributedString.Key: NSObject]?
    var compactLabel: [NSAttributedString.Key: NSObject]?
    var normalValue: [NSAttributedString.Key: NSObject]?
    var compactValue: [NSAttributedString.Key: NSObject]?

    private var fanIndicatorView: FanIndicatorView?
    private var memoryPopover: NSPopover?
    private var memoryTooltipController: MemoryTooltipViewController?
    private var memoryTrackingArea: NSTrackingArea?
    private var hoveringMemoryPie = false
    private var previousFanTemperature: Float?

    func setup() {
        let compactLineHeight: CGFloat = 6
        let paragraphStyle = NSMutableParagraphStyle()
        paragraphStyle.minimumLineHeight = compactLineHeight
        paragraphStyle.maximumLineHeight = compactLineHeight

        compactLabel = [
            .font: NSFont(name: "Monaco", size: 7)!,
            .foregroundColor: NSColor.labelColor,
            .paragraphStyle: paragraphStyle
        ]
        normalValue = [
            .font: NSFont.systemFont(ofSize: 14, weight: .regular),
            .foregroundColor: NSColor.labelColor
        ]
        compactValue = [
            .font: NSFont.systemFont(ofSize: 10, weight: .semibold),
            .foregroundColor: NSColor.labelColor
        ]
        normalLabel = [
            .font: NSFont.systemFont(ofSize: 12, weight: .regular),
            .foregroundColor: NSColor.labelColor
        ]

        let fan = FanIndicatorView(frame: NSRect(
            x: StatusbarLayout.fanX, y: 0,
            width: StatusbarLayout.fanSize, height: StatusbarLayout.fanSize
        ))
        fanIndicatorView = fan
        addSubview(fan)

        let tooltipController = MemoryTooltipViewController(nibName: nil, bundle: nil)
        let popover = NSPopover()
        popover.behavior = .transient
        popover.contentSize = NSSize(width: 128, height: 108)
        popover.contentViewController = tooltipController
        memoryTooltipController = tooltipController
        memoryPopover = popover
        tooltipController.update(snapshot: memorySnapshot)
    }

    override func layout() {
        super.layout()
        fanIndicatorView?.frame = NSRect(
            x: StatusbarLayout.fanX,
            y: max(0, (bounds.height - StatusbarLayout.fanSize) / 2.0),
            width: StatusbarLayout.fanSize,
            height: StatusbarLayout.fanSize
        )
        fanIndicatorView?.needsLayout = true
        refreshMemoryTrackingArea()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        refreshMemoryTrackingArea()
    }

    private var memoryPieRect: NSRect {
        NSRect(
            x: StatusbarLayout.memoryPieX,
            y: max(0, (bounds.height - StatusbarLayout.memoryPieSize) / 2.0),
            width: StatusbarLayout.memoryPieSize,
            height: StatusbarLayout.memoryPieSize
        )
    }

    private func refreshMemoryTrackingArea() {
        if let oldArea = memoryTrackingArea {
            removeTrackingArea(oldArea)
            memoryTrackingArea = nil
        }
        guard bounds.height >= StatusbarLayout.memoryPieSize else { return }
        let area = NSTrackingArea(
            rect: memoryPieRect,
            options: [.mouseEnteredAndExited, .activeAlways],
            owner: self,
            userInfo: nil
        )
        memoryTrackingArea = area
        addTrackingArea(area)
    }

    override func mouseEntered(with event: NSEvent) {
        guard let area = memoryTrackingArea, event.trackingArea === area else {
            super.mouseEntered(with: event)
            return
        }
        hoveringMemoryPie = true
        memoryTooltipController?.update(snapshot: memorySnapshot)
        if let popover = memoryPopover, !popover.isShown {
            popover.show(relativeTo: memoryPieRect, of: self, preferredEdge: .minY)
        }
    }

    override func mouseExited(with event: NSEvent) {
        guard let area = memoryTrackingArea, event.trackingArea === area else {
            super.mouseExited(with: event)
            return
        }
        hoveringMemoryPie = false
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.65) { [weak self] in
            guard let self = self, !self.hoveringMemoryPie else { return }
            if let popover = self.memoryPopover, popover.isShown {
                popover.performClose(nil)
            }
        }
    }

    func closeMemoryTooltip() {
        hoveringMemoryPie = false
        if let popover = memoryPopover, popover.isShown {
            popover.performClose(nil)
        }
    }

    func updateMetrics(meanFreq: Float, maxFreq: Float, temperature: Float, power: Float,
                       memory: MemorySnapshot?) {
        self.meanFreq = meanFreq
        self.maxFreq = maxFreq
        self.temp = temperature
        self.pwr = power
        if let memory = memory {
            memorySnapshot = memory
            memoryTooltipController?.update(snapshot: memory)
        }

        if let previous = previousFanTemperature {
            if previous != temperature {
                let crossed = (previous > StatusbarLayout.fanTemperatureThreshold)
                    != (temperature > StatusbarLayout.fanTemperatureThreshold)
                fanIndicatorView?.updateTemperature(temperature, crossedThreshold: crossed)
                previousFanTemperature = temperature
            }
        } else {
            fanIndicatorView?.setInitialTemperature(temperature)
            previousFanTemperature = temperature
        }
        setNeedsDisplay(bounds)
    }

    override func draw(_ dirtyRect: NSRect) {
        guard NSGraphicsContext.current?.cgContext != nil else { return }

        let averageFrequencyGHz = meanFreq * 0.001
        let maximumFrequencyGHz = maxFreq * 0.001
        let averageFrequency = String(format: "%.1f", averageFrequencyGHz)
        let maximumFrequency = String(format: "%.1f", maximumFrequencyGHz)

        // The fan replaces the former CPU text label. CPU values start six points
        // after the 16-point fan, and keep the original top/bottom arrangement.
        drawDoubleCompactValue(
            up: "\(maximumFrequency)ᴳ",
            down: "\(averageFrequency)ᴳ",
            x: StatusbarLayout.cpuValueX,
            upColor: maximumFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor,
            downColor: averageFrequencyGHz > StatusbarLayout.frequencyThreshold ? StatusbarLayout.highlightColor : .labelColor
        )

        drawCompactSingle(
            label: "TMP",
            value: "\(Int(round(temp)))º",
            x: StatusbarLayout.temperatureX,
            valueColor: temp > StatusbarLayout.temperatureThreshold ? StatusbarLayout.highlightColor : .labelColor
        )

        drawCompactSingle(
            label: "PWR",
            value: "\(Int(round(pwr)))ᵂ",
            x: StatusbarLayout.powerX,
            valueColor: pwr > StatusbarLayout.powerThreshold ? StatusbarLayout.highlightColor : .labelColor,
            rightAligned: true,
            valueWidth: StatusbarLayout.powerValueWidth
        )

        drawMemoryPie()
        drawMemoryValues()
    }

    private func drawMemoryPie() {
        let rect = memoryPieRect
        let center = NSPoint(x: rect.midX, y: rect.midY)
        let radius = min(rect.width, rect.height) / 2.0
        let pieces: [(UInt64, NSColor)] = [
            (memorySnapshot.availableBytes, StatusbarLayout.availableColor),
            (memorySnapshot.appBytes, StatusbarLayout.appMemoryColor),
            (memorySnapshot.wiredBytes, StatusbarLayout.wiredColor),
            (memorySnapshot.compressedBytes, StatusbarLayout.compressedColor)
        ]
        let total = pieces.reduce(UInt64(0)) { $0 + $1.0 }
        guard total > 0 else {
            StatusbarLayout.availableColor.setFill()
            NSBezierPath(ovalIn: rect).fill()
            return
        }

        var startAngle: CGFloat = 90.0
        for (bytes, color) in pieces where bytes > 0 {
            let sweep = CGFloat(Double(bytes) / Double(total) * 360.0)
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
            path.fill() // intentionally no black outline/stroke
            startAngle = endAngle
        }

        // A pressure ring sits just outside the pie; the progress color changes above the configured threshold.
        let ringRect = rect.insetBy(dx: -StatusbarLayout.memoryPressureRingInset,
                                    dy: -StatusbarLayout.memoryPressureRingInset)
        let track = NSBezierPath(ovalIn: ringRect)
        track.lineWidth = StatusbarLayout.memoryPressureRingWidth
        StatusbarLayout.memoryPressureTrackColor.setStroke()
        track.stroke()
        if let pressure = memorySnapshot.pressurePercent, pressure > 0 {
            let arc = NSBezierPath()
            arc.lineWidth = StatusbarLayout.memoryPressureRingWidth
            arc.lineCapStyle = .round
            let startAngle: CGFloat = 90
            let endAngle = startAngle - 360.0 * CGFloat(min(100, max(0, pressure))) / 100.0
            arc.appendArc(withCenter: center,
                          radius: radius + StatusbarLayout.memoryPressureRingInset,
                          startAngle: startAngle,
                          endAngle: endAngle,
                          clockwise: true)
            let pressureColor = pressure > StatusbarLayout.memoryPressureThreshold
                ? StatusbarLayout.highlightColor
                : StatusbarLayout.memoryPressureRingColor
            pressureColor.setStroke()
            arc.stroke()
        }
    }

    private func drawMemoryValues() {
        var attributes = compactValue ?? [:]
        attributes[.foregroundColor] = NSColor.labelColor
        let available = String(format: "%.1fG", memorySnapshot.availableGB)
        let used = String(format: "%.1fG", memorySnapshot.usedGB)
        drawRightAlignedValue(available, x: StatusbarLayout.memoryValueX,
                              y: StatusbarLayout.frequencyTopY,
                              width: StatusbarLayout.memoryValueWidth, attributes: attributes)
        drawRightAlignedValue(used, x: StatusbarLayout.memoryValueX,
                              y: StatusbarLayout.frequencyBottomY,
                              width: StatusbarLayout.memoryValueWidth, attributes: attributes)
    }

    private func drawRightAlignedValue(_ text: String, x: CGFloat, y: CGFloat,
                                       width: CGFloat,
                                       attributes: [NSAttributedString.Key: NSObject]) {
        let measuredWidth = (text as NSString).size(withAttributes: attributes).width
        NSAttributedString(string: text, attributes: attributes).draw(
            at: NSPoint(x: x + max(0, width - measuredWidth), y: y)
        )
    }

    private func drawVerticalLabel(_ label: String, x: CGFloat) {
        let attributedLabel = NSAttributedString(string: label, attributes: compactLabel)
        attributedLabel.draw(in: NSRect(
            x: x,
            y: StatusbarLayout.labelOriginY,
            width: StatusbarLayout.labelWidth,
            height: bounds.height
        ))
    }

    private func drawDoubleCompactValue(up: String, down: String, x: CGFloat,
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

    private func drawCompactSingle(label: String, value: String, x: CGFloat,
                                   valueColor: NSColor = .labelColor,
                                   rightAligned: Bool = false,
                                   valueWidth: CGFloat = 0) {
        drawVerticalLabel(label, x: x)
        var attributes = normalValue ?? [:]
        attributes[.foregroundColor] = valueColor
        if rightAligned {
            let valueX = x + StatusbarLayout.metricValueOffsetX
            let measuredWidth = (value as NSString).size(withAttributes: attributes).width
            NSAttributedString(string: value, attributes: attributes).draw(
                at: NSPoint(x: valueX + max(0, valueWidth - measuredWidth),
                            y: StatusbarLayout.valueOriginY)
            )
        } else {
            NSAttributedString(string: value, attributes: attributes).draw(
                at: NSPoint(x: x + StatusbarLayout.metricValueOffsetX,
                            y: StatusbarLayout.valueOriginY)
            )
        }
    }
}
'''

TIMER_OLD = '''        updateTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true, block: { _ in
            self.update()
        })'''
TIMER_NEW = '''        updateTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true, block: { [weak self] _ in
            self?.update()
        })
        update()'''

DISMISS_OLD = '''    func dismiss() {
        updateTimer?.invalidate()
        NSStatusBar.system.removeStatusItem(statusItem!)
        statusItem = nil
    }'''
DISMISS_NEW = '''    func dismiss() {
        updateTimer?.invalidate()
        updateTimer = nil
        view?.closeMemoryTooltip()
        if let item = statusItem {
            NSStatusBar.system.removeStatusItem(item)
        }
        statusItem = nil
        view = nil
    }'''

UPDATE_NEW = '''    func update() {
        let model = ProcessorModel.shared
        let numberOfCores = model.getNumOfCore()
        guard numberOfCores > 0 else { return }
        let outputStr = model.getMetric(forced: false)
        guard outputStr.count > numberOfCores + 2 else { return }

        let power = outputStr[0]
        let temperature = outputStr[1]
        var frequencies: [Float] = []
        for index in 0..<numberOfCores {
            frequencies.append(outputStr[index + 3])
        }
        guard !frequencies.isEmpty, let maximum = frequencies.max() else { return }
        let mean = frequencies.reduce(0, +) / Float(frequencies.count)

        // Exactly one memory sample per existing one-second update; no second timer.
        let memory = MemorySampler.sample()
        view?.updateMetrics(
            meanFreq: mean,
            maxFreq: maximum,
            temperature: temperature,
            power: power,
            memory: memory
        )
    }
'''

HEADER_OLD = "import Cocoa\n"
HEADER_NEW = "import Cocoa\nimport Darwin.Mach\nimport QuartzCore\n"


def fail(message):
    print("ERROR: " + message, file=sys.stderr)
    raise SystemExit(1)


def replace_once(source, old, new, description):
    count = source.count(old)
    if count != 1:
        fail("Anchor check failed for '{}': expected exactly 1 occurrence, found {}.".format(description, count))
    return source.replace(old, new, 1)


def validate_patched_source(source):
    requirements = [
        (PATCH_MARKER, "patch marker"),
        ("private final class FanIndicatorView", "fan indicator class"),
        ("private enum MemorySampler", "memory sampler"),
        ("private enum MemoryPressureSampler", "memory pressure command sampler"),
        ("/usr/bin/memory_pressure", "memory_pressure command path"),
        ("pressurePercent: MemoryPressureSampler.samplePercent()", "pressure percentage attached to snapshot"),
        ("memoryPressureRingColor", "memory pressure ring color"),
        ("static let memoryPressureRingColor = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 1)", "white memory pressure ring color"),
        ("static let memoryPressureTrackColor = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 0.5)", "translucent white pressure track color"),
        ("static let memoryPressureThreshold: Int = 70", "configurable memory pressure threshold"),
        ("pressure > StatusbarLayout.memoryPressureThreshold", "pressure ring threshold comparison"),
        ("? StatusbarLayout.highlightColor", "highlight color above threshold"),
        ("内存压力：--%", "first tooltip memory pressure row"),
        ("host_statistics64(host, HOST_VM_INFO64", "host VM statistics query"),
        ("mach_port_deallocate(mach_task_self_, host)", "Mach port release"),
        ("rotation.repeatCount = .infinity", "infinite fan rotation"),
        ("rotorLayer.add(rotation, forKey: \"fan.rotation\")", "single rotation animation installation"),
        ("rotorLayer.timeOffset = currentLocalTime", "phase-preserving speed update"),
        ("[weak self] _ in", "weak timer capture"),
        ("popover.contentSize = NSSize(width: 128, height: 108)", "128-point pressure-enabled hover tooltip"),
        ("static let fanTemperatureThreshold: Float = 65", "fan color threshold"),
        ("static let fanMinimumTemperature: Double = 45.0", "fan minimum temperature variable"),
        ("static let fanMaximumTemperature: Double = 85.0", "fan maximum temperature variable"),
        ("static let fanBaseRevolutionPeriod: Double = 10.0", "fan base revolution period variable"),
        ("let threshold = Double(StatusbarLayout.fanTemperatureThreshold)", "speed curve threshold uses configured variable"),
        ("let minimum = StatusbarLayout.fanMinimumTemperature", "speed curve minimum uses configured variable"),
        ("let maximum = StatusbarLayout.fanMaximumTemperature", "speed curve maximum uses configured variable"),
        ("REFERENCE_TRACE_POINTS: initial mockup contour traced from its blade silhouette.", "reference-traced four-blade silhouette"),
        ("let mirroredContourPoints = contourPoints.map {", "mirrored blade sweep"),
        ("CGPoint(x: side - $0.x, y: $0.y)", "horizontal contour reflection"),
        ("let hubRadius = side * 0.090", "reference-sized outlined white center hub"),
        ("hubLayer.strokeColor = NSColor(calibratedWhite: 0.12, alpha: 1).cgColor", "outlined white hub"),
        ("static let memoryPieSize: CGFloat = 16", "16-point memory pie"),
        ("static let fanSize: CGFloat = 18", "18-point fan"),
        ("static let frequencyValueOffsetX: CGFloat = 2", "frequency value offset"),
        ("_ = self.view", "macOS 10.13-compatible lazy tooltip view loading"),
    ]
    for needle, label in requirements:
        if needle not in source:
            fail("Post-patch validation failed: missing {}.".format(label))
    if "hubLayer.fillColor = color" in source:
        fail("Fan threshold color must affect blades only; the center hub must stay white.")
    if "loadViewIfNeeded()" in source:
        fail("Unsupported loadViewIfNeeded() call detected; use _ = self.view for macOS 10.13 compatibility.")
    if source.count('rotorLayer.add(rotation, forKey: "fan.rotation")') != 1:
        fail("Expected exactly one code path that installs the immutable rotation animation.")
    if "removeAnimation(forKey: \"fan.rotation\")" in source:
        fail("Unexpected remove/recreate animation path detected.")
    return True


def transform_source(source):
    if PATCH_MARKER in source or "private final class FanIndicatorView" in source:
        fail("The source already appears patched; refusing to apply twice. Restore the backup or start from a clean main-branch file.")

    layout_anchor = "private enum StatusbarLayout {\n"
    view_anchor = "fileprivate class StatusbarView: NSView {\n"
    controller_anchor = "\nclass StatusbarController {\n"
    for anchor, label in ((layout_anchor, "layout enum"), (view_anchor, "status view class"),
                          (controller_anchor, "controller class"), (HEADER_OLD, "Cocoa import"),
                          (TIMER_OLD, "one-second timer"), (DISMISS_OLD, "dismiss lifecycle")):
        if source.count(anchor) != 1:
            fail("Anchor check failed for '{}': expected exactly 1 occurrence, found {}.".format(label, source.count(anchor)))

    layout_start = source.index(layout_anchor)
    view_start = source.index(view_anchor, layout_start)
    if view_start <= layout_start:
        fail("Anchor order invalid: StatusbarView must follow StatusbarLayout.")
    source = source[:layout_start] + NEW_LAYOUT_AND_HELPERS + "\n\n" + source[view_start:]

    class_start = source.index(view_anchor)
    controller_start = source.index(controller_anchor, class_start)
    source = source[:class_start] + NEW_STATUSBAR_VIEW + "\n\nclass StatusbarController {\n" + source[controller_start + len(controller_anchor):]

    source = replace_once(source, HEADER_OLD, HEADER_NEW, "framework imports")
    source = replace_once(source, TIMER_OLD, TIMER_NEW, "weak one-second timer")
    source = replace_once(source, DISMISS_OLD, DISMISS_NEW, "weak timer / popover teardown")

    update_start_anchor = "    func update() {\n"
    item_clicked_anchor = "\n    @objc func itemClicked() {"
    if source.count(update_start_anchor) != 1 or source.count(item_clicked_anchor) != 1:
        fail("Anchor check failed for the StatusbarController.update() method boundary.")
    update_start = source.index(update_start_anchor)
    update_end = source.index(item_clicked_anchor, update_start)
    if update_end <= update_start:
        fail("Anchor order invalid: itemClicked() must follow update().")
    source = source[:update_start] + UPDATE_NEW + source[update_end:]
    validate_patched_source(source)
    return source


def make_test_fixture():
    # Exact structural anchors used by the current main-branch StatusbarController.swift.
    # This checks transformation mechanics only; it is not a substitute for macOS compilation.
    return '''import Cocoa
private enum StatusbarLayout {
    static let itemWidth: CGFloat = 92
}
fileprivate class StatusbarView: NSView {
}
class StatusbarController {
    var statusItem: NSStatusItem!
    fileprivate var view: StatusbarView!
    var updateTimer: Timer?
    init() {
        updateTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true, block: { _ in
            self.update()
        })
    }
    func dismiss() {
        updateTimer?.invalidate()
        NSStatusBar.system.removeStatusItem(statusItem!)
        statusItem = nil
    }
    func update() {
        let old = true
    }
    @objc func itemClicked() {
    }
}
'''


def run_self_test():
    patched = transform_source(make_test_fixture())
    validate_patched_source(patched)
    # Check endpoint periods and continuity at the configurable fan threshold (65 C).
    def period(temp):
        minimum, threshold, maximum, base_period = 45.0, 65.0, 85.0, 10.0
        value = min(maximum, max(minimum, float(temp)))
        if value <= threshold:
            x = (value - minimum) / (threshold - minimum)
            rps = 0.1 + 0.4 * (x ** 1.7)
        else:
            x = (value - threshold) / (maximum - threshold)
            rps = 0.5 + ((1.0 / 0.3) - 0.5) * (x ** 0.9)
        return base_period * 0.1 / rps
    assert abs(period(45) - 10.0) < 1e-9, period(45)
    assert abs(period(85) - 0.3) < 1e-9, period(85)
    assert abs(period(65) - 2.0) < 1e-9, period(65)
    assert abs(period(65.000001) - period(65)) < 0.001, (period(65), period(65.000001))
    assert "timeOffset = currentLocalTime" in patched
    assert "let mirroredContourPoints = contourPoints.map {" in patched
    assert "CGPoint(x: side - $0.x, y: $0.y)" in patched
    assert "let pointCount = mirroredContourPoints.count" in patched
    assert "100.0 - freePercent" in patched
    assert "arc.lineCapStyle = .round" in patched
    assert "pressurePercent: Int?" in patched
    assert "static let memoryPressureThreshold: Int = 70" in patched
    assert "pressure > StatusbarLayout.memoryPressureThreshold" in patched
    assert "? StatusbarLayout.highlightColor" in patched
    print("SELF-TEST PASS: anchors, mirrored blade sweep, pressure parser/ring/tooltip, patch transformation, speed endpoints, and mathematical continuity at 65 C.")
    print("NOTE: This does not compile AppKit/QuartzCore code or validate memory_pressure output on macOS. Pressure is an estimate from 100 - system-wide free percentage, not a guaranteed match for Activity Monitor's pressure graph.")


def main():
    parser = argparse.ArgumentParser(description="Patch StatusbarController.swift with low-overhead fan and memory indicators.")
    parser.add_argument("--root", default=".", help="repository root (default: current directory)")
    parser.add_argument("--dry-run", action="store_true", help="validate and print unified diff without writing files")
    parser.add_argument("--check", action="store_true", help="validate anchors and generated source without writing files")
    parser.add_argument("--self-test", action="store_true", help="test patch mechanics and curve endpoints on a synthetic fixture")
    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    root = Path(args.root).expanduser().resolve()
    target = root / TARGET_RELATIVE
    if not target.is_file():
        fail("Cannot find '{}'. Run from the repository root or supply --root /path/to/SMCAMDProcessor.".format(target))

    try:
        original = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail("Cannot read {}: {}".format(target, exc))
    patched = transform_source(original)

    if args.check:
        print("CHECK PASS: all current-source anchors match and the generated source contains the required fan/memory/lifecycle components.")
        print("No files were changed. Note: this is a source/anchor validation, not a macOS build.")
        return

    if args.dry_run:
        diff = difflib.unified_diff(
            original.splitlines(True), patched.splitlines(True),
            fromfile=str(target), tofile=str(target) + " (patched)")
        sys.stdout.writelines(diff)
        print("\nDRY RUN: no files changed.")
        return

    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = target.with_name(target.name + ".before-fan-memory-" + stamp + ".bak")
    suffix = 1
    while backup.exists():
        backup = target.with_name(target.name + ".before-fan-memory-{}-{}.bak".format(stamp, suffix))
        suffix += 1

    try:
        shutil.copy2(str(target), str(backup))
        original_mode = stat.S_IMODE(target.stat().st_mode)
        fd, temp_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
                stream.write(patched)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temp_name, original_mode)
            os.replace(temp_name, str(target))
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        written = target.read_text(encoding="utf-8")
        validate_patched_source(written)
    except Exception as exc:
        # Restore the exact pre-patch file if a write or read-back validation fails.
        if backup.exists():
            shutil.copy2(str(backup), str(target))
        fail("Patch failed; original source restored from backup if it had been created: {}".format(exc))

    print("PATCH PASS: {}".format(target))
    print("BACKUP: {}".format(backup))
    print("Post-write source validation passed. Real Xcode compilation and runtime phase testing have not been performed by this script.")


if __name__ == "__main__":
    main()
