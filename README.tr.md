# siyak-data

[English](README.md) · İngilizce sürümle son eşitleme: 2026-10-21 (ilk sürüm)

Ücretsiz ve açık kaynak Kur'an araştırma aracı [Siyak](https://github.com/siyak/siyak)'ın
veri hattı. Uygulamanın birlikte dağıttığı ve indirdiği içeriği üretir:

- **`core.db`**: kurulum dosyasıyla gelir: Tanzil Kur'an metni (Osmanî ve
  sade/harekesiz), sure bilgileri ve birlikte gelen mealler;
- **paketler**: uygulamanın Paketler ekranından indirilen mealler (sonraki
  aşamalarda tefsir ve morfoloji);
- **`manifest.json`** ve **`pricing.json`**: paketleri ve yapay zekâ model fiyatlarını tanımlar.

Kod: `MIT OR Apache-2.0`. **Veriler kendi lisanslarını korur**:
[docs/sources.md](docs/sources.md) ve `sources/*/LICENSE`.

## Hızlı başlangıç

Python ≥ 3.12 ve [uv](https://docs.astral.sh/uv/) gerekir.

```sh
uv sync
uv run siyak-data fetch      # sabitlenmiş kaynakları .cache/ içine indir (sha256 kontrollü)
uv run siyak-data build      # dist/core.db ve dist/<paket>.sqlite üret
uv run siyak-data validate   # doğrulama kapılarını çalıştır
uv run siyak-data manifest   # dist/manifest.json ve dist/pricing.json yaz
```

İnternet olmadan, depodaki test verileriyle:

```sh
uv run siyak-data build --profile fixtures
uv run siyak-data validate --profile fixtures
```

`uv run siyak-data check-updates`, kaynakların güncel hâlini sabitlenmiş sürümle karşılaştırır.

## Nasıl çalışır

- **Kaynaklar sabitlenir.** Her kaynak `sources/<…>/source.toml` ile tanımlanır:
  indirme adresi, sürüm, beklenen sha256, lisans, atıf. İndirilen dosyalar
  `.cache/` içinde durur (git'e girmez); bir dosyanın özeti sabitlenen değerden
  farklıysa `fetch` ve `build` durur. Test için kullanılan küçük, birebir alıntılar
  dışında üçüncü taraf veri depoya konmaz (`tests/fixtures/README.md`).
- **Kaynak metin asla değiştirilmez.** Dönüştürme yalnızca biçimi değiştirir.
- **Doğrulama kapıları** (114 sure, 6.236 ayet, kesintisiz ayet numaraları, eksiksiz
  mealler, harekesiz metinde işaret olmaması, kurulabilirlik…) hatalı bir sürümü,
  sorunlu ayeti veya tabloyu belirterek durdurur.
- **Tekrarlanabilir derleme:** aynı girdiler ve `SOURCE_DATE_EPOCH` ile her dosya
  bayt bayt aynıdır.

## Belgeler

| Belge | İçerik |
|---|---|
| [docs/pack-format.md](docs/pack-format.md) | Paket ve manifest biçimi, kurulum kuralları, sürümler (İngilizce) |
| [docs/normalization.md](docs/normalization.md) | Arapça arama normalizasyon kuralları (uygulamayla ortak, İngilizce) |
| [docs/sources.md](docs/sources.md) | Tüm kaynaklar: sürüm, lisans, atıf (İngilizce) |
| [docs/adding-a-source.md](docs/adding-a-source.md) | Meal veya tefsir ekleme rehberi ve lisans kontrol listesi (İngilizce) |
| [CONTRIBUTING.tr.md](CONTRIBUTING.tr.md) | Geliştirme ortamı ve çalışma düzeni |

## Sürümler

`data-YYYY.MM.N` etiketi gönderildiğinde `.github/workflows/data-release.yml` çalışır:
indir → derle → doğrula → `SHA256SUMS` → manifest ve fiyatlar → GitHub sürümü.
Uygulama manifesti `https://quran.kemalozyon.com/data/manifest.json` adresinden,
yedek olarak `https://github.com/siyak/siyak-data/releases/latest/download/manifest.json`
adresinden okur.
