import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import requests

import bjc


def _now_cn_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _http_get_text(url, *, timeout=8, headers=None):
    h = {
        "User-Agent": "north-america-watch/1.0 (+https://223.78.73.100:8000)",
        "Accept": "*/*",
    }
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    r.encoding = r.encoding or "utf-8"
    return r.text


def _http_get_json(url, *, timeout=10, headers=None):
    h = {
        "User-Agent": "north-america-watch/1.0 (+https://223.78.73.100:8000)",
        "Accept": "application/json",
    }
    if headers:
        h.update(headers)
    r = requests.get(url, headers=h, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _parse_rss_items(xml_text, limit=10):
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return []
    channel = root.find("channel")
    if channel is None:
        channel = root
    items = []
    for item in channel.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        if not title or not link:
            continue
        items.append({"title": title, "link": link, "pubDate": pub_date})
        if len(items) >= limit:
            break
    return items


def _google_news_rss(query, *, gl="US", hl="en-US", ceid="US:en", limit=8, when="7d"):
    q = f"{query} when:{when}"
    url = f"https://news.google.com/rss/search?q={quote_plus(q)}&hl={hl}&gl={gl}&ceid={ceid}"
    xml_text = _http_get_text(url, timeout=12)
    return _parse_rss_items(xml_text, limit=limit)


def _gdelt_doc(query, *, maxrecords=10, hours=24):
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(hours=hours)
    start_s = start_dt.strftime("%Y%m%d%H%M%S")
    url = (
        "https://api.gdeltproject.org/api/v2/doc/doc?"
        f"query={quote_plus(query)}&mode=ArtList&format=json&maxrecords={int(maxrecords)}&sort=HybridRel"
        f"&startdatetime={start_s}"
    )
    data = _http_get_json(url, timeout=10)
    arts = data.get("articles") or []
    out = []
    for a in arts:
        title = str(a.get("title") or "").strip()
        link = str(a.get("url") or "").strip()
        source = str(a.get("sourceCountry") or a.get("source") or "").strip()
        seendate = str(a.get("seendate") or "").strip()
        if not title or not link:
            continue
        out.append({"title": title, "link": link, "source": source, "seendate": seendate})
    return out


def _nws_active_alerts(area="US", limit=10):
    url = f"https://api.weather.gov/alerts/active?area={quote_plus(area)}"
    data = _http_get_json(url, timeout=10, headers={"Accept": "application/geo+json"})
    feats = data.get("features") or []
    out = []
    for f in feats:
        p = f.get("properties") or {}
        headline = str(p.get("headline") or "").strip()
        event = str(p.get("event") or "").strip()
        severity = str(p.get("severity") or "").strip()
        urgency = str(p.get("urgency") or "").strip()
        area_desc = str(p.get("areaDesc") or "").strip()
        link = str(p.get("web") or "").strip()
        if not link:
            link = str(p.get("id") or "").strip()
        if not (headline or event) or not link:
            continue
        title = headline or event
        out.append(
            {
                "title": title,
                "link": link,
                "severity": severity,
                "urgency": urgency,
                "area": area_desc,
            }
        )
        if len(out) >= limit:
            break
    return out


def _fetch_holidays_ics(ics_url, *, days_ahead=45):
    text = _http_get_text(ics_url, timeout=10)
    now = datetime.now(timezone.utc)
    end = now + timedelta(days=days_ahead)
    events = []
    cur = {}
    in_event = False
    for raw in text.splitlines():
        line = raw.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
            cur = {}
            continue
        if line == "END:VEVENT":
            in_event = False
            dtstart = cur.get("DTSTART") or ""
            summary = cur.get("SUMMARY") or ""
            if dtstart and summary:
                dt = None
                for fmt in ("%Y%m%d", "%Y%m%dT%H%M%SZ"):
                    try:
                        dt = datetime.strptime(dtstart, fmt).replace(tzinfo=timezone.utc)
                        break
                    except Exception:
                        dt = None
                if dt and (now <= dt <= end):
                    events.append({"date": dt.strftime("%Y-%m-%d"), "name": summary})
            cur = {}
            continue
        if not in_event or ":" not in line:
            continue
        k, v = line.split(":", 1)
        k0 = k.split(";", 1)[0]
        if k0 in {"DTSTART", "SUMMARY"}:
            cur[k0] = v.strip()
    events.sort(key=lambda x: x.get("date") or "")
    return events


def build_report(max_items_each=6):
    sections = []

    weather_items = []
    try:
        weather_items.extend(_nws_active_alerts("US", limit=max_items_each))
    except Exception:
        weather_items = []
    if not weather_items:
        try:
            weather_items = _google_news_rss("extreme weather United States Canada", limit=max_items_each, when="3d")
        except Exception:
            weather_items = []

    unrest_items = []
    try:
        q = "(protest OR riot OR strike) (sourceCountry:US OR sourceCountry:CA)"
        unrest_items = _gdelt_doc(q, maxrecords=max_items_each, hours=36)
    except Exception:
        unrest_items = []
    if not unrest_items:
        try:
            unrest_items = _google_news_rss("protest OR riot OR strike US Canada", limit=max_items_each, when="3d")
        except Exception:
            unrest_items = []

    holiday_items = []
    try:
        us_ics = "https://calendar.google.com/calendar/ical/en.usa%23holiday%40group.v.calendar.google.com/public/basic.ics"
        ca_ics = "https://calendar.google.com/calendar/ical/en.canadian%23holiday%40group.v.calendar.google.com/public/basic.ics"
        holiday_items = _fetch_holidays_ics(us_ics, days_ahead=45) + _fetch_holidays_ics(ca_ics, days_ahead=45)
        seen = set()
        dedup = []
        for it in holiday_items:
            key = (it.get("date"), it.get("name"))
            if key in seen:
                continue
            seen.add(key)
            dedup.append(it)
        holiday_items = dedup
    except Exception:
        holiday_items = []

    deal_items = []
    try:
        deal_items = _google_news_rss(
            '(Walmart OR Costco OR CVS OR Target OR Walgreens OR "Trader Joe\'s") (sale OR deal OR promotion OR clearance)',
            limit=max_items_each,
            when="7d",
        )
    except Exception:
        deal_items = []

    money_items = []
    try:
        money_items = _google_news_rss(
            "(tax refund OR tax rate OR IRS OR interest rate OR inflation OR tariff) (US OR Canada)",
            limit=max_items_each,
            when="7d",
        )
    except Exception:
        money_items = []

    def fmt_list(items, kind):
        if not items:
            return ["- 暂无可用结果"]
        lines = []
        if kind == "nws":
            for i, it in enumerate(items, 1):
                title = it.get("title") or ""
                link = it.get("link") or ""
                sev = it.get("severity") or ""
                urg = it.get("urgency") or ""
                area = it.get("area") or ""
                meta = " / ".join([x for x in [sev, urg, area] if x])
                if meta:
                    lines.append(f"- {i}. {title}（{meta}）\n  {link}")
                else:
                    lines.append(f"- {i}. {title}\n  {link}")
            return lines
        if kind == "gdelt":
            for i, it in enumerate(items, 1):
                title = it.get("title") or ""
                link = it.get("link") or ""
                source = it.get("source") or ""
                seendate = it.get("seendate") or ""
                meta = " / ".join([x for x in [source, seendate] if x])
                if meta:
                    lines.append(f"- {i}. {title}（{meta}）\n  {link}")
                else:
                    lines.append(f"- {i}. {title}\n  {link}")
            return lines
        if kind == "holiday":
            for i, it in enumerate(items[:max_items_each], 1):
                lines.append(f"- {i}. {it.get('date')} - {it.get('name')}")
            lines.append("- 来源：Google Public Holidays (ICS)")
            return lines
        for i, it in enumerate(items, 1):
            title = it.get("title") or ""
            link = it.get("link") or ""
            pub = it.get("pubDate") or ""
            if pub:
                lines.append(f"- {i}. {title}（{pub}）\n  {link}")
            else:
                lines.append(f"- {i}. {title}\n  {link}")
        return lines

    sections.append(("极端天气", fmt_list(weather_items, "nws" if weather_items and isinstance(weather_items[0], dict) and "severity" in weather_items[0] else "rss")))
    sections.append(("社会动荡（游行/暴动/罢工）", fmt_list(unrest_items, "gdelt" if unrest_items and isinstance(unrest_items[0], dict) and "seendate" in unrest_items[0] else "rss")))
    sections.append(("节假日（未来45天）", fmt_list(holiday_items, "holiday")))
    sections.append(("线下零售/美妆店大折扣促销", fmt_list(deal_items, "rss")))
    sections.append(("跟钱有关的新闻（退税/税率/利率等）", fmt_list(money_items, "rss")))

    lines = [f"北美资讯汇总（{_now_cn_str()}）"]
    for title, body_lines in sections:
        lines.append("")
        lines.append(f"【{title}】")
        lines.extend(body_lines)
    return "\n".join(lines).strip()


def _split_message(text, max_len=3500):
    t = str(text or "")
    if len(t) <= max_len:
        return [t]
    parts = []
    buf = []
    cur = 0
    for line in t.splitlines():
        add = len(line) + 1
        if cur + add > max_len and buf:
            parts.append("\n".join(buf).strip())
            buf = []
            cur = 0
        buf.append(line)
        cur += add
    if buf:
        parts.append("\n".join(buf).strip())
    return [p for p in parts if p]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--to", default="周俊成")
    ap.add_argument("--max-items", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    report = build_report(max_items_each=max(1, int(args.max_items)))
    parts = _split_message(report, max_len=3500)

    if args.dry_run:
        sys.stdout.write("DRY_RUN\n")
        for i, p in enumerate(parts, 1):
            sys.stdout.write(p + ("\n\n" if i < len(parts) else "\n"))
        sys.stdout.write("DRY_RUN_END\n")
        return 0

    ok_all = True
    for p in parts:
        ok = bjc.send_message(args.to, p)
        ok_all = ok_all and bool(ok)
    return 0 if ok_all else 2


if __name__ == "__main__":
    raise SystemExit(main())
