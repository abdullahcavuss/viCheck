# VI formatı — tersine mühendislik notları

viCheck'in pylabview çıktısından ek olarak okuduğu alanlar ve bunların nasıl doğrulandığı.
Kanıt seti: JKI State Machine (git geçmişi, 105 dosya) + NI LabVIEW Icon Editor (416 VI) — toplam 680 VI,
17 280 blok diyagram düğümü. Tüm VI'lar hatasız çözümleniyor.

Kural: bir kodun anlamı **kanıtla kesinleşmediyse isim uydurulmaz**; ya aday adlar `(#kod)` ile gösterilir
ya da ham kod ve olayın verdiği veri alanları yazılır.

## 1. Property Node / Invoke Node — kesin

Heap'te (`BDHb`) doğrudan var, eski parser okumuyordu:

| Alan | Anlam |
|---|---|
| `nodeName` | Sınıfın kısa adı: `"VI"`, `"App"`, `"Str"`, `"Bool"`, `"Tree (strict)"` … |
| `propList/propItemInfo/PropItemName` | Property adı, ör. `"FP.State"`, `"Val(Sgnl)"` (+ `PropItemCode`) |
| `methName` / `methCode` | Invoke Node metodu, ör. `"FP.Open"`, `"Run VI"` |
| `label` | Kontrole bağlı (implicit) düğümde kontrolün adı |

Gösterim: `VI: FP.State`, `Tree: Navigate Tree.Get Parent`, `Name: Caption, Text`.
Eşleştirme imzası sadece hedefi içerir; property listesi değişirse "değişti" olarak raporlanır.
Sonuç: 949/949 düğüm adlandırıldı.

## 2. Referans sabitleri (`ctlRefConst`) — kesin

Etiket metni hedefi verir: `Ref: This VI`, `Ref: Tree`, `Ref: Current VI Reference`.

## 3. Event Structure çerçeve adları

Her olay `EventNodeEvents/EventSpec` içinde:

| Alan | Anlam (kanıt) |
|---|---|
| `diagramIdx` | Olayın ait olduğu çerçeve |
| `source` | 1 = Dynamic (kayıtlı olay), 3 = kontrol, 4 = Application/Timeout, 5 = This VI |
| `ddoUID` | Kontrolün ön paneldeki nesnesi (FP heap'teki ddo uid → etiket) |
| `type` | Üst bitler: `0x4…` bildirim, `0x8…` filtre (`?` olayı); alt 16 bit: olay kodu |

Olay kodları, her olayın Event Data Node'una verdiği küme tipinin **alan adlarından** çıkarıldı (tip tablosu
`VCTP`'de "Event Data" kümesi, ör. `CtlRef, OldVal, NewVal`).

**Kesin:**

| Kod | Olay | Kanıt |
|---|---|---|
| 1 (source 4) | Timeout | alan yok; JKI şablonunun 0. çerçevesi |
| 2 | Value Change | `CtlRef, OldVal, NewVal`; 95 kullanım, hep buton/kontrol |
| 3 (filtre) | Panel Close? | `VIRef, Discard?`; JKI şablonu |
| 7 (filtre) | Mouse Down? | `Coords, Button, Mods, Discard?`; filtre sürümü olan tek fare tuşu olayı |
| 1000 (source 1) | User Event | `UsrEvtRef` + kullanıcı verisi; ad = veri etiketi |

**Çıkarım (aday adlar `(#kod)` ile gösterilir):**

| Kod | Aday | Kanıt |
|---|---|---|
| 8, 18 | Mouse Down / Mouse Up | ikisi de `Coords, Button, Mods`; Icon Editor'da aynı 3 resim kontrolünde 8, 9, 14, 15, 18 birlikte = 5 fare olayı |
| 9 | Mouse Move | yalnız `Coords` |
| 14, 15 | Mouse Enter / Leave | alan yok, aynı resim kontrolleri |
| 10, 11 (filtre) | Key Down? / Key Repeat? | `Char, VKey, ScanCode, Mods` |
| 5, 27 | Menu Selection (User / App) | `MenuRef, ItemTag, ItemPath`; aynı çerçevede birlikte |
| 26 | Application Instance Close | yalnız `AppRef` |
| 30, 31 | Item Open / Close (ağaç) | `Tag`, tree kontrolü |
| 51 (filtre) | Shortcut Menu Activation? | `MenuRef, Coords, SubObj, Discard?` |
| 52, 54 | Shortcut Menu Selection (User / App) | `MenuRef, ItemTag, ItemPath, Coords, SubObj` |
| 55 (filtre) | Edit Cell? | `String, Tag, Col, Discard?` |

Çözülemeyen: 12 (This VI; `ScanCode, Mods, PlatMods, FocusObj`), 25 (This VI; yalnız `VIRef`) — ham kod + alanlar.
Kanıt setinde 184 çerçevenin 149'u kesin, 33'ü aday adla, 2'si ham kodla adlandırılıyor.

## 4. Event Data Node — kesin

Seçili çıkışlar, terminal tiplerinin etiketlerinden: `Event Data: Source, NewVal`.

## 5. Sabit değerleri (cluster, dizi, path) — kesin

`ConstValue` LabVIEW *flattened* verisi: big-endian; string/dizi uzunluk önekli; cluster = elemanların arka arkaya
dizilişi, dolgu yok; tamamı sıfır olan değerler kısaltılmış saklanır (eksik baytlar sıfır sayılır). Tip ağacı `VCTP`'den
okunup özyinelemeli çözülüyor (`engine/lvtypes.py`): `{status: False, code: 0, source: ""}`,
`{left: 0, top: 0, right: 32, bottom: 32}`, `["A", "B", "C", "D"]`.
301 cluster sabitinin 232'si okunuyor, 41'i `{default}` (hepsi sıfır). İçinde refnum/variant/timestamp olan 28 cluster çözülmüyor.

## 6. Klavye kısayolları (Key Navigation) — kesin

Ön panel heap'inde panel düzeyinde `keyMapList/KeyMappingBinding`: `VKey`, `CharCode`, `Mods`, `Action`,
`Obj` (kontrolün ddo uid'i).

| VKey | Tuş | Kanıt |
|---|---|---|
| 55 | Enter | OK / Save / Yes butonları; JKI commit `#20 Bind "OK" button to <Escape> (not <Enter>)`: 55 → 45 |
| 45 | Esc | Exit / Cancel butonları; aynı commit |
| 15 | F1 | Help butonları |

`Action` (0/1/2) ve `Mods` bitleri henüz çözülmedi; sıfır değilse ham gösterilir.
Sonuç: JKI `#43 Remove Exit Keyboard Binding` artık **"Exit": keyboard shortcut Esc → none** olarak raporlanıyor
(önceden "Front panel (details not available)").

## 7. Gürültü ayıklama

| Heap alanı | Sınıf | Kanıt |
|---|---|---|
| `nRC`, `oRC`, `MinButSize`, `minPaneSize` | yerleşim (koordinat) | JKI "set pane origins to 0,0" commit'inde hepsi aynı miktarda kayıyor |
| `fgColor`, `bgColor` | görünüm | JKI "Changed comment colours from yellow to grey" |
| `textRec/flags` bit `0x1000`, `objFlags` | yok sayılır | değişiklik olmayan sabitlerde ardışık kayıtlar arasında açılıp kapanıyor |
| `textRec/flags`, `mode`, font | yazı biçimi (görünüm) | JKI "Left-justified state string": yalnız `"State"` sabitinin etiketinde `flags 0x400`, `mode 0x10` |

Ayrıca içerik özetinde bir hata düzeltildi: görünüm sayılan bir öğe içerik özetine kapanış işareti bırakıyordu; bu yüzden
yalnız renk eklenmesi bile "içerik değişti" sonucunu veriyordu.

Etki (test klasörü, 13 değişen VI): "Block diagram (details not available)" 4 VI'dan 0'a indi; şablon VI'daki gerçek
değişiklik (Esc kısayolunun kaldırılması) ilk kez görünür oldu.

## Hâlâ okunamayanlar

- `VITS` bloğu (VI'a kaydedilmiş etiket verisi): pylabview çözemiyor; diyagram ve diff'i etkilemiyor.
- Refnum / variant / timestamp içeren cluster sabitleri.
- Olay kodları 12, 25; 8↔18, 14↔15, 5↔27, 52↔54 ikililerinin hangisinin hangisi olduğu.
- `KeyMappingBinding/Action`, `Mods` bitleri.
- Yazı biçimi bitlerinin tek tek anlamı (hizalama / kalın / italik ayrımı): değişiklik bulunuyor ama türü söylenmiyor.
- Primitive adları LabVIEW kurulu değilse `#numara` kalıyor (kurulu ise paletlerden okunuyor).

## Araçlar

Bu çalışma `tools/re/` altındaki betiklerle tekrarlanabilir:
`events.py` (olay kodları + veri alanları), `nodes.py` (property/invoke/ref), `keys.py` (kısayollar),
`loosediff.py` (iki VI'ın "içerik" farkını heap düzeyinde gösterir), `bulk.py` (tüm VI'larda regresyon).
