# openwrt-geo-dat

Ежедневная сборка урезанных `geosite.dat` / `geoip.dat` и бинарных rule-set (`.srs`) для **sing-box / HomeProxy** из [runetfreedom/russia-v2ray-rules-dat](https://github.com/runetfreedom/russia-v2ray-rules-dat).

Стек: чистый **Python 3** (stdlib) + `sing-box rule-set compile` в CI. Сборка и публикация — через GitHub Actions.

## Скачать

### Классика (v2ray / совместимость)

- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite.dat
- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip.dat
- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-txt.zip
- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-txt.zip

### sing-box rule-set (`.srs`)

Архив со всеми файлами:

- https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/sing-box-srs.zip

Примеры прямых URL для remote Rule Set в HomeProxy (`format: binary`, `type: remote`, `update_interval` по желанию):

| Назначение | URL |
|---|---|
| Ads (block) | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-category-ads-all.srs` |
| YouTube | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-youtube.srs` |
| OpenAI | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-openai.srs` |
| Meta | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-meta.srs` |
| TikTok | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-tiktok.srs` |
| Facebook | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-facebook.srs` |
| Telegram | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-telegram.srs` |
| Discord | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geosite-discord.srs` |
| GeoIP Telegram | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-telegram.srs` |
| GeoIP Facebook | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-facebook.srs` |
| GeoIP Twitter | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-twitter.srs` |
| GeoIP RU | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-ru.srs` |
| GeoIP private | `https://github.com/Borntowarn/openwrt-geo-dat/releases/latest/download/geoip-private.srs` |

Шаблон имени: `geosite-<category>.srs` / `geoip-<category>.srs` (категория в нижнем регистре).

### HomeProxy (Custom)

1. **Routing mode** → Custom, default outbound → Direct.
2. **Rule Set** → добавить remote binary URL из таблицы выше.
3. **Rules**: ads → reject/block; нужные списки → proxy (urltest/группа); остальное → direct.

Конвертация `.dat` → JSON на роутере больше не нужна.

## Категории

`category-ads-all` дополнительно объединяется с [Yularzhi/geosite_russia](https://github.com/Yularzhi/geosite_russia) (`ADS_MERGE_URL` / `ADS_MERGE_CATEGORY` в workflow).

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
# нужен sing-box в PATH (для .srs)
python build_release.py \
  --upstream runetfreedom/russia-v2ray-rules-dat \
  --geosite-categories "category-ads-all,youtube" \
  --geoip-categories "ru,private" \
  --download-dir .tmp/upstream \
  --out-dir out

# только dat/txt + JSON, без compile:
python build_release.py ... --skip-srs-compile
```

## Тесты

```bash
python -m unittest discover -s . -p "test_*.py"
```

## Файлы

- `geosite_tool.py` — list / extract / build / filter для `geosite.dat`
- `geoip_tool.py` — то же для `geoip.dat`
- `srs_tool.py` — JSON rule-set + `sing-box rule-set compile` → `.srs`
- `build_release.py` — download upstream, filter, zip, sha256, srs
- `.github/workflows/build.yml` — ежедневный релиз
