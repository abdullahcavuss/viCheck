# viCheck — LabVIEW VI / klasör karşılaştırma

İki VI'ı veya iki klasörü karşılaştırır. Blok diyagramlar LabVIEW **olmadan** çözümlenir ve yan yana **SVG** olarak çizilir. Motor (pylabview + diff + çizim) VIVER projesiyle aynıdır; viCheck sadece karşılaştırma yapar, depo/commit yoktur.

## Kurulum — exe üretmek

pylabview bu repoya **git alt modülü** olarak bağlı (bkz. [pylabview](#pylabview)); repoyu alt modülüyle birlikte alın:

```
git clone --recursive https://github.com/abdullahcavuss/viCheck.git
```

(`--recursive` olmadan klonladıysanız `git submodule update --init`; `build.bat` / `run.bat` bunu eksikse kendisi de yapar.)

1. Bu klasörde **`build.bat`** dosyasına çift tıklayın (yalnızca derleme için Python 3.9+ gerekir).
2. Bittiğinde: **`dist\viCheck\viCheck.exe`**. Başka bir bilgisayarda kullanmak için `dist\viCheck` klasörünün tamamını kopyalayın; orada Python gerekmez.

Derlemeden denemek için: `run.bat`.

## Kullanım

- **A** (eski) ve **B** (yeni) için VI veya klasör seçin: *Choose VI… / Choose folder…*, yolu yapıştırın ya da dosyayı/klasörü kutuya sürükleyin (iki öğeyi birden bırakırsanız A ve B'ye yerleşir). **Compare**.
- **İki VI** → blok diyagram diff: değişiklik listesi, yan yana diyagramlar, eklenen/silinen/değişen öğeler renkli. `j`/`k` ile değişiklikler arasında gezinilir.
- **İki klasör** → dosyalar göreli yollarına göre eşleşir: değişen, yalnızca A'da, yalnızca B'de, taşınan ve aynı dosyalar. Her VI için özet (içerik / görsel-yerleşim / sadece yeniden kaydedilmiş). Metin dosyalarında metin diff'i.
- **SVG**
  - Pencere içinde sağ tık → **Inspect** (geliştirici araçları) ile SVG öğelerine bakabilirsiniz; ya da üstteki **↗ Open in browser** ile sayfayı tarayıcıda açıp F12 kullanın.
  - **⬇ Save view as SVG**: ekranda gördüğünüz A + B görünümünü tek SVG dosyası olarak kaydeder.
  - **🖼 Export SVG**: A ve B diyagramlarını numaralı değişiklik işaretleriyle SVG dosyalarına çizer (+ README.md).
  - Klasör karşılaştırmasında **📄 Report with SVG images…**: tüm değişen VI'lar için Markdown raporu + SVG'ler (ZIP olarak da indirilebilir).
- **Primitive names**: LabVIEW kuruluysa primitive adları ilk açılışta paletlerden otomatik okunur.

### Komut satırı / LabVIEW'den çağırma

```
viCheck.exe "C:\eski\Main.vi" "C:\yeni\Main.vi"
viCheck.exe "C:\proje_v1" "C:\proje_v2"
viCheck.exe --browser            (pencere yerine varsayılan tarayıcıda açar)
```

LabVIEW'den *System Exec.vi* ile aynı komut çağrılabilir.

## Neleri okuyabiliyor

pylabview'in çıkardığı veriye ek olarak viCheck şunları da çözüyor (ayrıntı ve kanıtlar: `docs/reverse-engineering.md`):
Property/Invoke Node property ve method adları, referans sabitlerinin hedefi, Event Structure çerçevelerinin olay adları
(`"OK": Value Change`, `<This VI>: Panel Close?`, `Timeout`), Event Data Node alanları, cluster/dizi/path sabitlerinin içeriği,
kontrollerin klavye kısayolları (Enter/Esc/F1) ve yazı biçimi değişiklikleri. Kesin çözülemeyen olay kodları
`Mouse Down/Up (#8)` gibi aday adla gösterilir.

## pylabview

VI dosyalarını okuyan kütüphane, [abdullahcavuss/pylabview](https://github.com/abdullahcavuss/pylabview) fork'unun
`heap-descriptions` dalından alt modül olarak geliyor (`third_party/pylabview`). Fork, orijinal
[mefistotelis/pylabview](https://github.com/mefistotelis/pylabview)'e şunları ekliyor:

- `--tolerant` seçeneği — tutarsız veri içeren VI'lar da uyarıyla okunur; viCheck pylabview'i hep bununla çağırır
- iki çökme düzeltmesi
- çıkarılan heap XML'ine olay ve klavye kısayolu açıklamaları (yorum olarak)

viCheck'e özgü çözümlemeler (property/method adları, olay çerçeve adları, cluster değerleri, diff) pylabview'de değil,
`engine/` altında. Fork'u güncellemek için:

```
cd third_party/pylabview
git pull
cd ../..
git add third_party/pylabview
git commit -m "Update pylabview"
```

## Test verileri

Geliştirmede kullanılan VI'lar JKI State Machine projesine ait ve repoda yok. `python tools/make_testdata.py` ile
`testdata/` altına indirilir; beklenen sonuçlar `testdata/README.md` içinde.

## Güvenlik

Karşılaştırılan dosyalar yalnızca okunur. Her VI önce özel bir geçici klasöre kopyalanır, kopya karşılaştırma anındaki hash ile doğrulanır ve pylabview ayrı bir süreçte kopyadan okur. Önbellek, dışa aktarımlar ve primitive adları `%LOCALAPPDATA%\viCheck` altında tutulur (`VICHECK_DATA` ortam değişkeniyle değiştirilebilir).

## Pencere

viCheck, Windows'un yerleşik **Microsoft Edge WebView2** bileşeniyle kendi penceresinde açılır (pywebview). Arayüz tarayıcıdakiyle aynıdır. WebView2 yoksa Edge/Chrome "uygulama penceresi" modunda, o da yoksa varsayılan tarayıcıda açılır.

Electron yerine bu yolu seçmemin nedeni şu: VI'ları çözümleyen motor Python'da. Electron'da da Python'u ayrıca paketlemek gerekirdi. Bu yöntemde exe çok daha küçük oluyor ve arayüz yine Chromium tabanlı.

## Yapı

```
vicheck.py        başlatıcı: pencere, komut satırı, --pylabview / --pick yardımcı modları
app.py            web uygulaması (Flask): karşılaştırma, diff, SVG export, rapor
engine/           files.py (tarama, hash, kayıt), lvtypes.py (tip tablosu + değer çözücü), vi_parser, vi_diff, render, svgrender, changelog ...
docs/             reverse-engineering.md — VI formatından ek çözülen alanlar ve kanıtları
tools/re/         format araştırma betikleri (olay kodları, kısayollar, heap farkı, toplu regresyon)
tools/make_testdata.py  test VI'larını JKI deposundan indirir
static/, templates/   arayüz (diagram.js SVG çizici, vidiff.js, vicheck.js)
third_party/pylabview pylabview fork'u (git alt modülü, MIT)
testdata/         test VI'ları — repoda yok, tools/make_testdata.py ile oluşturulur
vicheck.spec, build.bat   exe paketleme (PyInstaller, tek klasör)
```

Lisans: MIT. pylabview (MIT) alt modül olarak kullanılır; bkz. THIRD_PARTY_NOTICES.md. LabVIEW, National Instruments Corporation'ın ticari markasıdır.
