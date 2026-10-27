#import "../packages/pptx-media/lib.typ": media
#set page(width: 720pt, height: 405pt, margin: 36pt)
#set text(size: 24pt)
= Embedded video
#media("../tests/fixtures/video.mp4", width: 400pt, height: 225pt,
  playback: (autoplay: true, loop: true, muted: true))
#pagebreak()
= Click to play
#media("../tests/fixtures/video.mp4", width: 400pt, height: 225pt,
  playback: (volume: 0.5))
