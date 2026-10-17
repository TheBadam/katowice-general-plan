#!/usr/bin/env bash
# Launch the interactive Environmental impact on Katowice plan viewer.
# Extra arguments are passed to gml_viewer.py (e.g. -o map.png).
cd "$(dirname "$0")"
exec .venv/bin/python gml_viewer.py katowice_plan_ogolny_26.gml \
    --zones zones.json \
    --colors group_definitions.json \
    --overlay \
    --zone-definition zone_definition.json \
    --default-off AktPlanowaniaPrzestrzennego \
    --default-off ObszarZabudowySrodmiejskiej \
    --default-alpha StrefaPlanistyczna=0.75 \
    --default-alpha ObszarUzupelnieniaZabudowy=0.75 \
    --layer-names layer_names.json \
    --streets streets.geojson \
    --descriptions zones_description.json \
    --page-title "Potencjalne zagrożenia stanu środowiska, mogących wystąpić w wyniku realizacji Planu Ogólnego." \
    --page-subtitle "Na bazie \"Prognozy oddziaływania na środowisko projektu Planu Ogólnego miasta Katowice\", dr Grzegorz Synowiec, Katowice 04.10.2026r" \
    --page-note page_note.txt \
    --page-link "Environmental report=https://planogolnydlakatowic.pl/" \
    --page-link "GML registry=https://rejestr-urbanistyczny.gov.pl/published/details/pog/4521" \
    --web "$@"
