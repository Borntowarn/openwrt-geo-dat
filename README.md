# openwrt-geo-dat

Ежедневная сборка урезанных `geosite.dat` и `geoip.dat` из [runetfreedom/russia-v2ray-rules-dat](https://github.com/runetfreedom/russia-v2ray-rules-dat).

Стек: чистый **Python 3** (stdlib), без Go и bash-пайплайна. Сборка и публикация — через GitHub Actions.

## Скачать

- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite.dat
- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip.dat
- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-txt.zip
- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-txt.zip

## Категории

Список задаётся в `.github/workflows/build.yml` (`env`), по одной категории на строку:

```yaml
GEOSITE_CATEGORIES: |
  category-ads-all
  youtube
GEOIP_CATEGORIES: |
  ru
  private
```

Пустой список или несуществующая категория валят сборку.

## Запуск

- Автоматически раз в сутки (cron в workflow)
- Вручную: **Actions** → **Build filtered geo dat** → **Run workflow**

Локально:

```bash
python build_release.py \
  --upstream runetfreedom/russia-v2ray-rules-dat \
  --geosite-categories "category-ads-all,youtube" \
  --geoip-categories "ru,private" \
  --download-dir .tmp/upstream \
  --out-dir out
```

## Тесты

```bash
python -m unittest discover -s . -p "test_*.py"
```

## Файлы

- `geosite_tool.py` — list / extract / build / filter для `geosite.dat`
- `geoip_tool.py` — то же для `geoip.dat`
- `build_release.py` — download upstream, filter, zip, sha256
- `.github/workflows/build.yml` — ежедневный релиз
