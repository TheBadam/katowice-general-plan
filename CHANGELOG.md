# Lista zmian / Changelog

## 2026-10-18

- Nowa warstwa "Open Street Map (zieleń)" w sekcji warstw GML: pokazuje
  miejsca, w których tereny zielone z OpenStreetMap (lasy, łąki,
  parki...) nakładają się na strefy planistyczne. Widoczność sterowana
  przełącznikami typów stref, ale wyłączenie warstwy stref nie ukrywa
  zieleni. Warstwa jest domyślnie wyłączona, a jej dane (osobny plik
  greens.json) pobierają się dopiero po włączeniu. Kolory i wzory
  terenów zielonych jak w standardowym stylu OpenStreetMap.
- Dymek strefy pokazuje udział terenów zielonych (procent i hektary);
  najechanie na strefę pobiera dane greens.json, jeśli jeszcze ich nie ma.
- Dane terenów zielonych: © OpenStreetMap contributors (ODbL).
- Nowa zwijana sekcja "Lista zmian" w panelu bocznym (zwinięta domyślnie).
- Szczegóły elementu po najechaniu kursorem (hover details).
- Pełne tłumaczenia EN/PL interfejsu.
- Poprawione złamanie linii w opisach grup.
- Usunięto grupę "tornado".
- Nowe narzędzia analizy terenów zielonych z OpenStreetMap:
  `fetch_greens.py` (pobranie lasów, łąk, parków...) i `greens_overlap.py`
  (powierzchnia nakładania się terenów zielonych z typami stref).

## 2026-10-17

- Widok udostępniany przez parametry URL (przełączniki, strefy, przezroczystość).
- Przycinanie renderowania do widocznego obszaru (viewport culling).
- Uporządkowany panel boczny: sekcje "Warstwy GML", "Oddziaływanie na
  środowisko", "Ulice"; zwijanie panelu na małych ekranach.
- Domyślna przezroczystość 0,75 dla stref planistycznych i obszarów
  uzupełnienia zabudowy.
- Aktualizacja definicji stref; grupowanie warstw GML.
- Pierwsza działająca mapa.
