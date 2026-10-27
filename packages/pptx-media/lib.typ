// Pass thumbnail: path("poster.png") to resolve a caller-owned image. Video paths
// are resolved relative to the compiler's --media-root (default: input folder).
#let media(source, thumbnail: none, width: 100%, height: 180pt,
           compatible: "pptx", playback: (:)) = {
  assert(type(source) == str, message: "media source must be a URL or path string")
  assert(compatible in ("pptx", "none"), message: "compatible must be pptx or none")
  assert(type(playback) == dictionary, message: "playback must be a dictionary")
  for (key, value) in playback {
    assert(key in ("autoplay", "loop", "muted", "volume"), message: "unknown playback setting: " + key)
    if key == "volume" {
      assert(type(value) in (int, float) and value >= 0 and value <= 1,
             message: "volume must be between 0 and 1")
    } else {
      assert(type(value) == bool, message: key + " must be boolean")
    }
  }
  block(width: width, height: height, clip: true, breakable: false,
    layout(size => context {
      if compatible == "pptx" {
        let pos = here().position()
        [#metadata((kind: "typst-pptx-media", version: 1, source: source,
          page: pos.page, x: pos.x / 1pt, y: pos.y / 1pt,
          width: size.width / 1pt, height: size.height / 1pt,
          playback: playback)) <typst-pptx-media>]
      }
      if thumbnail != none {
        image(thumbnail, width: size.width, height: size.height, fit: "contain")
      } else {
        // An image fallback needs no video decoder in ordinary Typst.
        image(bytes("<svg xmlns='http://www.w3.org/2000/svg' width='640' height='360'><rect width='640' height='360' fill='#172033'/><path d='M280 120L280 240L390 180Z' fill='white'/></svg>"),
          format: "svg", width: size.width, height: size.height, fit: "contain")
      }
    })
  )
}
