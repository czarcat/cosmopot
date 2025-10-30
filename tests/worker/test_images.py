from __future__ import annotations

import io

from PIL import Image

from backend.app.worker.images import generate_thumbnail


def test_generate_thumbnail_scales_image_preserving_aspect_ratio() -> None:
    image = Image.new("RGB", (800, 400), color="red")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")

    thumbnail_bytes = generate_thumbnail(buffer.getvalue(), size=(200, 200))
    thumb = Image.open(io.BytesIO(thumbnail_bytes))

    assert thumb.width == 200
    assert thumb.height <= 200
    assert thumb.mode == "RGB"
