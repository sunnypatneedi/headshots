// Resolve Finder drops into a folder the CLI can polish.
//
// Root cause of IMG_4529.JPG failing: the drop handler used to require hasDirectoryPath,
// so any file — including a normal iPhone .JPG — was ignored. Extensions are matched
// case-insensitively; keep the set in sync with src/headshots/drop.py.

import AppKit
import Foundation
import UniformTypeIdentifiers

enum DropIntake {
    /// Lowercased extensions without a leading dot. Same set as headshots.drop.IMAGE_EXTS.
    static let imageExtensions: Set<String> = [
        "jpg", "jpeg", "png", "heic", "heif", "tif", "tiff", "webp"
    ]

    /// Types the drop target advertises. fileURL covers Finder folders and files;
    /// image types help when the source vends image data alongside a URL.
    static var acceptedTypes: [UTType] {
        [.fileURL, .image, .jpeg, .png, .heic, .tiff, .folder]
    }

    struct Item: Equatable {
        let url: URL
        let isDirectory: Bool
    }

    struct Result: Equatable {
        var folder: URL?
        var message: String?
        var fromSingleImage: Bool = false
    }

    static func isSupportedImage(_ url: URL) -> Bool {
        imageExtensions.contains(url.pathExtension.lowercased())
    }

    static func resolve(_ items: [Item]) -> Result {
        if items.isEmpty {
            return Result(message: "Nothing was dropped.")
        }

        let folders = items.filter(\.isDirectory)
        let images = items.filter { !$0.isDirectory && isSupportedImage($0.url) }
        let other = items.filter { !$0.isDirectory && !isSupportedImage($0.url) }

        if !folders.isEmpty && (!images.isEmpty || !other.isEmpty) {
            return Result(message: "Drop a folder, or drop photos — not both at once.")
        }
        if folders.count > 1 {
            return Result(message: "Drop one folder at a time.")
        }
        if folders.count == 1 {
            return Result(folder: folders[0].url.standardizedFileURL)
        }
        if !other.isEmpty && images.isEmpty {
            let types = Array(Set(other.map { extLabel($0.url) })).sorted()
            let shown = types.prefix(4).joined(separator: ", ")
            return Result(
                message: "That file type isn’t supported (\(shown)). "
                    + "Drop a folder, or photos: JPG, JPEG, PNG, HEIC."
            )
        }
        if !other.isEmpty && !images.isEmpty {
            return Result(
                message: "Some dropped files aren’t photos. Drop only JPG, JPEG, PNG or HEIC — or a folder."
            )
        }
        if images.isEmpty {
            return Result(message: "Nothing was dropped.")
        }

        let parents = Set(images.map { $0.url.deletingLastPathComponent().standardizedFileURL })
        if parents.count > 1 {
            return Result(
                message: "Those photos are in different folders. Drop one folder, or photos from the same folder."
            )
        }
        guard let folder = parents.first else {
            return Result(message: "Nothing was dropped.")
        }
        // iPhone exports like IMG_4529.JPG land here: file drop → parent folder.
        return Result(folder: folder, fromSingleImage: images.count == 1)
    }

    static func resolve(urls: [URL]) -> Result {
        let items = urls.map { url -> Item in
            var isDir: ObjCBool = false
            let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDir)
            // If the path vanished mid-drop, treat image-looking names as files.
            let directory = exists ? isDir.boolValue : url.hasDirectoryPath
            return Item(url: url, isDirectory: directory)
        }
        return resolve(items)
    }

    private static func extLabel(_ url: URL) -> String {
        let ext = url.pathExtension
        return ext.isEmpty ? "(none)" : ".\(ext.lowercased())"
    }
}

enum DropReaders {
    /// Load file URLs from an NSItemProvider, trying URL object and raw fileURL data.
    static func loadURLs(from providers: [NSItemProvider]) async -> [URL] {
        var urls: [URL] = []
        for provider in providers {
            if let url = await loadURL(from: provider) {
                _ = url.startAccessingSecurityScopedResource()
                urls.append(url)
            }
        }
        return urls
    }

    private static func loadURL(from provider: NSItemProvider) async -> URL? {
        if provider.canLoadObject(ofClass: URL.self) {
            let url: URL? = await withCheckedContinuation { cont in
                _ = provider.loadObject(ofClass: URL.self) { object, _ in
                    cont.resume(returning: object as? URL)
                }
            }
            if let url { return url }
        }

        let typeId = UTType.fileURL.identifier
        guard provider.hasItemConformingToTypeIdentifier(typeId) else { return nil }
        return await withCheckedContinuation { cont in
            provider.loadItem(forTypeIdentifier: typeId, options: nil) { item, _ in
                if let url = item as? URL {
                    cont.resume(returning: url)
                } else if let data = item as? Data {
                    cont.resume(returning: URL(dataRepresentation: data, relativeTo: nil))
                } else if let str = item as? String {
                    cont.resume(returning: URL(fileURLWithPath: str))
                } else {
                    cont.resume(returning: nil)
                }
            }
        }
    }
}
