#!/usr/bin/env bash
# Export the interactive "Environmental impact on Katowice plan" viewer as a
# static site into static_site/ - no server is started, no Python is needed
# to host the result. Extra arguments are passed to gml_viewer.py
# (e.g. -o map.png for a preview image). The exported site is also bundled
# into a single downloadable archive: static_site.7z when 7z is installed,
# otherwise static_site.zip (via Python, no extra tools needed).
cd "$(dirname "$0")"

.venv/bin/python gml_viewer.py katowice_plan_ogolny_26.gml \
    --zones zones.json \
    --colors group_definitions.json \
    --overlay \
    --zone-definition zone_definition.json \
    --default-off AktPlanowaniaPrzestrzennego \
    --default-off ObszarZabudowySrodmiejskiej \
    --default-alpha StrefaPlanistyczna=0.75 \
    --default-alpha ObszarUzupelnieniaZabudowy=0.75 \
    --layer-names layer_names.json \
    --i18n i18n.json \
    --streets streets.geojson \
    --descriptions zones_description.json \
    --page-title "Potencjalne zagrożenia stanu środowiska, mogące wystąpić w wyniku realizacji Planu Ogólnego." \
    --page-subtitle "Na bazie \"Prognozy oddziaływania na środowisko projektu Planu Ogólnego miasta Katowice\",dr Grzegorz Synowiec, Katowice 04.10.2026r" \
    --page-note page_note.txt \
    --page-link "report=https://planogolnydlakatowic.pl/" \
    --page-link "registry=https://rejestr-urbanistyczny.gov.pl/published/details/pog/4521" \
    --export-static static_site "$@"
status=$?

# bundle the exported site into one downloadable archive
if [ $status -eq 0 ]; then
    if command -v 7z >/dev/null 2>&1; then
        rm -f static_site.7z
        7z a -bd static_site.7z ./static_site >/dev/null \
            && echo "Downloadable archive -> static_site.7z"
    else
        rm -f static_site.zip
        .venv/bin/python -c "import shutil; shutil.make_archive('static_site', 'zip', '.', 'static_site')" \
            && echo "Downloadable archive -> static_site.zip"
    fi
fi
exit $status
