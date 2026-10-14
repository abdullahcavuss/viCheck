# viCheck test VI'ları

> **Dosyalar repoda yok.** VI'lar JKI State Machine projesine ait (BSD lisansı), bu yüzden viCheck reposunda
> dağıtılmıyor. Oluşturmak için proje klasöründe: `python tools/make_testdata.py` (git gerekir). Betik JKI deposunu
> indirip aşağıdaki klasörleri her seferinde aynı içerikle kurar.

Gerçek LabVIEW VI'ları: açık kaynak **JKI State Machine** projesinin (BSD lisansı, bkz. `LICENSE-JKI-State-Machine.txt`) git geçmişindeki farklı sürümler. Hepsi LabVIEW 2020 ile kaydedilmiş.

## İki VI karşılaştırma — `vi-pairs\`

Her klasörde `A\` (eski) ve `B\` (yeni) altında aynı adlı bir VI var. viCheck'te A için `A\...vi`, B için `B\...vi` seçin.

| Klasör | Ne değişti | viCheck'in beklenen sonucu |
|---|---|---|
| `01_diagram-disable-to-case-structure` | Bir Diagram Disable yapısı Case Structure ile değiştirildi, içindeki subVI ve sabitler yeni yapıya taşındı | **Content changed** — +2 −1 ~3, 5 tel, “moved into another frame” (mor) |
| `02_text-justification-only` | Bir sabitin yazısı sola hizalandı | **Visual/layout** — `Constant “State” text format changed` |
| `03_comment-change` | Bir diyagram yorumunun metni değişti | **Visual/layout** — sadece yorum eklendi/silindi |
| `04_subvi-added-and-reentrant` | Yeni subVI bağımlılığı, reentrant ayarı, yerleşim | **Content changed** — Dependencies, VI properties |

## İki klasör karşılaştırma — `folders\`

`folders\A` ve `folders\B`: kütüphanenin `source` klasörünün iki sürümü (çoğu VI sadece yerleşim değişikliği). Ek olarak:

- `Random String.vi` sadece A'da → *only in A*
- `SimulateButtonPress.vi` ve `notes.txt` sadece B'de → *only in B*

Beklenen: 14 farklı dosya; 3 VI içerik değişikliği — `Periodic State String.vi`, `Periodic Trigger__ogtk__JKI-SM.vi` ve şablon VI'da **“Exit”: keyboard shortcut Esc → none**; diğerleri görsel/yerleşim; aynı dosyalar katlanmış listede.
