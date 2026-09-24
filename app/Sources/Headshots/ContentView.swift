// The window: drop a folder, choose how it should look, watch it happen, open the result.

import AppKit
import SwiftUI
import UniformTypeIdentifiers

struct ContentView: View {
    @StateObject private var runner = Runner()
    @State private var folder: URL?
    @State private var options = Options()
    @State private var targeted = false

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            DropZone(folder: $folder, targeted: $targeted, disabled: runner.running)
            if !runner.running && runner.polished == nil {
                settings
            }
            if runner.running || runner.polished != nil {
                progress
            }
            if let failure = runner.failure {
                Label(failure, systemImage: "exclamationmark.triangle")
                    .foregroundStyle(.red).font(.callout).textSelection(.enabled)
            }
            Spacer(minLength: 0)
            controls
        }
        .padding(20)
        .frame(minWidth: 620, minHeight: 560)
    }

    // ---------------------------------------------------------------- settings

    private var settings: some View {
        Grid(alignment: .leading, horizontalSpacing: 14, verticalSpacing: 12) {
            GridRow {
                Text("Shape").gridColumnAlignment(.trailing).foregroundStyle(.secondary)
                Picker("", selection: $options.shape) {
                    ForEach(Options.Shape.allCases) { Text($0.label).tag($0) }
                }.labelsHidden().frame(maxWidth: 260)
            }
            GridRow {
                Text("Width").foregroundStyle(.secondary)
                HStack {
                    TextField("", value: $options.width, format: .number).frame(width: 70)
                    Text("px  —  \(options.width) × \(height)").foregroundStyle(.secondary).font(.callout)
                }
            }
            GridRow {
                Text("Crop").foregroundStyle(.secondary)
                HStack {
                    Slider(value: $options.zoom, in: 0.7...1.3).frame(width: 200)
                    Text(zoomLabel).foregroundStyle(.secondary).font(.callout).frame(width: 150, alignment: .leading)
                }
            }
            GridRow {
                Text("").gridCellUnsizedAxes(.horizontal)
                VStack(alignment: .leading, spacing: 6) {
                    Toggle("Black and white", isOn: $options.blackAndWhite)
                    Toggle("Group by person afterwards", isOn: $options.groupByPerson)
                    if options.groupByPerson {
                        Text("Downloads a 37 MB matching model the first time.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var height: Int {
        let parts = options.shape.rawValue.split(separator: ":").compactMap { Double($0) }
        guard parts.count == 2, parts[1] != 0 else { return options.width }
        return Int((Double(options.width) * parts[1] / parts[0]).rounded())
    }

    private var zoomLabel: String {
        switch options.zoom {
        case ..<0.93: return "wider — head and shoulders"
        case 0.93...1.07: return "standard"
        default: return "tighter — head fills more"
        }
    }

    // ---------------------------------------------------------------- progress

    private var progress: some View {
        VStack(alignment: .leading, spacing: 10) {
            if runner.running {
                ProgressView(value: Double(runner.done), total: Double(max(runner.total, 1))) {
                    Text(runner.total > 0 ? "\(runner.done) of \(runner.total)" : "Reading the folder…")
                }
            }
            if let p = runner.polished {
                Text(summary(p)).font(.headline)
                if let note = p.setNote {
                    Label(note, systemImage: "lightbulb").font(.callout).foregroundStyle(.secondary)
                }
            }
            if let g = runner.grouped {
                Text("\(g.students) people across \(g.photos) photos")
                    .font(.headline)
                Text("grouped at \(g.threshold, specifier: "%.2f") — \(g.why)")
                    .font(.callout).foregroundStyle(.secondary)
            }
            List(runner.photos.reversed()) { photo in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Circle().fill(colour(photo.grade)).frame(width: 8, height: 8)
                    Text(photo.source).font(.system(.callout, design: .monospaced))
                    Text(photo.why).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                }
            }
            .frame(minHeight: 150)
            .listStyle(.plain)
        }
    }

    private func summary(_ p: Event.Polished) -> String {
        let parts = ["PASS", "REVIEW", "FAIL", "SKIPPED"]
            .compactMap { g in (p.counts[g] ?? 0) > 0 ? "\(p.counts[g]!) \(g.lowercased())" : nil }
        return "\(p.processed) polished, \(p.unchanged) unchanged — " + parts.joined(separator: ", ")
    }

    private func colour(_ grade: String) -> Color {
        switch grade {
        case "PASS": return .green
        case "REVIEW": return .orange
        default: return .red
        }
    }

    // ---------------------------------------------------------------- controls

    private var controls: some View {
        HStack {
            if let p = runner.polished {
                Button("Show polished photos") { NSWorkspace.shared.open(URL(fileURLWithPath: p.out)) }
                Button("Open contact sheet") { NSWorkspace.shared.open(URL(fileURLWithPath: p.sheet)) }
            }
            if let g = runner.grouped, let first = g.sheets.first {
                Button("Open people sheet") { NSWorkspace.shared.open(URL(fileURLWithPath: first)) }
            }
            Spacer()
            if runner.running {
                Button("Stop", role: .cancel) { runner.cancel() }
            } else {
                Button(runner.polished == nil ? "Polish" : "Polish again") {
                    if let folder { runner.run(folder: folder, options: options) }
                }
                .keyboardShortcut(.defaultAction)
                .disabled(folder == nil)
            }
        }
    }
}

// ---------------------------------------------------------------- drop zone

private struct DropZone: View {
    @Binding var folder: URL?
    @Binding var targeted: Bool
    let disabled: Bool

    var body: some View {
        RoundedRectangle(cornerRadius: 12)
            .strokeBorder(style: StrokeStyle(lineWidth: 2, dash: folder == nil ? [7] : []))
            .foregroundStyle(targeted ? Color.accentColor : Color.secondary.opacity(0.4))
            .background(RoundedRectangle(cornerRadius: 12).fill(Color.secondary.opacity(targeted ? 0.12 : 0.04)))
            .frame(height: 92)
            .overlay {
                VStack(spacing: 4) {
                    if let folder {
                        Text(folder.lastPathComponent).font(.headline)
                        Text(folder.deletingLastPathComponent().path).font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text("Drop a folder of photos").font(.headline)
                        Text("originals are never modified").font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
            .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
                guard !disabled, let provider = providers.first else { return false }
                _ = provider.loadObject(ofClass: URL.self) { url, _ in
                    guard let url, url.hasDirectoryPath else { return }
                    Task { @MainActor in folder = url }
                }
                return true
            }
            .onTapGesture { choose() }
            .help("Click to choose a folder, or drag one in")
    }

    private func choose() {
        guard !disabled else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Choose"
        if panel.runModal() == .OK { folder = panel.url }
    }
}
