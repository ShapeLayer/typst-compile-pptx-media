# typst-compile-pptx-media

Typst 문서를 PowerPoint로 내보내는 독립 CLI 확장과 `pptx-media` Typst 패키지입니다.
Typst 자체를 수정하지 않고 설치된 Typst CLI를 호출합니다.

## 설치

Python 3.10 이상과 Typst 0.15 이상이 필요합니다. 영상이 있는 문서를 컴파일하는 과정에서 FFmpeg의 `ffprobe`와 `ffmpeg`가 필요합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

```sh
pip install pipx
pipx install .
```

## 컴파일

```sh
# 기본값: 페이지별 SVG를 실제 슬라이드 배경(p:bg)으로 지정
 typst-pptx slides.typ slides.pptx --mode background

# PNG 또는 JPEG 배경. SVG에는 이전 Office용 PNG 대체 이미지도 포함
 typst-pptx slides.typ slides.pptx --background-format jpeg --ppi 192
 typst-pptx slides.typ slides.pptx --background-format png

# 편집 모드 기본값: 편집 가능한 텍스트 + 개별 SVG 벡터 이미지
 typst-pptx slides.typ slides.pptx --mode editable

# 벡터 경로 자체를 PowerPoint 도형으로 편집하려면
 typst-pptx slides.typ slides.pptx --mode editable --vector-format native

# 저장소 예제는 상위 폴더의 패키지를 가져오므로 프로젝트 루트를 지정
 typst-pptx examples/demo.typ build/demo.pptx --root . --mode editable
```

모든 Typst 페이지가 슬라이드가 됩니다. PowerPoint는 파일 전체가 하나의 슬라이드 크기를
사용하므로 페이지 크기가 다른 문서는 오류로 처리합니다. 출력은 성공 시에만 교체합니다.

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

- `source`: 영상 URL 또는 파일 경로 문자열. 상대 영상 경로는 컴파일러의 `--media-root`
  기준입니다. 영상 코덱과 컨테이너는 컴파일 시 검사하며, 필요하면 승인 후 MP4로 변환합니다.
- `thumbnail`: `path("poster.png")` 또는 이미지 bytes. 지정하지 않으면 내장 재생 아이콘
  이미지가 사용됩니다. 썸네일은 지정한 영역 안에 `contain` 방식으로 원본 비율을 유지해 표시합니다.
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
컴파일러는 영상의 실제 표시 비율(픽셀 비율과 회전 정보 포함)을 검사하고, 지정한 영역
안에 가로·세로를 같은 배율로 맞춰 중앙에 배치합니다. 남는 공간을 채우기 위해 영상을
늘리지 않습니다. 이전 패키지를 프로젝트에 복사해 사용했다면 `lib.typ`도 갱신해야
썸네일과 재생 중 영상의 배치가 일치합니다.

## 영상 코덱 검사와 변환

기존 버전에서 생성한 PPTX의 영상 클릭이 다음 슬라이드로 넘어간다면 최신 컴파일러로
다시 내보내세요. 영상 인식용 확장 식별자와 PowerPoint의 주 재생·클릭 제어 시퀀스를
수정했습니다. 일반 Open XML 스키마 검사는 확장 식별자의 의미까지 검증하지 않습니다.

영상 파일은 로컬 경로와 URL 모두 `ffprobe`로 실제 코덱을 검사합니다. 확장자만으로
지원 여부를 판단하지 않습니다. 운영체제별 차이를 줄이기 위한 공통 호환 프로필은
H.264 영상, 8비트 4:2:0(`yuv420p`/`yuvj420p`), AAC 음성(또는 무음), MP4/M4V/MOV입니다.
이 프로필 밖의 모든 형식이 모든 PowerPoint에서 재생 불가능하다는 의미는 아닙니다.
Microsoft의 [권장 형식](https://support.microsoft.com/en-us/powerpoint/video-and-audio-file-formats-supported-in-powerpoint)은 H.264/AAC MP4입니다.

기본 `ask`에서는 프로필에 맞지 않는 영상의 현재 코덱과 이유를 표시하고
`H.264/AAC MP4로 변환하여 포함할까요? [y/N]`로 묻습니다. 명시적으로 승인해야 변환하며,
거절·빈 입력·입력 종료 시 컴파일을 중단합니다. 원본 파일과 기존 PPTX 출력은 유지됩니다.
승인한 변환은 임시 파일에서 수행하고 결과를 다시 검사한 뒤 PPTX에 포함합니다.
같은 영상이 여러 슬라이드에서 반복되면 한 번만 검사하고 확인·변환합니다.

```sh
# 기본 동작: 필요한 경우 변환 여부 확인
 typst-pptx slides.typ slides.pptx

# 스크립트/CI에서 필요한 변환을 미리 승인
 typst-pptx slides.typ slides.pptx --video-conversion convert

# 호환 프로필에 맞지 않으면 변환 없이 오류로 중단
 typst-pptx slides.typ slides.pptx --video-conversion error
```

대화형 터미널이 없으면 `ask`가 자동으로 승인하지 않으며 위의 명시적 옵션을 안내합니다.
검사 도구 부재, 손상된 영상, 변환 실패도 오류로 처리하며 검사를 생략하지 않습니다.
파일 확장자와 관계없이 FFmpeg가 읽을 수 있는 영상(예: MKV)도 검사·변환 대상으로 받을 수 있습니다.
변환 시 첫 실제 영상 트랙과 음성 트랙을 사용하며, 원본 컨테이너의 자막·첨부 파일은 포함하지 않습니다.

Python API는 기본적으로 사용자 입력을 직접 읽지 않습니다. `video_conversion="convert"` 또는
`"error"`를 지정하거나, `confirm_video_conversion(source, inspection) -> bool` 콜백으로
확인 UI를 연결하세요. `inspection.description`과 `inspection.reasons`에 검사 결과가 있습니다.

## 편집 모드의 변환 범위

PDF의 문자와 폰트·크기·색상을 텍스트 상자로, 선·사각형·베지어 경로를 개별 SVG
벡터 이미지로, 래스터 이미지를 별도 그림 개체로 변환합니다. SVG에는 실제 벡터 경로가
저장되며 PNG 대체 이미지는 SVG 미지원 프로그램을 위한 것입니다.
`--vector-format native`를 지정하면 벡터 경로를 DrawingML 도형으로 변환합니다. PDF의 그리기 순서를 유지합니다.
래스터 이미지는 PDF의 회전 전 크기, 회전각과 반전을 유지합니다. 회전 후 바깥 영역에
원본 이미지를 늘려 넣지 않으므로 세로 이미지의 비율도 보존합니다. 기울이기 변환은
SVG에 원래 변환 행렬을 기록하여 보존합니다.
표와 차트는 원래 Typst의 선·텍스트 등 구성 개체로 편집하며 PowerPoint의 표/차트
데이터 모델로 재구성하지는 않습니다. 수식은 추출 가능한 문자와 경로로 변환됩니다.

배경 모드의 SVG는 Typst의 벡터·그라디언트를 그대로 보존합니다.
가져온 SVG 그림도 내부 벡터 도형을 페이지에 직접 포함하여 PowerPoint에서 표시합니다.
SVG 안의 사진은 EXIF 방향을 픽셀에 반영하고 방향 메타데이터를 제거하여,
PowerPoint에서도 PDF와 같은 방향과 비율로 표시합니다.
배경 모드에서 영상은 썸네일의 원래 그리기 순서에 삽입됩니다. 영상 뒤에 그려진
제목·머리말·쪽 번호는 투명한 전경 레이어로 보존합니다. PowerPoint의 영상 우선 표시로
전경이 가려질 수 있는 겹침을 감지하면 기본적으로 해당 페이지와 영상 경로를 알리고
합성 여부를 질문합니다. 예를 선택하면 내장 영상 복사본에 겹치는 전경을 합성하고
H.264 MP4로 다시 인코딩합니다. 원본 파일은 변경하지 않습니다. 아니오(기본 응답)는
경고와 함께 합성 없이 계속합니다. 입력이 종료되면 컴파일을 중단합니다.

```sh
# 겹침이 있으면 질문 (기본값)
typst-pptx main.typ main.pptx --video-foreground ask
# 질문 없이 합성 / 합성 없이 유지 / 겹침이 있으면 중단
typst-pptx main.typ main.pptx --video-foreground composite
typst-pptx main.typ main.pptx --video-foreground preserve
typst-pptx main.typ main.pptx --video-foreground error
```

비대화형 실행에서 `ask`가 겹침을 발견하면 명시적 옵션을 요구하며 기존 출력 파일을
보존합니다. 겹침이 없으면 질문이나 합성이 없습니다. 코덱 변환 정책인
`--video-conversion`과는 독립된 옵션입니다. Python API에서는
`video_foreground="ask"`와 `confirm_video_foreground(page, source)` 콜백을 사용하며,
콜백의 `True`는 합성, `False`는 합성 없이 계속하기입니다.
편집 모드의 PDF 그라디언트는 다른 내용과 분리된 래스터 그림 개체로 보존합니다. 분리할 수 없는 PDF 셰이딩은
내용을 생략하지 않고 오류로 알립니다. PDF를 거치므로 복잡한 클리핑, 문자 배치·폰트
대체는 원본과 차이가 날 수 있습니다. 정확한 외형이 우선이면 배경 모드를 사용하세요. Office에서 해당 영상 코덱을 지원해야 합니다.
URL 영상은 컴파일할 때 다운로드하며, 내보낸 PPTX의 영상 재생에는 원본 파일이나 네트워크가
필요하지 않습니다. 다운로드 실패 시 외부 링크로 대체하지 않고 컴파일 오류로 처리합니다.
웹페이지 URL(예: 일반 동영상 시청 페이지)은 원시 영상 파일 URL과 다릅니다.

## Misc

기술 참조: [Typst 메타데이터](https://typst.app/docs/reference/introspection/metadata/),
[Typst path](https://typst.app/docs/reference/foundations/path/),
[PyMuPDF 추출 API](https://pymupdf.readthedocs.io/en/latest/functions.html),
[PowerPoint 미디어 노드](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.presentation.commonmedianode?view=openxml-3.0.1).
