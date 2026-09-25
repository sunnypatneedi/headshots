// Three-step product flow: Select folder → Polish → Gallery of polished outputs.
// Craft: Harbor/Familiar calm hierarchy, Ice compact chrome, IINA image-first lightbox.

import AppKit
import SwiftUI
import UniformTypeIdentifiers

private enum FlowPhase: Int, CaseIterable {
    case select, polish, gallery

    var title: String {
        switch self {
        case .select: return "Select"
        case .polish: return "Polish"
        case .gallery: return "Gallery"
        }
    }
}

struct ContentView: View {
    @StateObject private var runner = Runner()
    @State private var folder: URL?
    @State private var options = Options()
    @State private var targeted = false
    @State private var galleryFilter: GalleryFilter = .all
    @State private var gallerySelection: Event.Photo.ID?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var phase: FlowPhase {
        if runner.running { return .polish }
        if runner.polished != nil || !runner.photos.isEmpty { return .gallery }
        return .select
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    FlowStepper(phase: phase)

                    switch phase {
                    case .select:
                        selectStep
                    case .polish:
                        polishStep
                    case .gallery:
                        galleryStep
                    }

                    if let failure = runner.failure {
                        ErrorBanner(message: failure, onDismiss: { runner.failure = nil })
                            .transition(panelTransition)
                    }
                }
                .padding(20)
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: phase)
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: runner.failure)
            }

            Divider()
            ActionBar(
                folder: $folder,
                options: options,
                runner: runner,
                phase: phase,
                onChooseDifferentFolder: chooseDifferentFolder
            )
            .padding(.horizontal, 20)
            .padding(.vertical, 14)
            .background(.bar)
        }
        .background(WindowBackdrop())
        .frame(minWidth: 680, minHeight: 600)
    }

    // MARK: Steps

    private var selectStep: some View {
        VStack(alignment: .leading, spacing: 18) {
            DropZone(folder: $folder, targeted: $targeted, disabled: false)
                .accessibilityLabel(dropAccessibilityLabel)
            SettingsPanel(options: $options)
        }
    }

    private var polishStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            FolderChip(folder: folder)
            ProgressStrip(runner: runner)
            GalleryPanel(
                photos: runner.photos,
                outDir: runner.outDir,
                running: true,
                filter: $galleryFilter,
                selection: $gallerySelection
            )
        }
    }

    private var galleryStep: some View {
        VStack(alignment: .leading, spacing: 16) {
            FolderChip(folder: folder)
            if let polished = runner.polished {
                ResultSummary(polished: polished, grouped: runner.grouped)
            }
            GalleryPanel(
                photos: runner.photos,
                outDir: runner.outDir ?? runner.polished?.out,
                running: false,
                filter: $galleryFilter,
                selection: $gallerySelection
            )
        }
    }

    private var dropAccessibilityLabel: String {
        if let folder {
            return "Selected folder \(folder.lastPathComponent). Click to choose another."
        }
        return "Drop a folder of photos, or click to choose one"
    }

    private var panelTransition: AnyTransition {
        reduceMotion ? .opacity : .opacity.combined(with: .move(edge: .top))
    }

    private func chooseDifferentFolder() {
        gallerySelection = nil
        galleryFilter = .all
        runner.resetResults()
        folder = nil
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Choose"
        if panel.runModal() == .OK {
            folder = panel.url
        }
    }
}

// MARK: - Flow chrome

private struct FlowStepper: View {
    let phase: FlowPhase

    var body: some View {
        HStack(spacing: 0) {
            ForEach(FlowPhase.allCases, id: \.self) { step in
                HStack(spacing: 6) {
                    Circle()
                        .fill(step.rawValue <= phase.rawValue ? Color.accentColor : Color.secondary.opacity(0.25))
                        .frame(width: 7, height: 7)
                    Text(step.title)
                        .font(.subheadline.weight(step == phase ? .semibold : .regular))
                        .foregroundStyle(step == phase ? .primary : .secondary)
                }
                .accessibilityLabel("\(step.title)\(step == phase ? ", current step" : "")")
                if step != .gallery {
                    Rectangle()
                        .fill(Color.secondary.opacity(0.25))
                        .frame(height: 1)
                        .frame(maxWidth: 28)
                        .padding(.horizontal, 8)
                        .accessibilityHidden(true)
                }
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Workflow: Select, Polish, Gallery. Current step \(phase.title)")
    }
}

private struct FolderChip: View {
    let folder: URL?

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "folder.fill")
                .foregroundStyle(.secondary)
            if let folder {
                Text(folder.lastPathComponent)
                    .font(.subheadline.weight(.medium))
                    .lineLimit(1)
                Text(folder.deletingLastPathComponent().path)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            } else {
                Text("No folder selected")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(
            RoundedRectangle(cornerRadius: 8, style: .continuous)
                .fill(.ultraThinMaterial)
        )
    }
}

private struct WindowBackdrop: View {
    var body: some View {
        ZStack {
            Color(nsColor: .windowBackgroundColor)
            LinearGradient(
                colors: [
                    Color.primary.opacity(0.03),
                    Color.clear,
                    Color.primary.opacity(0.02),
                ],
                startPoint: .top,
                endPoint: .bottom
            )
        }
        .ignoresSafeArea()
    }
}

// MARK: - Home / drop

private struct DropZone: View {
    @Binding var folder: URL?
    @Binding var targeted: Bool
    let disabled: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        let active = targeted && !disabled
        let hasFolder = folder != nil

        Button(action: choose) {
            ZStack {
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(.ultraThinMaterial)
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .fill(fillTint(active: active, hasFolder: hasFolder))
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(
                        borderColor(active: active, hasFolder: hasFolder),
                        style: StrokeStyle(
                            lineWidth: active || hasFolder ? 1.5 : 1.25,
                            dash: hasFolder || active ? [] : [6, 5]
                        )
                    )

                VStack(spacing: 10) {
                    Image(systemName: hasFolder ? "folder.fill" : "person.crop.rectangle.stack")
                        .font(.system(size: 28, weight: .medium))
                        .foregroundStyle(active ? Color.accentColor : Color.secondary)
                        .symbolRenderingMode(.hierarchical)
                        .accessibilityHidden(true)

                    if let folder {
                        Text(folder.lastPathComponent)
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(.primary)
                            .lineLimit(1)
                        Text(folder.deletingLastPathComponent().path)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(1)
                            .truncationMode(.middle)
                    } else {
                        Text("Drop a folder of photos")
                            .font(.title3.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text("Select → Polish → Gallery. Originals stay untouched.")
                            .font(.callout)
                            .foregroundStyle(.secondary)
                            .multilineTextAlignment(.center)
                            .frame(maxWidth: 420)
                    }
                }
                .padding(.horizontal, 24)
                .padding(.vertical, 22)
            }
            .frame(minHeight: hasFolder ? 110 : 148)
            .scaleEffect(reduceMotion ? 1 : (active ? 1.01 : 1))
            .animation(reduceMotion ? nil : .easeOut(duration: 0.15), value: active)
        }
        .buttonStyle(.plain)
        .disabled(disabled)
        .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
            guard !disabled, let provider = providers.first else { return false }
            _ = provider.loadObject(ofClass: URL.self) { url, _ in
                guard let url, url.hasDirectoryPath else { return }
                Task { @MainActor in folder = url }
            }
            return true
        }
        .help(hasFolder ? "Click to choose a different folder" : "Click to choose a folder, or drag one in")
        .accessibilityAddTraits(.isButton)
    }

    private func fillTint(active: Bool, hasFolder: Bool) -> Color {
        if active { return Color.accentColor.opacity(colorScheme == .dark ? 0.18 : 0.10) }
        if hasFolder { return Color.primary.opacity(colorScheme == .dark ? 0.06 : 0.03) }
        return Color.primary.opacity(colorScheme == .dark ? 0.04 : 0.02)
    }

    private func borderColor(active: Bool, hasFolder: Bool) -> Color {
        if active { return Color.accentColor.opacity(0.85) }
        if hasFolder { return Color.secondary.opacity(0.45) }
        return Color.secondary.opacity(0.35)
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

// MARK: - Settings / options

private struct SettingsPanel: View {
    @Binding var options: Options

    private var height: Int {
        let parts = options.shape.rawValue.split(separator: ":").compactMap { Double($0) }
        guard parts.count == 2, parts[1] != 0 else { return options.width }
        return Int((Double(options.width) * parts[1] / parts[0]).rounded())
    }

    private var zoomLabel: String {
        switch options.zoom {
        case ..<0.93: return "Wider — head and shoulders"
        case 0.93...1.07: return "Standard crop"
        default: return "Tighter — head fills more"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            sectionHeader("Frame", systemImage: "aspectratio")
            GroupBox {
                VStack(alignment: .leading, spacing: 14) {
                    labeledRow("Shape") {
                        Picker("Shape", selection: $options.shape) {
                            ForEach(Options.Shape.allCases) { Text($0.label).tag($0) }
                        }
                        .labelsHidden()
                        .frame(maxWidth: 280, alignment: .leading)
                        .accessibilityLabel("Crop shape")
                    }

                    labeledRow("Width") {
                        HStack(spacing: 10) {
                            TextField("Width", value: $options.width, format: .number)
                                .frame(width: 72)
                                .accessibilityLabel("Output width in pixels")
                            Text("px · \(options.width) × \(height)")
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .accessibilityLabel("Output size \(options.width) by \(height) pixels")
                        }
                    }

                    labeledRow("Crop") {
                        HStack(spacing: 12) {
                            Slider(value: $options.zoom, in: 0.7...1.3)
                                .frame(maxWidth: 220)
                                .accessibilityLabel("Crop zoom")
                                .accessibilityValue(zoomLabel)
                            Text(zoomLabel)
                                .font(.callout)
                                .foregroundStyle(.secondary)
                                .frame(minWidth: 160, alignment: .leading)
                                .lineLimit(1)
                        }
                    }
                }
                .padding(4)
            }

            sectionHeader("Finish", systemImage: "camera.filters")
            GroupBox {
                VStack(alignment: .leading, spacing: 10) {
                    Toggle("Black and white", isOn: $options.blackAndWhite)
                    Toggle("Group by person afterwards", isOn: $options.groupByPerson)
                    if options.groupByPerson {
                        Label(
                            "Downloads a 37 MB matching model the first time — then works offline.",
                            systemImage: "arrow.down.circle"
                        )
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityLabel(
                            "Group by person downloads a 37 megabyte matching model the first time, then works offline."
                        )
                    }
                }
                .padding(4)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func sectionHeader(_ title: String, systemImage: String) -> some View {
        Label(title, systemImage: systemImage)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.secondary)
            .labelStyle(.titleAndIcon)
    }

    private func labeledRow<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 14) {
            Text(title)
                .foregroundStyle(.secondary)
                .frame(width: 56, alignment: .trailing)
            content()
            Spacer(minLength: 0)
        }
    }
}

// MARK: - Progress (secondary to gallery)

private struct ProgressStrip: View {
    @ObservedObject var runner: Runner

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(runner.total > 0
                     ? "\(runner.done) of \(runner.total)"
                     : "Reading the folder…")
                    .font(.subheadline.weight(.medium))
                Spacer()
                if runner.total > 0 {
                    Text("\(percent)%")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                }
            }
            ProgressView(value: Double(runner.done), total: Double(max(runner.total, 1)))
                .accessibilityLabel("Polishing progress")
                .accessibilityValue(runner.total > 0
                    ? "\(runner.done) of \(runner.total)"
                    : "Reading the folder")
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(.ultraThinMaterial)
        )
    }

    private var percent: Int {
        guard runner.total > 0 else { return 0 }
        return Int((Double(runner.done) / Double(runner.total) * 100).rounded())
    }
}

private struct ResultSummary: View {
    let polished: Event.Polished
    let grouped: Event.Grouped?

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("\(polished.processed) polished, \(polished.unchanged) unchanged")
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)

            HStack(spacing: 8) {
                ForEach(["PASS", "REVIEW", "FAIL", "SKIPPED"], id: \.self) { grade in
                    if let count = polished.counts[grade], count > 0 {
                        GradeChip(grade: grade, count: count)
                    }
                }
            }

            if let note = polished.setNote {
                Label(note, systemImage: "lightbulb")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let grouped {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(grouped.students) people across \(grouped.photos) photos")
                        .font(.subheadline.weight(.semibold))
                    Text("Grouped at \(grouped.threshold, specifier: "%.2f") — \(grouped.why)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .padding(.top, 2)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(.ultraThinMaterial)
        )
    }
}

// MARK: - Error / offline-ish

private struct ErrorBanner: View {
    let message: String
    var onDismiss: (() -> Void)?

    private var kind: Kind { Kind(message: message) }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: kind.symbol)
                .font(.title3)
                .foregroundStyle(kind.tint)
                .accessibilityHidden(true)

            VStack(alignment: .leading, spacing: 4) {
                Text(kind.title)
                    .font(.subheadline.weight(.semibold))
                Text(message)
                    .font(.callout)
                    .foregroundStyle(.primary)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                Text(kind.recovery)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            Spacer(minLength: 0)

            if let onDismiss {
                Button(action: onDismiss) {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Dismiss error")
            }
        }
        .padding(14)
        .background(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(kind.tint.opacity(0.10))
        )
        .overlay(
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .strokeBorder(kind.tint.opacity(0.35), lineWidth: 1)
        )
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(kind.title). \(message). \(kind.recovery)")
    }

    private enum Kind {
        case missingCLI
        case cancelled
        case failure

        init(message: String) {
            let lower = message.lowercased()
            if lower.contains("missing") || lower.contains("command is missing") {
                self = .missingCLI
            } else if lower.contains("cancel") || lower.contains("terminated") {
                self = .cancelled
            } else {
                self = .failure
            }
        }

        var title: String {
            switch self {
            case .missingCLI: return "Command not found"
            case .cancelled: return "Stopped"
            case .failure: return "Something went wrong"
            }
        }

        var symbol: String {
            switch self {
            case .missingCLI: return "terminal"
            case .cancelled: return "stop.circle"
            case .failure: return "exclamationmark.triangle.fill"
            }
        }

        var tint: Color {
            switch self {
            case .missingCLI: return .orange
            case .cancelled: return .secondary
            case .failure: return .red
            }
        }

        var recovery: String {
            switch self {
            case .missingCLI:
                return "Build the app with `make app`, or install the CLI with `pipx install headshots`."
            case .cancelled:
                return "Nothing was written over your originals. Drop the folder again when you are ready."
            case .failure:
                return "Check the folder path and try again. Originals were not modified."
            }
        }
    }
}

// MARK: - Primary action bar

private struct ActionBar: View {
    @Binding var folder: URL?
    let options: Options
    @ObservedObject var runner: Runner
    let phase: FlowPhase
    let onChooseDifferentFolder: () -> Void

    var body: some View {
        HStack(spacing: 10) {
            if phase == .gallery || phase == .polish {
                if let out = runner.outDir ?? runner.polished?.out {
                    Button {
                        NSWorkspace.shared.open(URL(fileURLWithPath: out))
                    } label: {
                        Label("Show in Finder", systemImage: "folder")
                    }
                    .accessibilityLabel("Show polished photos in Finder")
                    .help("Open the polished output folder")
                }

                if let sheet = runner.polished?.sheet {
                    Button {
                        NSWorkspace.shared.open(URL(fileURLWithPath: sheet))
                    } label: {
                        Label("Contact sheet", systemImage: "rectangle.grid.2x2")
                    }
                    .accessibilityLabel("Open contact sheet")
                }

                if let grouped = runner.grouped, let first = grouped.sheets.first {
                    Button {
                        NSWorkspace.shared.open(URL(fileURLWithPath: first))
                    } label: {
                        Label("People sheet", systemImage: "person.2")
                    }
                    .accessibilityLabel("Open people sheet")
                }

                if phase == .gallery {
                    Button("Choose folder…", action: onChooseDifferentFolder)
                        .accessibilityLabel("Choose a different photos folder")
                }
            }

            Spacer(minLength: 8)

            if runner.running {
                Button(role: .cancel) {
                    runner.cancel()
                } label: {
                    Text("Stop")
                }
                .keyboardShortcut(.cancelAction)
                .accessibilityLabel("Stop polishing")
                .help("Cancel the current run (Esc)")
            } else {
                Button {
                    if let folder { runner.run(folder: folder, options: options) }
                } label: {
                    Text(phase == .gallery ? "Polish again" : "Polish")
                }
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .disabled(folder == nil)
                .accessibilityLabel(phase == .gallery ? "Polish again" : "Polish photos")
                .accessibilityHint(folder == nil
                    ? "Choose a folder first"
                    : "Runs headshots on the selected folder")
                .help(folder == nil ? "Drop or choose a folder first" : "Run polish (↩)")
            }
        }
    }
}
