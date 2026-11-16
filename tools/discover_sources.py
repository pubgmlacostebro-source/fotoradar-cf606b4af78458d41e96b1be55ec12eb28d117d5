import sys,json,re,html,time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import collector as c
sys.stdout.reconfigure(encoding='utf-8')
names='mama_ekb kastingiekbtfp tfpekb1 tgrabotaekb rusvacant ekb_rabota rabota_ekb rabotaekb vakansii_ekb ekbjob rabota66 ekb66 ekaterinburg e1_news e1_ru ekb_now ekb_live ekbtypical tipichny_ekaterinburg ekaterinburg_online ekb_mama mamy_ekb svadbaekb tfprus ekaterinburgads rusvacant_ekb ekbbiznes skazkovomam baraholkaekb ekbclub atobar_ekb Nedvizg_Ekaterinburg sve_obyavleniya obyavleniaekaterinburg'.split()
names = sys.argv[1:] or names
def probe(name):
 try:
  page=c.http_get('https://t.me/s/'+name,timeout=18)
  title=c.RE_TG_TITLE.search(page)
  posts=c.RE_TG_POST.findall(page)
  times=c.RE_TG_TIME.findall(page)
  return dict(username=name,title=html.unescape(title.group(1)) if title else name,posts=len(posts),latest=times[-1] if times else None,error='')
 except Exception as e:return dict(username=name,posts=0,error=type(e).__name__)
with ThreadPoolExecutor(max_workers=4) as ex:
 rows=list(ex.map(probe,names))
for x in rows:print(json.dumps(x,ensure_ascii=False))
url='https://api.hh.ru/vacancies?'+c.urllib.parse.urlencode({'text':'NAME:фотограф','area':'3','per_page':100,'period':7})
try:
 r=json.loads(c.http_get(url));print('HH',r.get('found'),[(x['id'],x['name'],x['area']['name']) for x in r.get('items',[])][:15])
except Exception as e:print('HH ERROR',repr(e))
folder=Path(__file__).resolve().parents[1]/'research';folder.mkdir(exist_ok=True)
old_path=folder/'source-probe.json'
if old_path.exists():
 previous=json.loads(old_path.read_text('utf-8')).get('telegram',[])
 merged={x['username'].lower():x for x in previous+rows}
 rows=list(merged.values())
(folder/'source-probe.json').write_text(json.dumps({'checked':int(time.time()),'telegram':rows},ensure_ascii=False,indent=2),'utf-8')
