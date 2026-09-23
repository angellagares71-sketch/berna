import urllib.request
import re

url = "https://suno.com/s/UA4gy95wpKptFMM7"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    m = re.search(r'property="og:audio" content="([^"]+)"', html)
    if not m:
        m = re.search(r'https?://[^\s<>"]+?\.mp3[^\s<>"]*', html)
    
    if m:
        audio_url = m.group(1) if m.groups() else m.group(0)
        print("AUDIO URL:", audio_url)
        urllib.request.urlretrieve(audio_url, r"C:\Users\alaga\Desktop\Canciones de Suno\Diez Años de Fuego.mp3")
        print("DESCARGADO OK")
    else:
        # Buscar en todo el html por suno.ai o cdn y mp3
        print("HTML length:", len(html))
        # Vamos a buscar cualquier url que contenga suno o cdn
        urls = re.findall(r'https?://[^\s<>"]+', html)
        audio_candidates = [u for u in urls if 'audio' in u or 'cdn' in u or '.mp3' in u]
        print("Candidatos:", audio_candidates[:10])
except Exception as e:
    print("Error:", e)
