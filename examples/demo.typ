#import "../packages/pptx-media/lib.typ": media
#set page(width: 720pt, height: 405pt, margin: 36pt)
#set text(size: 24pt)
= Typst → PowerPoint
Editable text, shapes, and video.
#rect(width: 200pt, height: 45pt, fill: rgb("#4775d1"), radius: 8pt)
#pagebreak()
= Video
#media("https://example.com/video.mp4", width: 360pt, height: 202.5pt,
  playback: (autoplay: true, loop: true, muted: true))
