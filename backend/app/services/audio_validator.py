from dataclasses import dataclass
from typing import Tuple, Optional, Set

# Maximum file size allowed by Sarvam synchronous STT REST endpoint: 15 MB
MAX_AUDIO_SIZE_BYTES = 15 * 1024 * 1024

# Supported MIME types per official Sarvam AI documentation
SUPPORTED_MIME_TYPES: Set[str] = {
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/opus",
    "audio/mp3",
    "audio/mpeg",
    "audio/m4a",
    "audio/x-m4a",
    "audio/mp4",
    "audio/aac",
    "audio/flac",
    "application/octet-stream",  # Often sent by browsers when recording raw blobs
}

# Magic bytes signatures for common audio container verification
AUDIO_MAGIC_SIGNATURES = [
    (b"RIFF", 0),                # WAV
    (b"\x1a\x45\xdf\xa3", 0),    # WebM / Matroska
    (b"OggS", 0),                # OGG / OPUS
    (b"ID3", 0),                 # MP3 with ID3v2
    (b"\xff\xfb", 0),            # MP3 without ID3
    (b"\xff\xf3", 0),            # MP3 MPEG-2
    (b"\xff\xf2", 0),            # MP3 MPEG-2.5
    (b"fLaC", 0),                # FLAC
    (b"ftyp", 4),                # MP4 / M4A (starts at offset 4)
    (b"styp", 4),                # Fragmented MP4 (Safari/iOS MediaRecorder)
    (b"moov", 4),                # MP4 movie box
    (b"moof", 4),                # MP4 movie fragment box
    (b"wide", 4),                # QuickTime container prefix
]


class AudioValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


@dataclass(frozen=True)
class AudioFormatInfo:
    format_name: str
    filename: str
    content_type: str


def detect_audio_format(audio_bytes: bytes) -> AudioFormatInfo:
    """
    Detects audio format based on binary container signatures.
    Returns AudioFormatInfo with format name, recommended filename, and content type.
    Raises AudioValidationError if container signature is unsupported or not recognized.
    """
    if not audio_bytes or len(audio_bytes) == 0:
        raise AudioValidationError(
            error_code="EMPTY_AUDIO_FILE",
            message="Uploaded audio file is empty. Please record audio before submitting.",
        )

    # 1. WAV / RIFF
    if audio_bytes.startswith(b"RIFF"):
        return AudioFormatInfo(format_name="wav", filename="audio.wav", content_type="audio/wav")

    # 2. WebM / Matroska
    if audio_bytes.startswith(b"\x1a\x45\xdf\xa3"):
        return AudioFormatInfo(format_name="webm", filename="audio.webm", content_type="audio/webm")

    # 3. OGG
    if audio_bytes.startswith(b"OggS"):
        return AudioFormatInfo(format_name="ogg", filename="audio.ogg", content_type="audio/ogg")

    # 4. MP3
    if (
        audio_bytes.startswith(b"ID3")
        or audio_bytes.startswith(b"\xff\xfb")
        or audio_bytes.startswith(b"\xff\xf3")
        or audio_bytes.startswith(b"\xff\xf2")
    ):
        return AudioFormatInfo(format_name="mp3", filename="audio.mp3", content_type="audio/mpeg")

    # 5. MP4 / M4A / ISOBMFF (ftyp, styp, moov, moof, wide)
    if len(audio_bytes) >= 8 and audio_bytes[4:8] in (b"ftyp", b"styp", b"moov", b"moof", b"wide"):
        return AudioFormatInfo(format_name="mp4", filename="audio.mp4", content_type="audio/mp4")

    # 6. FLAC
    if audio_bytes.startswith(b"fLaC"):
        return AudioFormatInfo(format_name="flac", filename="audio.flac", content_type="audio/flac")

    raise AudioValidationError(
        error_code="INVALID_AUDIO_FORMAT",
        message="Uploaded file does not match a valid audio container header (WAV, WebM, MP3, OGG, M4A).",
    )


def validate_audio_payload(
    audio_bytes: bytes,
    content_type: Optional[str] = None,
    filename: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validates uploaded audio payload against Sarvam constraints and container signatures.
    Raises AudioValidationError with structured code and message if invalid.
    """
    # 1. Empty audio check
    if not audio_bytes or len(audio_bytes) == 0:
        raise AudioValidationError(
            error_code="EMPTY_AUDIO_FILE",
            message="Uploaded audio file is empty. Please record audio before submitting.",
        )

    # 2. File size limit
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise AudioValidationError(
            error_code="AUDIO_FILE_TOO_LARGE",
            message=f"Audio file exceeds maximum size of {MAX_AUDIO_SIZE_BYTES // (1024 * 1024)}MB.",
        )

    # 3. Content-Type check (if provided)
    if content_type:
        clean_ct = content_type.split(";")[0].strip().lower()
        if clean_ct not in SUPPORTED_MIME_TYPES:
            raise AudioValidationError(
                error_code="UNSUPPORTED_MIME_TYPE",
                message=f"Audio MIME type '{clean_ct}' is not supported. Use WAV, WebM, MP3, OGG, or M4A.",
            )

    # 4. Binary header / magic signature check
    header = audio_bytes[:16]
    is_valid_signature = False
    for sig, offset in AUDIO_MAGIC_SIGNATURES:
        if len(header) >= offset + len(sig):
            if header[offset : offset + len(sig)] == sig:
                is_valid_signature = True
                break

    if not is_valid_signature:
        raise AudioValidationError(
            error_code="INVALID_AUDIO_FORMAT",
            message="Uploaded file does not match a valid audio container header (WAV, WebM, MP3, OGG, M4A).",
        )

    return True, None
