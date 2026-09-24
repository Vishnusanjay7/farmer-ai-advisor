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
]


class AudioValidationError(Exception):
    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code
        self.message = message


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
