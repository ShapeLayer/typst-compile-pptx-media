# pptx-media

Typst 0.15+ media thumbnail and PowerPoint metadata package.

```typst
#import "@local/pptx-media:0.1.0": media
#media("movie.mp4", thumbnail: path("poster.png"),
  width: 320pt, height: 180pt,
  compatible: "pptx",
  playback: (autoplay: true, loop: true, muted: false, volume: 0.8))
```

`source` is a URL or file path string. Local video paths resolve relative to
`typst-pptx --media-root` (default: the input document directory).
Pass thumbnails as `path(...)` so they resolve in the calling document.
The default thumbnail is a built-in play image. `compatible: "none"` renders
only the image and omits PowerPoint video metadata. Ordinary Typst always
renders the image, without opening or decoding the video.

Compile with `typst-pptx document.typ document.pptx` using either background
or editable mode. See the repository README for installation and CLI options.
