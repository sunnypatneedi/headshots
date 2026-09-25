// Gallery + lightbox: image-first results (IINA-ish quiet chrome), calm empty (Harbor).

import AppKit
import SwiftUI

enum GalleryFilter: String, CaseIterable, Identifiable {
    case all = "All"
    case pass = "Pass"
    case review = "Review"
    case fail = "Fail"

    var id: String { rawValue }

    func matches(_ grade: String) -> Bool {
        switch self {
        case .all: return true
        case .pass: return grade == "PASS"
        case .review: return grade == "REVIEW"
        case .fail: return grade == "FAIL"
        }
    }
}

struct GalleryPanel: View {
    let photos: [Event.Photo]
    let outDir: String?
    let running: Bool
    @Binding var filter: GalleryFilter
    @Binding var selection: Event.Photo.ID?

    private var filtered: [Event.Photo] {
        photos.filter { filter.matches($0.grade) }
    }

    private let columns = [GridItem(.adaptive(minimum: 132, maximum: 200), spacing: 12)]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                Text("Gallery")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer(minLength: 8)
                Picker("Filter", selection: $filter) {
                    ForEach(GalleryFilter.allCases) { Text($0.rawValue).tag($0) }
                }
                .pickerStyle(.segmented)
                .frame(maxWidth: 320)
                .accessibilityLabel("Filter gallery by grade")
            }

            if photos.isEmpty && running {
                GalleryEmptyState(
                    title: "Polishing…",
                    detail: "Tiles appear here as each photo finishes — originals stay untouched.",
                    systemImage: "sparkles",
                    showsProgress: true
                )
            } else if photos.isEmpty {
                GalleryEmptyState(
                    title: "No polished photos yet",
                    detail: "Run Polish to build a matched set. Results land in this gallery.",
                    systemImage: "photo.on.rectangle.angled",
                    showsProgress: false
                )
            } else if filtered.isEmpty {
                GalleryEmptyState(
                    title: "Nothing in \(filter.rawValue.lowercased())",
                    detail: "Try All, or another grade filter.",
                    systemImage: "line.3.horizontal.decrease.circle",
                    showsProgress: false
                )
            } else {
                LazyVGrid(columns: columns, spacing: 12) {
                    ForEach(filtered) { photo in
                        GalleryTile(
                            photo: photo,
                            imageURL: imageURL(for: photo),
                            isSelected: selection == photo.id
                        ) {
                            selection = photo.id
                        }
                    }
                }
            }
        }
        .sheet(item: selectedPhoto) { photo in
            LightboxView(
                photos: filtered,
                photo: photo,
                outDir: outDir,
                onClose: { selection = nil }
            )
        }
    }

    private var selectedPhoto: Binding<Event.Photo?> {
        Binding(
            get: { filtered.first { $0.id == selection } ?? photos.first { $0.id == selection } },
            set: { selection = $0?.id }
        )
    }

    private func imageURL(for photo: Event.Photo) -> URL? {
        guard let name = photo.output, let outDir, !name.isEmpty else { return nil }
        return URL(fileURLWithPath: outDir).appendingPathComponent(name)
    }
}

// MARK: - Tile

private struct GalleryTile: View {
    let photo: Event.Photo
    let imageURL: URL?
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 6) {
                ZStack(alignment: .topTrailing) {
                    ThumbnailView(url: imageURL)
                        .frame(maxWidth: .infinity)
                        .aspectRatio(4 / 5, contentMode: .fit)
                        .clipShape(RoundedRectangle(cornerRadius: 10, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .strokeBorder(
                                    isSelected ? Color.accentColor : Color.secondary.opacity(0.2),
                                    lineWidth: isSelected ? 2 : 1
                                )
                        )

                    GradeBadge(grade: photo.grade)
                        .padding(8)
                }

                Text(photo.source)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(photo.grade), \(photo.source)")
        .accessibilityHint(photo.why.isEmpty ? "Show larger preview" : photo.why)
        .help(photo.why.isEmpty ? photo.source : "\(photo.source) — \(photo.why)")
    }
}

// MARK: - Thumbnail

struct ThumbnailView: View {
    let url: URL?
    @State private var image: NSImage?

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 10, style: .continuous)
                .fill(Color.primary.opacity(0.06))
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFill()
            } else {
                Image(systemName: url == nil ? "photo" : "photo.badge.arrow.down")
                    .font(.title2)
                    .foregroundStyle(.tertiary)
            }
        }
        .clipped()
        .task(id: url?.path) { await load() }
    }

    @MainActor
    private func load() async {
        image = nil
        guard let url else { return }
        let path = url.path
        let loaded = await Task.detached(priority: .utility) {
            NSImage(contentsOfFile: path)
        }.value
        image = loaded
    }
}

// MARK: - Empty

private struct GalleryEmptyState: View {
    let title: String
    let detail: String
    let systemImage: String
    let showsProgress: Bool

    var body: some View {
        VStack(spacing: 10) {
            if showsProgress {
                ProgressView()
                    .controlSize(.small)
            } else {
                Image(systemName: systemImage)
                    .font(.system(size: 28, weight: .medium))
                    .foregroundStyle(.secondary)
                    .symbolRenderingMode(.hierarchical)
            }
            Text(title)
                .font(.headline)
            Text(detail)
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 360)
        }
        .frame(maxWidth: .infinity, minHeight: 180)
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .fill(.ultraThinMaterial)
        )
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .strokeBorder(Color.secondary.opacity(0.22), style: StrokeStyle(lineWidth: 1, dash: [5, 4]))
        )
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Lightbox (image-first, quiet chrome)

private struct LightboxView: View {
    let photos: [Event.Photo]
    let photo: Event.Photo
    let outDir: String?
    let onClose: () -> Void

    @State private var index: Int = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(spacing: 0) {
            ZStack {
                Color.black.opacity(0.92).ignoresSafeArea()
                if let url = imageURL(for: current) {
                    LightboxImage(url: url)
                        .padding(24)
                } else {
                    VStack(spacing: 8) {
                        Image(systemName: "photo")
                            .font(.largeTitle)
                            .foregroundStyle(.white.opacity(0.5))
                        Text("No output file for this photo")
                            .foregroundStyle(.white.opacity(0.7))
                    }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)

            // Floating media chrome — quiet, IINA-ish.
            HStack(spacing: 14) {
                GradeBadge(grade: current.grade)
                VStack(alignment: .leading, spacing: 2) {
                    Text(current.source)
                        .font(.headline)
                        .foregroundStyle(.primary)
                        .lineLimit(1)
                    if !current.why.isEmpty {
                        Text(current.why)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                }
                Spacer(minLength: 8)
                Button {
                    step(-1)
                } label: {
                    Image(systemName: "chevron.left")
                }
                .disabled(photos.count < 2)
                .accessibilityLabel("Previous photo")

                Text("\(index + 1) / \(max(photos.count, 1))")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)

                Button {
                    step(1)
                } label: {
                    Image(systemName: "chevron.right")
                }
                .disabled(photos.count < 2)
                .accessibilityLabel("Next photo")

                Button("Done", action: onClose)
                    .keyboardShortcut(.cancelAction)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(.bar)
        }
        .frame(minWidth: 720, minHeight: 560)
        .onAppear {
            index = photos.firstIndex(where: { $0.id == photo.id }) ?? 0
        }
    }

    private var current: Event.Photo {
        guard photos.indices.contains(index) else { return photo }
        return photos[index]
    }

    private func step(_ delta: Int) {
        guard !photos.isEmpty else { return }
        let next = (index + delta + photos.count) % photos.count
        if reduceMotion {
            index = next
        } else {
            withAnimation(.easeInOut(duration: 0.18)) { index = next }
        }
    }

    private func imageURL(for photo: Event.Photo) -> URL? {
        guard let name = photo.output, let outDir, !name.isEmpty else { return nil }
        return URL(fileURLWithPath: outDir).appendingPathComponent(name)
    }
}

private struct LightboxImage: View {
    let url: URL
    @State private var image: NSImage?

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .scaledToFit()
                    .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
                    .shadow(color: .black.opacity(0.35), radius: 24, y: 8)
            } else {
                ProgressView()
                    .controlSize(.regular)
                    .tint(.white)
            }
        }
        .task(id: url.path) {
            let path = url.path
            image = await Task.detached(priority: .userInitiated) {
                NSImage(contentsOfFile: path)
            }.value
        }
    }
}

// sheet(item:) needs Identifiable — Event.Photo already is.
extension Event.Photo: Hashable {
    static func == (lhs: Event.Photo, rhs: Event.Photo) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
