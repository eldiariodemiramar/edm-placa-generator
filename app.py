from flask import Flask, request, jsonify, send_file
from PIL import Image, ImageDraw, ImageFont
import requests
import textwrap
import io
import os
import numpy as np

app = Flask(__name__)

# ── Assets ────────────────────────────────────────────────────────────────────
ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')
os.makedirs(ASSETS_DIR, exist_ok=True)

EDM_BASE = 'https://eldiariodemiramar.com.ar'
RECURSOS = f'{EDM_BASE}/recursos'

ASSET_URLS = {
    'font':      f'{RECURSOS}/LeagueSpartan-Bold.ttf',
    'logo':      f'{RECURSOS}/Logo-DDM-Blanco-01.png',
    'redes':     f'{RECURSOS}/pie-redes.png',
    'dib_logo':  f'{RECURSOS}/dib-logo.png',
}

def get_asset(name):
    path = os.path.join(ASSETS_DIR, name)
    if not os.path.exists(path):
        url = ASSET_URLS[name.replace('-', '_').replace('.ttf','').replace('.png','')]
        # Match by key
        for key, asset_url in ASSET_URLS.items():
            if asset_url.endswith(name):
                r = requests.get(asset_url, timeout=15)
                r.raise_for_status()
                with open(path, 'wb') as f:
                    f.write(r.content)
                break
    return path

def download_assets():
    files = {
        'LeagueSpartan-Bold.ttf': ASSET_URLS['font'],
        'Logo-DDM-Blanco-01.png': ASSET_URLS['logo'],
        'pie-redes.png':          ASSET_URLS['redes'],
        'dib-logo.png':           ASSET_URLS['dib_logo'],
    }
    for filename, url in files.items():
        path = os.path.join(ASSETS_DIR, filename)
        if not os.path.exists(path):
            try:
                r = requests.get(url, timeout=15)
                r.raise_for_status()
                with open(path, 'wb') as f:
                    f.write(r.content)
                print(f'Downloaded: {filename}')
            except Exception as e:
                print(f'Failed to download {filename}: {e}')

# ── Placa generator ───────────────────────────────────────────────────────────
W, H = 1080, 1440
AZUL = (1, 65, 109)
BLANCO = (255, 255, 255)

def get_tracked_width(draw, text, font, tracking=-4):
    total = 0
    for i, char in enumerate(text):
        bbox = draw.textbbox((0, 0), char, font=font)
        total += bbox[2] - bbox[0]
        if i < len(text) - 1:
            total += tracking
    return total

def draw_tracked_text(draw, pos, text, font, fill, tracking=-4):
    x, y = pos
    for char in text:
        draw.text((x, y), char, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), char, font=font)
        x += (bbox[2] - bbox[0]) + tracking

def wrap_tracked(text, font, max_width, draw, tracking=-4):
    words = text.split()
    lines, current = [], ''
    for word in words:
        test = (current + ' ' + word).strip()
        if get_tracked_width(draw, test, font, tracking) <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def fit_title(draw, titulo, max_w, available_h, font_path, tracking=-4, line_spacing=0.95, size_max=110, size_min=36):
    for size in range(size_max, size_min - 1, -2):
        font = ImageFont.truetype(font_path, size)
        lines = wrap_tracked(titulo, font, max_w, draw, tracking)
        sample = draw.textbbox((0, 0), 'Ag', font=font)
        lh = int((sample[3] - sample[1]) * line_spacing)
        if lh * len(lines) <= available_h:
            return font, lines, lh
    font = ImageFont.truetype(font_path, size_min)
    lines = wrap_tracked(titulo, font, max_w, draw, tracking)
    sample = draw.textbbox((0, 0), 'Ag', font=font)
    lh = int((sample[3] - sample[1]) * line_spacing)
    return font, lines, lh

def remove_white_bg(img):
    img = img.convert('RGBA')
    data = np.array(img)
    r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
    white_mask = (r > 230) & (g > 230) & (b > 230)
    data[:,:,3] = np.where(white_mask, 0, a)
    return Image.fromarray(data)

def generar_placa(titulo, cintillo, foto_url, is_dib=False, crop_offset=0.5):
    font_path = os.path.join(ASSETS_DIR, 'LeagueSpartan-Bold.ttf')
    logo_path = os.path.join(ASSETS_DIR, 'Logo-DDM-Blanco-01.png')
    redes_path = os.path.join(ASSETS_DIR, 'pie-redes.png')
    dib_path   = os.path.join(ASSETS_DIR, 'dib-logo.png')

    # Descargar foto de la nota
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; EDMPublisher/1.0)'}
    r = requests.get(foto_url, headers=headers, timeout=15)
    r.raise_for_status()
    foto = Image.open(io.BytesIO(r.content)).convert('RGB')

    logo  = Image.open(logo_path).convert('RGBA')
    redes = Image.open(redes_path).convert('RGBA')

    img = Image.new('RGB', (W, H), AZUL)
    draw = ImageDraw.Draw(img)

    # Foto — 62% del alto
    foto_h = int(H * 0.62)
    ratio = foto.width / foto.height
    new_w = int(foto_h * ratio)
    foto_r = foto.resize((new_w, foto_h), Image.LANCZOS)
    max_offset = max(0, new_w - W)
    x_off = int(max_offset * crop_offset)
    foto_r = foto_r.crop((x_off, 0, x_off + W, foto_h))
    img.paste(foto_r, (0, 0))

    # Logo DIB arriba izquierda
    if is_dib and os.path.exists(dib_path):
        dib = remove_white_bg(Image.open(dib_path))
        dib_h_target = 86
        dib_w_target = int(dib_h_target * dib.width / dib.height)
        dib_r = dib.resize((dib_w_target, dib_h_target), Image.LANCZOS)
        img.paste(dib_r, (40, 40), dib_r)

    # Gradiente
    GRAD = 150
    for i in range(GRAD):
        alpha = int(255 * (i / GRAD) ** 0.5)
        overlay = Image.new('RGBA', (W, 1), (*AZUL, alpha))
        img.paste(overlay, (0, foto_h - GRAD + i), overlay)

    MARGIN = 55
    TEXT_MAX_W = W - MARGIN * 2
    TRACKING = -4
    PIE_Y = H - 155

    # Pastilla sección
    font_tag = ImageFont.truetype(font_path, 58)
    pad_x, pad_y = 34, 16
    text_w = get_tracked_width(draw, cintillo, font_tag, tracking=-2)
    char_bbox = draw.textbbox((0, 0), cintillo, font=font_tag)
    text_h = char_bbox[3] - char_bbox[1]
    tag_w = text_w + pad_x * 2
    tag_h = text_h + pad_y * 2
    tag_y = foto_h - GRAD + int(GRAD * 0.30) - tag_h // 2
    draw.rounded_rectangle([MARGIN, tag_y, MARGIN + tag_w, tag_y + tag_h], radius=30, fill=BLANCO)
    text_x = MARGIN + (tag_w - text_w) // 2
    text_y_c = tag_y + (tag_h - text_h) // 2 - char_bbox[1]
    draw_tracked_text(draw, (text_x, text_y_c), cintillo, font_tag, AZUL, tracking=-2)

    # Título
    title_start_y = tag_y + tag_h + 30
    available_h = PIE_Y - 30 - title_start_y
    font_title, lines, lh = fit_title(draw, titulo, TEXT_MAX_W, available_h, font_path, TRACKING)
    total_text_h = lh * len(lines)
    text_y = title_start_y + (available_h - total_text_h) // 2
    for line in lines:
        draw_tracked_text(draw, (MARGIN, text_y), line, font_title, BLANCO, TRACKING)
        text_y += lh

    # Logo EDM
    logo_w = 360
    logo_h = int(logo_w * logo.height / logo.width)
    logo_r = logo.resize((logo_w, logo_h), Image.LANCZOS)
    logo_base = PIE_Y + logo_h
    img.paste(logo_r, (MARGIN, PIE_Y), logo_r)

    # Redes
    redes_h = 58
    redes_w = int(redes_h * redes.width / redes.height)
    redes_r = redes.resize((redes_w, redes_h), Image.LANCZOS)
    img.paste(redes_r, (W - MARGIN - redes_w, logo_base - redes_h), redes_r)

    # Convertir a JPG en memoria
    output = io.BytesIO()
    img.convert('RGB').save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return jsonify({'status': 'EDM Placa Generator OK'})

@app.route('/generar', methods=['POST'])
def generar():
    try:
        data = request.get_json()
        titulo      = data.get('titulo', '')
        cintillo    = data.get('cintillo', '')
        foto_url    = data.get('foto_url', '')
        is_dib      = data.get('is_dib', False)
        crop_offset = float(data.get('crop_offset', 0.5))

        if not titulo or not cintillo or not foto_url:
            return jsonify({'error': 'Faltan datos: titulo, cintillo, foto_url'}), 400

        imagen = generar_placa(titulo, cintillo, foto_url, is_dib, crop_offset)
        return send_file(imagen, mimetype='image/jpeg', download_name='placa-edm.jpg')

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    download_assets()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
