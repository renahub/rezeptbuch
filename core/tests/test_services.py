"""Unit-Tests für core/services.py (KI-Scan-Wrapper).

Die Gemini-API selbst wird gemockt. Getestet wird ausschließlich die
Python-Logik um den API-Aufruf herum:
- Bild-Vorverarbeitung (Listen-Normalisierung, EXIF-Strip)
- Parsing der Modellantwort (JSON-Extraktion via Regex)
- Normalisierung der Felder (Rating-Clamp 1-3, amount-Fallback auf 0.0)
- Fehlerbehandlung (urheberrechtlich blockierte Antworten, finish_reason == RECITATION
- Speicherung des Rezeptbildes (Dateiname, Eindeutigkeit, Pfad)

Hinweis: Die inhaltliche Qualität wirdseparat als Black-Box-Test geprüft (nicht hier).
"""
import io
import json
import os
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image
from google.genai import types
from django.core.files.uploadedfile import SimpleUploadedFile
from google.genai.errors import ServerError

from core import services
from core.services import (
    extract_recipe_from_image,
    load_prompt,
    strip_exif,
)
from core.tests.helpers import make_uploaded_image


# ---------------------------------------------------------------------------
# Hilfsfunktionen für die Tests
# ---------------------------------------------------------------------------
def make_response(text, finish_reason=None):
    """Baut ein Mock-Objekt, das einer Gemini-API-Antwort entspricht."""
    response = MagicMock()
    response.text = text
    candidate = MagicMock()
    candidate.finish_reason = finish_reason or types.FinishReason.STOP
    response.candidates = [candidate]
    return response


def make_blocked_response():
    """Antwort mit finish_reason == 4 (urheberrechtlich blockiert)."""
    response = MagicMock()
    response.text = ""
    candidate = MagicMock()
    candidate.finish_reason = types.FinishReason.RECITATION
    response.candidates = [candidate]
    return response


@pytest.fixture
def mock_gemini():
    """Patcht genai.Client und liefert das Mock-Objekt für generate_content."""
    with patch("core.services.genai.Client") as mock_client_cls:
        instance = MagicMock()
        mock_client_cls.return_value = instance
        yield instance.models.generate_content


@pytest.fixture
def tmp_image_dir(monkeypatch, tmp_path):
    """Lenke RECIPE_IMAGE_DIR auf tmp_path um, damit reale Medien unangetastet bleiben."""
    target = tmp_path / "recipe_images"
    target.mkdir()
    monkeypatch.setattr(services, "RECIPE_IMAGE_DIR", str(target))
    return target


# ---------------------------------------------------------------------------
# load_prompt
# ---------------------------------------------------------------------------
class TestLoadPrompt:
    def test_returns_non_empty_string(self):
        prompt = load_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0


# ---------------------------------------------------------------------------
# strip_exif
# ---------------------------------------------------------------------------
class TestStripExif:
    def test_removes_metadata(self):
        img = Image.new("RGB", (5, 5), (255, 0, 0))
        img.info["exif"] = b"fake-exif-bytes"
        clean = strip_exif(img)
        assert "exif" not in clean.info

    def test_preserves_size_and_mode(self):
        img = Image.new("RGB", (8, 4), (0, 128, 0))
        clean = strip_exif(img)
        assert clean.size == (8, 4)
        assert clean.mode == "RGB"


# ---------------------------------------------------------------------------
# extract_recipe_from_image: Eingabe-Normalisierung
# ---------------------------------------------------------------------------
class TestInputNormalization:
    def test_single_file_is_wrapped_in_list(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name": "X", "rating": 3, "ingredients": []}'
        )
        # Ein einzelnes File (nicht in Liste) wird akzeptiert
        result = extract_recipe_from_image(make_uploaded_image(), api_key="dummy")
        assert result["name"] == "X"

    def test_multiple_files_accepted(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name": "Buch-Rezept", "rating": 3, "ingredients": []}'
        )
        files = [make_uploaded_image("p1.png"), make_uploaded_image("p2.png")]
        result = extract_recipe_from_image(files, api_key="dummy")
        assert result["name"] == "Buch-Rezept"
        # Beide Bilder wurden an die API übergeben (Prompt + 2 Bilder = 3 contents)
        call_kwargs = mock_gemini.call_args.kwargs
        assert len(call_kwargs["contents"]) == 3


# ---------------------------------------------------------------------------
# extract_recipe_from_image: JSON-Parsing
# ---------------------------------------------------------------------------
class TestJsonParsing:
    def test_plain_json_response(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name": "Pasta", "rating": 2, "ingredients": []}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["name"] == "Pasta"
        assert result["rating"] == 2

    def test_json_wrapped_in_markdown_fences(self, mock_gemini):
        """Gemini liefert manchmal ```json ... ```: Regex extrahiert das innere JSON."""
        mock_gemini.return_value = make_response(
            '```json\n{"name": "Salat", "rating": 2, "ingredients": []}\n```'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["name"] == "Salat"

    def test_json_with_surrounding_text(self, mock_gemini):
        mock_gemini.return_value = make_response(
            'Hier das Ergebnis: {"name": "Suppe", "rating": 2, "ingredients": []} '
            'Bitte prüfen.'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["name"] == "Suppe"

    def test_invalid_json_raises(self, mock_gemini):
        mock_gemini.return_value = make_response("Kein JSON in dieser Antwort.")
        with pytest.raises(json.JSONDecodeError):
            extract_recipe_from_image(make_uploaded_image(), api_key="x")


# ---------------------------------------------------------------------------
# extract_recipe_from_image: Rating-Normalisierung
# ---------------------------------------------------------------------------
class TestRatingNormalization:
    @pytest.mark.parametrize("raw,expected", [
    (2, 2),       # gültiger Wert bleibt
    (1, 1),       # untere Grenze
    (3, 3),       # obere Grenze
    (0, 1),       # zu klein → auf 1 geclampt
    (-2, 1),      # negativ → auf 1 geclampt
    (5, 3),       # zu groß → auf 3 geclampt
    (99, 3),      # weit zu groß → auf 3 geclampt
    ])

    def test_rating_is_clamped(self, mock_gemini, raw, expected):
        mock_gemini.return_value = make_response(
            f'{{"name": "X", "rating": {raw}, "ingredients": []}}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["rating"] == expected

    def test_missing_rating_defaults_to_two(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name": "X", "ingredients": []}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["rating"] == 2


# ---------------------------------------------------------------------------
# extract_recipe_from_image: Zutaten-Normalisierung
# ---------------------------------------------------------------------------
class TestIngredientAmountNormalization:
    def test_valid_amount_kept(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[{"name":"Mehl","amount":250,"unit":"g"}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["amount"] == 250.0

    def test_none_amount_becomes_zero(self, mock_gemini):
        """None-Menge wird auf 0.0 normalisiert (semantisch: 'Menge unbekannt'/'nach Bedarf')."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[{"name":"Salz","amount":null,"unit":"Prise"}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["amount"] == 0.0

    def test_invalid_amount_string_becomes_zero(self, mock_gemini):
        """Ungültiger amount-String (z.B. 'etwas') wird auf 0.0 normalisiert."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[{"name":"Pfeffer","amount":"etwas","unit":"Prise"}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["amount"] == 0.0

    def test_decimal_string_amount_parsed(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[{"name":"Öl","amount":"2.5","unit":"EL"}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["amount"] == 2.5

    def test_no_ingredients_field(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3}'
        )
        # Darf nicht crashen, wenn 'ingredients' fehlt
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert "name" in result


# ---------------------------------------------------------------------------
# extract_recipe_from_image: Fehler-Handling
# ---------------------------------------------------------------------------
class TestErrorHandling:
    def test_blocked_response_raises_valueerror(self, mock_gemini):
        """finish_reason == 4 → urheberrechtlich geschützt."""
        mock_gemini.return_value = make_blocked_response()
        with pytest.raises(ValueError, match="urheberrechtlich"):
            extract_recipe_from_image(make_uploaded_image(), api_key="x")

    def test_empty_candidates_raises_valueerror(self, mock_gemini):
        response = MagicMock()
        response.candidates = []
        mock_gemini.return_value = response
        with pytest.raises(ValueError, match="urheberrechtlich"):
            extract_recipe_from_image(make_uploaded_image(), api_key="x")

    def test_service_unavailable_raises_friendly_error(self, mock_gemini):
        """API-Überlastung (503) wird in nutzerfreundliche Fehlermeldung umgesetzt."""
        mock_gemini.side_effect = ServerError(
            503, {"error": {"message": "Service Unavailable", "code": 503}}
        )
        with pytest.raises(ValueError, match="überlastet"):
            extract_recipe_from_image(make_uploaded_image(), api_key="x")

    def test_server_error_other_code_is_reraised(self, mock_gemini):
        """ServerError mit Code ≠ 503 wird unverändert weitergereicht (Zeile 87: raise)."""
        mock_gemini.side_effect = ServerError(
            500, {"error": {"message": "Internal", "code": 500}}
        )
        with pytest.raises(ServerError):
            extract_recipe_from_image(make_uploaded_image(), api_key="x")

# ---------------------------------------------------------------------------
# extract_recipe_from_image: Bild-Speicherung (dish_image_index)
# ---------------------------------------------------------------------------
class TestDishImageSaving:
    def test_no_dish_image_index_returns_none(self, mock_gemini, tmp_image_dir):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["image"] is None

    def test_valid_index_saves_image(self, mock_gemini, tmp_image_dir):
        mock_gemini.return_value = make_response(
            '{"name":"Mein Rezept","rating":3,"ingredients":[],"dish_image_index":0}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["image"] is not None
        assert result["image"].startswith("recipe_images/")
        assert result["image"].endswith(".png")
        # Datei wurde tatsächlich auf der Platte angelegt
        saved_filename = os.path.basename(result["image"])
        assert (tmp_image_dir / saved_filename).exists()

    def test_filename_is_sanitized(self, mock_gemini, tmp_image_dir):
        mock_gemini.return_value = make_response(
            '{"name":"Spätzle mit Käse & Speck!!!","rating":3,'
            '"ingredients":[],"dish_image_index":0}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        filename = os.path.basename(result["image"])
        # Sonderzeichen ersetzt, keine doppelten Unterstriche, kleingeschrieben
        assert " " not in filename
        assert "!" not in filename
        assert "&" not in filename
        assert "__" not in filename
        assert filename == filename.lower()

    def test_index_out_of_range_returns_none(self, mock_gemini, tmp_image_dir):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[],"dish_image_index":99}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["image"] is None

    def test_negative_index_returns_none(self, mock_gemini, tmp_image_dir):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[],"dish_image_index":-1}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["image"] is None

    def test_unique_filename_on_collision(self, mock_gemini, tmp_image_dir):
        """Bestehende Datei → es wird ein Suffix _1, _2, ... angehängt."""
        # Erste Speicherung
        mock_gemini.return_value = make_response(
            '{"name":"Pasta","rating":3,"ingredients":[],"dish_image_index":0}'
        )
        result1 = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        # Zweite Speicherung mit identischem Rezeptnamen
        result2 = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result1["image"] != result2["image"]
        assert "_1" in os.path.basename(result2["image"])

    def test_dish_image_index_field_removed_from_result(self, mock_gemini, tmp_image_dir):
        """Nach der Verarbeitung wird 'dish_image_index' aus dem Ergebnis entfernt."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":3,"ingredients":[],"dish_image_index":0}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert "dish_image_index" not in result


    def test_rgba_image_is_converted_before_save(self, mock_gemini, tmp_image_dir):
        """RGBA-Bilder werden vor dem Speichern zu RGB konvertiert (PNG-kompatibel)."""
        img = Image.new("RGBA", (10, 10), (255, 0, 0, 128))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        rgba_file = SimpleUploadedFile("rgba.png", buf.getvalue(), content_type="image/png")

        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":[],"dish_image_index":0}'
        )
        result = extract_recipe_from_image(rgba_file, api_key="x")
        assert result["image"] is not None

# ---------------------------------------------------------------------------
# extract_recipe_from_image: Komma-Bereinigung in instructions
# ---------------------------------------------------------------------------
class TestInstructionsCommaCleanup:
    """Komma direkt nach Satzende-Zeichen (., !, ?) wird durch Whitespace ersetzt.
    Verhindert, dass Gemini-Antworten wie 'Schritt eins., Schritt zwei.'
    typografische Fehler in der Anwendung erzeugen."""

    def test_comma_after_period_removed(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":[],'
            '"instructions":"Schritt eins., Schritt zwei."}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["instructions"] == "Schritt eins. Schritt zwei."

    def test_comma_after_exclamation_removed(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":[],'
            '"instructions":"Fertig!, jetzt servieren."}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["instructions"] == "Fertig! jetzt servieren."

    def test_comma_after_question_removed(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":[],'
            '"instructions":"Schmeckt es?, dann fertig."}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["instructions"] == "Schmeckt es? dann fertig."

    def test_normal_commas_in_middle_of_sentence_kept(self, mock_gemini):
        """Kommata innerhalb von Sätzen bleiben unverändert."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":[],'
            '"instructions":"Salz, Pfeffer und Öl mischen."}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["instructions"] == "Salz, Pfeffer und Öl mischen."

    def test_missing_instructions_does_not_crash(self, mock_gemini):
        """Fehlt 'instructions' komplett, läuft die Funktion ohne Exception durch
        (deckt den False-Zweig des isinstance-Checks ab)."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":[]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result.get("instructions") is None

# ---------------------------------------------------------------------------
# extract_recipe_from_image: Unit-Fallback bei leerer Einheit (Zeile 121-122)
# ---------------------------------------------------------------------------
class TestUnitFallback:
    """Leere/fehlende Zutaten-Einheiten werden auf 'nach Bedarf' gesetzt,
    damit der DB-NOT-NULL-Constraint von RecipeIngredient.unit nicht
    verletzt wird."""

    def test_empty_string_unit_becomes_nach_bedarf(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":'
            '[{"name":"Salz","amount":1,"unit":""}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["unit"] == "nach Bedarf"

    def test_whitespace_only_unit_becomes_nach_bedarf(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":'
            '[{"name":"Pfeffer","amount":1,"unit":"   "}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["unit"] == "nach Bedarf"

    def test_null_unit_becomes_nach_bedarf(self, mock_gemini):
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":'
            '[{"name":"Zucker","amount":1,"unit":null}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["unit"] == "nach Bedarf"

    def test_missing_unit_key_becomes_nach_bedarf(self, mock_gemini):
        """Schlüssel 'unit' fehlt komplett im JSON → derselbe Fallback greift."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":'
            '[{"name":"Mehl","amount":250}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["unit"] == "nach Bedarf"

    def test_valid_unit_is_preserved(self, mock_gemini):
        """Eine gültige Einheit wird nicht überschrieben (False-Zweig)."""
        mock_gemini.return_value = make_response(
            '{"name":"X","rating":2,"ingredients":'
            '[{"name":"Milch","amount":200,"unit":"ml"}]}'
        )
        result = extract_recipe_from_image(make_uploaded_image(), api_key="x")
        assert result["ingredients"][0]["unit"] == "ml"

# ---------------------------------------------------------------------------
# extract_recipe_from_image: Bounding-Box-Crop (Zeilen 137-145)
# ---------------------------------------------------------------------------
class TestBoundingBoxCrop:
    """Wenn Gemini eine dish_image_bbox liefert (Format [ymin, xmin, ymax, xmax],
    normalisiert auf 0..1000), wird das Bild vor dem Skalieren auf diese
    Box zugeschnitten. Implausible/unvollständige Boxen werden ignoriert."""

    @staticmethod
    def _make_sized_image(width, height, name="sized.png"):
        """Erzeugt ein PNG fester Größe (helpers.make_uploaded_image ist nur 10x10)."""
        img = Image.new("RGB", (width, height), (200, 100, 50))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")

    def test_valid_bbox_crops_image(self, mock_gemini, tmp_image_dir):
        """Bbox [100,200,800,900] auf 500x500:
        left=100, top=50, right=450, bottom=400 → Crop-Ergebnis 350x350.
        thumbnail(400,400) skaliert nicht weiter herunter."""
        img_file = self._make_sized_image(500, 500)
        mock_gemini.return_value = make_response(
            '{"name":"Crop-Test","rating":2,"ingredients":[],'
            '"dish_image_index":0,"dish_image_bbox":[100,200,800,900]}'
        )
        result = extract_recipe_from_image(img_file, api_key="x")
        saved = tmp_image_dir / os.path.basename(result["image"])
        with Image.open(saved) as out:
            assert out.size == (350, 350)

    def test_implausible_bbox_skips_crop(self, mock_gemini, tmp_image_dir):
        """Invertierte Bbox (xmin > xmax) verletzt den Plausibilitätscheck
        (0 <= left < right <= w) → kein Crop, Bild bleibt im Original
        500x500 und wird per thumbnail auf 400x400 verkleinert."""
        img_file = self._make_sized_image(500, 500)
        mock_gemini.return_value = make_response(
            '{"name":"NoCrop1","rating":2,"ingredients":[],'
            '"dish_image_index":0,"dish_image_bbox":[800,900,100,200]}'
        )
        result = extract_recipe_from_image(img_file, api_key="x")
        saved = tmp_image_dir / os.path.basename(result["image"])
        with Image.open(saved) as out:
            assert out.size == (400, 400)

    def test_bbox_with_wrong_length_skips_crop(self, mock_gemini, tmp_image_dir):
        """Bbox mit ≠ 4 Werten erfüllt 'len == 4' nicht → Block wird übersprungen."""
        img_file = self._make_sized_image(500, 500)
        mock_gemini.return_value = make_response(
            '{"name":"NoCrop2","rating":2,"ingredients":[],'
            '"dish_image_index":0,"dish_image_bbox":[100,200,800]}'
        )
        result = extract_recipe_from_image(img_file, api_key="x")
        saved = tmp_image_dir / os.path.basename(result["image"])
        with Image.open(saved) as out:
            assert out.size == (400, 400)

    def test_no_bbox_no_crop(self, mock_gemini, tmp_image_dir):
        """Ohne dish_image_bbox im JSON wird gar nicht zugeschnitten."""
        img_file = self._make_sized_image(500, 500)
        mock_gemini.return_value = make_response(
            '{"name":"NoCrop3","rating":2,"ingredients":[],"dish_image_index":0}'
        )
        result = extract_recipe_from_image(img_file, api_key="x")
        saved = tmp_image_dir / os.path.basename(result["image"])
        with Image.open(saved) as out:
            assert out.size == (400, 400)


# ---------------------------------------------------------------------------
# extract_recipe_from_image: PDF-Verarbeitung
# ---------------------------------------------------------------------------
class TestPdfHandling:
    def test_pdf_pages_become_images(self, mock_gemini):
        """Eine PDF mit 2 Seiten wird zu 2 Bildern → 3 contents (Prompt + 2 Seiten)."""
        # Minimal-PDF mit 2 leeren Seiten via PyMuPDF erzeugen
        import fitz
        doc = fitz.open()
        doc.new_page(width=100, height=100)
        doc.new_page(width=100, height=100)
        pdf_bytes = doc.tobytes()
        doc.close()

        pdf_file = SimpleUploadedFile("scan.pdf", pdf_bytes, content_type="application/pdf")

        mock_gemini.return_value = make_response(
            '{"name":"PDF-Rezept","rating":3,"ingredients":[]}'
        )
        result = extract_recipe_from_image(pdf_file, api_key="x")
        assert result["name"] == "PDF-Rezept"

        # Prompt + 2 Seiten = 3 contents
        call_kwargs = mock_gemini.call_args.kwargs
        assert len(call_kwargs["contents"]) == 3
