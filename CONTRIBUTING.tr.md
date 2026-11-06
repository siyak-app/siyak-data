# siyak-data'ya katkı

[English](CONTRIBUTING.md) · İngilizce sürümle son eşitleme: 2026-10-21 (ilk sürüm)

Yardımınız için teşekkürler. Kod yazmadan da katkı verebilirsiniz: kaynak
önermek (lisans araştırmasıyla), Türkçe sure adlarını gözden geçirmek veya bir
veri hatası bildirmek çok değerlidir. Sorun (issue) formlarını kullanın.

## Kurulum

```sh
uv sync                                    # Python ≥ 3.12, geliştirme araçları dahil
uv run siyak-data build --profile fixtures # internetsiz çalışır
uv run pytest
```

Tam derleme: `uv run siyak-data fetch && uv run siyak-data build && uv run siyak-data validate`.

## Kontroller (CI aynılarını çalıştırır)

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy            # pipeline/ için --strict
uv run pytest
```

Kontrolleri geçmeyen bir PR açmayın.

## Kurallar

- Kod, yorum, commit mesajı, PR ve belgelerde **yalnızca İngilizce**
  (`*.tr.md` dosyaları hariç).
- **Kaynak içerik asla değiştirilmez.** Dönüştürme yalnızca biçimi değiştirir.
  Kaynakta hata varsa kaynağa bildirin; düzeltmeyi kendiniz uygulamayın.
- **Üçüncü taraf veri git'e girmez**; yalnızca kaynağın şartlarının izin verdiği
  küçük, birebir test alıntıları (bkz. `tests/fixtures/README.md`).
- **Sabitlenen özetler gözden geçirilir.** `source.toml` içindeki yeni veya
  değişen her sha256, dosyayı kontrol eden bir gözden geçirici gerektirir.
- **Normalizasyon uygulamayla bir sözleşmedir**: kural değişiklikleri
  `docs/normalization.md` → "Changing the rules" adımlarını izler.
- **Yeni kaynaklar** lisans kontrol listesi dahil
  [docs/adding-a-source.md](docs/adding-a-source.md) rehberini izler.

## Commit ve PR

- [Conventional Commits](https://www.conventionalcommits.org/):
  `feat:`, `fix:`, `docs:`, `test:`, `build:`, `ci:`, `refactor:`, `chore:`.
- PR başına tek mantıksal değişiklik; neyin neden değiştiğini ve nasıl test
  ettiğinizi yazın.
- Veri değişiklikleri: hangi paketlerin değiştiğini belirtin ve
  `[pack].version` değerini artırın (`docs/pack-format.md` §5).

## Dizin yapısı

| Yol | İçerik |
|---|---|
| `pipeline/` | `siyak-data` komutunun Python paketi |
| `schema/content.sql` | paketlerin uyması gereken içerik veritabanı şeması |
| `sources/` | kaynak başına bir dizin: `source.toml`, `README.md`, `LICENSE`, `NOTICE` |
| `data/` | elle yazılmış küçük veriler (Türkçe sure adları, fiyatlar, anlamsal değerlendirme seti `eval/semantic.toml`) |
| `tests/` | testler, ortak normalizasyon vektörleri, test verileri |
| `docs/` | biçim ve süreç belgeleri |
