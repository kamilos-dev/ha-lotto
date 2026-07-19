# Lotto — integracja Home Assistant

Dodaje pozycję **Lotto** w bocznym menu Home Assistant. Panel pozwala dodawać
kupony (Lotto / EuroJackpot), pokazuje ich listę i status, a integracja w tle
co jakiś czas sprawdza wyniki losowań i informuje o trafieniach.

## 1. Instalacja

### Wariant A: HACS (zalecane)

Repozytorium: **https://github.com/kamilos-dev/ha-lotto**

1. W HA otwórz **HACS → Integracje**, kliknij trzy kropki w prawym górnym
   rogu → **Custom repositories**.
2. Wklej `https://github.com/kamilos-dev/ha-lotto`, kategoria **Integration**,
   kliknij **Add**.
3. Znajdź na liście **Lotto** i kliknij **Download**.
4. Zrestartuj Home Assistant.

### Wariant B: ręcznie

Skopiuj folder `custom_components/lotto` do katalogu `config/custom_components/`
Twojej instancji Home Assistant, np.:

```
config/
  custom_components/
    lotto/
      __init__.py
      manifest.json
      ...
```

Zrestartuj Home Assistant.

## 2. Źródło wyników losowań

Integracja obsługuje dwa źródła — wybór jest automatyczny na podstawie tego,
czy podasz klucz API podczas konfiguracji:

- **Bez klucza API (domyślnie)** — od razu, bez żadnej rejestracji, korzysta
  z nieoficjalnego, publicznego endpointu, który zasila stronę wyników na
  lotto.pl. Nic nie trzeba konfigurować, ale **na części sieci bywa
  zablokowany przez Cloudflare** (potwierdzone: HTTP 403) — endpoint
  wymaga ciasteczka `cf_clearance` uzyskiwanego przez przejście wyzwania JS
  w prawdziwej przeglądarce oraz tokenu `request-token` generowanego przez
  ich SPA, których nie da się odtworzyć zwykłym zapytaniem HTTP w tle. Jeśli
  trafisz na tę blokadę, jedynym pewnym rozwiązaniem jest oficjalny klucz API
  poniżej — integracja i tak się zainstaluje (patrz sekcja 3), ale nie będzie
  w stanie sprawdzać wyników, dopóki nie dodasz klucza. Cała obsługa tego
  źródła jest w klasie `LottoPublicApiClient` w
  `custom_components/lotto/lotto_api.py`.
- **Z kluczem API** — korzysta z oficjalnego **Lotto Open API**
  (`developers.lotto.pl`), stabilniejszego, ale wymagającego darmowego klucza:
  1. Wyślij e-mail na `openapi@totalizator.pl` (albo skorzystaj z formularza
     kontaktowego na [lotto.pl/kontakt](https://www.lotto.pl/kontakt)),
     podając imię i nazwisko / nazwę firmy, e-mail i telefon.
  2. Po weryfikacji otrzymasz klucz API (`Secret`), który wpisujesz podczas
     konfiguracji integracji w Home Assistant.
  3. Dokumentacja API (Swagger) jest dostępna pod
     `https://developers.lotto.pl/swagger/index.html`.

Jeśli integracja zgłasza błędy pobierania wyników, oba klienty (i dokładne
nazwy pól odpowiedzi, jakich się spodziewają) są w jednym pliku
`custom_components/lotto/lotto_api.py`, więc ewentualna korekta jest lokalna.
Możesz też w każdej chwili przełączyć się między źródłami — wystarczy dodać
albo usunąć klucz API w opcjach integracji.

## 3. Konfiguracja

**Ustawienia → Urządzenia i usługi → Dodaj integrację → Lotto**, następnie:

- **Klucz API (Secret) — opcjonalnie** — zostaw puste, żeby korzystać z
  publicznego źródła bez rejestracji; wpisz klucz z kroku 2, żeby korzystać
  z oficjalnego API. Puste pole nie jest sprawdzane przy dodawaniu integracji
  (bo publiczne źródło bywa blokowane w sposób, którego nie da się odróżnić od
  chwilowej awarii) — instalacja zawsze się powiedzie; z kluczem API
  poprawność jest weryfikowana od razu, więc zły klucz zostanie zgłoszony
  natychmiast.
- **Co ile godzin sprawdzać wyniki** — domyślnie 4h (1–24h). Harmonogram
  losowań: Lotto/Lotto Plus we wtorek, czwartek i sobotę o 22:00; EuroJackpot
  we wtorek (20:15–21:00) i piątek (20:00–21:00) — częstsze sprawdzanie nie
  jest potrzebne, ale możesz to zmienić w każdej chwili w opcjach integracji.

Po dodaniu integracji w bocznym menu pojawi się pozycja **Lotto**.

## 4. Dodawanie kuponów

W panelu Lotto wybierz typ losowania, kliknij odpowiednią liczbę liczb na
siatce (6 z 1-49 dla Lotto; 5 z 1-50 + 2 liczby Euro z 1-12 dla EuroJackpot),
podaj na ile kolejnych losowań kupon jest ważny oraz datę pierwszego
losowania, którego dotyczy. Kupon pojawi się na liście poniżej wraz ze
statusem (Aktywny / Zakończony / Wygrana!) i historią sprawdzonych losowań.

## 5. Powiadomienia o trafieniu

Integracja **nie wysyła sama powiadomień push** — zamiast tego przy każdym
trafieniu:

- tworzy trwałe powiadomienie w Home Assistant (ikona dzwoneczka),
- emituje zdarzenie `lotto_win` z pełnymi danymi (`coupon_id`, `game_type`,
  `numbers`, `euro_numbers`, `draw_date`, `matched_numbers`,
  `matched_euro_numbers`, `prize_tier`).

Podepnij dowolną automatyzację pod to zdarzenie, np. wysyłkę powiadomienia na
telefon:

```yaml
alias: Powiadom o wygranej w Lotto
trigger:
  - platform: event
    event_type: lotto_win
action:
  - service: notify.mobile_app_twoj_telefon
    data:
      title: "Lotto: trafienie!"
      message: >
        {{ trigger.event.data.game_type }}: {{ trigger.event.data.matched_numbers }}
        trafień w losowaniu {{ trigger.event.data.draw_date }}.
```

## Testy

```
pip install -r requirements_test.txt
pytest
```

Uruchamia testy end-to-end na prawdziwej instancji Home Assistant
(`pytest-homeassistant-custom-component`) w katalogu `tests/` — pokrywają
storage kuponów, koordynator (w tym wykrywanie trafień i wybór dostawcy
wyników), websocket API, sensor, cykl życia config entry, config flow oraz
parsowanie odpowiedzi obu dostawców.

## Ograniczenia

- Przy domyślnym źródle (bez klucza API) każdy kupon jest sprawdzany dokładnie
  od jego `first_draw_date` — więc nawet jeśli Home Assistant był długo
  wyłączony, żadne losowanie z okresu ważności kuponu nie zostanie pominięte.
  Przy oficjalnym Open API (z kluczem) sprawdzane jest wyłącznie 20
  najnowszych losowań danego typu gry na każdym cyklu odpytywania — jeśli HA
  był długo wyłączony i kupon czeka na bardzo stare losowanie, może zostać
  pominięty (można to zwiększyć w `RESULTS_FETCH_SIZE` w `const.py`).
- Publiczny endpoint lotto.pl (domyślne źródło bez klucza) bywa blokowany
  przez Cloudflare (patrz sekcja 2) — sprawdzone, że to realny problem, nie
  tylko teoretyczne ryzyko. Jeśli w Ustawienia → System → Logi widzisz
  powtarzające się wpisy `custom_components.lotto` z "HTTP 403" albo
  "nieprawidłowym JSON-em", to oznacza tę blokadę — jedynym pewnym wyjściem
  jest dodanie klucza do oficjalnego Open API w opcjach integracji.
- Cała logika (dodawanie/usuwanie/listowanie kuponów, wykrywanie trafień,
  zdarzenie `lotto_win`, powiadomienie, sensor, cykl życia integracji) jest
  pokryta automatycznymi testami end-to-end na prawdziwej instancji Home
  Assistant (`pytest-homeassistant-custom-component`, katalog `tests/`, do
  uruchomienia przez `pip install -r requirements_test.txt && pytest`) z
  podstawionym źródłem wyników. Rejestracja panelu w przeglądarce nie jest
  objęta tymi testami (wymaga pełnego stosu HTTP Home Assistant) — sprawdzana
  wyłącznie ręcznie. Oficjalne Open API nie zostało jeszcze sprawdzone na
  żywo (brak klucza w środowisku, w którym integracja powstała); publiczny
  endpoint lotto.pl został sprawdzony na żywo i **potwierdzono blokadę
  Cloudflare** (patrz sekcja 2) — nie jest to już tylko teoretyczne ryzyko.

Po wdrożeniu warto dodać testowy kupon z datą pierwszego losowania w
przeszłości, aby sprawdzić ścieżkę wykrywania trafień od razu po dodaniu.
