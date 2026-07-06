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
EDM_PROXY = 'https://eldiariodemiramar.com.ar/edm-proxy.php'

ASSET_FILES = {
    'LeagueSpartan-Bold.ttf': f'{RECURSOS}/LeagueSpartan-Bold.ttf',
    'Logo-DDM-Blanco-01.png': f'{RECURSOS}/Logo-DDM-Blanco-01.png',
    'pie-redes.png':          f'{RECURSOS}/pie-redes.png',
    'dib-logo.png':           f'{RECURSOS}/dib-logo.png',
}

def download_assets():
    for filename, url in ASSET_FILES.items():
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

def ensure_asset(filename):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        url = ASSET_FILES.get(filename)
        if url:
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            with open(path, 'wb') as f:
                f.write(r.content)
    return path

def ensure_all_assets():
    for filename in ASSET_FILES:
        try:
            ensure_asset(filename)
        except Exception as e:
            print(f'Warning: could not download {filename}: {e}')

def asset(filename):
    return ensure_asset(filename)

def descargar_imagen(foto_url):
    """Descarga imagen intentando directo primero, luego via proxy EDM."""
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; EDMPublisher/1.0)'}
    
    # Intento 1: directo
    try:
        r = requests.get(foto_url, headers=headers, timeout=15)
        r.raise_for_status()
        print(f'Imagen descargada directo: {foto_url}')
        return r.content
    except Exception as e:
        print(f'Descarga directa falló ({e}), intentando via proxy EDM...')
    
    # Intento 2: via proxy PHP de EDM
    try:
        proxy_url = f'{EDM_PROXY}?url={requests.utils.quote(foto_url, safe="")}'
        r = requests.get(proxy_url, headers=headers, timeout=15)
        r.raise_for_status()
        ct = r.headers.get('content-type', '')
        if 'image/' in ct:
            print(f'Imagen descargada via proxy EDM')
            return r.content
        else:
            raise Exception(f'Proxy devolvió content-type: {ct}')
    except Exception as e:
        raise Exception(f'No se pudo descargar la imagen: {e}')

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

    img_data = descargar_imagen(foto_url)
    foto = Image.open(io.BytesIO(img_data)).convert('RGB')

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

with app.app_context():
    ensure_all_assets()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)



def generar_placa_farmacias(fecha_hoy, fecha_manana, farmacias_hoy, farmacias_manana, bg_index=0):
    font_path = asset('LeagueSpartan-Bold.ttf')

    # Descargar lienzo de Photoshop
    lienzo_url = f'{RECURSOS}/Farmacias-lienzo.png'
    lienzo_data = descargar_imagen(lienzo_url)
    lienzo = Image.open(io.BytesIO(lienzo_data)).convert('RGBA')
    W_l, H_l = lienzo.size

    # Cargar foto de fondo rotativa
    canvas = None
    bg_num = (bg_index % 7) + 1
    for ext in ['jpg', 'jpeg', 'png', 'webp']:
        try:
            bg_url = f'{RECURSOS}/farm-bg-{bg_num:02d}.{ext}'
            bg_data = descargar_imagen(bg_url)
            foto = Image.open(io.BytesIO(bg_data)).convert('RGB')
            ratio = max(W_l/foto.width, H_l/foto.height)
            new_w, new_h = int(foto.width*ratio), int(foto.height*ratio)
            foto = foto.resize((new_w, new_h), Image.LANCZOS)
            x_off = (new_w - W_l) // 2
            y_off = (new_h - H_l) // 2
            foto = foto.crop((x_off, y_off, x_off+W_l, y_off+H_l))
            canvas = foto.convert('RGBA')
            overlay = Image.new('RGBA', (W_l, H_l), (1, 65, 109, 180))
            canvas = Image.alpha_composite(canvas, overlay)
            print(f'Foto de fondo: farm-bg-{bg_num:02d}.{ext}')
            break
        except Exception as e:
            print(f'bg {bg_num}.{ext}: {e}')

    if canvas is None:
        canvas = Image.new('RGBA', (W_l, H_l), (1, 65, 109, 255))

    # Pegar lienzo encima
    canvas = Image.alpha_composite(canvas, lienzo)
    draw = ImageDraw.Draw(canvas)

    BLANCO = (255, 255, 255)
    CELESTE = (200, 230, 245)
    MARGIN = 60

    font_fecha   = ImageFont.truetype(font_path, 40)
    font_nombre  = ImageFont.truetype(font_path, 86)
    font_detalle = ImageFont.truetype(font_path, 40)
    font_manana  = ImageFont.truetype(font_path, 34)
    font_leyenda = ImageFont.truetype(font_path, 30)

    def draw_centered(text, y, font, fill):
        bbox = draw.textbbox((0,0), text, font=font)
        x = (W_l - (bbox[2]-bbox[0])) // 2
        draw.text((x, y), text, font=font, fill=fill)
        return bbox[3] - bbox[1]

    y = 430

    # Fecha
    h = draw_centered(fecha_hoy.capitalize(), y, font_fecha, CELESTE)
    y += h + 36

    # Separador
    draw.line([(MARGIN, y), (W_l-MARGIN, y)], fill=BLANCO, width=2)
    y += 32

    # Farmacias de hoy
    for farm in farmacias_hoy:
        nombre = farm.get('nombre', '')
        direccion = farm.get('dir', '')
        telefono = farm.get('tel', '')
        box_h = 260
        draw.rounded_rectangle([MARGIN, y, W_l-MARGIN, y+box_h], radius=20,
                               outline=(255,255,255), width=1)
        inner = Image.new('RGBA', (W_l-MARGIN*2-2, box_h-2), (255,255,255,25))
        canvas.paste(inner, (MARGIN+1, y+1), inner)
        draw = ImageDraw.Draw(canvas)
        h = draw_centered(nombre, y+24, font_nombre, BLANCO)
        ty = y + 24 + h + 12
        h = draw_centered(direccion, ty, font_detalle, CELESTE)
        ty += h + 10
        draw_centered(f"Tel: {telefono}", ty, font_detalle, BLANCO)
        y += box_h + 22

    # Leyenda horario
    draw.line([(MARGIN, y), (W_l-MARGIN, y)], fill=BLANCO, width=1)
    y += 20
    partes_hoy = fecha_hoy.split()
    partes_man = fecha_manana.split()
    h = draw_centered(f"Turnos desde las 9:00 del {partes_hoy[1]} de {' '.join(partes_hoy[2:])}", y, font_leyenda, CELESTE)
    y += h + 6
    h = draw_centered(f"hasta las 9:00 del {partes_man[1]} de {' '.join(partes_man[2:])}", y, font_leyenda, CELESTE)
    y += h + 40

    # Mañana de turno
    draw.line([(MARGIN, y), (W_l-MARGIN, y)], fill=BLANCO, width=1)
    y += 24
    h = draw_centered("MAÑANA DE TURNO:", y, font_manana, CELESTE)
    y += h + 20
    for nombre in farmacias_manana:
        h = draw_centered(nombre, y, font_detalle, BLANCO)
        y += h + 12

    output = io.BytesIO()
    canvas.convert('RGB').save(output, format='JPEG', quality=95)
    output.seek(0)
    return output


@app.route('/generar-farmacias', methods=['POST', 'OPTIONS'])
def generar_farmacias():
    if request.method == 'OPTIONS':
        return '', 204
    try:
        data = request.get_json()
        fecha_hoy      = data.get('fecha_hoy', '')
        fecha_manana   = data.get('fecha_manana', '')
        farmacias_hoy  = data.get('farmacias_hoy', [])
        farmacias_manana = data.get('farmacias_manana', [])
        if not farmacias_hoy:
            return jsonify({'error': 'Faltan farmacias_hoy'}), 400
        from datetime import date
        bg_index = date.today().timetuple().tm_yday  # rota por día del año
        imagen = generar_placa_farmacias(fecha_hoy, fecha_manana, farmacias_hoy, farmacias_manana, bg_index)
        return send_file(imagen, mimetype='image/jpeg', download_name='farmacias-turno.jpg')
    except Exception as e:
        print(f'Error en /generar-farmacias: {e}')
        return jsonify({'error': str(e)}), 500
