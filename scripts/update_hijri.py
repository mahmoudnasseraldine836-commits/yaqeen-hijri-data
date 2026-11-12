"""Read published civil-date calendars; never guess missing dates."""
import json, re, unicodedata
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

URL = "https://www.bayynat.org.lb/prayer-time"
PATH = Path("data/hijri.json")
GREG = ["كانون الثاني","شباط","اذار","نيسان","ايار","حزيران","تموز","اب","ايلول","تشرين الاول","تشرين الثاني","كانون الاول"]
HIJRI = {"محرم":1,"صفر":2,"ربيع الاول":3,"ربيع الثاني":4,"ربيع الاخر":4,"جمادى الاولى":5,"جمادى الثانية":6,"جمادى ثاني":6,"جمادى الاخرة":6,"جمادى اخرة":6,"رجب":7,"شعبان":8,"رمضان":9,"شوال":10,"ذو القعدة":11,"ذي القعدة":11,"ذو الحجة":12,"ذي الحجة":12}

class Visible(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ("script","style"): self.skip+=1
    def handle_endtag(self, tag):
        if tag in ("script","style") and self.skip: self.skip-=1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

def normalize(s):
    s="".join(c for c in unicodedata.normalize("NFKD",s) if not unicodedata.combining(c))
    s=s.translate(str.maketrans("أإآٱ٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹","اااا01234567890123456789"))
    return " ".join(s.replace("ـ","").split())

def parse(html):
    p=Visible(); p.feed(html); t=normalize(" ".join(p.parts))
    g="|".join(map(re.escape,GREG))
    h="|".join(map(re.escape,sorted(HIJRI,key=len,reverse=True)))
    pattern=rf"(\d{{1,2}}) ({g}) (20\d{{2}})\s*(?:م\s*)?الموافق\s*(?:ل\s*)?(\d{{1,2}}) ({h}) (14\d{{2}})"
    matches=set(re.findall(pattern,t))
    if len(matches)!=1: raise ValueError("Missing or ambiguous official date pair")
    gd,gm,gy,hd,hm,hy=matches.pop()
    return date(int(gy),GREG.index(gm)+1,int(gd)), int(hd),HIJRI[hm],int(hy)

def parse_sistani(html):
    p=Visible(); p.feed(html); t=normalize(" ".join(p.parts))
    h="|".join(map(re.escape,sorted(HIJRI,key=len,reverse=True)))
    pattern=rf"(\d{{1,2}})\s*-\s*({h})\s*-\s*(14\d{{2}})\s*ه(?:ـ)?\s*\|\|\s*\(النجف الاشرف\)\s*\|\|\s*[A-Za-z]{{3}},\s*(\d{{1,2}})\s*([A-Za-z]{{3}})\s*(20\d{{2}})"
    matches=set(re.findall(pattern,t))
    if len(matches)!=1: raise ValueError("Missing or ambiguous Najaf calendar")
    hd,hm,hy,gd,gm,gy=matches.pop()
    months="Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return date(int(gy),months.index(gm)+1,int(gd)),int(hd),HIJRI[hm],int(hy)

def refresh_one(key, URL, hosts, status):
    req=Request(URL,headers={"User-Agent":"YaqeenCalendar/1.0"})
    with urlopen(req,timeout=30) as res:
        if urlparse(res.geturl()).hostname not in hosts: raise ValueError("Unexpected source host")
        html=res.read(4000000).decode("utf-8")
    if key=="khamenei" and "مدينة بيروت" not in html: raise ValueError("Beirut calendar not found")
    civil,day,month,year=(parse_sistani(html) if key=="sistani" else parse(html))
    region,timezone=("IQ","Asia/Baghdad") if key=="sistani" else ("LB","Asia/Beirut")
    today=datetime.now(ZoneInfo(timezone)).date()
    if civil != today or not 1<=day<=30: raise ValueError("Source date not current or invalid")
    start=civil-timedelta(days=day-1)
    data=json.loads(PATH.read_text())
    old=data["maraji"][key]
    prev=date.fromisoformat(old["month_start"])
    delta=(start-prev).days
    old_index=old["hijri_year"]*12+old["hijri_month"]
    new_index=year*12+month
    if delta==0 and new_index==old_index:
        print(f"{key}: Official date agrees with stored month"); return
    if delta not in (29,30) or new_index!=old_index+1:
        raise ValueError("Unexpected month transition; retain verified data")
    data["maraji"][key]={"status":status,"region":region,"timezone":timezone,"hijri_year":year,"hijri_month":month,"month_start":start.isoformat(),"source":URL,"basis":"official published civil-date calendar"}
    PATH.write_text(json.dumps(data,ensure_ascii=False,indent=2)+"\n")

def refresh():
    errors=[]
    for key,url,hosts,status in [
        ("fadlallah",URL,("www.bayynat.org.lb","bayynat.org.lb"),"official_calendar"),
        ("khamenei","https://almaaref.org.lb/",("almaaref.org.lb","www.almaaref.org.lb"),"published_local_calendar"),
        ("sistani","https://www.sistani.org/",("sistani.org","www.sistani.org"),"official_calendar"),
    ]:
        try: refresh_one(key,url,hosts,status)
        except Exception as exc:
            print(f"{key}: {exc}",flush=True); errors.append(key)
    if errors: print("::warning::Source checks failed: "+", ".join(errors))

if __name__=="__main__":
    import sys
    if "--test" in sys.argv:
        assert parse("<p>الخميس 12 تشرين الثاني 2026</p><p>الموافق</p><p>3 جمادى آخرة 1448</p>")== (date(2026,11,12),3,6,1448)
        try: parse("<p>no date</p>")
        except ValueError: pass
        else: raise AssertionError("Missing date accepted")
        assert parse("<p>مواقيت الصلاة ليوم الخميس (12 تشرين الثاني 2026 م الموافق لـ 02 جمادى الثانية 1448 هـ) - حسب توقيت مدينة بيروت</p>")== (date(2026,11,12),2,6,1448)
        assert parse_sistani("<p>الجمعة ٢ - جمادى الآخرة - ١٤٤٨ هـ || (النجف الأشرف) || Fri, 13 Nov 2026</p>")== (date(2026,11,13),2,6,1448)
        print("Parser fixtures passed")
    else: refresh()
