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

## 2. Uzyskaj klucz do Lotto Open API

Integracja wymaga klucza do oficjalnego, darmowego API Totalizatora
Sportowego — bez niego nie da się jej skonfigurować:

1. Wyślij e-mail na `openapi@totalizator.pl` (albo skorzystaj z formularza
   kontaktowego na [lotto.pl/kontakt](https://www.lotto.pl/kontakt)),
   podając imię i nazwisko / nazwę firmy, e-mail i telefon.
2. Po weryfikacji otrzymasz klucz API (`Secret`), który wpisujesz podczas
   konfiguracji integracji w Home Assistant.
3. Dokumentacja API (Swagger) jest dostępna pod
   `https://developers.lotto.pl/swagger/index.html` — jeśli integracja
   zgłasza błędy pobierania wyników, warto porównać dokładne nazwy
   endpointów/parametrów z tym, co jest zaszyte w
   `custom_components/lotto/lotto_api.py` (cała komunikacja z API jest w
   tym jednym pliku, więc ewentualna korekta jest lokalna).

Wcześniejsza wersja tej integracji miała też darmowy, nieoficjalny tryb bez
klucza — usunięty, ponieważ jego publiczny endpoint okazał się chroniony
przez Cloudflare na części sieci (potwierdzone: HTTP 403, wymaga ciasteczka
`cf_clearance` z przejścia wyzwania JS w przeglądarce oraz tokenu SPA,
których nie da się odtworzyć zwykłym zapytaniem HTTP w tle) — integracja
instalowała się, ale cicho nigdy nie sprawdzała wyników na dotkniętych
sieciach. Klucz API jest teraz jedyną, ale za to niezawodną drogą.

## 3. Konfiguracja

**Ustawienia → Urządzenia i usługi → Dodaj integrację → Lotto**, następnie:

- **Klucz API (Secret)** — klucz z kroku 2. Wymagany, weryfikowany od razu
  przy dodawaniu — zły klucz zostanie zgłoszony natychmiast.
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
storage kuponów, koordynator (w tym wykrywanie trafień), websocket API,
sensor, cykl życia config entry, config flow oraz parsowanie odpowiedzi API.

## Ograniczenia

- Każdy kupon jest sprawdzany przez zapytanie zakotwiczone na jego własnej
  `first_draw_date` (endpoint `by-collection-per-game`), a nie przez
  wspólne "ostatnie N wyników" dla danego typu gry — dzięki temu nawet
  bardzo stare, jeszcze niesprawdzone losowanie z okresu ważności kuponu nie
  powinno zostać pominięte. **Uwaga:** ten konkretny endpoint dla
  oficjalnego Open API nie został jeszcze potwierdzony na żywo (jego
  istnienie wywnioskowano z tego, że działa identycznie nazwany endpoint na
  publicznej stronie lotto.pl, prawdopodobnie na tym samym backendzie) — po
  aktualizacji warto sprawdzić w Ustawienia → System → Logi, czy nie pojawia
  się wpis o HTTP 404 i przejściu na tryb zapasowy (`last-results`, bez
  filtrowania po dacie ani zawsze po typie gry po stronie serwera — w takim
  wypadku bardzo stare losowania mogą jednak zostać pominięte, jeśli inne,
  częściej losowane gry, np. Keno, zdominują okno `RESULTS_FETCH_SIZE`,
  domyślnie 100, konfigurowalne w `const.py`).
- Cała logika (dodawanie/usuwanie/listowanie kuponów, wykrywanie trafień,
  zdarzenie `lotto_win`, powiadomienie, sensor, cykl życia integracji,
  parsowanie odpowiedzi Open API) jest pokryta automatycznymi testami
  end-to-end na prawdziwej instancji Home Assistant
  (`pytest-homeassistant-custom-component`, katalog `tests/`, do
  uruchomienia przez `pip install -r requirements_test.txt && pytest`) z
  podstawionym źródłem wyników. Rejestracja panelu w przeglądarce nie jest
  objęta tymi testami (wymaga pełnego stosu HTTP Home Assistant) — sprawdzana
  wyłącznie ręcznie.

Po wdrożeniu warto dodać testowy kupon z datą pierwszego losowania w
przeszłości, aby sprawdzić ścieżkę wykrywania trafień od razu po dodaniu.
