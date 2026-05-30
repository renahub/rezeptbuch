"""Services for the core application."""

import io
import json
import os
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from django.conf import settings

from PIL import Image
import fitz  # pymupdf
from google import genai
from google.genai import types
from google.genai.errors import ServerError

PROMPT_PATH = Path(__file__).parent / 'prompts' / 'recipe_scan.txt'
RECIPE_IMAGE_DIR = os.path.join(settings.MEDIA_ROOT, 'recipe_images')


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


def strip_exif(img: Image.Image) -> Image.Image:
    clean = Image.new(img.mode, img.size)
    clean.frombytes(img.tobytes())
    return clean


def extract_recipe_from_image(image_files, api_key):
    """
    image_files: eine einzelne Datei oder eine Liste von Dateien (Fotos/PDFs).
    Mehrere Bilder werden gemeinsam an die API übergeben, z.B. mehrere Buchseiten.
    """
    client = genai.Client(api_key=api_key)

    # Schritt 1: Normalisierung - immer eine Liste
    if not isinstance(image_files, (list, tuple)):
        image_files = [image_files]

    # Schritt 2: Alle Dateien in PIL-Images umwandeln (PDFs seitenweise)
    images = []
    for image_file in image_files:
        filename = getattr(image_file, 'name', '')
        if filename.lower().endswith('.pdf'):
            pdf_bytes = image_file.read()
            doc = fitz.open(stream=pdf_bytes, filetype='pdf')
            for page in doc:
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes('png')
                images.append(Image.open(io.BytesIO(img_bytes)))
        else:
            images.append(Image.open(image_file))

    prompt = load_prompt()

    # Schritt 3: Metadaten entfernen und Bilder als PNG-Bytes für die API vorbereiten
    image_parts = []
    for img in images:
        clean = strip_exif(img)
        buf = io.BytesIO()
        clean.save(buf, format='PNG')
        image_parts.append(
            types.Part.from_bytes(
                data=buf.getvalue(),
                mime_type='image/png',
            )
        )

    # Schritt 4: Prompt und Bilder an die Gemini API übergeben
    contents = [prompt] + image_parts

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents,
        )
    except ServerError as e:
        if e.code == 503:
            raise ValueError(
                "Der KI-Dienst ist momentan überlastet. "
                "Bitte versuche es in wenigen Minuten erneut."
            )
        raise

    if (
        not response.candidates
        or response.candidates[0].finish_reason == types.FinishReason.RECITATION
    ):
        raise ValueError(
            'Das Rezept konnte nicht ausgelesen werden. '
            'Es ist möglicherweise urheberrechtlich geschützt. '
            'Bitte Felder manuell ausfüllen.'
        )

    # Schritt 5: Modellantwort parsen und normalisieren
    raw = response.text.strip()

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    data = json.loads(match.group() if match else raw)

    # Komma direkt nach Satzende (., !, ?) entfernen
    if isinstance(data.get('instructions'), str):
        data['instructions'] = re.sub(
            r'([.!?]),(\s|$)', r'\1\2', data['instructions']
        )

    # Rating auf gültige Werte begrenzen (1-3)
    data['rating'] = max(1, min(3, int(data.get('rating', 2))))

    # Zutatenmengen: None oder ungültige Werte auf 0 setzen
    for ing in data.get('ingredients', []):
        try:
            ing['amount'] = float(Decimal(str(ing.get('amount') or 0)))
        except (InvalidOperation, TypeError, ValueError):
            ing['amount'] = 0.0
        # unit darf nicht leer sein (DB-Constraint)
        if not ing.get('unit') or not str(ing['unit']).strip():
            ing['unit'] = 'nach Bedarf'

    # Schritt 6: Rezeptbild speichern
    dish_image_index = data.pop('dish_image_index', None)
    dish_image_bbox = data.pop('dish_image_bbox', None)
    data['image'] = None

    if dish_image_index is not None:
        try:
            idx = int(dish_image_index)
            if 0 <= idx < len(images):
                dish_img = images[idx]

                # Auf Bounding-Box zuschneiden, falls Gemini eine geliefert hat
                if dish_image_bbox and len(dish_image_bbox) == 4:
                    ymin, xmin, ymax, xmax = dish_image_bbox
                    w, h = dish_img.size
                    left   = int(xmin / 1000 * w)
                    top    = int(ymin / 1000 * h)
                    right  = int(xmax / 1000 * w)
                    bottom = int(ymax / 1000 * h)
                    # Nur croppen wenn die Box plausibel ist
                    if 0 <= left < right <= w and 0 <= top < bottom <= h:
                        dish_img = dish_img.crop((left, top, right, bottom))

                # Auf max. 400x400px verkleinern
                dish_img.thumbnail((400, 400), Image.Resampling.LANCZOS)

                # Dateiname aus Rezeptnamen ableiten
                recipe_name = data.get('name', 'rezept')
                safe_name = re.sub(r'[^\w\-]', '_', recipe_name).strip('_').lower()
                safe_name = re.sub(r'_+', '_', safe_name)  # doppelte _ entfernen

                # Zielordner anlegen falls nicht vorhanden
                os.makedirs(RECIPE_IMAGE_DIR, exist_ok=True)

                # Eindeutigen Dateinamen sicherstellen
                image_filename = f"{safe_name}.png"
                image_path = os.path.join(RECIPE_IMAGE_DIR, image_filename)
                counter = 1
                while os.path.exists(image_path):
                    image_filename = f"{safe_name}_{counter}.png"
                    image_path = os.path.join(RECIPE_IMAGE_DIR, image_filename)
                    counter += 1

                #RGBA oder Palettenmodus in RGB konvertieren vor dem Speichern
                if dish_img.mode in ("RGBA", "P"):
                    dish_img = dish_img.convert("RGB")
                dish_img.save(image_path, format="PNG", optimize=True)

                # Relativen Pfad zurückgeben (Django-kompatibel)
                data['image'] = f"recipe_images/{image_filename}"

        except (ValueError, TypeError, IndexError, OSError):
            data['image'] = None

    return data
