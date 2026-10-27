"""Inspect media and convert to a conservative PowerPoint compatibility profile."""
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class VideoInspection:
    video_stream: int
    video_codec: str
    audio_codecs: tuple
    pixel_format: str
    reasons: tuple
    display_aspect_ratio: float = 0.0

    @property
    def compatible(self):
        return not self.reasons

    @property
    def description(self):
        audio = ', '.join(self.audio_codecs) or 'none'
        return f'video={self.video_codec}, pixels={self.pixel_format}, audio={audio}'


def _invoke(command, tool, timeout=None):
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=timeout, check=False)
    except FileNotFoundError as exc:
        raise RuntimeError(f'{tool} is required for video media. Install FFmpeg (includes ffprobe), or set --{tool.lower()} PATH.') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'{tool} timed out while checking video media') from exc
    if result.returncode:
        detail = '\n'.join(result.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f'{tool} failed: {detail or "unknown media error"}')
    return result.stdout


def display_aspect_ratio(stream):
    """Display geometry includes non-square pixels and orientation metadata."""
    try:
        width, height = float(stream['width']), float(stream['height'])
        sar = stream.get('sample_aspect_ratio', '1:1')
        try:
            numerator, denominator = map(float, sar.split(':'))
            if numerator > 0 and denominator > 0:
                width *= numerator / denominator
        except (ValueError, AttributeError, ZeroDivisionError):
            pass
        rotation = float(stream.get('tags', {}).get('rotate', 0))
        for side_data in stream.get('side_data_list', []):
            if 'rotation' in side_data:
                rotation = float(side_data['rotation'])
                break
        angle = math.radians(rotation)
        w = abs(math.cos(angle))*width + abs(math.sin(angle))*height
        h = abs(math.sin(angle))*width + abs(math.cos(angle))*height
        if not all(math.isfinite(v) and v > 0 for v in (width, height, w, h)):
            raise ValueError('invalid dimensions')
        return w/h
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise RuntimeError('FFprobe could not identify the video display dimensions') from exc


def inspect_video(path, extension, ffprobe='ffprobe'):
    raw = _invoke([ffprobe, '-v', 'error', '-show_streams', '-show_format',
                   '-of', 'json', str(path)], 'FFprobe', timeout=30)
    try:
        data = json.loads(raw)
        streams = data['streams']
        video = next(s for s in streams if s.get('codec_type') == 'video'
                     and not s.get('disposition', {}).get('attached_pic'))
        audios = tuple(s.get('codec_name', 'unknown') for s in streams if s.get('codec_type') == 'audio')
        formats = data['format']['format_name'].split(',')
        codec, pixels = video.get('codec_name', 'unknown'), video.get('pix_fmt', 'unknown')
        stream_index = int(video['index'])
    except (ValueError, KeyError, TypeError, StopIteration, AttributeError) as exc:
        raise RuntimeError('FFprobe could not identify a playable video stream') from exc
    reasons = []
    # This is the project's cross-platform profile, not a claim that every
    # other codec is unsupported by every version of Office.
    if codec != 'h264':
        reasons.append(f'video codec {codec}: H.264 is required by the compatibility profile')
    if pixels not in ('yuv420p', 'yuvj420p'):
        reasons.append(f'pixel format {pixels}: 8-bit 4:2:0 is required by the compatibility profile')
    if any(codec != 'aac' for codec in audios):
        reasons.append('audio codec: AAC is required by the compatibility profile')
    if extension not in ('mp4', 'm4v', 'mov') or 'mov' not in formats:
        reasons.append('container: MP4/M4V/MOV is required by the compatibility profile')
    return VideoInspection(stream_index, codec, audios, pixels, tuple(reasons),
                           display_aspect_ratio(video))


class VideoProcessor:
    def __init__(self, directory, policy='ask', confirm=None, ffprobe='ffprobe', ffmpeg='ffmpeg'):
        if policy not in ('ask', 'convert', 'error'):
            raise ValueError('video_conversion must be ask, convert, or error')
        self.directory = Path(directory)
        self.policy, self.confirm = policy, confirm
        self.ffprobe, self.ffmpeg = ffprobe, ffmpeg
        self.cache = {}
        self.display_aspects = {}

    def prepare(self, data, extension, source):
        key = (hashlib.sha256(data).hexdigest(), extension)
        if key in self.cache:
            return self.cache[key]
        path = self.directory / f'video-{key[0]}.bin'
        path.write_bytes(data)
        info = inspect_video(path, extension, self.ffprobe)
        if info.compatible:
            result = (data, extension)
        else:
            detail = f'Video {source!r}: {info.description}. ' + '; '.join(info.reasons)
            if self.policy == 'error':
                raise RuntimeError(detail + '. Use --video-conversion convert to convert to H.264/AAC MP4.')
            if self.policy == 'ask':
                if self.confirm is None:
                    raise RuntimeError(detail + '. Conversion requires confirmation. Use a confirmation callback or --video-conversion convert.')
                if self.confirm(source, info) is not True:
                    raise RuntimeError(f'Video conversion declined for {source!r}; compilation cancelled')
            output = self.directory / f'video-{key[0]}-compatible.mp4'
            _invoke([self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                     '-i', str(path), '-map', f'0:{info.video_stream}', '-map', '0:a?',
                     '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium',
                     '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
                     '-c:a', 'aac', '-b:a', '192k', '-map_metadata', '-1',
                     '-movflags', '+faststart', str(output)], 'FFmpeg')
            verified = inspect_video(output, 'mp4', self.ffprobe)
            if not verified.compatible:
                raise RuntimeError('Converted video did not pass the PowerPoint compatibility check')
            converted = output.read_bytes()
            if not converted:
                raise RuntimeError('FFmpeg produced an empty video')
            result = (converted, 'mp4')
            info = verified
        self.display_aspects[(hashlib.sha256(result[0]).hexdigest(), result[1])] = info.display_aspect_ratio
        self.cache[key] = result
        return result

    def aspect_ratio(self, data, extension):
        return self.display_aspects[(hashlib.sha256(data).hexdigest(), extension)]

    def composite_foreground(self, data, extension, foreground):
        """Embed foreground pixels into a copy for Office's topmost video player."""
        key = hashlib.sha256(data + foreground).hexdigest()
        output = self.directory / f'video-{key}-foreground.mp4'
        if output.exists():
            return output.read_bytes(), 'mp4'
        source = self.directory / f'video-{key}.{extension}'
        overlay = self.directory / f'video-{key}-foreground.png'
        source.write_bytes(data)
        overlay.write_bytes(foreground)
        raw = _invoke([self.ffprobe, '-v', 'error', '-select_streams', 'v:0',
                       '-show_streams', '-of', 'json', str(source)], 'FFprobe', timeout=30)
        stream = json.loads(raw)['streams'][0]
        width, height = int(stream['width']), int(stream['height'])
        # FFmpeg autorotates on decode; choose a square-pixel display canvas.
        aspect = display_aspect_ratio(stream)
        rotation = float(stream.get('tags', {}).get('rotate', 0))
        for side in stream.get('side_data_list', []):
            if 'rotation' in side:
                rotation = float(side['rotation'])
                break
        if abs(math.sin(math.radians(rotation))) > .5:
            height = width
        width = max(2, round(height * aspect / 2) * 2)
        height = max(2, round(height / 2) * 2)
        filters = (f'[0:v]scale={width}:{height},setsar=1[base];'
                   f'[1:v]scale={width}:{height}[front];'
                   '[base][front]overlay=0:0:eof_action=repeat:format=auto[v]')
        _invoke([self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
                 '-i', str(source), '-i', str(overlay), '-filter_complex', filters,
                 '-map', '[v]', '-map', '0:a?', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                 '-crf', '18', '-preset', 'fast', '-c:a', 'copy', '-map_metadata', '-1',
                 '-movflags', '+faststart', str(output)], 'FFmpeg')
        return output.read_bytes(), 'mp4'
