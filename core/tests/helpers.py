"""Test-Helfer: Erzeugung kleiner Test-Bilder im Speicher.

Diese Funktionen liegen bewusst NICHT in conftest.py, da sie aus mehreren
Testmodulen direkt importiert werden (z.B. test_services.py, test_models.py).
"""
import io

try:
    from PIL import Image
except ImportError:
    Image = None

from django.core.files.uploadedfile import SimpleUploadedFile


def make_png_bytes(color=(255, 0, 0), size=(10, 10)):
    """Erzeugt ein kleines, valides PNG-Bild im Speicher (für ImageField-Tests)."""
    if Image is None:
        # Minimal 1x1 PNG fallback (gültiger PNG-Header)
        return (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
            b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
            b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02"
            b"\xfe\xa3\x35\x81\x84\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def make_uploaded_image(name="test.png"):
    """Liefert ein SimpleUploadedFile, das von Djangos ImageField akzeptiert wird."""
    return SimpleUploadedFile(name, make_png_bytes(), content_type="image/png")
