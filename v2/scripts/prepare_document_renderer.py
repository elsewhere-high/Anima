from pathlib import Path
import requests,hashlib,json,re
root=Path(__file__).resolve().parents[1];folder=root/'tools';folder.mkdir(exist_ok=True)
url='https://download.documentfoundation.org/libreoffice/stable/26.8.0/win/x86_64/LibreOffice_26.8.0_Win_x86-64.msi'
r=requests.get(url+'.mirrorlist',timeout=60);r.raise_for_status()
(folder/'libreoffice_mirrorlist.html').write_text(r.text,encoding='utf-8')
match=re.search(r'SHA-256.*?([a-fA-F0-9]{64})',r.text,re.S|re.I)
if not match:match=re.search(r'([a-fA-F0-9]{64})',r.text)
if not match:raise RuntimeError('No official SHA256 found')
target=folder/'LibreOffice.msi';digest=hashlib.sha256()
with requests.get(url,stream=True,timeout=90) as response:
    response.raise_for_status()
    with target.open('wb') as f:
        for chunk in response.iter_content(1024*1024):f.write(chunk);digest.update(chunk)
if digest.hexdigest().lower()!=match.group(1).lower():raise RuntimeError('MSI checksum mismatch')
(folder/'libreoffice_download.json').write_text(json.dumps({'url':url,'sha256':digest.hexdigest(),'verified':True},indent=2))
print('DOWNLOAD_VERIFIED',target,flush=True)
