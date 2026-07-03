from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import os
import numpy as np

app = Flask(__name__)
CORS(app)

ASSETS_DIR = os.path.join(os.path.dirname(__file__), 'assets')
os.makedirs(ASSETS_DIR, exist_ok=True)

RECURSOS = 'https://eldiariodemiramar.com.ar/recursos'

ASSET_FILES = {
    'LeagueSpartan-Bold.ttf': f'{RECURSOS}/LeagueSpartan-Bold.ttf',
    'Logo-DDM-Blanco-01.png': f'{RECURSOS}/Logo-DDM-Blanco-01.png',
    'pie-redes.png':          f'{RECURSOS}/pie-redes.png',
    'dib-logo.png':           f'{RECURSOS}/dib-logo.png',
}

def ensure_asset(filename):
    """Descarga un asset si no existe localmente."""
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        url = ASSET_FILES[filename]
        print(f'Downloading {filename} from {url}...')
        r = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        r.raise_for_status()
        with open(path, 'wb') as f:
            f.write(r.content)
        print(f'OK: {filename} ({len(r.content)} bytes)')
    return path

def ensure_all_assets():
    for filename in ASSET_FILES:
        try:
            ensure_asset(filename)
        except Exception as e:
            print(f'Warning: could not download {filename}: {e}')

def asset(filename):
    return ensure_asset(filename)

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
    font_path  = asset('LeagueSpartan-Bold.ttf')
    logo_path  = asset('Logo-DDM-Blanco-01.png')
    redes_path = asset('pie-redes.png')
    dib_path   = os.path.join(ASSETS_DIR, 'dib-logo.png')

    headers = {'User-Agent': 'Mozilla/5.0 (compatible; EDMPublisher/1.0)'}
    r = requests.get(foto_url, headers=headers, timeout=15)
    r.raise_for_status()
    foto = Image.open(io.BytesIO(r.content)).convert('RGB')

    logo  = Image.open(logo_path).convert('RGBA')
    redes = Image.open(redes_path).convert('RGBA')

    img = Image.new('RGB', (W, H), AZUL)
    draw = ImageDraw.Draw(img)

    foto_h = int(H * 0.62)
    ratio = foto.width / foto.height
    new_w = int(foto_h * ratio)
    foto_r = foto.resize((new_w, foto_h), Image.LANCZOS)
    max_offset = max(0, new_w - W)
    x_off = int(max_offset * crop_offset)
    foto_r = foto_r.crop((x_off, 0, x_off + W, foto_h))
    img.paste(foto_r, (0, 0))

    if is_dib:
        try:
            dib_path = asset('dib-logo.png')
            dib = remove_white_bg(Image.open(dib_path))
            dib_h = 86
            dib_w = int(dib_h * dib.width / dib.height)
            dib_r = dib.resize((dib_w, dib_h), Image.LANCZOS)
            img.paste(dib_r, (40, 40), dib_r)
        except Exception as e:
            print(f'DIB logo error: {e}')

    GRAD = 150
    for i in range(GRAD):
        alpha = int(255 * (i / GRAD) ** 0.5)
        overlay = Image.new('RGBA', (W, 1), (*AZUL, alpha))
        img.paste(overlay, (0, foto_h - GRAD + i), overlay)

    MARGIN = 55
    TEXT_MAX_W = W - MARGIN * 2
    TRACKING = -4
    PIE_Y = H - 155

    font_tag = ImageFont.truetype(font_path, 58)
    pad_x, pad_y = 34, 16
    text_w = get_tracked_width(draw, cintillo, font_tag, tracking=-2)
    char_bbox = draw.textbbox((0, 0), cintillo, font=font_tag)
    text_h_tag = char_bbox[3] - char_bbox[1]
    tag_w = text_w + pad_x * 2
    tag_h = text_h_tag + pad_y * 2
    tag_y = foto_h - GRAD + int(GRAD * 0.30) - tag_h // 2
    draw.rounded_rectangle([MARGIN, tag_y, MARGIN + tag_w, tag_y + tag_h], radius=30, fill=BLANCO)
    text_x = MARGIN + (tag_w - text_w) // 2
    text_y_c = tag_y + (tag_h - text_h_tag) // 2 - char_bbox[1]
    draw_tracked_text(draw, (text_x, text_y_c), cintillo, font_tag, AZUL, tracking=-2)

    title_start_y = tag_y + tag_h + 30
    available_h = PIE_Y - 30 - title_start_y
    font_title, lines, lh = fit_title(draw, titulo, TEXT_MAX_W, available_h, font_path, TRACKING)
    total_text_h = lh * len(lines)
    text_y = title_start_y + (available_h - total_text_h) // 2
    for line in lines:
        draw_tracked_text(draw, (MARGIN, text_y), line, font_title, BLANCO, TRACKING)
        text_y += lh

    logo_w = 360
    logo_h_px = int(logo_w * logo.height / logo.width)
    logo_r = logo.resize((logo_w, logo_h_px), Image.LANCZOS)
    logo_base = PIE_Y + logo_h_px
    img.paste(logo_r, (MARGIN, PIE_Y), logo_r)

    redes_h = 58
    redes_w = int(redes_h * redes.width / redes.height)
    redes_r = redes.resize((redes_w, redes_h), Image.LANCZOS)
    img.paste(redes_r, (W - MARGIN - redes_w, logo_base - redes_h), redes_r)

    output = io.BytesIO()
    img.convert('RGB').save(output, format='JPEG', quality=95)
    output.seek(0)
    return output

@app.route('/')
def index():
    return jsonify({'status': 'EDM Placa Generator OK'})

@app.route('/warmup', methods=['GET'])
def warmup():
    """Descarga todos los assets y los cachea."""
    try:
        ensure_all_assets()
        assets_ok = {f: os.path.exists(os.path.join(ASSETS_DIR, f)) for f in ASSET_FILES}
        return jsonify({'status': 'OK', 'assets': assets_ok})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/generar', methods=['POST', 'OPTIONS'])
def generar():
    if request.method == 'OPTIONS':
        return '', 204
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
        print(f'Error en /generar: {e}')
        return jsonify({'error': str(e)}), 500

# Descargar assets al iniciar
with app.app_context():
    ensure_all_assets()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
