import SwiftUI
import AppKit

struct Flavor: Decodable, Identifiable, Hashable {
    let product: String
    let dir: String
    let folder: String
    let expected: String
    let installed: String
    let bundle: String
    let region: String
    let library: [String]
    let running: Bool

    var id: String { product }
    var swapped: Bool { !installed.isEmpty && !expected.isEmpty && installed != expected }
}

struct StatusData: Decodable {
    let game_dir: String
    let flavors: [Flavor]
    let cache_bytes: Int
    let library_bytes: Int
}

struct Build: Decodable, Identifiable, Hashable {
    let version: String
    let created_at: String
    let current: Bool
    let in_library: Bool

    var id: String { version }
}

struct ListData: Decodable {
    let product: String
    let region: String
    let builds: [Build]
}

enum Tool {
    static var python: String {
        let fm = FileManager.default
        for p in ["/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"]
        where fm.isExecutableFile(atPath: p) { return p }
        return "/usr/bin/python3"
    }

    static var script: String {
        let home = ("~/wow-build-fetch/wowbuild.py" as NSString).expandingTildeInPath
        if FileManager.default.isReadableFile(atPath: home) { return home }
        return Bundle.main.path(forResource: "wowbuild", ofType: "py") ?? home
    }
}

@MainActor
final class Model: ObservableObject {
    @Published var status: StatusData?
    @Published var builds: [Build] = []
    @Published var selected = ""
    @Published var log = ""
    @Published private(set) var busy = false
    @Published var error: String?

    fileprivate static weak var live: Model?
    fileprivate var child: Process?
    private var jobs = 0 { didSet { busy = jobs > 0 } }

    init() { Model.live = self }

    var flavor: Flavor? { status?.flavors.first { $0.product == selected } }

    func cancel() { child?.terminate() }

    private func capture(_ args: [String]) async -> (out: Data, err: String, code: Int32) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: Tool.python)
        p.arguments = ["-u", Tool.script] + args
        p.standardInput = FileHandle.nullDevice
        let out = Pipe()
        let err = Pipe()
        p.standardOutput = out
        p.standardError = err
        child = p
        defer { if child === p { child = nil } }

        return await withCheckedContinuation { (c: CheckedContinuation<(out: Data, err: String, code: Int32), Never>) in
            DispatchQueue.global(qos: .userInitiated).async {
                do { try p.run() } catch {
                    c.resume(returning: (Data(), error.localizedDescription, -1))
                    return
                }
                let drained = NSMutableData()
                let g = DispatchGroup()
                DispatchQueue.global(qos: .userInitiated).async(group: g) {
                    drained.append(err.fileHandleForReading.readDataToEndOfFile())
                }
                let o = out.fileHandleForReading.readDataToEndOfFile()
                g.wait()
                p.waitUntilExit()
                let e = String(data: drained as Data, encoding: .utf8) ?? ""
                c.resume(returning: (o, e, p.terminationStatus))
            }
        }
    }

    private func reason(_ r: (out: Data, err: String, code: Int32), _ fallback: String) -> String {
        let t = r.err.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? fallback : t
    }

    func refresh() async {
        jobs += 1
        defer { jobs -= 1 }
        let r = await capture(["status", "--json"])
        if let s = try? JSONDecoder().decode(StatusData.self, from: r.out) {
            status = s
            error = nil
            if !s.flavors.contains(where: { $0.product == selected }) {
                selected = (s.flavors.first { !$0.expected.isEmpty } ?? s.flavors.first)?.product ?? ""
            }
        } else {
            error = reason(r, "could not read the game folder")
        }
    }

    func reloadBuilds() async {
        guard let f = flavor, !f.expected.isEmpty else { builds = []; return }
        jobs += 1
        defer { jobs -= 1 }
        let r = await capture(["list", "--json", "-p", f.product, "-n", "25"])
        guard selected == f.product else { return }
        if let l = try? JSONDecoder().decode(ListData.self, from: r.out), l.product == f.product {
            builds = l.builds
            error = nil
        } else {
            builds = []
            error = reason(r, "could not read the build list for \(f.folder)")
        }
    }

    func run(_ args: [String]) async {
        guard !busy else { return }
        jobs += 1
        defer { jobs -= 1 }
        log = "$ \(Tool.script) \(args.joined(separator: " "))\n"

        let p = Process()
        p.executableURL = URL(fileURLWithPath: Tool.python)
        p.arguments = ["-u", Tool.script] + args
        p.standardInput = FileHandle.nullDevice
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        let h = pipe.fileHandleForReading
        child = p
        defer { if child === p { child = nil } }

        h.readabilityHandler = { fh in
            let d = fh.availableData
            guard !d.isEmpty, let s = String(data: d, encoding: .utf8) else { return }
            Task { @MainActor in self.log += s }
        }

        let note: String? = await withCheckedContinuation { (c: CheckedContinuation<String?, Never>) in
            p.terminationHandler = { proc in
                h.readabilityHandler = nil
                let rest = h.readDataToEndOfFile()
                if let s = String(data: rest, encoding: .utf8), !s.isEmpty {
                    Task { @MainActor in self.log += s }
                }
                if proc.terminationReason == .uncaughtSignal {
                    c.resume(returning: "stopped before it finished\n")
                } else if proc.terminationStatus != 0 {
                    c.resume(returning: "exited with code \(proc.terminationStatus)\n")
                } else {
                    c.resume(returning: nil)
                }
            }
            do {
                try p.run()
            } catch {
                p.terminationHandler = nil
                h.readabilityHandler = nil
                c.resume(returning: "failed to launch: \(error.localizedDescription)\n")
            }
        }

        if let n = note { log += n }

        await refresh()
        await reloadBuilds()
    }
}

struct ContentView: View {
    @StateObject private var m = Model()
    @State private var confirming: Build?
    @State private var confirmRevert = false

    var body: some View {
        VStack(spacing: 0) {
            header
            Divider()
            if let e = m.error {
                Text(e).foregroundStyle(.red).padding()
                Spacer()
            } else if m.status != nil && m.builds.isEmpty && !m.busy {
                Text(placeholder).font(.callout).foregroundStyle(.secondary).padding()
                Spacer()
            } else {
                List {
                    ForEach(m.builds) { b in
                        BuildRow(build: b, flavor: m.flavor, busy: m.busy) { confirming = b }
                    }
                }
                .listStyle(.inset)
            }
            Divider()
            footer
        }
        .frame(minWidth: 720, minHeight: 560)
        .task { await m.refresh() }
        .alert("Switch to \(confirming?.version ?? "")?",
               isPresented: Binding(get: { confirming != nil },
                                    set: { if !$0 { confirming = nil } })) {
            Button("Cancel", role: .cancel) {}
            Button("Switch") {
                guard let b = confirming else { return }
                confirming = nil
                Task { await m.run(["install", b.version, "-p", m.selected, "-y"]) }
            }
        } message: {
            Text("Replaces the app bundle in \(m.flavor?.dir ?? "").\nYour current build is kept in the library, so you can switch back.")
        }
        .alert("Restore \(m.flavor?.expected ?? "")?", isPresented: $confirmRevert) {
            Button("Cancel", role: .cancel) {}
            Button("Restore") {
                Task { await m.run(["revert", "-p", m.selected]) }
            }
        } message: {
            Text(revertMessage)
        }
    }

    private var placeholder: String {
        guard let f = m.flavor else { return "no World of Warcraft folder found" }
        if f.expected.isEmpty {
            return "Battle.net has no active branch for \(f.folder), so there is nothing to list."
        }
        return "no builds found for \(f.folder)."
    }

    private var revertMessage: String {
        let base = "Puts back the build Battle.net expects."
        guard let f = m.flavor, !f.expected.isEmpty, !f.library.contains(f.expected) else { return base }
        return base + "\n\(f.expected) is not in the library, so it is downloaded from Blizzard's CDN first."
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("WoW Build Switcher").font(.title2.weight(.semibold))
                Spacer()
                if m.busy { ProgressView().controlSize(.small) }
                Button {
                    Task { await m.refresh(); await m.reloadBuilds() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .disabled(m.busy)
            }
            if let s = m.status {
                Picker("", selection: $m.selected) {
                    ForEach(s.flavors) { f in
                        Text(f.folder).tag(f.product)
                    }
                }
                .pickerStyle(SegmentedPickerStyle())
                .labelsHidden()
                .disabled(m.busy)
                .onChange(of: m.selected, initial: true) {
                    Task { await m.reloadBuilds() }
                }
                if let f = m.flavor {
                    HStack(spacing: 18) {
                        Label {
                            Text(f.installed).font(.system(.callout, design: .monospaced))
                        } icon: {
                            Image(systemName: f.swapped ? "exclamationmark.triangle.fill"
                                                        : "checkmark.circle.fill")
                                .foregroundStyle(f.swapped ? Color.orange : Color.green)
                        }
                        Text(f.expected.isEmpty ? "Battle.net has no active branch"
                                                : "Battle.net expects \(f.expected)")
                            .font(.callout).foregroundStyle(.secondary)
                        Spacer()
                        if f.running { Tag(text: "running", color: .orange) }
                        Text(f.region).font(.caption).foregroundStyle(.secondary)
                    }
                    Text(s.game_dir).font(.caption).foregroundStyle(.tertiary).lineLimit(1)
                }
            }
        }
        .padding(14)
    }

    private var footer: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !m.log.isEmpty {
                ScrollView {
                    Text(m.log)
                        .font(.system(size: 11, weight: .regular, design: .monospaced))
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .defaultScrollAnchor(.bottom)
                .frame(height: 130)
                .background(Color(nsColor: .textBackgroundColor),
                            in: RoundedRectangle(cornerRadius: 6, style: .continuous))
            }
            HStack {
                Button("Restore Battle.net Build") { confirmRevert = true }
                    .disabled(m.busy
                              || !(m.flavor?.swapped ?? false)
                              || (m.flavor?.running ?? true))
                if let f = m.flavor {
                    Button("Open Folder") { NSWorkspace.shared.open(URL(fileURLWithPath: f.dir)) }
                }
                if m.busy {
                    Button("Stop") { m.cancel() }
                }
                Spacer()
                if let s = m.status {
                    Text("library \(Int64(s.library_bytes).formatted(.byteCount(style: .file))) · cache \(Int64(s.cache_bytes).formatted(.byteCount(style: .file)))")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }
        }
        .padding(14)
    }
}

struct BuildRow: View {
    let build: Build
    let flavor: Flavor?
    let busy: Bool
    let install: () -> Void

    private var isActive: Bool { build.version == flavor?.installed }

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: build.current ? "largecircle.fill.circle" : "circle")
                .foregroundStyle(build.current ? Color.accentColor : Color.secondary.opacity(0.4))
            VStack(alignment: .leading) {
                Text(build.version).font(.system(.body, design: .monospaced))
                Text(build.created_at).font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if build.current { Tag(text: "Battle.net", color: .blue) }
            if build.in_library { Tag(text: "Downloaded", color: .green) }
            Button(isActive ? "Active" : (build.in_library ? "Switch" : "Download")) { install() }
                .disabled(isActive || busy || flavor == nil || flavor?.running == true)
        }
    }
}

struct Tag: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.caption2.weight(.medium))
            .padding(.horizontal, 7)
            .padding(.vertical, 2)
            .background(color.opacity(0.16), in: Capsule())
            .foregroundStyle(color)
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        MainActor.assumeIsolated { () -> NSApplication.TerminateReply in
            guard let p = Model.live?.child, p.isRunning else { return .terminateNow }
            p.terminate()
            DispatchQueue.global(qos: .userInitiated).async {
                p.waitUntilExit()
                DispatchQueue.main.async { sender.reply(toApplicationShouldTerminate: true) }
            }
            return .terminateLater
        }
    }
}

struct WowBuildApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup("WoW Build Switcher") { ContentView() }
            .defaultSize(width: 760, height: 620)
    }
}

WowBuildApp.main()
