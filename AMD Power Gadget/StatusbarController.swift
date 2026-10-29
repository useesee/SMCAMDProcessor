//
//  StatusbarController.swift
//  AMD Power Gadget
//
//  Menu-bar layout modification:
//  - CPU label is vertical like TEM/PWR.
//  - Layout and spacing are controlled by StatusbarLayout constants.
//  - Temperature turns red above 70 C; power turns red above 10 W.
//

import Cocoa
import Darwin.Mach
import Darwin
import IOKit
import QuartzCore

/// Tweak these constants to adjust menu-bar positions and spacing.
// BEGIN statusbar-fan-memory patch (2026-10-22)
// BEGIN statusbar-cpu-gpu-tooltip patch (2026-10-29)
/// All menu-bar geometry and thresholds are centralized here.
private enum StatusbarLayout {
    static let fanX: CGFloat = 0
    static let fanSize: CGFloat = 18
    static var frequencyValueX: CGFloat = 20
    // 功率在上、温度在下；两行复用 CPU 频率紧凑字形。
    static let powerTemperatureX: CGFloat = 36
    static let powerTemperatureValueWidth: CGFloat = 26
    static let labelWidth: CGFloat = 8
    static let labelOriginY: CGFloat = -4
    static let metricValueOffsetX: CGFloat = 7
    static let valueOriginY: CGFloat = 2.5
    static let frequencyTopY: CGFloat = 9
    static let frequencyBottomY: CGFloat = -1
    static let memoryPieSize: CGFloat = 16
    static let memoryPiePopWidth: CGFloat = 128
    static let memoryPiePopHigh: CGFloat = 128
    static let memoryPieLabelSize: CGFloat = 60
    static let memoryPieValueSize: CGFloat = 60
    static let memoryPressureRingInset: CGFloat = 1.5
    static let memoryPressureRingWidth: CGFloat = 1.5
    static let memoryPressureThreshold: Int = 70
    static let memoryPressureRingColor = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 1) // #FFFFFF
    static let memoryPressureTrackColor = NSColor(calibratedRed: 1, green: 1, blue: 1, alpha: 0.5) // #FFFFFF80
    static let memoryPressureDotColor = memoryPressureRingColor
    static var memoryPieX: CGFloat {
        powerTemperatureX + powerTemperatureValueWidth + 6
    }
    static let memoryPieToValueGap: CGFloat = 4
    static let cpuPieSize: CGFloat = 16
    static let cpuPiePopWidth: CGFloat = 128
    static let cpuPiePopHigh: CGFloat = 108
    static let cpuPieLabelSize: CGFloat = 58
    static let cpuPieValueSize: CGFloat = 80
    static let cpuPieRingInset: CGFloat = 1.5
    static let cpuPieRingWidth: CGFloat = 1.5
    static let cpuPieToValueGap: CGFloat = 4
    static var memoryValueX: CGFloat {
        memoryPieX + memoryPieSize + memoryPieToValueGap
    }
    static let memoryValueWidth: CGFloat = 28
    static var cpuPieX: CGFloat { memoryValueX + memoryValueWidth + 6 }
    static var cpuValueX: CGFloat { cpuPieX + cpuPieSize + cpuPieToValueGap }
    static let cpuValueWidth: CGFloat = 30
    static var itemWidth: CGFloat { cpuValueX + cpuValueWidth + 2 }
    static let frequencyThreshold: Float = 3.2
    static let cpuUsageThreshold: Double = 50.0
    static let gpuUsageThreshold: Double = 50.0
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
    static let cpuSystemColor = NSColor(calibratedRed: 1, green: 0, blue: 0, alpha: 0.88)
    static let cacheMemoryColor = NSColor(calibratedWhite: 0.60, alpha: 1)
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
        hubLayer.strokeColor = NSColor.white.cgColor
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
    /// File-backed pages (external_page_count), used as a cache-memory estimate.
    let cachedBytes: UInt64
    /// Estimated pressure derived from memory_pressure's system-wide free percentage.
    /// nil means the command failed or its output could not be parsed.
    let pressurePercent: Int?

    var usedBytes: UInt64 { appBytes + wiredBytes + compressedBytes }
    var totalBytes: UInt64 { availableBytes + usedBytes }
    var availableGB: Double { Double(availableBytes) / 1_073_741_824.0 }
    var appGB: Double { Double(appBytes) / 1_073_741_824.0 }
    var wiredGB: Double { Double(wiredBytes) / 1_073_741_824.0 }
    var compressedGB: Double { Double(compressedBytes) / 1_073_741_824.0 }
    var cachedGB: Double { Double(cachedBytes) / 1_073_741_824.0 }
    var usedGB: Double { Double(usedBytes) / 1_073_741_824.0 }

    static let zero = MemorySnapshot(availableBytes: 0, appBytes: 0, wiredBytes: 0, compressedBytes: 0, cachedBytes: 0, pressurePercent: nil)
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
        let rawCached = UInt64(statistics.external_page_count) * pageBytes

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
            cachedBytes: min(rawCached, total),
            pressurePercent: MemoryPressureSampler.samplePercent()
        )
    }
}


/// Menu-bar CPU/GPU values sampled from the existing one-second status-bar update.
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

private final class MemoryColorDotView: NSView {
    var color: NSColor = .green { didSet { needsDisplay = true } }

    override func draw(_ dirtyRect: NSRect) {
        color.setFill()
        NSBezierPath(ovalIn: bounds.insetBy(dx: 0.25, dy: 0.25)).fill()
    }
}

/// Native popover tooltip with fixed 128-point width and four same-color dots.
private final class MemoryTooltipViewController: NSViewController {
    private var labelFields: [NSTextField] = []
    private var valueFields: [NSTextField] = []
    private var pressureValueField: NSTextField?
    private let rowLabels = ["可用内存：", "App内存：", "联动内存：", "压缩内存：", "缓存内存："]
    private let rowColors = [
        StatusbarLayout.availableColor,
        StatusbarLayout.appMemoryColor,
        StatusbarLayout.wiredColor,
        StatusbarLayout.compressedColor,
        StatusbarLayout.cacheMemoryColor
    ]

    override func loadView() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: StatusbarLayout.memoryPiePopWidth, height: StatusbarLayout.memoryPiePopHigh))
        let pressureDot = MemoryColorDotView(frame: NSRect(x: 8, y: 110, width: 8, height: 8))
        pressureDot.color = StatusbarLayout.memoryPressureDotColor
        content.addSubview(pressureDot)

        let pressureLabel = NSTextField(labelWithString: "内存压力：")
        pressureLabel.frame = NSRect(x: 18, y: 108, width: StatusbarLayout.memoryPieLabelSize, height: 16)
        pressureLabel.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        pressureLabel.textColor = NSColor.labelColor
        pressureLabel.alignment = .left
        content.addSubview(pressureLabel)

        let pressureValue = NSTextField(labelWithString: "--%")
        pressureValue.frame = NSRect(x: 58, y: 108, width: StatusbarLayout.memoryPieValueSize, height: 16)
        pressureValue.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        pressureValue.textColor = NSColor.labelColor
        pressureValue.alignment = .right
        content.addSubview(pressureValue)
        pressureValueField = pressureValue

        for index in 0..<rowLabels.count {
            let rowY = CGFloat(88 - index * 20)
            let dot = MemoryColorDotView(frame: NSRect(x: 8, y: rowY + 3, width: 8, height: 8))
            dot.color = rowColors[index]
            content.addSubview(dot)

            let label = NSTextField(labelWithString: rowLabels[index])
            label.frame = NSRect(x: 18, y: rowY, width: StatusbarLayout.memoryPieLabelSize, height: 16)
            label.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            label.textColor = NSColor.labelColor
            label.alignment = .left
            label.lineBreakMode = .byTruncatingTail
            content.addSubview(label)
            labelFields.append(label)

            let value = NSTextField(labelWithString: "--.-G")
            value.frame = NSRect(x: 58, y: rowY, width: StatusbarLayout.memoryPieValueSize, height: 16)
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
    private let rowLabels = ["系统：", "用户：", "闲置：", "GPU：", "负载"]
    private let rowColors = [
        StatusbarLayout.cpuSystemColor,
        StatusbarLayout.wiredColor,
        StatusbarLayout.availableColor,
        StatusbarLayout.memoryPressureDotColor,
        StatusbarLayout.appMemoryColor
    ]

    override func loadView() {
        let content = NSView(frame: NSRect(x: 0, y: 0, width: StatusbarLayout.cpuPiePopWidth, height: StatusbarLayout.cpuPiePopHigh))
        for index in 0..<rowLabels.count {
            let rowY = CGFloat(88 - index * 20)
            let dot = MemoryColorDotView(frame: NSRect(x: 8, y: rowY + 3, width: 8, height: 8))
            dot.color = rowColors[index]
            content.addSubview(dot)

            let label = NSTextField(labelWithString: rowLabels[index])
            label.frame = NSRect(x: 18, y: rowY, width: StatusbarLayout.cpuPieLabelSize, height: 16)
            label.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            label.textColor = NSColor.labelColor
            label.alignment = .left
            content.addSubview(label)

            let value = NSTextField(labelWithString: "--.-%")
            value.frame = NSRect(x: 40, y: rowY, width: StatusbarLayout.cpuPieValueSize, height: 16)
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

// END statusbar-fan-memory patch (2026-10-22)


fileprivate class StatusbarView: NSView {
    var meanFreq: Float = 0
    var maxFreq: Float = 0
    var temp: Float = 0
    var pwr: Float = 0
    private var memorySnapshot = MemorySnapshot.zero
    private var cpuSnapshot = CPUSnapshot.zero

    var normalLabel: [NSAttributedString.Key: NSObject]?
    var compactLabel: [NSAttributedString.Key: NSObject]?
    var normalValue: [NSAttributedString.Key: NSObject]?
    var compactValue: [NSAttributedString.Key: NSObject]?

    private var fanIndicatorView: FanIndicatorView?
    private var memoryPopover: NSPopover?
    private var memoryTooltipController: MemoryTooltipViewController?
    private var memoryTrackingArea: NSTrackingArea?
    private var cpuPopover: NSPopover?
    private var cpuTooltipController: CPUTooltipViewController?
    private var cpuTrackingArea: NSTrackingArea?
    private enum TooltipKind: Equatable { case memory, cpu }
    private var activeTooltipKind: TooltipKind?
    private var activeTooltipPopover: NSPopover?
    private var tooltipPositionTimer: Timer?
    private var tooltipOutsideSince: TimeInterval?
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

        let memoryController = MemoryTooltipViewController(nibName: nil, bundle: nil)
        let memoryPopover = NSPopover()
        memoryPopover.behavior = .transient
        memoryPopover.contentSize = NSSize(width: StatusbarLayout.memoryPiePopWidth, height: StatusbarLayout.memoryPiePopHigh)
        memoryPopover.contentViewController = memoryController
        self.memoryTooltipController = memoryController
        self.memoryPopover = memoryPopover
        memoryController.update(snapshot: memorySnapshot)

        let cpuController = CPUTooltipViewController(nibName: nil, bundle: nil)
        let cpuPopover = NSPopover()
        cpuPopover.behavior = .transient
        cpuPopover.contentSize = NSSize(width: StatusbarLayout.cpuPiePopWidth, height: StatusbarLayout.cpuPiePopHigh)
        cpuPopover.contentViewController = cpuController
        self.cpuTooltipController = cpuController
        self.cpuPopover = cpuPopover
        cpuController.update(snapshot: cpuSnapshot)
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
        refreshCPUTrackingArea()
    }

    override func viewDidMoveToWindow() {
        super.viewDidMoveToWindow()
        refreshMemoryTrackingArea()
        refreshCPUTrackingArea()
    }

    private var memoryPieRect: NSRect {
        NSRect(
            x: StatusbarLayout.memoryPieX,
            y: max(0, (bounds.height - StatusbarLayout.memoryPieSize) / 2.0),
            width: StatusbarLayout.memoryPieSize,
            height: StatusbarLayout.memoryPieSize
        )
    }

    private var cpuPieRect: NSRect {
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

    func updateMetrics(meanFreq: Float, maxFreq: Float, temperature: Float, power: Float,
                       memory: MemorySnapshot?, cpu: CPUSnapshot) {
        self.meanFreq = meanFreq
        self.maxFreq = maxFreq
        self.temp = temperature
        self.pwr = power
        if let memory = memory {
            memorySnapshot = memory
            memoryTooltipController?.update(snapshot: memory)
        }
        cpuSnapshot = cpu
        cpuTooltipController?.update(snapshot: cpu)

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

    private func drawCPUPie() {
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
                : StatusbarLayout.memoryPressureRingColor
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


class StatusbarController {

    var statusItem: NSStatusItem!
    fileprivate var view: StatusbarView!

    var updateTimer: Timer?
    var menu: NSMenu?

    init() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.isVisible = true

        view = StatusbarView()
        view.setup()

        statusItem.button?.wantsLayer = true
        statusItem.button?.addSubview(view)

        statusItem.button?.target = self
        statusItem.button?.action = #selector(itemClicked)
        statusItem.button?.sendAction(on: [.leftMouseUp, .rightMouseUp])

        statusItem.length = StatusbarLayout.itemWidth
        view.frame = statusItem.button!.bounds

        addMenuItems()

        updateTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true, block: { [weak self] _ in
            self?.update()
        })
        update()
    }

    func dismiss() {
        updateTimer?.invalidate()
        updateTimer = nil
        view?.closeMemoryTooltip()
        if let item = statusItem {
            NSStatusBar.system.removeStatusItem(item)
        }
        statusItem = nil
        view = nil
    }

    func update() {
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

        // Memory, CPU, GPU and load averages reuse this existing one-second update.
        let memory = MemorySampler.sample()
        let cpu = CPUUsageSampler.sample()
        view?.updateMetrics(
            meanFreq: mean,
            maxFreq: maximum,
            temperature: temperature,
            power: power,
            memory: memory,
            cpu: cpu
        )
    }

    @objc func itemClicked() {
        switch NSApp.currentEvent?.type {
        case .leftMouseUp:
            NSApp.activate(ignoringOtherApps: true)
            ViewController.launch(forceFocus: true)

        case .rightMouseUp:
            guard let m = menu else { return }
            statusItem.popUpMenu(m)

        default:
            break
        }
    }

    @objc func gadget() {
        ViewController.launch(forceFocus: true)
    }

    @objc func tool() {
        PowerToolViewController.launch(forceFocus: true)
    }

    @objc func fans() {
        SystemMonitorViewController.launch(forceFocus: true)
    }

    @objc func exitApp() {
        exit(0)
    }

    private func addMenuItems() {
        menu = NSMenu()
        guard let m = menu else { return }

        var item = NSMenuItem(title: "AMD Power Gadget", action: #selector(gadget), keyEquivalent: "")
        item.target = self
        m.addItem(item)

        item = NSMenuItem(title: "AMD Power Tool", action: #selector(tool), keyEquivalent: "")
        item.target = self
        m.addItem(item)

        item = NSMenuItem(title: "SMC Fans", action: #selector(fans), keyEquivalent: "")
        item.target = self
        m.addItem(item)

        m.addItem(NSMenuItem.separator())

        item = NSMenuItem(title: "Exit", action: #selector(exitApp), keyEquivalent: "")
        item.target = self
        m.addItem(item)
    }
}
