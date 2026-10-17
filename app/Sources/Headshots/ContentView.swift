// Four-step product flow: Add Photos → Check Photos → Finish → Save.
// Notion-flat chrome on named role tokens. Interior principles: reserve space for
// every state, move only when something happened, honour reduced motion, keep
// frequent controls under 120ms.

import AppKit
import SwiftUI
import UniformTypeIdentifiers

private enum FlowStep: Int, CaseIterable, Identifiable {
    case add, check, finish, save

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .add: return "Add Photos"
        case .check: return "Check Photos"
        case .finish: return "Finish"
        case .save: return "Save"
        }
    }
}

struct ContentView: View {
    @StateObject private var runner = Runner()
    @State private var folder: URL?
    @State private var photoCount = 0
    @State private var options = Options()
    @State private var targeted = false
    @State private var stepOverride: FlowStep?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var step: FlowStep {
        if let stepOverride { return stepOverride }
        if runner.polished != nil || (!runner.photos.isEmpty && !runner.running) { return .save }
        if runner.running { return .finish }
        if folder != nil { return .check }
        return .add
    }

    var body: some View {
        HStack(spacing: 0) {
            Sidebar(
                step: step,
                onSelect: navigate(to:),
                canVisit: canVisit(_:)
            )
            .frame(width: 220)

            Divider().background(HSTheme.border)

            mainPane
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .background(HSTheme.canvas)
        .frame(minWidth: 720, minHeight: 560)
        .onChange(of: folder) { url in
            photoCount = Runner.countPhotos(in: url)
            if url != nil, stepOverride == .add || stepOverride == nil {
                stepOverride = nil
            }
        }
    }

    @ViewBuilder
    private var mainPane: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: HSTheme.Space.xl) {
                    switch step {
                    case .add:
                        WelcomePane(
                            folder: $folder,
                            targeted: $targeted,
                            disabled: runner.running,
                            onChosen: { stepOverride = nil }
                        )
                    case .check:
                        CheckPane(
                            folder: folder,
                            photoCount: photoCount,
                            onChangeFolder: { stepOverride = .add; folder = nil; runner.resetResults() },
                            onContinue: { stepOverride = .finish }
                        )
                    case .finish:
                        if runner.running {
                            ProcessingPane(runner: runner)
                        } else {
                            FinishPane(options: $options)
                        }
                    case .save:
                        ResultsPane(runner: runner, folder: folder)
                    }

                    if let failure = runner.failure {
                        ErrorBanner(message: failure) {
                            runner.failure = nil
                        }
                    }
                }
                .padding(HSTheme.Space.xl)
                .frame(maxWidth: 720, alignment: .leading)
                .frame(maxWidth: .infinity, alignment: .center)
                .animation(.hsPanel(reduceMotion: reduceMotion), value: step)
            }

            ActionBar(
                step: step,
                folder: folder,
                photoCount: photoCount,
                options: options,
                runner: runner,
                onBack: goBack,
                onContinue: goForward
            )
        }
        .background(HSTheme.surface)
    }

    private func canVisit(_ target: FlowStep) -> Bool {
        switch target {
        case .add: return true
        case .check: return folder != nil
        case .finish: return folder != nil && photoCount > 0
        case .save: return runner.polished != nil || !runner.photos.isEmpty
        }
    }

    private func navigate(to target: FlowStep) {
        guard canVisit(target), !runner.running else { return }
        stepOverride = target
    }

    private func goBack() {
        switch step {
        case .add: break
        case .check:
            stepOverride = .add
        case .finish:
            stepOverride = folder == nil ? .add : .check
        case .save:
            stepOverride = .finish
            runner.resetResults()
        }
    }

    private func goForward() {
        switch step {
        case .add:
            break
        case .check:
            stepOverride = .finish
        case .finish:
            guard let folder else { return }
            stepOverride = nil
            runner.run(folder: folder, options: options)
        case .save:
            break
        }
    }
}

// MARK: - Sidebar

private struct Sidebar: View {
    let step: FlowStep
    let onSelect: (FlowStep) -> Void
    let canVisit: (FlowStep) -> Bool

    var body: some View {
        VStack(alignment: .leading, spacing: HSTheme.Space.xl) {
            HStack(spacing: HSTheme.Space.sm) {
                RoundedRectangle(cornerRadius: HSTheme.Radius.sm, style: .continuous)
                    .fill(HSTheme.accent)
                    .frame(width: 32, height: 32)
                    .overlay {
                        Image(systemName: "person.crop.rectangle")
                            .foregroundStyle(HSTheme.accentOn)
                            .font(.system(size: 14, weight: .semibold))
                    }
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 1) {
                    Text("Headshots").font(HSTypography.brand).foregroundStyle(HSTheme.ink)
                    Text("Polished portraits").font(HSTypography.brandTag).foregroundStyle(HSTheme.inkSecondary)
                }
            }
            .accessibilityElement(children: .combine)

            VStack(alignment: .leading, spacing: HSTheme.Space.xs) {
                ForEach(FlowStep.allCases) { item in
                    StepRow(
                        index: item.rawValue + 1,
                        title: item.title,
                        state: state(for: item)
                    ) {
                        onSelect(item)
                    }
                    .disabled(!canVisit(item))
                }
            }

            Spacer(minLength: 0)

            PrivacyNote()
        }
        .padding(HSTheme.Space.lg)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(HSTheme.surfaceMuted)
    }

    private func state(for item: FlowStep) -> StepRow.State {
        if item == step { return .current }
        if item.rawValue < step.rawValue { return .done }
        return .todo
    }
}

private struct StepRow: View {
    enum State { case todo, current, done }

    let index: Int
    let title: String
    let state: State
    let action: () -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @FocusState private var focused: Bool

    var body: some View {
        Button(action: action) {
            HStack(spacing: HSTheme.Space.sm) {
                ZStack {
                    Circle()
                        .fill(badgeFill)
                        .frame(width: 22, height: 22)
                    if state == .done {
                        Image(systemName: "checkmark")
                            .font(.system(size: 10, weight: .bold))
                            .foregroundStyle(HSTheme.accentOn)
                    } else {
                        Text("\(index)")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(badgeInk)
                    }
                }
                Text(title)
                    .font(state == .current ? HSTypography.headline : HSTypography.callout)
                    .foregroundStyle(state == .todo ? HSTheme.inkSecondary : HSTheme.ink)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, HSTheme.Space.sm)
            .padding(.vertical, HSTheme.Space.sm)
            .background(
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .fill(state == .current ? HSTheme.accentSoft : Color.clear)
            )
            .overlay {
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .strokeBorder(focused ? HSTheme.focusRing : Color.clear, lineWidth: 2)
            }
        }
        .buttonStyle(.plain)
        .focused($focused)
        .accessibilityLabel("\(title)\(state == .current ? ", current step" : state == .done ? ", completed" : "")")
        .animation(.hsControl(reduceMotion: reduceMotion), value: state)
    }

    private var badgeFill: Color {
        switch state {
        case .current: return HSTheme.accent
        case .done: return HSTheme.success
        case .todo: return HSTheme.border
        }
    }

    private var badgeInk: Color {
        switch state {
        case .current: return HSTheme.accentOn
        case .done: return HSTheme.accentOn
        case .todo: return HSTheme.inkSecondary
        }
    }
}

private struct PrivacyNote: View {
    var body: some View {
        HStack(alignment: .top, spacing: HSTheme.Space.sm) {
            Image(systemName: "lock.fill")
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(HSTheme.inkSecondary)
                .padding(.top, 2)
            VStack(alignment: .leading, spacing: 2) {
                Text("Private by design")
                    .font(HSTypography.label)
                    .foregroundStyle(HSTheme.ink)
                Text("Photos never leave your Mac.")
                    .font(HSTypography.caption)
                    .foregroundStyle(HSTheme.inkSecondary)
            }
        }
        .padding(HSTheme.Space.md)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(
            RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                .fill(HSTheme.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                        .strokeBorder(HSTheme.border, lineWidth: 1)
                )
        )
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Welcome

private struct WelcomePane: View {
    @Binding var folder: URL?
    @Binding var targeted: Bool
    let disabled: Bool
    let onChosen: () -> Void

    var body: some View {
        VStack(spacing: HSTheme.Space.lg) {
            DropZone(folder: $folder, targeted: $targeted, disabled: disabled, onChosen: onChosen)
                .frame(minHeight: 320)

            HStack(spacing: 6) {
                Image(systemName: "lock.fill")
                    .font(.system(size: 11))
                Text("Everything stays on your Mac. Nothing is uploaded.")
                    .font(HSTypography.caption)
            }
            .foregroundStyle(HSTheme.inkSecondary)
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .combine)
        }
    }
}

private struct DropZone: View {
    @Binding var folder: URL?
    @Binding var targeted: Bool
    let disabled: Bool
    var onChosen: () -> Void = {}

    @FocusState private var focused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        RoundedRectangle(cornerRadius: HSTheme.Radius.lg, style: .continuous)
            .strokeBorder(
                targeted || focused ? HSTheme.accent : HSTheme.borderStrong,
                style: StrokeStyle(lineWidth: 2, dash: folder == nil ? [8, 6] : [])
            )
            .background(
                RoundedRectangle(cornerRadius: HSTheme.Radius.lg, style: .continuous)
                    .fill(targeted ? HSTheme.dropTarget : HSTheme.surfaceMuted)
            )
            .overlay { content }
            .contentShape(RoundedRectangle(cornerRadius: HSTheme.Radius.lg, style: .continuous))
            .onDrop(of: [.fileURL], isTargeted: $targeted) { providers in
                guard !disabled, let provider = providers.first else { return false }
                _ = provider.loadObject(ofClass: URL.self) { url, _ in
                    guard let url, url.hasDirectoryPath else { return }
                    Task { @MainActor in
                        folder = url
                        onChosen()
                    }
                }
                return true
            }
            .onTapGesture { choose() }
            .focusable(!disabled)
            .focused($focused)
            .accessibilityElement(children: .combine)
            .accessibilityLabel(folder == nil
                ? "Drop photos or a folder here"
                : "Selected folder \(folder!.lastPathComponent). Click to choose another.")
            .accessibilityAddTraits(.isButton)
            .accessibilityHint("Click to choose a folder, or drag one in")
            .animation(.hsControl(reduceMotion: reduceMotion), value: targeted)
    }

    @ViewBuilder
    private var content: some View {
        VStack(spacing: HSTheme.Space.md) {
            ZStack {
                PortraitStack()
                Circle()
                    .fill(HSTheme.accent)
                    .frame(width: 44, height: 44)
                    .overlay {
                        Image(systemName: "arrow.down")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundStyle(HSTheme.accentOn)
                    }
                    .offset(y: 36)
                    .accessibilityHidden(true)
            }
            .frame(height: 110)
            .padding(.bottom, HSTheme.Space.sm)

            if let folder {
                Text(folder.lastPathComponent)
                    .font(HSTypography.title)
                    .foregroundStyle(HSTheme.ink)
                Text(folder.deletingLastPathComponent().path)
                    .font(HSTypography.callout)
                    .foregroundStyle(HSTheme.inkSecondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            } else {
                Text("Drop photos or a folder here")
                    .font(HSTypography.title)
                    .foregroundStyle(HSTheme.ink)
                Text("We’ll turn them into clean, matching headshots.")
                    .font(HSTypography.callout)
                    .foregroundStyle(HSTheme.inkSecondary)
            }

            HStack(spacing: HSTheme.Space.sm) {
                Button {
                    choose()
                } label: {
                    Label("Choose Photos", systemImage: "photo.on.rectangle")
                        .frame(minWidth: 140)
                }
                .buttonStyle(HSPrimaryButtonStyle())
                .disabled(disabled)

                Button {
                    choose()
                } label: {
                    Label("Choose a Folder", systemImage: "folder")
                        .frame(minWidth: 140)
                }
                .buttonStyle(HSSecondaryButtonStyle())
                .disabled(disabled)
            }
            .padding(.top, HSTheme.Space.xs)
        }
        .padding(HSTheme.Space.xl)
    }

    private func choose() {
        guard !disabled else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.prompt = "Choose"
        if panel.runModal() == .OK {
            folder = panel.url
            onChosen()
        }
    }
}

private struct PortraitStack: View {
    var body: some View {
        ZStack {
            card(offset: -28, rotation: -8, color: HSTheme.accentSoft)
            card(offset: 0, rotation: 0, color: HSTheme.surface)
            card(offset: 28, rotation: 8, color: HSTheme.successSoft)
        }
        .accessibilityHidden(true)
    }

    private func card(offset: CGFloat, rotation: Double, color: Color) -> some View {
        RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
            .fill(color)
            .frame(width: 64, height: 80)
            .overlay(
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .strokeBorder(HSTheme.border, lineWidth: 1)
            )
            .overlay {
                Image(systemName: "person.fill")
                    .foregroundStyle(HSTheme.inkSecondary)
            }
            .rotationEffect(.degrees(rotation))
            .offset(x: offset)
    }
}

// MARK: - Check

private struct CheckPane: View {
    let folder: URL?
    let photoCount: Int
    let onChangeFolder: () -> Void
    let onContinue: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: HSTheme.Space.lg) {
            if photoCount == 0 {
                EmptyStateCard(
                    systemImage: "photo.on.rectangle.angled",
                    title: "No photos in this folder",
                    detail: "Pick a folder with JPEGs, HEICs or PNGs at the top level. Subfolders are ignored.",
                    actionTitle: "Choose another folder",
                    action: onChangeFolder
                )
            } else {
                VStack(alignment: .leading, spacing: HSTheme.Space.sm) {
                    Text("Ready to polish")
                        .font(HSTypography.title)
                        .foregroundStyle(HSTheme.ink)
                    Text(folder.map(\.lastPathComponent) ?? "Folder")
                        .font(HSTypography.headline)
                        .foregroundStyle(HSTheme.ink)
                    Text("\(photoCount) photo\(photoCount == 1 ? "" : "s") at the top level. Originals stay untouched.")
                        .font(HSTypography.callout)
                        .foregroundStyle(HSTheme.inkSecondary)
                }

                HStack(spacing: HSTheme.Space.sm) {
                    Button("Choose another folder", action: onChangeFolder)
                        .buttonStyle(HSSecondaryButtonStyle())
                    Button("Continue to Finish", action: onContinue)
                        .buttonStyle(HSPrimaryButtonStyle())
                        .keyboardShortcut(.defaultAction)
                }
            }
        }
    }
}

// MARK: - Finish / options

private struct FinishPane: View {
    @Binding var options: Options

    var body: some View {
        VStack(alignment: .leading, spacing: HSTheme.Space.xl) {
            VStack(spacing: HSTheme.Space.sm) {
                Text("How should we finish them?")
                    .font(HSTypography.title)
                    .foregroundStyle(HSTheme.ink)
                    .frame(maxWidth: .infinity)
                HStack(spacing: 6) {
                    Image(systemName: "sparkles")
                    Text("These are our recommended settings. Just press Make Headshots.")
                        .font(HSTypography.caption)
                }
                .foregroundStyle(HSTheme.success)
                .padding(.horizontal, HSTheme.Space.md)
                .padding(.vertical, HSTheme.Space.sm)
                .background(
                    Capsule().fill(HSTheme.successSoft)
                )
                .frame(maxWidth: .infinity)
                .accessibilityElement(children: .combine)
            }

            OptionSection(title: "Framing") {
                HStack(spacing: HSTheme.Space.sm) {
                    ForEach(Options.Framing.allCases) { framing in
                        FramingCard(
                            framing: framing,
                            selected: options.framing == framing,
                            recommended: framing == .headShoulders
                        ) {
                            options.framing = framing
                        }
                    }
                }
            }

            HStack(alignment: .top, spacing: HSTheme.Space.lg) {
                OptionSection(title: "Color") {
                    VStack(spacing: HSTheme.Space.sm) {
                        ChoiceRow(
                            title: "Color",
                            selected: !options.blackAndWhite,
                            swatch: HSTheme.accent
                        ) { options.blackAndWhite = false }
                        ChoiceRow(
                            title: "Black & White",
                            selected: options.blackAndWhite,
                            swatch: HSTheme.inkSecondary
                        ) { options.blackAndWhite = true }
                    }
                }
                OptionSection(title: "Background") {
                    VStack(spacing: HSTheme.Space.sm) {
                        ChoiceRow(
                            title: "Soft studio",
                            selected: options.softStudio,
                            swatch: HSTheme.surfaceMuted
                        ) { options.softStudio = true }
                        ChoiceRow(
                            title: "Keep original",
                            selected: !options.softStudio,
                            swatch: HSTheme.warning
                        ) { options.softStudio = false }
                    }
                }
            }

            GroupToggle(isOn: $options.groupByPerson)
        }
    }
}

private struct OptionSection<Content: View>: View {
    let title: String
    @ViewBuilder let content: Content

    var body: some View {
        VStack(alignment: .leading, spacing: HSTheme.Space.sm) {
            Text(title.uppercased())
                .font(HSTypography.label)
                .foregroundStyle(HSTheme.inkSecondary)
                .tracking(0.6)
            content
        }
    }
}

private struct FramingCard: View {
    let framing: Options.Framing
    let selected: Bool
    let recommended: Bool
    let action: () -> Void

    @FocusState private var focused: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: HSTheme.Space.sm) {
                ZStack(alignment: .topLeading) {
                    RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                        .fill(HSTheme.surfaceMuted)
                        .frame(height: 88)
                        .overlay {
                            Image(systemName: framing.symbol)
                                .font(.system(size: 28, weight: .regular))
                                .foregroundStyle(HSTheme.inkSecondary)
                        }
                    if recommended {
                        Text("Recommended")
                            .font(.system(size: 10, weight: .semibold))
                            .foregroundStyle(HSTheme.accent)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(Capsule().fill(HSTheme.surface))
                            .padding(HSTheme.Space.sm)
                    }
                    if selected {
                        Image(systemName: "checkmark.circle.fill")
                            .foregroundStyle(HSTheme.accent)
                            .background(Circle().fill(HSTheme.surface).padding(2))
                            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topTrailing)
                            .padding(HSTheme.Space.sm)
                    }
                }
                Text(framing.title)
                    .font(HSTypography.headline)
                    .foregroundStyle(HSTheme.ink)
                Text(framing.detail)
                    .font(HSTypography.caption)
                    .foregroundStyle(HSTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(HSTheme.Space.md)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: HSTheme.Radius.lg, style: .continuous)
                    .fill(HSTheme.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: HSTheme.Radius.lg, style: .continuous)
                    .strokeBorder(selected || focused ? HSTheme.accent : HSTheme.border, lineWidth: selected || focused ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
        .focused($focused)
        .accessibilityLabel("\(framing.title). \(framing.detail)\(recommended ? ". Recommended" : "")")
        .accessibilityAddTraits(selected ? .isSelected : [])
        .animation(.hsControl(reduceMotion: reduceMotion), value: selected)
    }
}

private struct ChoiceRow: View {
    let title: String
    let selected: Bool
    let swatch: Color
    let action: () -> Void

    @FocusState private var focused: Bool

    var body: some View {
        Button(action: action) {
            HStack(spacing: HSTheme.Space.md) {
                RoundedRectangle(cornerRadius: 4, style: .continuous)
                    .fill(swatch)
                    .frame(width: 28, height: 28)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .strokeBorder(HSTheme.border, lineWidth: 1)
                    )
                Text(title)
                    .font(HSTypography.headline)
                    .foregroundStyle(HSTheme.ink)
                Spacer(minLength: 0)
                Image(systemName: selected ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(selected ? HSTheme.accent : HSTheme.borderStrong)
            }
            .padding(HSTheme.Space.md)
            .background(
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .fill(HSTheme.surface)
            )
            .overlay(
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .strokeBorder(selected || focused ? HSTheme.accent : HSTheme.border, lineWidth: selected || focused ? 2 : 1)
            )
        }
        .buttonStyle(.plain)
        .focused($focused)
        .accessibilityLabel(title)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

private struct GroupToggle: View {
    @Binding var isOn: Bool

    var body: some View {
        HStack(spacing: HSTheme.Space.md) {
            RoundedRectangle(cornerRadius: HSTheme.Radius.sm, style: .continuous)
                .fill(HSTheme.warning)
                .frame(width: 36, height: 36)
                .overlay {
                    Image(systemName: "person.2.fill")
                        .foregroundStyle(HSTheme.accentOn)
                        .font(.system(size: 14, weight: .semibold))
                }
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text("Group by person")
                    .font(HSTypography.headline)
                    .foregroundStyle(HSTheme.ink)
                Text(isOn
                     ? "Puts photos of the same person together. Downloads a 37 MB model the first time."
                     : "Puts photos of the same person together.")
                    .font(HSTypography.caption)
                    .foregroundStyle(HSTheme.inkSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
            Toggle("Group by person", isOn: $isOn)
                .labelsHidden()
                .tint(HSTheme.success)
        }
        .padding(HSTheme.Space.md)
        .background(
            RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                .fill(HSTheme.surface)
                .overlay(
                    RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                        .strokeBorder(HSTheme.border, lineWidth: 1)
                )
        )
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Processing

private struct ProcessingPane: View {
    @ObservedObject var runner: Runner

    var body: some View {
        VStack(alignment: .leading, spacing: HSTheme.Space.lg) {
            Text("Making headshots…")
                .font(HSTypography.title)
                .foregroundStyle(HSTheme.ink)
            Text(runner.total > 0
                 ? "\(runner.done) of \(runner.total) — tiles fill in as each one finishes."
                 : "Reading the folder…")
                .font(HSTypography.callout)
                .foregroundStyle(HSTheme.inkSecondary)
                .accessibilityLabel(runner.total > 0
                    ? "Processing \(runner.done) of \(runner.total)"
                    : "Reading the folder")

            ProgressView(value: Double(runner.done), total: Double(max(runner.total, 1)))
                .tint(HSTheme.accent)

            // Reserved list height so the layout does not jump when the first photo arrives.
            PhotoGradeList(photos: runner.photos)
                .frame(minHeight: 180)
        }
    }
}

// MARK: - Results

private struct ResultsPane: View {
    @ObservedObject var runner: Runner
    let folder: URL?

    var body: some View {
        VStack(alignment: .leading, spacing: HSTheme.Space.lg) {
            HStack(alignment: .top, spacing: HSTheme.Space.md) {
                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 28))
                    .foregroundStyle(HSTheme.success)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: HSTheme.Space.xs) {
                    Text("Your headshots are ready")
                        .font(HSTypography.title)
                        .foregroundStyle(HSTheme.ink)
                    if let polished = runner.polished {
                        Text(summary(polished))
                            .font(HSTypography.callout)
                            .foregroundStyle(HSTheme.inkSecondary)
                    }
                    if let grouped = runner.grouped {
                        Text("\(grouped.students) people across \(grouped.photos) photos — \(grouped.why)")
                            .font(HSTypography.caption)
                            .foregroundStyle(HSTheme.inkSecondary)
                    }
                }
            }
            .accessibilityElement(children: .combine)

            if runner.photos.isEmpty {
                EmptyStateCard(
                    systemImage: "photo.on.rectangle.angled",
                    title: "No tiles to show here",
                    detail: "The run finished, but nothing landed in the list. Open the polished folder in Finder.",
                    actionTitle: nil,
                    action: nil
                )
            } else {
                PhotoGradeList(photos: runner.photos)
                    .frame(minHeight: 200)
            }

            if let note = runner.polished?.setNote {
                Label(note, systemImage: "lightbulb")
                    .font(HSTypography.callout)
                    .foregroundStyle(HSTheme.inkSecondary)
            }
        }
    }

    private func summary(_ p: Event.Polished) -> String {
        let parts = ["PASS", "REVIEW", "FAIL", "SKIPPED"]
            .compactMap { g in (p.counts[g] ?? 0) > 0 ? "\(p.counts[g]!) \(g.lowercased())" : nil }
        var line = "\(p.processed) polished, \(p.unchanged) unchanged"
        if !parts.isEmpty { line += " — " + parts.joined(separator: ", ") }
        return line
    }
}

private struct PhotoGradeList: View {
    let photos: [Event.Photo]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(photos.suffix(40).reversed()) { photo in
                HStack(alignment: .firstTextBaseline, spacing: HSTheme.Space.sm) {
                    Circle()
                        .fill(gradeColor(photo.grade))
                        .frame(width: 8, height: 8)
                        .accessibilityHidden(true)
                    Text(photo.grade)
                        .font(HSTypography.label)
                        .foregroundStyle(gradeColor(photo.grade))
                        .frame(width: 56, alignment: .leading)
                    Text(photo.source)
                        .font(.system(.callout, design: .monospaced))
                        .foregroundStyle(HSTheme.ink)
                        .lineLimit(1)
                    Text(photo.why)
                        .font(HSTypography.caption)
                        .foregroundStyle(HSTheme.inkSecondary)
                        .lineLimit(1)
                    Spacer(minLength: 0)
                }
                .padding(.vertical, HSTheme.Space.sm)
                .accessibilityElement(children: .combine)
                .accessibilityLabel("\(photo.grade): \(photo.source). \(photo.why)")
                Divider().background(HSTheme.border)
            }
        }
    }

    private func gradeColor(_ grade: String) -> Color {
        switch grade {
        case "PASS": return HSTheme.success
        case "REVIEW": return HSTheme.warning
        default: return HSTheme.danger
        }
    }
}

// MARK: - Shared chrome

private struct EmptyStateCard: View {
    let systemImage: String
    let title: String
    let detail: String
    let actionTitle: String?
    let action: (() -> Void)?

    var body: some View {
        VStack(spacing: HSTheme.Space.md) {
            Image(systemName: systemImage)
                .font(.system(size: 28, weight: .regular))
                .foregroundStyle(HSTheme.inkSecondary)
            Text(title)
                .font(HSTypography.headline)
                .foregroundStyle(HSTheme.ink)
            Text(detail)
                .font(HSTypography.callout)
                .foregroundStyle(HSTheme.inkSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(HSPrimaryButtonStyle())
            }
        }
        .frame(maxWidth: .infinity)
        .padding(HSTheme.Space.xl)
        .background(
            RoundedRectangle(cornerRadius: HSTheme.Radius.lg, style: .continuous)
                .strokeBorder(HSTheme.border, style: StrokeStyle(lineWidth: 1, dash: [6, 4]))
        )
        .accessibilityElement(children: .contain)
    }
}

private struct ErrorBanner: View {
    let message: String
    let onDismiss: () -> Void

    var body: some View {
        HStack(alignment: .top, spacing: HSTheme.Space.md) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(HSTheme.danger)
            VStack(alignment: .leading, spacing: 4) {
                Text("Something stopped the run")
                    .font(HSTypography.headline)
                    .foregroundStyle(HSTheme.ink)
                Text(message)
                    .font(HSTypography.callout)
                    .foregroundStyle(HSTheme.inkSecondary)
                    .textSelection(.enabled)
            }
            Spacer(minLength: 0)
            Button("Dismiss", action: onDismiss)
                .buttonStyle(HSSecondaryButtonStyle())
        }
        .padding(HSTheme.Space.md)
        .background(
            RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                .fill(HSTheme.dangerSoft)
                .overlay(
                    RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                        .strokeBorder(HSTheme.danger, lineWidth: 1)
                )
        )
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Error: \(message)")
    }
}

private struct ActionBar: View {
    let step: FlowStep
    let folder: URL?
    let photoCount: Int
    let options: Options
    @ObservedObject var runner: Runner
    let onBack: () -> Void
    let onContinue: () -> Void

    var body: some View {
        HStack(spacing: HSTheme.Space.sm) {
            if step != .add {
                Button("Back", action: onBack)
                    .buttonStyle(HSSecondaryButtonStyle())
                    .disabled(runner.running && step == .finish)
            }

            Spacer(minLength: 0)

            if let polished = runner.polished, step == .save {
                Button("Show in Finder") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: polished.out))
                }
                .buttonStyle(HSSecondaryButtonStyle())
                Button("Open contact sheet") {
                    NSWorkspace.shared.open(URL(fileURLWithPath: polished.sheet))
                }
                .buttonStyle(HSSecondaryButtonStyle())
                if let grouped = runner.grouped, let first = grouped.sheets.first {
                    Button("Open people sheet") {
                        NSWorkspace.shared.open(URL(fileURLWithPath: first))
                    }
                    .buttonStyle(HSSecondaryButtonStyle())
                }
                Button("Polish again") {
                    if let folder { runner.run(folder: folder, options: options) }
                }
                .buttonStyle(HSPrimaryButtonStyle())
                .keyboardShortcut(.defaultAction)
            } else if runner.running {
                Button("Stop", role: .cancel) { runner.cancel() }
                    .buttonStyle(HSSecondaryButtonStyle())
                    .keyboardShortcut(.cancelAction)
            } else if step == .finish {
                Button("Make Headshots") { onContinue() }
                    .buttonStyle(HSPrimaryButtonStyle())
                    .keyboardShortcut(.defaultAction)
                    .disabled(folder == nil || photoCount == 0)
                    .help(folder == nil ? "Choose a folder first" : photoCount == 0 ? "No photos in this folder" : "Start polishing")
            } else if step == .check && photoCount > 0 {
                Button("Continue") { onContinue() }
                    .buttonStyle(HSPrimaryButtonStyle())
                    .keyboardShortcut(.defaultAction)
            }
        }
        .padding(.horizontal, HSTheme.Space.xl)
        .padding(.vertical, HSTheme.Space.md)
        .background(HSTheme.surface)
        .overlay(alignment: .top) {
            Rectangle().fill(HSTheme.border).frame(height: 1)
        }
    }
}

// MARK: - Button styles (fixed min width so labels do not jump — interior)

struct HSPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(HSTypography.headline)
            .foregroundStyle(HSTheme.accentOn)
            .padding(.horizontal, HSTheme.Space.lg)
            .padding(.vertical, 10)
            .frame(minWidth: 132, minHeight: 36)
            .background(
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .fill(isEnabled ? HSTheme.accent : HSTheme.borderStrong)
            )
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .animation(.hsControl(reduceMotion: reduceMotion), value: configuration.isPressed)
    }
}

struct HSSecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(HSTypography.headline)
            .foregroundStyle(isEnabled ? HSTheme.ink : HSTheme.inkSecondary)
            .padding(.horizontal, HSTheme.Space.lg)
            .padding(.vertical, 10)
            .frame(minWidth: 96, minHeight: 36)
            .background(
                RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                    .fill(configuration.isPressed ? HSTheme.surfaceMuted : HSTheme.surface)
                    .overlay(
                        RoundedRectangle(cornerRadius: HSTheme.Radius.md, style: .continuous)
                            .strokeBorder(HSTheme.borderStrong, lineWidth: 1)
                    )
            )
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.98 : 1)
            .animation(.hsControl(reduceMotion: reduceMotion), value: configuration.isPressed)
    }
}
