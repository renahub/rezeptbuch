"""Unit-Tests für die RecipeScanView (views.py).

Die View ist die HTTP-Schnittstelle für den KI-gestützten Rezept-Scan.
Der eigentliche API-Aufruf (extract_recipe_from_image) wird gemockt,
geprüft wird ausschließlich die Wiring-Logik der View:
- Upload-Handling (kein Bild, ein Bild, mehrere Bilder)
- JSON-Response-Format (success/error)
- HTTP-Statuscodes (200, 400, 500)
- Fehler-Weiterreichung aus dem Service
"""
import json
import pytest
from unittest.mock import patch
from django.urls import reverse

from core.tests.helpers import make_uploaded_image


SCAN_URL_NAME = "core:recipe_scan"


# ---------------------------------------------------------------------------
# Erfolgs-Pfad
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestScanViewSuccess:
    def test_post_with_single_image_returns_200(self, client):
        fake_data = {
            "name": "Tomatensuppe",
            "rating": 3,
            "ingredients": [{"name": "Tomate", "amount": 500.0, "unit": "g"}],
            "image": None,
        }
        with patch("core.views.extract_recipe_from_image", return_value=fake_data):
            response = client.post(
                reverse(SCAN_URL_NAME),
                {"image": make_uploaded_image()},
            )
        assert response.status_code == 200
        payload = response.json()
        assert payload == {"success": True, "data": fake_data}

    def test_response_is_valid_json(self, client):
        with patch("core.views.extract_recipe_from_image",
                   return_value={"name": "X", "rating": 3, "ingredients": []}):
            response = client.post(
                reverse(SCAN_URL_NAME),
                {"image": make_uploaded_image()},
            )
        # Wirft, falls keine gültige JSON-Antwort
        json.loads(response.content)
        assert response["Content-Type"].startswith("application/json")

    def test_multiple_images_passed_to_service(self, client):
        """Mehrere Bilder werden als Liste an extract_recipe_from_image übergeben."""
        files = [make_uploaded_image("p1.png"), make_uploaded_image("p2.png")]
        with patch("core.views.extract_recipe_from_image",
                   return_value={"name": "Buch", "rating": 3, "ingredients": []}
                   ) as mock_extract:
            response = client.post(
                reverse(SCAN_URL_NAME),
                {"image": files},
            )
        assert response.status_code == 200
        # Erstes positionales Argument war die Liste aller hochgeladenen Files
        call_args = mock_extract.call_args
        passed_files = call_args.args[0]
        assert len(passed_files) == 2

    def test_api_key_is_passed_from_settings(self, client, settings):
        settings.GEMINI_API_KEY = "test-api-key-xyz"
        with patch("core.views.extract_recipe_from_image",
                   return_value={"name": "X", "rating": 3, "ingredients": []}
                   ) as mock_extract:
            client.post(
                reverse(SCAN_URL_NAME),
                {"image": make_uploaded_image()},
            )
        # Zweites Argument (api_key) entspricht dem Settings-Wert
        assert mock_extract.call_args.args[1] == "test-api-key-xyz"


# ---------------------------------------------------------------------------
# Validierung der Eingabe
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestScanViewValidation:
    def test_post_without_image_returns_400(self, client):
        response = client.post(reverse(SCAN_URL_NAME), {})
        assert response.status_code == 400
        assert response.json() == {"error": "Kein Bild hochgeladen."}

    def test_post_with_empty_image_field_returns_400(self, client):
        """Der Form-Field 'image' fehlt komplett → 400."""
        response = client.post(reverse(SCAN_URL_NAME), {"other": "value"})
        assert response.status_code == 400
        assert "Kein Bild" in response.json()["error"]

    def test_validation_does_not_call_service(self, client):
        """Bei fehlendem Bild wird extract_recipe_from_image gar nicht erst aufgerufen."""
        with patch("core.views.extract_recipe_from_image") as mock_extract:
            client.post(reverse(SCAN_URL_NAME), {})
        mock_extract.assert_not_called()


# ---------------------------------------------------------------------------
# Fehlerbehandlung
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestScanViewErrorHandling:
    def test_value_error_returns_500_with_message(self, client):
        """ValueError aus dem Service (z.B. urheberrechtlich blockiert) → 500."""
        with patch(
            "core.views.extract_recipe_from_image",
            side_effect=ValueError("Das Rezept konnte nicht ausgelesen werden."
                                   "Es ist möglicherweise urheberrechtlich geschützt."),
        ):
            response = client.post(
                reverse(SCAN_URL_NAME),
                {"image": make_uploaded_image()},
            )
        assert response.status_code == 500
        assert "urheberrechtlich" in response.json()["error"]

    def test_generic_exception_returns_500(self, client):
        """Beliebige Ausnahme aus dem Service wird abgefangen und als 500 ausgeliefert."""
        with patch(
            "core.views.extract_recipe_from_image",
            side_effect=RuntimeError("Verbindung zur API fehlgeschlagen"),
        ):
            response = client.post(
                reverse(SCAN_URL_NAME),
                {"image": make_uploaded_image()},
            )
        assert response.status_code == 500
        assert response.json()["error"] == "Verbindung zur API fehlgeschlagen"

    def test_error_response_has_no_success_flag(self, client):
        """Fehler-Response enthält nur 'error', kein 'success': True."""
        with patch(
            "core.views.extract_recipe_from_image",
            side_effect=Exception("boom"),
        ):
            response = client.post(
                reverse(SCAN_URL_NAME),
                {"image": make_uploaded_image()},
            )
        payload = response.json()
        assert "success" not in payload
        assert "error" in payload


# ---------------------------------------------------------------------------
# HTTP-Methoden
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestScanViewHttpMethods:
    def test_get_not_allowed(self, client):
        """Die View akzeptiert nur POST, GET liefert 405."""
        response = client.get(reverse(SCAN_URL_NAME))
        assert response.status_code == 405

    def test_put_not_allowed(self, client):
        response = client.put(reverse(SCAN_URL_NAME))
        assert response.status_code == 405

    def test_delete_not_allowed(self, client):
        response = client.delete(reverse(SCAN_URL_NAME))
        assert response.status_code == 405
