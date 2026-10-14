"""
User interface languages: English (source) and Turkish.

- Templates call _("English text", **values); scripts call T("English text", {values}).
- Text produced by the diff engine (change titles, verdict labels, details) is translated on the way
  out by engine_text(), so the engine itself stays language independent.
- LabVIEW's own terms (Value Change, Property Node, Case Structure…) are not translated: LabVIEW shows
  them in English too.
"""
import re

LANGS = {"en": "English", "tr": "Türkçe"}
DEFAULT = "en"

# English -> Turkish. Keys are the English source strings; "{name}" placeholders are filled by format().
TR = {}
TR.update({
    # ---------------------------------------------------------------- top bar / common
    "New comparison": "Yeni karşılaştırma",
    "Primitive names": "Primitive adları",
    "About": "Hakkında",
    "↗ Open in browser": "↗ Tarayıcıda aç",
    "Open this page in your web browser — e.g. to inspect the SVG with the browser's developer tools (F12)":
        "Bu sayfayı web tarayıcınızda açar — örneğin SVG'yi tarayıcının geliştirici araçlarıyla (F12) incelemek için",
    "Language": "Dil",
    "folder comparison": "klasör karşılaştırma",
    "SVG export": "SVG dışa aktarma",
    "comparison report": "karşılaştırma raporu",
    "Show in Explorer": "Explorer'da göster",
    "Show in folder": "Klasörde göster",
    "Open": "Aç",
    "Open folder": "Klasörü aç",
    "Back": "Geri",
    "Back to the comparison": "Karşılaştırmaya dön",
    "Back to the diff": "Diff'e dön",
    "Clear": "Temizle",
    "Save": "Kaydet",
    "Add": "Ekle",
    "Edit": "Düzenle",
    "files": "dosya",
    "Compare": "Karşılaştır",
    "Comparing…": "Karşılaştırılıyor…",

    # ---------------------------------------------------------------- home
    "Compare LabVIEW code": "LabVIEW kodunu karşılaştır",
    "Choose two VIs or two folders. Block diagrams are parsed and compared without LabVIEW and drawn side by side as SVG.":
        "İki VI veya iki klasör seçin. Blok diyagramlar LabVIEW olmadan çözümlenip karşılaştırılır ve yan yana SVG olarak çizilir.",
    "old / reference": "eski / referans",
    "new / changed": "yeni / değişmiş",
    "Drop a VI or a folder here": "Bir VI veya klasörü buraya bırakın",
    "Choose VI…": "VI seç…",
    "Choose folder…": "Klasör seç…",
    "Recent comparisons": "Son karşılaştırmalar",
    "Nothing yet. Your comparisons will be listed here.": "Henüz yok. Karşılaştırmalarınız burada listelenecek.",
    "Folder comparison: ignored files": "Klasör karşılaştırma: yok sayılan dosyalar",
    "One rule per line. <code>name/</code> ignores a folder, <code>*.ext</code> a file type. Always ignored:":
        "Her satıra bir kural. <code>ad/</code> bir klasörü, <code>*.uzantı</code> bir dosya türünü yok sayar. Her zaman yok sayılanlar:",
    "Tips": "İpuçları",
    "Two folders: every file is matched by its relative path; VIs that were only re-saved by LabVIEW are grouped separately.":
        "İki klasör: her dosya göreli yoluyla eşleşir; LabVIEW'in sadece yeniden kaydettiği VI'lar ayrı gruplanır.",
    "From a command line or LabVIEW's <i>System Exec</i>:": "Komut satırından veya LabVIEW'in <i>System Exec</i>'inden:",
    "Diagrams are SVG: right-click → <i>Inspect</i>, or <b>↗ Open in browser</b> and use the developer tools (F12). <b>Export SVG</b> saves them as files.":
        "Diyagramlar SVG'dir: sağ tık → <i>Inspect</i>, ya da <b>↗ Tarayıcıda aç</b> ile geliştirici araçlarını (F12) kullanın. <b>SVG dışa aktar</b> bunları dosya olarak kaydeder.",
    "not found": "bulunamadı",
    "folder": "klasör",
    "file": "dosya",
    "This path does not exist": "Bu yol yok",
    "{vis} VI/control in {files} files": "{files} dosyada {vis} VI/kontrol",
    "⚠ A and B must both be files or both be folders.": "⚠ A ve B ya ikisi de dosya ya da ikisi de klasör olmalı.",
    "Folder comparison: every file is matched by its path.": "Klasör karşılaştırma: her dosya yoluyla eşleşir.",
    "Block diagram diff of the two VIs.": "İki VI'ın blok diyagram farkı.",
    "Choose both A and B.": "Hem A'yı hem B'yi seçin.",
    "Swap A and B": "A ile B'yi değiştir",
    "Drag & drop of files works in the viCheck window. In a browser, use <b>Choose VI…</b> / <b>Choose folder…</b> or paste the path.":
        "Dosya sürükle-bırak viCheck penceresinde çalışır. Tarayıcıda <b>VI seç…</b> / <b>Klasör seç…</b> kullanın ya da yolu yapıştırın.",
    "⚠ Could not open:": "⚠ Açılamadı:",

    # ---------------------------------------------------------------- errors (server)
    "Choose two VIs or two folders to compare.": "Karşılaştırmak için iki VI veya iki klasör seçin.",
    "Not found: {path}": "Bulunamadı: {path}",
    "Both sides must be of the same kind: two files or two folders (A is a {a}, B is a {b}).":
        "İki taraf aynı türde olmalı: iki dosya ya da iki klasör (A bir {a}, B bir {b}).",
    "A and B are the same {kind}.": "A ile B aynı {kind}.",
    "File not found: {path}": "Dosya bulunamadı: {path}",
    "A report can be made for two folders.": "Rapor iki klasör için oluşturulabilir.",
    "LabVIEW folder not found: {path}": "LabVIEW klasörü bulunamadı: {path}",
    "Folder not found: {path}": "Klasör bulunamadı: {path}",
    "The file for this comparison has changed or is missing on disk. Run the comparison again.":
        "Bu karşılaştırmanın dosyası diskte değişmiş veya silinmiş. Karşılaştırmayı yeniden çalıştırın.",
    "The file changed while it was being read. Run the comparison again.":
        "Dosya okunurken değişti. Karşılaştırmayı yeniden çalıştırın.",
    "The file changed while it was being copied. Run the comparison again.":
        "Dosya kopyalanırken değişti. Karşılaştırmayı yeniden çalıştırın.",
    "Unknown file. Reload the page to scan the files again.": "Bilinmeyen dosya. Dosyaları yeniden taramak için sayfayı yenileyin.",
    "Unknown file — run the comparison again.": "Bilinmeyen dosya — karşılaştırmayı yeniden çalıştırın.",

    # ---------------------------------------------------------------- folder comparison
    "Compare again": "Yeniden karşılaştır",
    "Change…": "Değiştir…",
    "Report with SVG images…": "SVG resimli rapor…",
    "A Markdown report: summary table, every changed VI with its change list and one SVG with the A and B block diagrams.":
        "Markdown rapor: özet tablo, her değişen VI için değişiklik listesi ve A ile B blok diyagramlarını içeren bir SVG.",
    "Generate report": "Raporu oluştur",
    # ---------------------------------------------------------------- first-start help
    "How to use viCheck": "viCheck nasıl kullanılır",
    "Welcome to viCheck": "viCheck'e hoş geldiniz",
    "viCheck compares two LabVIEW VIs or two folders. Block diagrams are read without LabVIEW and drawn side by side as SVG; your files are only read, never changed.":
        "viCheck iki LabVIEW VI'ını ya da iki klasörü karşılaştırır. Blok diyagramlar LabVIEW olmadan okunur ve yan yana SVG olarak çizilir; dosyalarınız yalnızca okunur, asla değiştirilmez.",
    "Choose A and B": "A ve B'yi seçin",
    "A is the old / reference version, B the new one. Pick a VI or a folder for each with <i>Choose VI…</i> / <i>Choose folder…</i>, paste a path, or drag files onto the boxes (two at once fill A and B).":
        "A eski / referans sürüm, B yeni sürümdür. Her biri için <i>VI seç…</i> / <i>Klasör seç…</i> ile bir VI ya da klasör seçin, yolu yapıştırın veya dosyaları kutulara sürükleyin (aynı anda iki dosya A ve B'yi doldurur).",
    "Two VIs open the block diagram diff. Two folders list the files that differ; open a VI with <i>Block diagram diff →</i>.":
        "İki VI blok diyagram karşılaştırmasını açar. İki klasörde farklı dosyalar listelenir; bir VI'ı <i>Blok diyagram farkı →</i> ile açın.",
    "Read the diff": "Farkları inceleyin",
    "The list on the left holds every change; click one (or use <kbd>j</kbd> / <kbd>k</kbd>) and both diagrams pan to it. Green = added, red = removed, orange = modified, purple = moved to another frame. <i>▴ Hide</i> folds the file details to give the list more room.":
        "Soldaki listede tüm değişiklikler var; birine tıklayın (ya da <kbd>j</kbd> / <kbd>k</kbd>), iki diyagram da oraya gider. Yeşil = eklendi, kırmızı = silindi, turuncu = değişti, mor = başka çerçeveye taşındı. <i>▴ Gizle</i> dosya ayrıntılarını katlayıp listeye yer açar.",
    "Save and share": "Kaydedin ve paylaşın",
    "<i>📄 PDF</i> makes a report with readable detail views of every change; <i>🖼 Export SVG</i> and <i>⬇ Save view as SVG</i> save the drawings. For two folders, <i>📄 Report with SVG images…</i> covers every changed VI.":
        "<i>📄 PDF</i> her değişikliğin okunaklı detay görünümleriyle bir rapor üretir; <i>🖼 SVG dışa aktar</i> ve <i>⬇ Görünümü SVG kaydet</i> çizimleri kaydeder. İki klasörde <i>📄 SVG resimli rapor…</i> tüm değişen VI'ları kapsar.",
    "Inspect the SVG": "SVG'yi inceleyin",
    "Right-click → <i>Inspect</i>, or <i>↗ Open in browser</i> and press F12.":
        "Sağ tık → <i>İncele</i>, ya da <i>↗ Tarayıcıda aç</i> ve F12.",
    "You can open this again with the <b>?</b> button at the top.": "Bu pencereyi üstteki <b>?</b> düğmesiyle yeniden açabilirsiniz.",
    "Start": "Başla",
    # ---------------------------------------------------------------- PDF, detail views, sidebar
    "Hide or show the file details": "Dosya ayrıntılarını gizle / göster",
    "Hide": "Gizle",
    "Details": "Ayrıntılar",
    "Also make a PDF": "PDF de oluştur",
    "For large VIs: a cropped A + B view of every group of nearby changes, printed at about 1:1":
        "Büyük VI'lar için: birbirine yakın her değişiklik grubunun kırpılmış A + B görünümü, yaklaşık 1:1 ölçekte",
    "Detail views around the changes": "Değişikliklerin detay görünümleri",
    "Off: one image per Stacked Sequence frame that has changes (narrower, easier to read on a page)":
        "Kapalı: değişiklik olan her Stacked Sequence çerçevesi için ayrı resim (daha dar, sayfada daha okunaklı)",
    "Stacked Sequence → Flat": "Stacked Sequence → Flat",
    "Open PDF": "PDF'i aç",
    "Contents": "İçerik",
    "Changes to include": "Dahil edilecek değişiklikler",
    "Drawing": "Çizim",
    "Summary tables": "Özet tabloları",
    "Change list of every VI": "Her VI'ın değişiklik listesi",
    "Change list": "Değişiklik listesi",
    "The whole A and B block diagram in one SVG, fitted to the page": "A ve B blok diyagramının tamamı tek SVG'de, sayfaya sığdırılmış",
    "Whole diagram (A + B)": "Diyagramın tamamı (A + B)",
    "Unreadable, out-of-scope and re-saved VIs, and the other changed files": "Okunamayan, kapsam dışı ve sadece yeniden kaydedilmiş VI'lar ile değişen diğer dosyalar",
    "Other files and VIs": "Diğer dosyalar ve VI'lar",
    "Primitive names and your LabVIEW version": "Primitive adları ve LabVIEW sürümünüz",
    "The primitive names are being read from the LabVIEW palettes now.": "Primitive adları şu anda LabVIEW paletlerinden okunuyor.",
    "{n} primitive names were read from {src}.": "{n} primitive adı {src} kurulumundan okundu.",
    "{n} primitive names are known.": "{n} primitive adı tanımlı.",
    "No LabVIEW installation was found on this computer, so primitives (Add, Array Size, …) are shown by number, e.g. <code>#1809</code>.":
        "Bu bilgisayarda LabVIEW kurulumu bulunamadı; bu yüzden primitive'ler (Add, Array Size, …) numarayla gösterilir, ör. <code>#1809</code>.",
    "VI files store primitives only by number and the names come from the palettes of a LabVIEW installation. If your VIs were made with another LabVIEW version, or LabVIEW is not installed here, import the names from that version's folder on the <a href=\"{url}\">Primitive names</a> page; you can also name a primitive by double-clicking it on a diagram.":
        "VI dosyaları primitive'leri yalnızca numarayla saklar; adlar bir LabVIEW kurulumunun paletlerinden gelir. VI'larınız başka bir LabVIEW sürümüyle yapıldıysa ya da burada LabVIEW kurulu değilse, adları o sürümün klasöründen <a href=\"{url}\">Primitive adları</a> sayfasında içe aktarın; bir primitive'e diyagramda çift tıklayarak da ad verebilirsiniz.",
    "Could not make the PDF:": "PDF oluşturulamadı:",
    "PDF needs Microsoft Edge or Google Chrome": "PDF için Microsoft Edge veya Google Chrome gerekli",
    "PDF": "PDF",
    "📄 PDF": "📄 PDF",
    "Generate again": "Yeniden oluştur",
    "A PDF with the list of changes, the whole A and B diagram and readable detail views of the changes":
        "Değişiklik listesi, A ve B diyagramının tamamı ve değişikliklerin okunaklı detay görünümleriyle bir PDF",
    "{n} file differs": "{n} dosya farklı",
    "{n} files differ": "{n} dosya farklı",
    "{n} modified": "{n} değişmiş",
    "{n} only in B": "{n} sadece B'de",
    "{n} only in A": "{n} sadece A'da",
    "{n} moved": "{n} taşınmış",
    "{n} identical": "{n} aynı",
    "VI/control:": "VI/kontrol:",
    "The folders are identical": "Klasörler aynı",
    "All {n} files have exactly the same content.": "{n} dosyanın hepsi tamamen aynı içerikte.",
    "only in B": "sadece B'de",
    "only in A": "sadece A'da",
    "Block diagram diff →": "Blok diyagram farkı →",
    "Text diff": "Metin farkı",
    "{n} identical file": "{n} aynı dosya",
    "{n} identical files": "{n} aynı dosya",
    "— byte-for-byte the same in A and B": "— A ve B'de bayt bayt aynı",
    "Ignored by your rules:": "Kurallarınızla yok sayılanlar:",
    "Added": "Eklendi",
    "Deleted": "Silindi",
    "Modified": "Değişti",
    "Moved/renamed": "Taşındı/yeniden adlandırıldı",

    # ---------------------------------------------------------------- VI summaries / filter (app.js)
    "Content changed": "İçerik değişti",
    "Visual/layout": "Görsel/yerleşim",
    "Visual/layout only": "Sadece görsel/yerleşim",
    "Re-saved only": "Sadece yeniden kaydedilmiş",
    "re-saved only": "sadece yeniden kaydedilmiş",
    "{n} VI content": "{n} VI içerik",
    "{n} VI visual/layout": "{n} VI görsel/yerleşim",
    "{n} VI re-saved only": "{n} VI sadece yeniden kaydedilmiş",
    "{n} VI unreadable": "{n} VI okunamadı",
    "⚠ unreadable": "⚠ okunamadı",
    "server error": "sunucu hatası",
    "{n} VI re-saved only (group)": "{n} VI sadece yeniden kaydedilmiş",
    "{n} VIs re-saved only": "{n} VI sadece yeniden kaydedilmiş",
    " — content unchanged (only revision / compiled code / internal numbers differ).":
        " — içerik aynı (sadece revizyon / derlenmiş kod / iç numaralar farklı).",
    "Show:": "Göster:",
    "Block diagram logic": "Blok diyagram mantığı",
    "Block diagram layout": "Blok diyagram yerleşimi",
    "Front panel": "Ön panel",
    "Timed Loop / XNode internal settings": "Timed Loop / XNode iç ayarları",
    "Other (icon, description, settings)": "Diğer (ikon, açıklama, ayarlar)",
    "{n} VI(s) hidden": "{n} VI gizlendi",
    "No text differences.": "Metin farkı yok.",
    "LabVIEW version": "LabVIEW sürümü",

    # ---------------------------------------------------------------- diff page
    "New comparison (start)": "Yeni karşılaştırma",
    "— not present": "— yok",
    "(no file)": "(dosya yok)",
    "Diagram": "Diyagram",
    "Panel": "Panel",
    "Dependencies": "Bağımlılıklar",
    "Properties": "Özellikler",
    "Block diagram": "Blok diyagram",
    "Front panel controls": "Ön panel kontrolleri",
    "SubVI, typedef and library dependencies": "SubVI, typedef ve kütüphane bağımlılıkları",
    "VI properties": "VI özellikleri",
    "Use <b>j</b>/<b>k</b> or ↑/↓ to move through the list · clicking an item pans both diagrams to that spot":
        "Listede <b>j</b>/<b>k</b> veya ↑/↓ ile gezinin · bir öğeye tıklayınca iki diyagram da oraya gider",
    "Side by side": "Yan yana",
    "Dim unchanged": "Değişmeyenleri soldur",
    "Show moved": "Taşınanları göster",
    "Stacked → Flat": "Stacked → Flat",
    "Show Stacked Sequence frames side by side like a Flat Sequence": "Stacked Sequence çerçevelerini Flat Sequence gibi yan yana göster",
    "Sync scroll": "Birlikte kaydır",
    "SubVI labels": "SubVI etiketleri",
    "⇄ Swap": "⇄ Değiştir",
    "⬇ Save view as SVG": "⬇ Görünümü SVG kaydet",
    "Save the SVG exactly as it is drawn in the panes now (current zoom and frames)":
        "SVG'yi bölmelerde şu an çizildiği gibi kaydet (geçerli yakınlaştırma ve çerçeveler)",
    "🖼 Export SVG": "🖼 SVG dışa aktar",
    "Draw the A and B block diagrams into one SVG file per view, with numbered change markers":
        "A ve B blok diyagramlarını numaralı değişiklik işaretleriyle görünüm başına bir SVG dosyasına çiz",
    "added": "eklendi",
    "removed": "silindi",
    "modified": "değişti",
    "other frame": "başka çerçeve",
    "moved": "taşındı",
    "Parsing and comparing the VIs with pylabview…": "VI'lar pylabview ile çözümlenip karşılaştırılıyor…",
    "The first time may take a few seconds; the result is cached.": "İlk seferde birkaç saniye sürebilir; sonuç önbelleğe alınır.",
    "⚠ Could not compute the diff:": "⚠ Fark hesaplanamadı:",
    "Parsing the VI (no LabVIEW needed)…": "VI çözümleniyor (LabVIEW gerekmez)…",
    "Removed": "Silindi",
    "Moved to another frame": "Başka çerçeveye taşındı",
    "Wires": "Teller",
    "Comments": "Yorumlar",
    "Moved": "Taşındı",
    "Timed Loop / XNode internal setting": "Timed Loop / XNode iç ayarı",
    "No changes match the filter.": "Filtreye uyan değişiklik yok.",
    "No functional change found on the block diagram.": "Blok diyagramda işlevsel değişiklik bulunmadı.",
    "The file was most likely only re-saved or recompiled.": "Dosya büyük olasılıkla sadece yeniden kaydedildi veya derlendi.",
    "No added/removed/type-changed front panel controls.": "Eklenen/silinen/türü değişen ön panel kontrolü yok.",
    "Controls in B": "B'deki kontroller",
    "Dependencies (subVIs, typedefs, libraries) did not change.": "Bağımlılıklar (subVI, typedef, kütüphane) değişmedi.",
    "Nodes / wires": "Düğüm / tel",
    "VI properties did not change.": "VI özellikleri değişmedi.",
    "Description changed": "Açıklama değişti",
    "Icon of A": "A'nın ikonu",
    "Icon of B": "B'nin ikonu",
    "icon changed": "ikon değişti",
    "{n} change": "{n} değişiklik",
    "{n} changes": "{n} değişiklik",
    "Block diagram, front panel, connector pane, dependencies and settings are the same; only revision/compile information changed.":
        "Blok diyagram, ön panel, konnektör paneli, bağımlılıklar ve ayarlar aynı; sadece revizyon/derleme bilgisi değişti.",
    "Name primitive…": "Primitive'e ad ver…",
    "Choose frame…": "Çerçeve seç…",
    "Copy name": "Adı kopyala",
    "Name for primitive #{id} (e.g. Add, Equal?, Index Array). Leave empty to delete the name.\nThis name is used in all VIs.":
        "#{id} primitive'i için ad (ör. Add, Equal?, Index Array). Adı silmek için boş bırakın.\nBu ad tüm VI'larda kullanılır.",
    "Wire": "Tel",
    "array": "dizi",
    "{n} ends": "{n} uç",
    "Comment": "Yorum",
    "added (dependency)": "eklendi",
    "removed (dependency)": "silindi",
    "✓ Saved": "✓ Kaydedildi",
    "Could not save": "Kaydedilemedi",

    # ---------------------------------------------------------------- diagram tooltips (diagram.js)
    "Moved into another structure/frame": "Başka bir yapıya/çerçeveye taşındı",
    "SubVI": "SubVI",
    "Primitive": "Primitive",
    "Structure": "Yapı",
    "Constant": "Sabit",
    "Terminal": "Terminal",
    "Node": "Düğüm",
    "Variable": "Değişken",
    "Block diagram is empty or could not be read": "Blok diyagram boş veya okunamadı",
    "No file in this version (newly added)": "Bu sürümde dosya yok (yeni eklenmiş)",
    "No file in this version (deleted)": "Bu sürümde dosya yok (silinmiş)",
    "Zoom in": "Yakınlaştır",
    "Zoom out": "Uzaklaştır",
    "Fit": "Sığdır",
    "indicator": "gösterge",
    "control": "kontrol",
    "local": "yerel",
    "global": "global",
    "read": "okuma",
    "write": "yazma",
    "Global VI:": "Global VI:",
    "Value:": "Değer:",
    "{n} frames": "{n} çerçeve",
    "Location:": "Konum:",
    "Right-click / double-click: name it": "Sağ tık / çift tık: ad ver",

    # ---------------------------------------------------------------- text diff / export / report
    "SVG export of {name}": "{name} — SVG dışa aktarma",
    "Saved to": "Kaydedildiği yer",
    "{n} SVG file and a README.md.": "{n} SVG dosyası ve bir README.md.",
    "{n} SVG files and a README.md.": "{n} SVG dosyası ve bir README.md.",
    "Each SVG holds the A and the B block diagram; numbered boxes match the list. Click an image to open it on its own (zoom stays sharp; right-click → Inspect to look at the SVG elements).":
        "Her SVG, A ve B blok diyagramını içerir; numaralı kutular listeyle eşleşir. Bir resmi tek başına açmak için tıklayın (yakınlaştırınca netliği bozulmaz; SVG öğelerine bakmak için sağ tık → Inspect).",
    "Nothing to draw: the VIs have no block diagram.": "Çizilecek bir şey yok: VI'ların blok diyagramı yok.",
    "Comparison report": "Karşılaştırma raporu",
    "⬇ ZIP (REPORT.md + SVG images)": "⬇ ZIP (REPORT.md + SVG resimleri)",
    "Could not generate the report:": "Rapor oluşturulamadı:",
    "Preparing…": "Hazırlanıyor…",
    "Every changed VI is parsed and compared without LabVIEW, and an SVG with both block diagrams is drawn. VIs opened before come from the cache.":
        "Her değişen VI LabVIEW olmadan çözümlenip karşılaştırılır ve iki blok diyagramı içeren bir SVG çizilir. Daha önce açılan VI'lar önbellekten gelir.",

    # ---------------------------------------------------------------- primitive names
    "{n} entries · {u} entered manually": "{n} kayıt · {u} elle girilmiş",
    "Search by name or resID…": "Ada veya resID'ye göre ara…",
    "Name": "Ad",
    "Source": "Kaynak",
    "manual": "elle",
    "resID (e.g. 1809)": "resID (ör. 1809)",
    "Name (e.g. Array Size)": "Ad (ör. Array Size)",
    "Import from a LabVIEW installation": "LabVIEW kurulumundan içe aktar",
    "VI files store primitives only by number (resID). viCheck reads the names from the function palettes (<code>menus\\*.mnu</code>) of the LabVIEW installed on this computer. LabVIEW is not opened and no file is changed.":
        "VI dosyaları primitive'leri sadece numarayla (resID) saklar. viCheck adları bu bilgisayardaki LabVIEW'in fonksiyon paletlerinden (<code>menus\\*.mnu</code>) okur. LabVIEW açılmaz, hiçbir dosya değiştirilmez.",
    "LabVIEW folder": "LabVIEW klasörü",
    "No installation was found automatically; enter the path manually.": "Otomatik olarak kurulum bulunamadı; yolu elle girin.",
    "Import names": "Adları içe aktar",
    "Names you entered manually are kept and never overwritten. Primitives not found in the palettes (hidden/old ones) stay as <code>#number</code>; you can name them by double-clicking them on a diagram.":
        "Elle girdiğiniz adlar korunur, üzerine yazılmaz. Paletlerde bulunmayan primitive'ler (gizli/eski olanlar) <code>#numara</code> olarak kalır; diyagramda çift tıklayarak ad verebilirsiniz.",
    "Name for resID {id} (empty = delete):": "resID {id} için ad (boş = sil):",
    "Reading palettes: {done}/{total} files": "Paletler okunuyor: {done}/{total} dosya",
    "{found} primitives found, {added} names added/updated": "{found} primitive bulundu, {added} ad eklendi/güncellendi",

    # ---------------------------------------------------------------- about
    "Compares two LabVIEW VIs or two folders of VIs and draws the block diagrams side by side as SVG — without LabVIEW.":
        "İki LabVIEW VI'ını veya iki VI klasörünü karşılaştırır ve blok diyagramları yan yana SVG olarak çizer — LabVIEW olmadan.",
    "Window": "Pencere",
    "desktop window (Microsoft Edge WebView2)": "masaüstü penceresi (Microsoft Edge WebView2)",
    "browser app window": "tarayıcı uygulama penceresi",
    "web browser": "web tarayıcısı",
    "Data folder": "Veri klasörü",
    "— cache, exports, primitive names": "— önbellek, dışa aktarımlar, primitive adları",
    "Safety": "Güvenlik",
    "The compared files are only read. Each VI is copied to a private temporary folder and parsed from the copy.":
        "Karşılaştırılan dosyalar sadece okunur. Her VI özel bir geçici klasöre kopyalanır ve kopyadan çözümlenir.",
    "VI parsing uses": "VI çözümleme için kullanılan:",
    "a fork of": "şunun fork'u:",
    "The diff engine and the diagram renderer come from VIVER. viCheck is not affiliated with NI or Emerson; LabVIEW is a trademark of National Instruments Corporation.":
        "Diff motoru ve diyagram çizici VIVER'dan gelir. viCheck'in NI veya Emerson ile bağlantısı yoktur; LabVIEW, National Instruments Corporation'ın ticari markasıdır.",
})


def detect(accept_language):
    """Language from the Accept-Language header (the desktop window sends the Windows UI language)."""
    for part in (accept_language or "").split(","):
        code = part.split(";")[0].strip().lower()[:2]
        if code in LANGS:
            return code
    return DEFAULT


def translate(text, lang, **values):
    if lang == "tr":
        text = TR.get(text, text)
    if values:
        try:
            text = text.format(**values)
        except (KeyError, IndexError, ValueError):
            pass
    return text


def plural(singular, plural_, n, lang, **values):
    return translate(singular if n == 1 else plural_, lang, n=n, **values)


def js_table(lang):
    """Translations handed to the page scripts."""
    return TR if lang == "tr" else {}


# ======================================================================= engine text
# Labels of verdict parts / categories (exact strings)
_LABELS_TR = {
    "Block diagram": "Blok diyagram",
    "Block diagram comments": "Blok diyagram yorumları",
    "Block diagram layout": "Blok diyagram yerleşimi",
    "Block diagram (details not available)": "Blok diyagram (ayrıntı yok)",
    "Typedef update": "Typedef güncellemesi",
    "Front panel controls": "Ön panel kontrolleri",
    "Front panel appearance": "Ön panel görünümü",
    "Front panel layout": "Ön panel yerleşimi",
    "Front panel (control properties/appearance)": "Ön panel (kontrol özellikleri/görünüm)",
    "Connector pane": "Konnektör paneli",
    "Dependencies": "Bağımlılıklar",
    "VI properties": "VI özellikleri",
    "Other VI settings": "Diğer VI ayarları",
    "Default values / data space": "Varsayılan değerler / veri alanı",
    "Icon": "İkon",
    "VI description": "VI açıklaması",
    "LabVIEW version": "LabVIEW sürümü",
    "New file": "Yeni dosya",
    "File deleted": "Dosya silindi",
    "Timed Loop / XNode internal setting": "Timed Loop / XNode iç ayarı",
    # VI property names
    "Reentrant": "Reentrant", "Priority": "Öncelik", "Preferred execution system": "Tercih edilen yürütme sistemi",
    "Subroutine": "Subroutine", "Run when opened": "Açılınca çalıştır", "Show front panel when called": "Çağrılınca ön paneli göster",
    "Close afterwards if originally closed": "Başta kapalıysa sonra kapat", "Allow debugging": "Hata ayıklamaya izin ver",
    "Inline": "Inline", "Automatic error handling": "Otomatik hata işleme", "Shared clone reentrancy": "Paylaşılan klon reentrancy",
    "Password protection": "Parola koruması", "Scroll bars": "Kaydırma çubukları", "Title bar": "Başlık çubuğu",
    "Menu bar": "Menü çubuğu", "Auto center": "Otomatik ortala",
}

_KIND_TR = [  # "<Kind> “" at the start of a title
    ("Local variable “", "Yerel değişken “"),
    ("Global variable “", "Global değişken “"),
    ("Constant “", "Sabit “"),
    ("Structure “", "Yapı “"),
    ("Node “", "Düğüm “"),
]

# whole-string or phrase rules, applied in order (regex, replacement)
_RULES_TR = [
    # change titles: the verb follows the closing quote of the name (or the variable's owner)
    (r"(”(?: \([^)]*\))?) moved into another structure/frame", r"\1 başka bir yapıya/çerçeveye taşındı"),
    (r"(”(?: \([^)]*\))?) text format changed", r"\1 yazı biçimi değişti"),
    (r"(”(?: \([^)]*\))?) modified", r"\1 değişti"),
    (r"(”(?: \([^)]*\))?) added", r"\1 eklendi"),
    (r"(”(?: \([^)]*\))?) removed", r"\1 silindi"),
    (r"(”(?: \([^)]*\))?) resized", r"\1 yeniden boyutlandırıldı"),
    (r"(”(?: \([^)]*\))?) moved", r"\1 taşındı"),
    (r"(”) \(text format\)", r"\1 (yazı biçimi)"),
    (r"^Wire data type changed$", "Tel veri tipi değişti"),
    (r"^Wire removed$", "Tel silindi"),
    (r"^Wire added$", "Tel eklendi"),
    (r"^Comment removed$", "Yorum silindi"),
    (r"^Comment added$", "Yorum eklendi"),
    # details
    (r"\bvalue changed\b", "değer değişti"),
    (r"\bvalue (.+?) → ", r"değer \1 → "),
    (r"\bterminal count (\d+) → (\d+)", r"terminal sayısı \1 → \2"),
    (r"\bframe added: ", "çerçeve eklendi: "),
    (r"\bframe removed: ", "çerçeve silindi: "),
    (r"\bframe order changed\b", "çerçeve sırası değişti"),
    (r"^type (.+) → ", r"tip \1 → "),
    (r"; type (.+?) → ", r"; tip \1 → "),
    (r"\bsetting/property changed\b", "ayar/özellik değişti"),
    (r"\bread → write\b", "okuma → yazma"),
    (r"\bwrite → read\b", "yazma → okuma"),
    (r"\bcontrol → indicator\b", "kontrol → gösterge"),
    (r"\bindicator → control\b", "gösterge → kontrol"),
    (r"\bmoved to another structure/frame\b", "başka bir yapıya/çerçeveye taşındı"),
    (r"internal setting changed \(may have been regenerated by LabVIEW\)", "iç ayar değişti (LabVIEW tarafından yeniden üretilmiş olabilir)"),
    (r"^position \(", "konum ("),
    (r"text/label display \(justification, font, style or label visibility\)",
     "yazı/etiket görünümü (hizalama, yazı tipi, stil veya etiket görünürlüğü)"),
    (r"\bkeyboard shortcut ([^→]+?) → (.+?)(?=\s*(?:\||;|·|$))",
     lambda m: "klavye kısayolu %s → %s" % tuple("yok" if x.strip() == "none" else x for x in (m.group(1), m.group(2)))),
    (r"\btypedef contents updated\b", "typedef içeriği güncellendi"),
    (r"\bappearance/property changed\b", "görünüm/özellik değişti"),
    (r" control (added|removed)$", lambda m: " kontrol " + ("eklendi" if m.group(1) == "added" else "silindi")),
    (r" indicator (added|removed)$", lambda m: " gösterge " + ("eklendi" if m.group(1) == "added" else "silindi")),
    # verdict details
    (r"^placement / wire routing / colors$", "yerleşim / tel yolları / renkler"),
    (r"^placement / wire routing$", "yerleşim / tel yolları"),
    (r"^placement / decorations$", "yerleşim / süslemeler"),
    (r"^(\d+) comment\(s\) added/removed$", r"\1 yorum eklendi/silindi"),
    (r"^(\d+) item\(s\) moved/resized/reformatted: ", r"\1 öğe taşındı/boyutlandı/biçimlendi: "),
    (r"^(\d+) item\(s\) moved/resized: ", r"\1 öğe taşındı/boyutlandı: "),
    (r"^(\d+) item\(s\): ", r"\1 öğe: "),
    (r"^moved/resized: ", "taşındı/boyutlandı: "),
    (r"(\d+) wire\(s\)", r"\1 tel"),
    (r"^e\.g\. property node item, label visibility, structure setting$", "ör. property node öğesi, etiket görünürlüğü, yapı ayarı"),
    (r" — source \.ctl changed, VI re-saved$", " — kaynak .ctl değişti, VI yeniden kaydedildi"),
    (r"\bpattern changed\b", "desen değişti"),
]
_RULES_TR = [(re.compile(p), r) for p, r in _RULES_TR]


def engine_text(text, lang):
    """Translates one string produced by the diff engine."""
    if lang != "tr" or not text:
        return text
    if text in _LABELS_TR:
        return _LABELS_TR[text]
    if text in TR:
        return TR[text]
    out = text
    for a, b in _KIND_TR:
        out = out.replace(a, b)
    for rx, rep in _RULES_TR:
        out = rx.sub(rep, out)
    return out


def localize_summary(summary, lang):
    if lang != "tr":
        return summary
    for p in summary.get("parts", []):
        p["label"] = engine_text(p.get("label"), lang)
        p["detail"] = engine_text(p.get("detail"), lang)
    return summary


def localize_diff(d, lang):
    """d = {"old", "new", "diff"} as returned by VIService.diff (a copy; it is changed in place)."""
    if lang != "tr":
        return d
    r = d["diff"]
    for c in r.get("changes", []):
        c["title"] = engine_text(c.get("title"), lang)
        c["detail"] = engine_text(c.get("detail"), lang)
    for c in r.get("fp", []):
        c["detail"] = engine_text(c.get("detail"), lang)
    for p in r.get("props", []):
        p["label"] = engine_text(p.get("label"), lang)
    v = r.get("verdict")
    if v:
        for p in v.get("parts", []):
            p["label"] = engine_text(p.get("label"), lang)
            p["detail"] = engine_text(p.get("detail"), lang)
    return d


# ======================================================================= report / export markdown
_REPORT_TR = [  # (English, Turkish) fixed sentences of the report generator, longest first where they overlap
    ("_Details and images are below; click a VI name to jump to its section._",
     "_Ayrıntılar ve resimler aşağıda; bölümüne gitmek için VI adına tıklayın._"),
    ("Changed items are marked with numbered boxes in the images: 🟩 added, 🟥 removed, 🟧 modified, 🟪 only moved into another structure/frame",
     "Değişen öğeler resimlerde numaralı kutularla işaretlidir: 🟩 eklendi, 🟥 silindi, 🟧 değişti, 🟪 sadece başka bir yapıya/çerçeveye taşındı"),
    (", 🟦 moved.", ", 🟦 taşındı."),
    ("Unchanged parts are dimmed. The numbers match the lists below.", "Değişmeyen kısımlar soluk gösterilir. Numaralar aşağıdaki listelerle eşleşir."),
    ("_The image is an SVG: click to open it full size; it stays sharp when you zoom in the browser._",
     "_Resim SVG'dir: tam boyut açmak için tıklayın; tarayıcıda yakınlaştırınca netliği bozulmaz._"),
    ("**Block diagrams of A and B** _(no block diagram changes to mark)_", "**A ve B blok diyagramları** _(işaretlenecek blok diyagram değişikliği yok)_"),
    ("**Block diagram — previous and new version**", "**Blok diyagram — A ve B**"),
    ("**Block diagram layout changes**", "**Blok diyagram yerleşim değişiklikleri**"),
    ("**Block diagram changes**", "**Blok diyagram değişiklikleri**"),
    ("VI(s) — changes only in categories that were not selected", "VI — değişiklikler sadece seçilmeyen kategorilerde"),
    ("VI(s) — content unchanged (revision / compiled code / internal numbers)", "VI — içerik aynı (revizyon / derlenmiş kod / iç numaralar)"),
    ("| VIs with visual/layout changes only |", "| Sadece görsel/yerleşim değişikliği olan VI'lar |"),
    ("| VIs with content changes |", "| İçeriği değişen VI'lar |"),
    ("| VIs re-saved only |", "| Sadece yeniden kaydedilmiş VI'lar |"),
    ("| VIs out of scope |", "| Kapsam dışındaki VI'lar |"),
    ("| Unreadable VIs |", "| Okunamayan VI'lar |"),
    ("| Other file changes |", "| Diğer dosya değişiklikleri |"),
    ("| | Count |", "| | Sayı |"),
    ("| VI | Status | What changed |", "| VI | Durum | Ne değişti |"),
    ("## Summary", "## Özet"),
    ("### Changed VIs", "### Değişen VI'lar"),
    ("## VIs with content changes", "## İçeriği değişen VI'lar"),
    ("## Visual/layout changes", "## Görsel/yerleşim değişiklikleri"),
    ("## Unreadable VIs", "## Okunamayan VI'lar"),
    ("## VIs out of scope", "## Kapsam dışındaki VI'lar"),
    ("## VIs re-saved only", "## Sadece yeniden kaydedilmiş VI'lar"),
    ("## Other files", "## Diğer dosyalar"),
    ("🟧 Modified (layout)", "🟧 Değişti (yerleşim)"),
    ("🟧 Modified", "🟧 Değişti"),
    ("🟩 New", "🟩 Yeni"),
    ("🟥 Deleted", "🟥 Silindi"),
    ("` · New VI", "` · Yeni VI"),
    ("` · Deleted VI", "` · Silinen VI"),
    ("` · Modified", "` · Değişti"),
    (" top-level items on the block diagram)", " üst düzey öğe)"),
    ("New VI added", "Yeni VI eklendi"),
    ("VI deleted", "VI silindi"),
    ("Details below", "Ayrıntılar aşağıda"),
    (" item(s) moved/resized", " öğe taşındı/boyutlandı"),
    (") — moved/renamed", ") — taşındı/yeniden adlandırıldı"),
    (" (moved/renamed)", " (taşındı/yeniden adlandırıldı)"),
    ("` — added (", "` — eklendi ("),
    ("` — deleted (", "` — silindi ("),
    ("` — modified (", "` — değişti ("),
    (" more lines)", " satır daha)"),
    ("_View ", "_Görünüm "),
    ("_Detail ", "_Detay "),
    (" · change ", " · değişiklik "),
    ("previous: ", "A: "),
    ("new: ", "B: "),
    ("Wire data type changed", "Tel veri tipi değişti"),
    ("Wire removed", "Tel silindi"),
    ("Wire added", "Tel eklendi"),
    ("Comment removed", "Yorum silindi"),
    ("Comment added", "Yorum eklendi"),
    ("> ⚠ Could not render an image for this VI", "> ⚠ Bu VI için resim çizilemedi"),
    ("The list of changes is above.", "Değişiklik listesi yukarıda."),
]


def report_markdown(md, lang):
    """Translates the Markdown written by the report generator (engine/changelog.py)."""
    if lang != "tr" or not md:
        return md
    for en, tr in _REPORT_TR:
        md = md.replace(en, tr)
    # part labels: "**Label**" and "Label: …"
    for en in sorted(_LABELS_TR, key=len, reverse=True):
        tr = _LABELS_TR[en]
        md = md.replace("**%s**" % en, "**%s**" % tr).replace("%s: " % en, "%s: " % tr)
    for en in ("Block diagram logic", "Block diagram layout", "Front panel", "Timed Loop / XNode internal settings",
               "Other (icon, description, settings)", "Re-saved only"):
        md = md.replace(en, TR.get(en, en))
    # change titles and details inside the lines
    for a, b in _KIND_TR:
        md = md.replace(a, b)
    lines = []
    for line in md.split("\n"):
        for rx, rep in _RULES_TR:
            if rx.pattern.startswith("^"):
                continue
            line = rx.sub(rep, line)
        lines.append(line)
    md = "\n".join(lines)
    for rx, rep in ((r"placement / wire routing / colors", "yerleşim / tel yolları / renkler"),
                    (r"placement / wire routing", "yerleşim / tel yolları"), (r"placement / decorations", "yerleşim / süslemeler"),
                    (r"moved/resized: ", "taşındı/boyutlandı: "), (r"(\d+) item\(s\) moved/resized/reformatted: ", r"\1 öğe taşındı/boyutlandı/biçimlendi: "),
                    (r"(\d+) comment\(s\) added/removed", r"\1 yorum eklendi/silindi"),
                    (r"e\.g\. property node item, label visibility, structure setting", "ör. property node öğesi, etiket görünürlüğü, yapı ayarı")):
        md = re.sub(rx, rep, md)
    return md


REPORT_HEAD = {
    "en": "# viCheck comparison report\n\n**A:** `{a}`  \n**B:** `{b}`  \n**Generated:** {now} · viCheck {ver}  \n**Scope:** {scope}\n\n",
    "tr": "# viCheck karşılaştırma raporu\n\n**A:** `{a}`  \n**B:** `{b}`  \n**Oluşturulma:** {now} · viCheck {ver}  \n**Kapsam:** {scope}\n\n",
}
