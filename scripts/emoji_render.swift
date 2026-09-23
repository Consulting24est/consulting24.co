import AppKit
// usage: swift emoji_render.swift <outdir> <size> name=TEXT name=TEXT ...
let args = CommandLine.arguments
let outdir = args[1]; let size = CGFloat(Double(args[2])!)
for pair in args[3...] {
    let parts = pair.split(separator: "=", maxSplits: 1).map(String.init)
    let name = parts[0]; let txt = parts[1]
    let font = NSFont(name: "AppleColorEmoji", size: size) ?? NSFont.systemFont(ofSize: size)
    let attr = NSAttributedString(string: txt, attributes: [.font: font])
    let sz = attr.size()
    let w = Int(ceil(sz.width)) + 4, h = Int(ceil(sz.height)) + 4
    let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: w, pixelsHigh: h, bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    attr.draw(at: NSPoint(x: 2, y: 2))
    NSGraphicsContext.restoreGraphicsState()
    let png = rep.representation(using: .png, properties: [:])!
    try! png.write(to: URL(fileURLWithPath: "\(outdir)/\(name).png"))
}
print("rendered \(args.count - 3)")
