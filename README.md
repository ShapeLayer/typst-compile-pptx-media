# typst-compile-pptx-media

Typst 문서를 PowerPoint로 내보내는 독립 CLI 확장과 `pptx-media` Typst 패키지입니다.
Typst 자체를 수정하지 않고 설치된 Typst CLI를 호출합니다.

## 설치

Python 3.10 이상과 Typst 0.15 이상이 필요합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

## 컴파일

```sh
# 페이지별 PNG를 실제 슬라이드 배경(p:bg)으로 지정
 typst-pptx slides.typ slides.pptx --mode background

# JPEG 또는 SVG 배경. SVG에는 이전 Office용 PNG 대체 이미지도 포함
 typst-pptx slides.typ slides.pptx --background-format jpeg --ppi 192
 typst-pptx slides.typ slides.pptx --background-format svg

# 텍스트, 벡터 경로, 이미지를 각각 편집 가능한 PowerPoint 개체로 변환
 typst-pptx slides.typ slides.pptx --mode editable

# 저장소 예제는 상위 폴더의 패키지를 가져오므로 프로젝트 루트를 지정
 typst-pptx examples/demo.typ build/demo.pptx --root . --mode editable
```

모든 Typst 페이지가 슬라이드가 됩니다. PowerPoint는 파일 전체가 하나의 슬라이드 크기를
사용하므로 페이지 크기가 다른 문서는 오류로 처리합니다. 출력은 성공 시에만 교체합니다.

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| `--mode` | `background` | `background` 또는 `editable` |
| `--background-format` | `png` | `png`, `jpeg`, `svg` (배경 모드) |
| `--ppi` | `144` | 배경 래스터 이미지 해상도 |
| `--root` | 입력 파일 폴더 | Typst 프로젝트 루트 |
| `--media-root` | 입력 파일 폴더 | 상대 영상 경로를 해석할 폴더 |
| `--typst` | `typst` | Typst 실행 파일 |
| `--input KEY=VALUE` | 없음 | `sys.inputs` 값; 여러 번 지정 가능 |
| `--font-path PATH` | 없음 | 추가 폰트 검색 폴더; 여러 번 지정 가능 |

Python에서도 `from typst_pptx import compile_pptx` 후
`compile_pptx("slides.typ", "slides.pptx", mode="editable")`로 호출할 수 있습니다.

## Typst media 함수

직접 가져오거나 `packages/pptx-media`를 Typst 로컬 패키지 경로의
`local/pptx-media/0.1.0`에 복사하여 `@local/pptx-media:0.1.0`으로 가져옵니다.
Python wheel 설치에도 `<Python 환경>/share/typst-pptx/pptx-media` 경로에 패키지가 포함됩니다.

```typst
#import "packages/pptx-media/lib.typ": media
#set page(width: 720pt, height: 405pt)

// 로컬 파일은 PPTX 내부에 포함됩니다.
#media("assets/movie.mp4",
  thumbnail: path("assets/poster.png"),
  width: 480pt,
  height: 270pt,
  playback: (autoplay: true, loop: true, muted: true),
)

// HTTP(S) URL은 다운로드하지 않고 외부 영상으로 연결합니다.
#media("https://example.org/movie.mp4",
  width: 480pt,
  height: 270pt,
  playback: (autoplay: false, volume: 0.6),
)

// 일반 이미지로만 내보내고, PPTX 영상 개체는 만들지 않습니다.
#media("assets/movie.mp4",
  thumbnail: path("assets/poster.png"),
  compatible: "none",
)
```

시그니처:

```typst
media(source, thumbnail: none, width: 100%, height: 180pt,
      compatible: "pptx", playback: (:))
```

- `source`: 영상 URL 또는 파일 경로 문자열. 상대 영상 경로는 컴파일러의 `--media-root`
  기준입니다. 로컬 영상은 mp4, m4v, mov, avi, wmv, webm, mpeg, mpg 확장자를 지원합니다.
- `thumbnail`: `path("poster.png")` 또는 이미지 bytes. 지정하지 않으면 내장 재생 아이콘
  이미지가 사용됩니다. 썸네일은 지정한 영역을 `cover` 방식으로 채웁니다.
- `compatible`: `"pptx"`가 기본값이며 영상 메타데이터를 기록합니다. `"none"`이면 기록하지
  않으므로 영상 파일이 존재하지 않아도 썸네일만 렌더링할 수 있습니다.
- `playback`: `autoplay`, `loop`, `muted`는 bool이며 기본값은 모두 false입니다.
  `volume`은 0–1이며 기본값은 1입니다. `muted: true`이면 volume보다 우선합니다.
  자동 재생을 끄면 영상 개체를 클릭하여 재생합니다.

썸네일은 호출한 문서에서 `path(...)`로 만들어 전달하세요. Typst 패키지 내부에서 문자열
경로를 이미지로 읽으면 해당 패키지 위치를 기준으로 해석되기 때문입니다.
일반 Typst PDF/PNG/SVG 출력에는 영상 디코딩이나 네트워크 접속 없이 이미지가 표시됩니다.
PPTX 내보내기에는 두 모드 모두 같은 위치에 썸네일을 가진 영상 개체가 추가됩니다.
영상은 페이지 사이에 나뉘지 않으며 한 페이지 안에 완전히 들어가야 합니다.

## 편집 모드의 변환 범위

PDF의 문자와 폰트·크기·색상을 텍스트 상자로, 선·사각형·베지어 경로를 DrawingML
도형으로, 이미지를 별도 그림 개체로 변환합니다. PDF의 그리기 순서를 유지합니다.
표와 차트는 원래 Typst의 선·텍스트 등 구성 개체로 편집하며 PowerPoint의 표/차트
데이터 모델로 재구성하지는 않습니다. 수식은 추출 가능한 문자와 경로로 변환됩니다.

그라디언트는 다른 내용과 분리된 그림 개체로 보존합니다. 분리할 수 없는 PDF 셰이딩은
내용을 생략하지 않고 오류로 알립니다. PDF를 거치므로 복잡한 클리핑, 문자 배치·폰트
대체는 원본과 차이가 날 수 있습니다. 정확한 외형이 우선이면 배경 모드를 사용하세요. Office에서 영상 코덱과
HTTP 링크 재생을 지원해야 하며, 외부 URL 재생에는 네트워크가 필요합니다.
웹페이지 URL(예: 일반 동영상 시청 페이지)은 원시 영상 파일 URL과 다릅니다.

## Misc

기술 참조: [Typst 메타데이터](https://typst.app/docs/reference/introspection/metadata/),
[Typst path](https://typst.app/docs/reference/foundations/path/),
[PyMuPDF 추출 API](https://pymupdf.readthedocs.io/en/latest/functions.html),
[PowerPoint 미디어 노드](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.commonmedianode?view=openxml-3.0.1).
