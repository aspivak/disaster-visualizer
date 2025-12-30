import argparse
import json
import logging
import asyncio
import aiohttp
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from shapely.geometry import shape, Polygon, Point, MultiPolygon
from shapely.wkt import dumps as wkt_dumps
import time
import re
from pathlib import Path
from collections import defaultdict

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# MeteoAlarm country mapping
COUNTRY_MAP = {
    'at': 'austria',
    'be': 'belgium',
    'ba': 'bosnia-herzegovina',
    'bg': 'bulgaria',
    'hr': 'croatia',
    'cy': 'cyprus',
    'cz': 'czech-republic',
    'dk': 'denmark',
    'ee': 'estonia',
    'fi': 'finland',
    'fr': 'france',
    'de': 'germany',
    'gr': 'greece',
    'hu': 'hungary',
    'is': 'iceland',
    'ie': 'ireland',
    'it': 'italy',
    'lv': 'latvia',
    'lt': 'lithuania',
    'lu': 'luxembourg',
    'mt': 'malta',
    'md': 'moldova',
    'me': 'montenegro',
    'nl': 'netherlands',
    'mk': 'north-macedonia',
    'no': 'norway',
    'pl': 'poland',
    'pt': 'portugal',
    'ro': 'romania',
    'rs': 'serbia',
    'sk': 'slovakia',
    'si': 'slovenia',
    'es': 'spain',
    'se': 'sweden',
    'ch': 'switzerland',
    'uk': 'united-kingdom',
    'il': 'israel'
}

# Namespaces for parsing MeteoAlarm feeds
NS = {
    'atom': 'http://www.w3.org/2005/Atom',
    'cap': 'urn:oasis:names:tc:emergency:cap:1.2',
    'ha': 'http://www.alertas-ve.gob.ve/cap'
}

async def fetch_eonet_async(session, start_date, end_date):
    """Fetches events from NASA EONET API (async)."""
    url = "https://eonet.gsfc.nasa.gov/api/v3/events"
    params = {
        "start": start_date,
        "end": end_date,
        "status": "all"
    }
    
    events_data = []
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(url, params=params, timeout=timeout) as response:
            response.raise_for_status()
            data = await response.json()
            
            for event in data.get('events', []):
                geometries = event.get('geometry', [])
                if not geometries:
                    continue
                
                polygons = []
                date = geometries[-1]['date'][:10].replace('-', '')
                
                for geo in geometries:
                    geo_type = geo['type']
                    coords = geo['coordinates']
                    
                    if geo_type == 'Point':
                        p = Point(coords)
                        polygons.append(p.buffer(0.1))
                    elif geo_type == 'Polygon':
                        polygons.append(Polygon(coords[0]))
                
                if polygons:
                    multi_poly = MultiPolygon(polygons) if len(polygons) > 1 else polygons[0]
                    wkt_str = wkt_dumps(multi_poly)
                    
                    events_data.append({
                        'date': date,
                        'country': event.get('categories', [{}])[0].get('title', 'Unknown'),
                        'event': event.get('title', 'Unknown Event'),
                        'polygon': wkt_str
                    })
        
        logger.info(f"EONET: Fetched {len(events_data)} events")
        return events_data
        
    except Exception as e:
        logger.error(f"EONET error: {e}")
        return []

async def fetch_gdacs_async(session):
    """Fetches events from GDACS RSS feed (async)."""
    url = "https://www.gdacs.org/xml/rss.xml"
    events_data = []
    
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with session.get(url, timeout=timeout) as response:
            response.raise_for_status()
            content = await response.read()
            
            # Parse XML (CPU-bound, but fast)
            root = ET.fromstring(content)
            
            for item in root.findall('.//item'):
                title = item.find('title')
                pub_date = item.find('pubDate')
                geo_point = item.find('{http://www.georss.org/georss}point')
                
                if title is not None and pub_date is not None and geo_point is not None:
                    try:
                        date_str = pub_date.text
                        dt = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %Z')
                        formatted_date = dt.strftime('%Y%m%d')
                        
                        coords = geo_point.text.strip().split()
                        if len(coords) == 2:
                            lat, lon = map(float, coords)
                            point = Point(lon, lat)
                            buffered = point.buffer(0.5)
                            
                            country = "Unknown"
                            title_text = title.text
                            if ',' in title_text:
                                parts = title_text.split(',')
                                if len(parts) >= 2:
                                    country = parts[1].strip()
                            
                            events_data.append({
                                'date': formatted_date,
                                'country': country,
                                'event': title_text,
                                'polygon': wkt_dumps(buffered)
                            })
                    except Exception as e:
                        logger.debug(f"GDACS item parse error: {e}")
                        continue
        
        logger.info(f"GDACS: Fetched {len(events_data)} events")
        return events_data
        
    except Exception as e:
        logger.error(f"GDACS error: {e}")
        return []

async def fetch_meteoalarm_feed_async(session, iso_code, slug):
    """Fetches one MeteoAlarm country feed (async)."""
    url = f"https://feeds.meteoalarm.org/feeds/meteoalarm-legacy-atom-{slug}"
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(url, timeout=timeout) as response:
            if response.status == 200:
                content = await response.read()
                return iso_code, content
    except Exception as e:
        logger.debug(f"[{iso_code}] Exception: {e}")
    return iso_code, None

async def fetch_meteoalarm_cap_async(session, url):
    """Fetches CAP content (async)."""
    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(url, timeout=timeout) as response:
            if response.status == 200:
                return await response.read()
    except Exception:
        pass
    return None

def parse_polygon(polygon_str):
    """Parses whitespace-separated CAP coordinates into WKT format."""
    if not polygon_str:
        return None
        
    parts = polygon_str.split()
    coords = []
    for p in parts:
        try:
            if ',' in p:
                lat, lon = map(float, p.split(','))
                coords.append(f"{lon} {lat}")
        except ValueError:
            continue
    
    if coords:
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        return f"POLYGON (({', '.join(coords)}))"
    return None

async def fetch_meteoalarm_async(session, start_date):
    """Fetches weather warning events from MeteoAlarm (async)."""
    try:
        target_date = datetime.strptime(start_date, "%Y%m%d").date()
    except ValueError:
        logger.error("Invalid date format for MeteoAlarm. Use YYYYMMDD.")
        return []

    # 1. Fetch all country feeds concurrently
    active_entries = []
    logger.info("Fetching MeteoAlarm country feeds...")
    
    tasks = [fetch_meteoalarm_feed_async(session, iso, slug) for iso, slug in COUNTRY_MAP.items()]
    results = await asyncio.gather(*tasks)
    
    for iso, content in results:
        if content:
            try:
                root = ET.fromstring(content)
                entries = root.findall('atom:entry', NS)
                logger.info(f"[{iso.upper()}] {len(entries)} found.")
                
                for entry in entries:
                    expires = entry.find('cap:expires', NS)
                    if expires is not None:
                        try:
                            expires_text = expires.text.replace('Z', '+00:00')
                            expires_dt = datetime.fromisoformat(expires_text).date()
                            if expires_dt < target_date:
                                continue
                        except Exception:
                            pass
                    
                    cap_link = None
                    for link in entry.findall('atom:link', NS):
                        if link.get('type') == 'application/cap+xml':
                            cap_link = link.get('href')
                            break
                    
                    if cap_link:
                        active_entries.append({
                            'country_code': iso,
                            'country_name': COUNTRY_MAP[iso],
                            'cap_link': cap_link
                        })
                        
            except ET.ParseError:
                logger.warning(f"[{iso.upper()}] XML Parse Error")

    # 2. Fetch CAP details concurrently
    logger.info(f"Fetching details for {len(active_entries)} MeteoAlarm warnings...")
    
    events_data = []
    cap_tasks = [fetch_meteoalarm_cap_async(session, item['cap_link']) for item in active_entries]
    cap_results = await asyncio.gather(*cap_tasks)
    
    for item, content in zip(active_entries, cap_results):
        if not content:
            continue
            
        try:
            root = ET.fromstring(content)
            infos = root.findall('cap:info', NS)
            selected_info = None
            
            for info in infos:
                lang = info.find('cap:language', NS)
                if lang is not None and ('en' in lang.text or 'en-' in lang.text):
                    selected_info = info
                    break
            if selected_info is None and infos:
                selected_info = infos[0]
            
            if selected_info is None:
                continue
                
            event_type_e = selected_info.find('cap:event', NS)
            event_type = event_type_e.text if event_type_e is not None else "Unknown Event"
            
            severity_e = selected_info.find('cap:severity', NS)
            severity = severity_e.text if severity_e is not None else "Unknown Severity"
            
            onset_elem = selected_info.find('cap:onset', NS)
            effective_elem = selected_info.find('cap:effective', NS)
            
            onset_str = "Unknown"
            if onset_elem is not None:
                onset_str = onset_elem.text
            elif effective_elem is not None:
                onset_str = effective_elem.text

            headline_elem = selected_info.find('cap:headline', NS)
            headline = headline_elem.text if headline_elem is not None else f"{severity} {event_type}"
            
            description = selected_info.find('cap:description', NS)
            desc_text = description.text if description is not None else ""
            short_desc = (desc_text[:75] + '..') if len(desc_text) > 75 else desc_text
            
            country_name = item.get('country_name', 'unknown').title().replace('-', ' ')
            if country_name == "United Kingdom":
                country_name = "United Kingdom"
            if country_name == "Bosnia Herzegovina":
                country_name = "Bosnia and Herzegovina"
            if not country_name or country_name.lower() == 'unknown':
                country_name = "Unknown"
            
            try:
                dt = datetime.fromisoformat(onset_str.replace('Z', '+00:00'))
                onset_fmt = dt.strftime("%d/%m/%Y %H:%M UTC")
                event_date = dt.strftime("%Y%m%d")
            except:
                onset_fmt = onset_str
                event_date = start_date

            key_str = f"{headline} in {country_name} {onset_fmt}, {short_desc}"
            
            for area in selected_info.findall('cap:area', NS):
                poly_elem = area.find('cap:polygon', NS)
                if poly_elem is not None:
                    wkt = parse_polygon(poly_elem.text)
                    if wkt:
                        events_data.append({
                            "date": event_date,
                            "country": country_name,
                            "event": key_str,
                            "polygon": wkt
                        })

        except ET.ParseError:
            pass
        except Exception as e:
            logger.debug(f"Error parsing MeteoAlarm entry: {e}")

    logger.info(f"MeteoAlarm: Fetched {len(events_data)} events")
    return events_data

async def main_async():
    """Main async function."""
    parser = argparse.ArgumentParser(description="Fetch disaster event polygons.")
    parser.add_argument("--start_date", required=True, help="Start date in YYYYMMDD format")
    parser.add_argument("--firms_key", help="NASA FIRMS Map Key")
    
    args = parser.parse_args()
    
    try:
        dt = datetime.strptime(args.start_date, "%Y%m%d")
        formatted_date = dt.strftime("%Y-%m-%d")
        end_formatted_date = formatted_date
    except ValueError:
        logger.error("Invalid date format. Use YYYYMMDD.")
        return

    logger.info(f"Fetching events for {formatted_date}...")
    start_time = time.time()
    
    # Create single aiohttp session for all requests
    timeout = aiohttp.ClientTimeout(total=30)
    connector = aiohttp.TCPConnector(limit=100)
    
    async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
        # Run all fetches concurrently
        tasks = [
            fetch_eonet_async(session, formatted_date, end_formatted_date),
            fetch_gdacs_async(session),
            fetch_meteoalarm_async(session, args.start_date)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Collect all events
        all_events = []
        for result in results:
            if isinstance(result, list):
                all_events.extend(result)
            elif isinstance(result, Exception):
                logger.error(f"Task failed: {result}")
    
    # Filter events by date
    all_events = [e for e in all_events if e.get('date') == args.start_date]
    
    # Optimized grouping using defaultdict
    grouped_results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    
    for event in all_events:
        d = event['date']
        c = event['country']
        e = event['event']
        p = event['polygon']
        grouped_results[d][c][e].append(p)
    
    # Convert defaultdict to regular dict for JSON serialization
    grouped_results = {k: {k2: dict(v2) for k2, v2 in v.items()} for k, v in grouped_results.items()}

    with open("results.json", "w") as f:
        json.dump(grouped_results, f, indent=2)
    
    elapsed = time.time() - start_time
    logger.info(f"✅ Done in {elapsed:.2f}s. Saved {len(all_events)} events to results.json")

if __name__ == "__main__":
    asyncio.run(main_async())
