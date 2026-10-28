# typst-compile-pptx-media

Typst 문서를 PowerPoint로 내보내는 독립 CLI 확장과 `pptx-media` Typst 패키지입니다.

[사용 사례](https://github.com/shapelayer-args/basic-physics-experiments-2-seminar)

## 설치

Python 3.10 이상과 Typst 0.15 이상, FFmpeg 6 이상이 필요합니다.　　

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

혹은 

```sh
pip install pipx
pipx install .
```

## 컴파일

```sh
# 기본값: 페이지를 벡터 그래픽으로 변환하여 슬라이드 배경으로 지정
 typst-pptx slides.typ slides.pptx --mode background

# 페이지를 래스터 이미지로 변환하여 슬라이드 배경으로 지정
 typst-pptx slides.typ slides.pptx --background-format jpeg --ppi 192
 typst-pptx slides.typ slides.pptx --background-format png

# 편집 모드: 편집 가능한 텍스트 + 개별 SVG 벡터 이미지
 typst-pptx slides.typ slides.pptx --mode editable

# 벡터 그래픽 포맷을 PowerPoint 도형으로 다루기
 typst-pptx slides.typ slides.pptx --mode editable --vector-format native

# 예제 컴파일
 typst-pptx examples/demo.typ build/demo.pptx --root . --mode editable
```

| 옵션 | 기본값 | 의미 |
| --- | --- | --- |
| `--mode` | `background` | `background` 또는 `editable` |
| `--background-format` | `svg` | `png`, `jpeg`, `svg` (배경 모드) |
| `--vector-format` | `svg` | `svg` 벡터 이미지 또는 `native` PowerPoint 도형 (편집 모드) |
| `--ppi` | `192` | 래스터 배경·SVG 대체 이미지 해상도 |
| `--root` | 입력 파일 폴더 | Typst 프로젝트 루트 |
| `--media-root` | 입력 파일 폴더 | 상대 영상 경로를 해석할 폴더 |
| `--video-conversion` | `ask` | 호환 프로필 미충족 시 `ask` 확인, `convert` 변환, `error` 중단 |
| `--video-foreground` | `ask` | 배경 모드에서 전경 겹침 시 `ask` 질문, `composite` 합성, `preserve` 합성 없이 유지, `error` 중단 |
| `--ffprobe` | `ffprobe` | 영상 검사 실행 파일 |
| `--ffmpeg` | `ffmpeg` | 영상 변환 실행 파일 |
| `--typst` | `typst` | Typst 실행 파일 |
| `--input KEY=VALUE` | 없음 | `sys.inputs` 값; 여러 번 지정 가능 |
| `--font-path PATH` | 없음 | 추가 폰트 검색 폴더; 여러 번 지정 가능 |

이 프로젝트는 Python 라이브러리로 구성되어있어 Python API를 호출하여 컴파일할 수 있습니다.  
```py
from typst_pptx import compile_pptx
compile_pptx("slides.typ", "slides.pptx", mode="editable")
```

## Typst media 함수

이 프로젝트에서 영상을 PPTX에 포함하려면 Typst 패키지 `pptx-media`가 필요합니다.  

`packages/pptx-media`를 직접 프로젝트에 복사하여 포함시키거나, Typst 로컬 패키지 경로의 `local/pptx-media/0.1.0`에 복사하여 `@local/pptx-media:0.1.0`로 사용할 수 있습니다. Python wheel에도 `<Python 환경>/share/typst-pptx/pptx-media` 경로에 패키지가 포함됩니다.  

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

// HTTP(S) URL도 다운로드한 영상 파일을 PPTX 내부에 포함합니다.
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

- `source`: 영상 URL 또는 파일 경로 문자열. 상대 영상 경로는 컴파일러의 `--media-root`를 기준으로 합니다.
- `thumbnail`: `path("poster.png")` 또는 이미지 bytes. 지정하지 않으면 내장 재생 아이콘 이미지가 사용됩니다.
- `compatible`: (`"pptx"`(기본값) 또는 `"none"`) 대상 형식에 대응하는 메타데이터를 컴파일 시 함께 기록합니다.
  - `"pptx"`: PPTX 내보내기 시 영상 개체를 만듭니다.
  - `"none"`: 아무 작업을 하지 않습니다.
- `playback`: (Dictionary) `autoplay`(`bool`), `loop`(`bool`), `muted`(`bool`), `volume`(`float`)
  - `compatible: "pptx"` 시
    - `float volume`: 볼륨
    - `bool autoplay`: 자동 재생 여부
    - `bool loop`: 반복 재생 여부
    - `bool muted`: 음소거 여부

썸네일은 호출한 문서에서 `path(...)`로 만들어 전달하세요. Typst 패키지 내부에서 문자열 경로를 이미지로 읽으면 해당 패키지 위치를 기준으로 해석될 수 있습니다. 

## 옵션

```sh
# 기본 동작: 필요한 경우 변환 여부 확인
 typst-pptx slides.typ slides.pptx

# 스크립트/CI에서 필요한 변환을 미리 승인
 typst-pptx slides.typ slides.pptx --video-conversion convert

# 호환 프로필에 맞지 않으면 변환 없이 오류로 중단
 typst-pptx slides.typ slides.pptx --video-conversion error

# 영상 변환 시 영상 위에 콘텐츠 요소가 있을 때 정책
typst-pptx main.typ main.pptx --video-foreground ask        # 사용자에게 묻기
typst-pptx main.typ main.pptx --video-foreground composite  # 합성
  # 관련하여 추가 처리 않음(영상이 다른 콘텐츠를 가릴 수도 있습니다.)
typst-pptx main.typ main.pptx --video-foreground preserve
typst-pptx main.typ main.pptx --video-foreground error      # 중단
```

## Misc

기술 참조: [Typst 메타데이터](https://typst.app/docs/reference/introspection/metadata/),
[Typst path](https://typst.app/docs/reference/foundations/path/),
[PyMuPDF 추출 API](https://pymupdf.readthedocs.io/en/latest/functions.html),
[PowerPoint 미디어 노드](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.commonmedianode?view=openxml-3.0.1).
