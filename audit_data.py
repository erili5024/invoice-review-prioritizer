"""Prepare public source data and a real DEV cache. Does not compute final features/results."""
from pathlib import Path
import zipfile,json,urllib.request,pandas as pd,core
root=Path(__file__).parent
archive=root/'data/uci-online-retail-ii.zip'
archive.parent.mkdir(exist_ok=True)
if not archive.exists():
 print('Downloading public UCI Online Retail II data...')
 urllib.request.urlretrieve('https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip',archive)
with zipfile.ZipFile(archive) as z:
 with z.open('online_retail_II.xlsx') as f:
  lines=core.load_invoices(f,'online_retail_II.xlsx')
lines.to_pickle(root/'data/prepared.pkl')
(root/'data/data_audit.json').write_text(json.dumps(lines.attrs['audit'],indent=2))
print(lines.attrs['audit'])
print({k:v.invoice.nunique() for k,v in core.split_periods(lines).items()})
