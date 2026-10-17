// Runs the bundled `headshots` command and turns its output into events on the main actor.
//
// The command lives inside the app bundle (Contents/Resources/bin/headshots). If it is missing -
// which happens when you build the app without building the command first - we say so plainly
// instead of failing silently.

import Foundation

@MainActor
final class Runner: ObservableObject {
    @Published var running = false
    @Published var done = 0
    @Published var total = 0
    @Published var photos: [Event.Photo] = []
    @Published var polished: Event.Polished?
    @Published var grouped: Event.Grouped?
    @Published var lines: [String] = []
    @Published var failure: String?

    private var process: Process?

    static var toolURL: URL? {
        let bundled = Bundle.main.resourceURL?.appendingPathComponent("bin/headshots")
        if let bundled, FileManager.default.isExecutableFile(atPath: bundled.path) { return bundled }
        // A developer build: fall back to whatever `headshots` is on PATH.
        for dir in ["/opt/homebrew/bin", "/usr/local/bin"] {
            let p = URL(fileURLWithPath: dir).appendingPathComponent("headshots")
            if FileManager.default.isExecutableFile(atPath: p.path) { return p }
        }
        return nil
    }

    /// Top-level image count for the Check step. Subfolders are ignored, matching the CLI.
    static func countPhotos(in folder: URL?) -> Int {
        guard let folder else { return 0 }
        let fm = FileManager.default
        guard let items = try? fm.contentsOfDirectory(
            at: folder,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else { return 0 }
        return items.filter { url in
            guard (try? url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile) == true else {
                return false
            }
            return DropIntake.isSupportedImage(url)
        }.count
    }

    func cancel() {
        process?.terminate()
        process = nil
        running = false
    }

    func resetResults() {
        cancel()
        photos = []
        lines = []
        polished = nil
        grouped = nil
        failure = nil
        done = 0
        total = 0
    }

    func run(folder: URL, options: Options) {
        guard let tool = Runner.toolURL else {
            failure = "The headshots command is missing from this app. Build it with `make app`, "
                + "or install it with `pipx install headshots`."
            return
        }
        photos = []; lines = []; polished = nil; grouped = nil; failure = nil
        done = 0; total = 0; running = true

        let task = Process()
        task.executableURL = tool
        task.arguments = ["--json"] + options.arguments(folder: folder)
        let out = Pipe(), err = Pipe()
        task.standardOutput = out
        task.standardError = err
        process = task

        // Stream stdout line by line so the window fills in as the work happens.
        Task.detached {
            var buffer = Data()
            let handle = out.fileHandleForReading
            while let chunk = try? handle.read(upToCount: 4096), !chunk.isEmpty {
                buffer.append(chunk)
                while let nl = buffer.firstIndex(of: UInt8(ascii: "\n")) {
                    let line = String(decoding: buffer[..<nl], as: UTF8.self)
                    buffer.removeSubrange(...nl)
                    if let event = Event.decode(line) {
                        await MainActor.run { self.apply(event) }
                    }
                }
            }
        }

        task.terminationHandler = { finished in
            let stderr = String(decoding: err.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
            Task { @MainActor in
                self.running = false
                self.process = nil
                // Exit code 1 just means at least one photo graded FAIL, which is a result, not an error.
                if finished.terminationStatus > 1 {
                    self.failure = stderr.isEmpty
                        ? "The command stopped unexpectedly. Try Polish again, or run `headshots` in Terminal for detail."
                        : stderr
                }
            }
        }

        do { try task.run() } catch {
            failure = error.localizedDescription
            running = false
        }
    }

    private func apply(_ event: Event) {
        switch event {
        case let .start(total, _, _):
            self.total = total
        case let .photo(p):
            photos.append(p)
            done += 1
        case let .polished(p):
            polished = p
        case let .grouped(g):
            grouped = g
        case let .log(text):
            let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
            if !trimmed.isEmpty { lines.append(trimmed) }
        }
    }
}

struct Options {
    enum Shape: String, CaseIterable, Identifiable {
        case fourFive = "4:5", twoThree = "2:3", square = "1:1"
        var id: String { rawValue }
        var label: String {
            switch self {
            case .fourFive: return "4:5 — standard headshot"
            case .twoThree: return "2:3 — taller, prints at 4×6"
            case .square: return "1:1 — square"
            }
        }
    }

    /// Framing presets map to `--zoom`. Defaults match the Finish mockup recommendations.
    enum Framing: String, CaseIterable, Identifiable {
        case headShoulders, closeUp, halfBody
        var id: String { rawValue }

        var title: String {
            switch self {
            case .headShoulders: return "Head & shoulders"
            case .closeUp: return "Close-up"
            case .halfBody: return "Half body"
            }
        }

        var detail: String {
            switch self {
            case .headShoulders: return "Best for most uses"
            case .closeUp: return "Face fills the frame"
            case .halfBody: return "More of the outfit"
            }
        }

        var symbol: String {
            switch self {
            case .headShoulders: return "person.crop.rectangle"
            case .closeUp: return "person.crop.circle"
            case .halfBody: return "person"
            }
        }

        var zoom: Double {
            switch self {
            case .headShoulders: return 0.85
            case .closeUp: return 1.15
            case .halfBody: return 0.70
            }
        }
    }

    var shape: Shape = .fourFive
    var width = 1600
    var framing: Framing = .headShoulders
    var blackAndWhite = false
    /// Soft studio runs the tone/colour finish. Keep original is crop-only (`--no-finish`).
    var softStudio = true
    var groupByPerson = true

    var zoom: Double { framing.zoom }

    func arguments(folder: URL) -> [String] {
        var a = [groupByPerson ? "run" : "polish", folder.path,
                 "--ratio", shape.rawValue,
                 "--width", String(width),
                 "--zoom", String(format: "%.2f", zoom)]
        a.append(blackAndWhite ? "--bw" : "--no-bw")
        a.append(softStudio ? "--finish" : "--no-finish")
        return a
    }
}
