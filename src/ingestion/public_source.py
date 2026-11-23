"""P0-0 discovery sample. Search results only identify URLs; the post endpoint supplies the words."""
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
import re
from urllib.parse import urlsplit

from src.execution.transport import network, outbound, redact

SITE = "cooking"
DOMAIN = "cooking.stackexchange.com"
TOPIC = "measuring cups"
QUERY = "site:cooking.stackexchange.com/questions measuring cups sticky honey"
LICENSES = {f"CC BY-SA {v}": f"https://creativecommons.org/licenses/by-sa/{v}/" for v in ("2.5","3.0","4.0")}
PUBLIC = {"public_approved"}


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fragments = []

    def handle_data(self, data):
        self.fragments.append(data)


def post_id(url):
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    match = re.match(r"^/(?:questions|q)/([1-9]\d{0,11})(?:/|$)", parsed.path)
    if parsed.scheme == "https" and parsed.netloc == DOMAIN and match:
        return match[1]
    return None


def first_sentence(html):
    parser = PlainText()
    parser.feed(html)
    plain = " ".join("".join(parser.fragments).split())
    hit = re.search(r"^.{12,400}?[.!?](?:\s|$)", plain)
    return hit.group().strip() if hit else plain[:360]


def discover(settings, store, attempt, transport=network):
    secrets = list(settings.keys.values())
    refs, candidates, errors = [], [], []
    for engine in ("tavily","brave","forum_search"):
        key = settings.keys.get(engine)
        if engine != "forum_search" and not key:
            errors.append(f"{engine} 未配置")
            refs.append(store.record(attempt,engine,"configuration",{"query":QUERY},{"sent":False,"reason":"missing_key"}))
            continue
        if engine == "tavily":
            params = {"query": QUERY,"include_domains":[DOMAIN],"max_results":5,"include_answer":False}
            reply = outbound(engine, labels=PUBLIC, method="POST",body=params,
                             headers={"Authorization":"Bearer " + key,"Content-Type":"application/json"},transport=transport)
        elif engine == "brave":
            params = {"q":QUERY,"count":5}
            reply = outbound(engine,labels=PUBLIC,query=params,headers={"X-Subscription-Token":key},transport=transport)
        else:
            params = {"site":SITE,"title":TOPIC,"sort":"votes","order":"desc","pagesize":4}
            reply = outbound("forum_search",labels=PUBLIC,query=params,transport=transport)
        obj = reply.body if isinstance(reply.body,dict) else {}
        listings = (obj.get("web") or {}).get("results",[]) if engine == "brave" and isinstance(obj.get("web"),dict) else obj.get("items" if engine == "forum_search" else "results",[])
        hits = []
        if reply.status == 200 and isinstance(listings,list):
            for item in listings:
                if not isinstance(item,dict):
                    continue
                link = item.get("url") or item.get("link")
                if ident := post_id(link):
                    hits.append({"id":ident,"url":link,"title":unescape(str(item.get("title","")))[:240]})
                    candidates.append((engine,ident))
        refs.append(store.record(attempt,engine,"live_http",params,redact({"hits":hits,"error":obj.get("error") or obj.get("error_message"),"quota_remaining":obj.get("quota_remaining")},secrets),reply.status))
        if not hits:
            errors.append(f"{engine} 未取得可核验链接")
    # Each request is for an ID returned by a search in this run.
    tried = set()
    for engine, ident in candidates:
        if ident in tried or len(tried) >= 4:
            continue
        tried.add(ident)
        params = {"site":SITE,"filter":"withbody"}
        reply = outbound("stackexchange",labels=PUBLIC,path=ident,query=params,transport=transport)
        obj = reply.body if isinstance(reply.body,dict) else {}
        items = obj.get("items")
        item = items[0] if reply.status == 200 and isinstance(items,list) and items and isinstance(items[0],dict) else {}
        license_name = item.get("content_license")
        quote = first_sentence(item.get("body","")) if isinstance(item.get("body"),str) else ""
        original = item.get("link")
        author = str((item.get("owner") or {}).get("display_name","")).strip()
        obtained = item.get("creation_date")
        expires = item.get("last_activity_date")
        verified = (license_name in LICENSES and post_id(original)==ident and str(item.get("question_id"))==ident
                    and bool(quote and author) and type(obtained) is int and redact(quote,secrets)==quote)
        citation = {"search":engine,"post_id":ident,"url":original,"text":quote,"author":unescape(author),
                    "license":license_name,"license_url":LICENSES.get(license_name),"method":"Stack Exchange API /questions/{id}",
                    "published_at":datetime.fromtimestamp(obtained,timezone.utc).isoformat() if type(obtained) is int else None,
                    "last_activity_epoch":expires,"verified":verified,"role":"public_connectivity_sample","research_denominator":0}
        ref = store.record(attempt,"forum_post","live_http",{"question_id":ident,**params},
                           redact(citation if verified else {"verified":False,"error":obj.get("error_message")},secrets),reply.status)
        refs.append(ref)
        if verified:
            return citation, refs, engine in {"tavily","brave"}, errors
    return None, refs, False, errors
