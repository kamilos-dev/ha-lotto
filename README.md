# Lotto — integracja Home Assistant

Dodaje pozycję **Lotto** w bocznym menu Home Assistant. Panel pozwala dodawać
kupony (Lotto / EuroJackpot), pokazuje ich listę i status, a integracja w tle
co jakiś czas sprawdza wyniki losowań (oficjalne **Lotto Open API**,
`developers.lotto.pl`) i informuje o trafieniach.

## 1. Uzyskaj klucz do Lotto Open API

Integracja korzysta z oficjalnego, darmowego API Totalizatora Sportowego.
Nie da się go uzyskać automatycznie — trzeba o niego poprosić:

1. Wyślij e-mail na `openapi@totalizator.pl` (albo skorzystaj z formularza
   kontaktowego na [lotto.pl/kontakt](https://www.lotto.pl/kontakt)),
   podając imię i nazwisko / nazwę firmy, e-mail i telefon.
2. Po weryfikacji otrzymasz klucz API (`Secret`), który wpisujesz podczas
   konfiguracji integracji w Home Assistant.
3. Dokumentacja API (Swagger) jest dostępna pod
   `https://developers.lotto.pl/swagger/index.html` — jeśli po wdrożeniu
   integracja zgłasza błędy pobierania wyników, warto porównać dokładne
   nazwy endpointów/parametrów z tym, co jest zaszyte w
   `custom_components/lotto/lotto_api.py` (cała komunikacja z API jest w
   tym jednym pliku, więc ewentualna korekta jest lokalna).

## 2. Instalacja

### Wariant A: HACS (zalecane)

Repozytorium: **https://github.com/kamilos-dev/ha-lotto**

1. W HA otwórz **HACS → Integracje**, kliknij trzy kropki w prawym górnym
   rogu → **Custom repositories**.
2. Wklej `https://github.com/kamilos-dev/ha-lotto`, kategoria **Integration**,
   kliknij **Add**.
3. Znajdź na liście **Lotto** i kliknij **Download**.
4. Zrestartuj Home Assistant.

Kolejne aktualizacje integracji (np. nowe wersje z poprawkami do
`lotto_api.py`, gdyby zmienił się kontrakt API) będą widoczne w HACS jak przy
każdej innej instalowanej stamtąd integracji.

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

## 3. Konfiguracja

**Ustawienia → Urządzenia i usługi → Dodaj integrację → Lotto**, następnie:

- **Klucz API (Secret)** — klucz z kroku 1.
- **Co ile godzin sprawdzać wyniki** — domyślnie 4h (1–24h). Losowania Lotto
  odbywają się we wt/czw/sob, EuroJackpot we wt/pt — częstsze sprawdzanie nie
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

## Ograniczenia

- Sprawdzane jest wyłącznie 20 najnowszych losowań danego typu gry na każdym
  cyklu odpytywania — jeśli Home Assistant był długo wyłączony i kupon czeka
  na bardzo stare losowanie, może zostać pominięty (można to zwiększyć w
  `RESULTS_FETCH_SIZE` w `const.py`).
- Ta integracja nie została przetestowana na żywej instancji Home Assistant
  ani z rzeczywistym kluczem Lotto Open API (brak dostępu do obu w środowisku,
  w którym powstała) — wykonano wyłącznie statyczną weryfikację kodu. Po
  wdrożeniu warto dodać testowy kupon z datą pierwszego losowania w
  przeszłości, aby sprawdzić ścieżkę wykrywania trafień od razu po dodaniu.
