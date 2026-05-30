/**
 * recipe_form.js
 * Gemeinsame Formular-Logik für Rezept anlegen und bearbeiten:
 * - dynamisches Hinzufügen/Entfernen von Zutaten-, Kategorie- und Bild-Zeilen
 * - sicherstellt, dass immer nur ein Titelbild ausgewählt ist
 *
 * Wird von recipe_create.html und recipe_edit.html eingebunden.
 */
document.addEventListener("DOMContentLoaded", function () {

    /**
     * Verkabelt einen "+ hinzufügen"-Button mit seiner Tabelle und seinem Formset.
     * @param {string} tableSelector   CSS-Selektor des <tbody>
     * @param {string} addBtnId        ID des Hinzufügen-Buttons
     * @param {string} totalFormsId    ID des TOTAL_FORMS-Hidden-Inputs
     * @param {string} templateSelector CSS-Selektor der leeren Vorlage-Zeile
     * @param {string} removeClass     CSS-Klasse des Entfernen-Buttons
     */
    function setupRowFormset(tableSelector, addBtnId, totalFormsId, templateSelector, removeClass) {
        const tableBody = document.querySelector(tableSelector);
        const addBtn = document.getElementById(addBtnId);
        const totalForms = document.getElementById(totalFormsId);
        const template = document.querySelector(templateSelector);

        if (!tableBody || !addBtn || !totalForms || !template) return;

        // Neue Zeile anhängen
        addBtn.addEventListener("click", function () {
            const formCount = parseInt(totalForms.value);
            const newHtml = template.outerHTML.replace(/__prefix__/g, formCount);
            tableBody.insertAdjacentHTML("beforeend", newHtml);
            totalForms.value = formCount + 1;
        });

        // Zeile entfernen (DELETE-Checkbox setzen statt löschen, damit Django sie kennt)
        tableBody.addEventListener("click", function (e) {
            if (e.target.classList.contains(removeClass)) {
                const row = e.target.closest("tr");
                const deleteInput = row.querySelector('input[name$="DELETE"]');
                if (deleteInput) {
                    deleteInput.checked = true;
                    row.style.display = "none";
                } else {
                    row.remove();
                }
            }
        });
    }

    // Zutaten-Formset
    setupRowFormset(
        "#ingredient-table tbody",
        "add-row",
        "id_recipe_ingredients-TOTAL_FORMS",
        "#empty-form-template tr",
        "remove-row"
    );

    // Kategorien-Formset
    setupRowFormset(
        "#category-table tbody",
        "add-cat-row",
        "id_categories-TOTAL_FORMS",
        "#empty-category-template tr",
        "remove-cat-row"
    );

    // Bilder-Formset (eigene Logik, weil keine Tabelle sondern <div>s)
    const imageContainer = document.getElementById("image-formset-container");
    const addImageBtn = document.getElementById("add-image-row");
    const totalImageForms = document.getElementById("id_images-TOTAL_FORMS");
    const emptyImageTemplate = document.querySelector("#empty-image-template .image-form-row");

    if (imageContainer && addImageBtn && totalImageForms && emptyImageTemplate) {

        addImageBtn.addEventListener("click", function () {
            const formCount = parseInt(totalImageForms.value);
            const newHtml = emptyImageTemplate.outerHTML.replace(/__prefix__/g, formCount);
            imageContainer.insertAdjacentHTML("beforeend", newHtml);
            totalImageForms.value = formCount + 1;
        });

        imageContainer.addEventListener("click", function (e) {
            const btn = e.target.closest(".remove-image-row");
            if (btn) {
                const row = btn.closest(".image-form-row");
                const deleteInput = row.querySelector('input[name$="DELETE"]');
                if (deleteInput) {
                    deleteInput.checked = true;
                    row.style.display = "none";
                } else {
                    row.remove();
                }
            }
        });

        // Sicherstellen, dass immer nur ein Titelbild aktiv ist
        imageContainer.addEventListener("change", function (e) {
            if (e.target.name && e.target.name.endsWith("-is_title") && e.target.checked) {
                document.querySelectorAll('input[name$="-is_title"]').forEach(function (cb) {
                    if (cb !== e.target) cb.checked = false;
                });
            }
        });
    }
});