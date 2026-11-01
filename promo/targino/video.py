"""Renderiza o vídeo promocional vertical (1080x1920, 30 qps) da Targino Custom Pedals.

Uso: python3 video.py <trilha.wav> <saida.mp4>
Se existir a pasta fotos/ com arquivos <identificador>.png|jpg (ex.: fotos/rage.jpg),
a foto real substitui a ilustração do pedal correspondente.
"""
import math
import os
import subprocess
import sys
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1080, 1920, 30
TOTAL = 37.0
AQUI = os.path.dirname(os.path.abspath(__file__))

BOLD = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
REG = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
SERIF = '/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'

FUNDO = (14, 12, 11)
AMBAR = (255, 122, 26)
CREME = (242, 230, 208)
CINZA = (150, 140, 128)

PEDAIS = [
    # identificador, nome, categoria, frase, cor do gabinete, rótulos dos botões
    ('bravo', 'BRAVO', 'Reforço de sinal limpo', 'Mais volume. O mesmo timbre.\nSeu amplificador, só que maior.',
     (232, 224, 205), ['VOLUME']),
    ('pure', 'PURE OVERDRIVE', 'Saturação', 'Drive orgânico que responde\nà força da sua palheta.',
     (46, 120, 78), ['GANHO', 'TOM', 'NÍVEL']),
    ('dual', 'DUAL DRIVE', 'Saturação dupla', 'Dois sabores de drive\nem um único pedal.',
     (230, 110, 30), ['GANHO', 'TOM', 'GANHO', 'TOM']),
    ('rage', 'RAGE', 'Distorção', 'Do médio ao alto ganho.\nPeso sem embolar.',
     (178, 24, 30), ['GANHO', 'TOM', 'VOL']),
    ('fuzz', 'FUZZ', 'Fuzz de pegada russa', 'Sustain sem fim.\nUma parede de som.',
     (88, 46, 130), ['SUST', 'TOM', 'VOL']),
    ('comp', 'COMPRESSOR', 'Compressor óptico', 'Dinâmica sob controle,\nnotas que florescem.',
     (40, 92, 160), ['COMP', 'NÍVEL']),
    ('plexi', 'PLEXI IN A BOX', 'Timbre de amplificador britânico', 'O rugido clássico dos anos 60\naos seus pés.',
     (30, 28, 26), ['PRES', 'GRAVE', 'AGUDO', 'VOL']),
    ('trio', 'TRIOZÃO', 'Distorção + modulação + eco', 'Três efeitos independentes.\nUm só gabinete.',
     (170, 172, 176), ['DIST', 'MODUL', 'ECO']),
]

# Linha do tempo (segundos)
T_HOOK, T_TENSAO, T_MARCA, T_PEDAIS, T_ARTE, T_ROCK, T_LOUVOR, T_CTA = 0, 3, 6, 10, 22, 26, 28, 30
DUR_PEDAL = 1.5


# ---------------------------------------------------------------- utilidades
def ease_out(x):
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def ease_in_out(x):
    x = min(max(x, 0.0), 1.0)
    return 3 * x * x - 2 * x * x * x


def prog(t, a, d):
    return min(max((t - a) / d, 0.0), 1.0)


@lru_cache(maxsize=None)
def fonte(caminho, tam):
    return ImageFont.truetype(caminho, tam)


@lru_cache(maxsize=None)
def texto_img(txt, tam, cor=CREME, caminho=BOLD, espaco=1.15, alinhamento='center', sombra=True,
              tracking=0):
    """Renderiza texto multilinhas em camada RGBA (com sombra suave)."""
    f = fonte(caminho, tam)
    linhas = txt.split('\n')
    alt_linha = int(tam * espaco)

    def largura(l):
        return f.getlength(l) + tracking * max(len(l) - 1, 0)

    larg = int(max(largura(l) for l in linhas)) + 40
    alt = alt_linha * len(linhas) + 40
    img = Image.new('RGBA', (larg, alt), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(linhas):
        lw = largura(l)
        x = 20 + {'center': (larg - 40 - lw) / 2, 'left': 0}[alinhamento]
        y = 20 + i * alt_linha
        if tracking:
            for ch in l:
                d.text((x, y), ch, font=f, fill=cor + (255,))
                x += f.getlength(ch) + tracking
        else:
            d.text((x, y), l, font=f, fill=cor + (255,))
    if sombra:
        s = Image.new('RGBA', img.size, (0, 0, 0, 0))
        s.putalpha(img.getchannel('A').filter(ImageFilter.GaussianBlur(10)).point(lambda v: v * 0.8))
        s.alpha_composite(img)
        img = s
    return img


def colar(base, img, cx, cy, alfa=1.0, escala=1.0):
    if alfa <= 0.01:
        return
    if abs(escala - 1) > 0.002:
        img = img.resize((max(1, int(img.width * escala)), max(1, int(img.height * escala))),
                         Image.LANCZOS)
    if alfa < 0.999:
        img = img.copy()
        img.putalpha(img.getchannel('A').point(lambda v: int(v * alfa)))
    base.alpha_composite(img, (int(cx - img.width / 2), int(cy - img.height / 2)))


def texto(base, txt, cx, cy, tam, t_ini, t, cor=CREME, caminho=BOLD, sobe=60, dur=0.35, **kw):
    """Texto que entra subindo com esmaecimento."""
    p = ease_out(prog(t, t_ini, dur))
    if p <= 0:
        return
    colar(base, texto_img(txt, tam, cor, caminho, **kw), cx, cy + (1 - p) * sobe, p)


# ---------------------------------------------------------------- texturas
def _fundo_base():
    y, x = np.mgrid[0:H, 0:W]
    r = np.sqrt(((x - W / 2) / W) ** 2 + ((y - H * 0.45) / H) ** 2)
    vinheta = np.clip(1.15 - r * 1.6, 0.25, 1)[..., None]
    arr = np.array(FUNDO, np.float32)[None, None, :] * vinheta * 1.6
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).convert('RGBA')


FUNDO_IMG = None
GRAOS = []


def preparar_texturas():
    global FUNDO_IMG
    FUNDO_IMG = _fundo_base()
    rng = np.random.default_rng(3)
    for _ in range(6):
        g = rng.normal(0, 1, (H // 2, W // 2))
        a = np.clip(np.abs(g) * 6, 0, 14).astype(np.uint8)
        v = np.where(g > 0, 255, 0).astype(np.uint8)
        img = Image.merge('RGBA', [Image.fromarray(v)] * 3 + [Image.fromarray(a)])
        GRAOS.append(img.resize((W, H), Image.NEAREST))


@lru_cache(maxsize=None)
def brilho(raio, cor, intensidade=180):
    tam = raio * 2
    y, x = np.mgrid[0:tam, 0:tam]
    d = np.sqrt((x - raio) ** 2 + (y - raio) ** 2) / raio
    a = (np.clip(1 - d, 0, 1) ** 2.2 * intensidade).astype(np.uint8)
    img = Image.new('RGBA', (tam, tam), cor + (0,))
    img.putalpha(Image.fromarray(a))
    return img


# ---------------------------------------------------------------- pedais
@lru_cache(maxsize=None)
def pedal_img(idx, larg=520):
    ident, nome, categoria, _, cor, botoes = PEDAIS[idx]
    for ext in ('png', 'jpg', 'jpeg'):
        foto = os.path.join(AQUI, 'fotos', f'{ident}.{ext}')
        if os.path.exists(foto):
            im = Image.open(foto).convert('RGBA')
            im.thumbnail((larg, int(larg * 1.6)))
            return im
    S = 3  # superamostragem para bordas suaves
    w, h = larg * S, int(larg * 1.45) * S
    pad = 40 * S
    img = Image.new('RGBA', (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # sombra
    sombra = Image.new('L', img.size, 0)
    ImageDraw.Draw(sombra).rounded_rectangle((pad + 10 * S, pad + 30 * S, pad + w - 10 * S, pad + h + 18 * S),
                                             radius=40 * S, fill=170)
    sombra = sombra.filter(ImageFilter.GaussianBlur(22 * S))
    img.putalpha(sombra)
    img = Image.merge('RGBA', (Image.new('L', img.size, 0),) * 3 + (sombra,))
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = pad, pad, pad + w, pad + h
    escuro = tuple(int(c * 0.62) for c in cor)
    claro = tuple(min(255, int(c * 1.18 + 18)) for c in cor)
    d.rounded_rectangle((x0, y0, x1, y1), radius=38 * S, fill=escuro)
    d.rounded_rectangle((x0 + 6 * S, y0 + 4 * S, x1 - 6 * S, y1 - 10 * S), radius=34 * S, fill=cor)
    # reflexo superior
    d.rounded_rectangle((x0 + 14 * S, y0 + 10 * S, x1 - 14 * S, y0 + 60 * S), radius=26 * S, fill=claro)
    d.rectangle((x0 + 14 * S, y0 + 40 * S, x1 - 14 * S, y0 + 62 * S), fill=cor)
    lum = sum(cor) / 3
    tinta = (25, 22, 20) if lum > 150 else (240, 232, 218)
    # botões
    n = len(botoes)
    linhas = [botoes] if n <= 3 else [botoes[:2], botoes[2:]]
    raio = (62 if n <= 2 else 52 if n == 3 else 42) * S
    fl = fonte(BOLD, 22 * S)
    for li, linha in enumerate(linhas):
        cy = y0 + ((150 if len(linhas) == 1 else 115) + li * 150) * S
        for bi, rot in enumerate(linha):
            cx = x0 + w * (bi + 1) / (len(linha) + 1)
            d.ellipse((cx - raio, cy - raio + 8 * S, cx + raio, cy + raio + 8 * S), fill=(0, 0, 0))
            d.ellipse((cx - raio, cy - raio, cx + raio, cy + raio), fill=(28, 26, 25))
            d.ellipse((cx - raio * 0.82, cy - raio * 0.82, cx + raio * 0.82, cy + raio * 0.82),
                      fill=(48, 45, 43))
            ang = math.radians(-130 + (bi * 67 + li * 41) % 200)
            d.line((cx, cy, cx + math.sin(ang) * raio * 0.75, cy - math.cos(ang) * raio * 0.75),
                   fill=CREME, width=7 * S)
            tw = fl.getlength(rot)
            d.text((cx - tw / 2, cy + raio + 16 * S), rot, font=fl, fill=tinta)
    # nome do pedal
    fy = y0 + (360 if len(linhas) == 1 else 405) * S
    tam = 74 if len(nome) <= 6 else 56 if len(nome) <= 10 else 46
    fn = fonte(BOLD, tam * S)
    tw = fn.getlength(nome)
    d.text(((x0 + x1) / 2 - tw / 2, fy), nome, font=fn, fill=tinta)
    fm = fonte(REG, 22 * S)
    marca = 'T A R G I N O   C U S T O M   P E D A L S'
    tw = fm.getlength(marca)
    d.text(((x0 + x1) / 2 - tw / 2, fy + (tam + 22) * S), marca, font=fm, fill=tinta)
    # LED e pedal de acionamento
    led_y = y1 - 210 * S
    cx = (x0 + x1) / 2
    d.ellipse((cx - 16 * S, led_y - 16 * S, cx + 16 * S, led_y + 16 * S), fill=(255, 40, 30))
    d.ellipse((cx - 7 * S, led_y - 9 * S, cx + 3 * S, led_y - 1 * S), fill=(255, 190, 170))
    n_sw = 3 if PEDAIS[idx][0] == 'trio' else 2 if PEDAIS[idx][0] == 'dual' else 1
    sw_y = y1 - 110 * S
    for k in range(n_sw):
        sx = x0 + w * (k + 1) / (n_sw + 1)
        d.ellipse((sx - 58 * S, sw_y - 58 * S, sx + 58 * S, sw_y + 58 * S), fill=(120, 120, 124))
        d.ellipse((sx - 46 * S, sw_y - 46 * S, sx + 46 * S, sw_y + 46 * S), fill=(205, 205, 210))
        d.ellipse((sx - 30 * S, sw_y - 34 * S, sx + 22 * S, sw_y + 14 * S), fill=(235, 235, 240))
    # parafusos
    for px, py in ((x0 + 30 * S, y0 + 30 * S), (x1 - 30 * S, y0 + 30 * S),
                   (x0 + 30 * S, y1 - 40 * S), (x1 - 30 * S, y1 - 40 * S)):
        d.ellipse((px - 9 * S, py - 9 * S, px + 9 * S, py + 9 * S), fill=escuro)
    return img.resize((img.width // S, img.height // S), Image.LANCZOS)


def led_brilho(base, pedal, cx, cy, escala, t):
    """Halo do LED aceso (pulsando no tempo da música)."""
    ph = 0.75 + 0.25 * math.cos(2 * math.pi * t * 2)
    led_y = cy + (pedal.height / 2 - 40 - 210) * escala
    colar(base, brilho(70, (255, 50, 30), int(200 * ph)), cx, led_y, 1.0, escala)


# ---------------------------------------------------------------- cenas
def cena_gancho(base, t):
    # 0–3 s: pergunta-gancho, com "tremor" no ataque do acorde.
    tremor = max(0, 1 - t / 0.5) * 14
    dx = math.sin(t * 90) * tremor
    texto(base, 'Seu timbre', W / 2 + dx, 760, 96, 0.05, t, dur=0.25)
    texto(base, 'soa igual ao de', W / 2 + dx, 880, 96, 0.25, t, dur=0.25)
    texto(base, 'todo mundo?', W / 2 + dx, 1010, 118, 0.5, t, cor=AMBAR, dur=0.25)
    # risco de "cabo" descendo
    p = ease_out(prog(t, 0.8, 1.5))
    ImageDraw.Draw(base).line((W / 2, 1120, W / 2, 1120 + 260 * p), fill=AMBAR + (255,), width=6)


def cena_tensao(base, t):
    texto(base, 'Pedal de prateleira', W / 2, 760, 82, T_TENSAO, t, cor=CINZA)
    texto(base, 'é feito para milhões.', W / 2, 860, 82, T_TENSAO + 0.25, t, cor=CINZA)
    texto(base, 'O seu deveria ser', W / 2, 1060, 92, T_TENSAO + 1.3, t)
    p = ease_out(prog(t, T_TENSAO + 1.8, 0.3))
    if p > 0:
        esc = 1.0 + 0.25 * (1 - p) + 0.03 * math.sin((t - T_TENSAO) * 4 * math.pi)
        colar(base, texto_img('feito para VOCÊ.', 104, AMBAR), W / 2, 1180, p, esc)


def cena_marca(base, t):
    lt = t - T_MARCA
    # clarão de entrada no "drop"
    if lt < 0.25:
        flash = Image.new('RGBA', (W, H), (255, 160, 80, int(200 * (1 - lt / 0.25))))
        base.alpha_composite(flash)
    pulso = 0.8 + 0.2 * math.cos(2 * math.pi * lt * 2)
    colar(base, brilho(420, AMBAR, int(120 * pulso)), W / 2, 880, ease_out(prog(lt, 0, 0.6)))
    p = ease_out(prog(lt, 0.05, 0.5))
    colar(base, texto_img('TARGINO', 190, CREME, SERIF, tracking=6), W / 2, 820, p, 1.25 - 0.25 * p)
    texto(base, 'C U S T O M   P E D A L S', W / 2, 960, 50, T_MARCA + 0.4, t, cor=AMBAR)
    p2 = ease_out(prog(lt, 0.7, 0.5))
    d = ImageDraw.Draw(base)
    d.line((W / 2 - 300 * p2, 1050, W / 2 + 300 * p2, 1050), fill=CREME + (200,), width=3)
    texto(base, 'Pedais de efeito artesanais\npara guitarra e baixo', W / 2, 1170, 52, T_MARCA + 1.0, t,
          caminho=REG)
    texto(base, 'Feitos à mão em Guaraciaba do Norte · Ceará', W / 2, 1330, 38, T_MARCA + 1.6, t,
          cor=CINZA, caminho=REG)


def cena_pedais(base, t):
    lt = t - T_PEDAIS
    i = min(int(lt // DUR_PEDAL), len(PEDAIS) - 1)
    pt = lt - i * DUR_PEDAL
    ident, nome, categoria, frase, cor, _ = PEDAIS[i]
    # halo da cor do pedal
    colar(base, brilho(520, cor, 110), W / 2, 820, ease_out(prog(pt, 0, 0.3)))
    ped = pedal_img(i)
    entrada = ease_out(prog(pt, 0, 0.32))
    saida = ease_in_out(prog(pt, DUR_PEDAL - 0.18, 0.18)) if i < len(PEDAIS) - 1 else \
        ease_in_out(prog(pt, DUR_PEDAL - 0.25, 0.25))
    cx = W / 2 + (1 - entrada) * 700 - saida * 700
    esc = 0.98 + 0.04 * ease_out(prog(pt, 0, DUR_PEDAL))
    flut = math.sin(pt * 3) * 6
    colar(base, ped, cx, 800 + flut, 1 - saida * 0.6, esc)
    if not os.path.exists(os.path.join(AQUI, 'fotos')):
        led_brilho(base, ped, cx, 800 + flut, esc, t)
    # rótulos
    alfa = 1 - saida
    colar(base, texto_img(categoria.upper(), 40, AMBAR, BOLD, tracking=3), W / 2,
          1330 + (1 - ease_out(prog(pt, 0.1, 0.3))) * 40, ease_out(prog(pt, 0.1, 0.3)) * alfa)
    colar(base, texto_img(frase, 52, CREME, REG), W / 2,
          1460 + (1 - ease_out(prog(pt, 0.2, 0.3))) * 40, ease_out(prog(pt, 0.2, 0.3)) * alfa)
    # contador de catálogo
    colar(base, texto_img(f'{i + 1:02d} / {len(PEDAIS):02d}', 30, CINZA, REG), W / 2, 1640, 0.9)
    # chamada fixa no topo
    colar(base, texto_img('CATÁLOGO TARGINO', 34, CINZA, BOLD, tracking=8), W / 2, 230,
          ease_out(prog(lt, 0, 0.4)))


def cena_arte(base, t):
    texto(base, 'Nada de linha de montagem.', W / 2, 520, 62, T_ARTE, t, cor=CINZA)
    texto(base, 'Feito à mão,\npeça por peça.', W / 2, 700, 104, T_ARTE + 0.3, t)
    itens = ['Montagem artesanal, um a um', 'Projeto pensado para o palco',
             'Timbre ajustado ao seu jeito de tocar', 'Atendimento direto com o construtor']
    for k, it in enumerate(itens):
        ti = T_ARTE + 1.0 + k * 0.5
        p = ease_out(prog(t, ti, 0.3))
        if p <= 0:
            continue
        y = 1010 + k * 120
        x = 90 + (1 - p) * -80
        d = ImageDraw.Draw(base)
        d.rounded_rectangle((x, y - 26, x + 52, y + 26), radius=10, outline=AMBAR + (int(255 * p),), width=5)
        if p > 0.6:
            d.line((x + 12, y, x + 23, y + 12, x + 41, y - 13), fill=AMBAR + (255,), width=6)
        img = texto_img(it, 42, CREME, REG, alinhamento='left', sombra=False)
        colar(base, img, x + 80 + img.width / 2 - 20, y, p)


def cena_publicos(base, t):
    if t < T_LOUVOR:
        lt = t - T_ROCK
        colar(base, brilho(560, (200, 30, 20), 150), W / 2, 980, ease_out(prog(lt, 0, 0.4)))
        tremor = max(0, 1 - lt / 0.4) * 10
        texto(base, 'Do peso do rock', W / 2 + math.sin(t * 80) * tremor, 860, 90, T_ROCK, t, dur=0.25)
        texto(base, 'no palco de sábado...', W / 2, 1000, 64, T_ROCK + 0.5, t, cor=CINZA, caminho=REG)
        for k, (pi, dx) in enumerate(((3, -260), (4, 260))):
            p = ease_out(prog(lt, 0.6 + k * 0.2, 0.4))
            colar(base, pedal_img(pi), W / 2 + dx, 1440 + (1 - p) * 200, p, 0.62)
    else:
        lt = t - T_LOUVOR
        luz = ease_out(prog(lt, 0, 0.8))
        colar(base, brilho(640, (255, 214, 150), int(130 * luz)), W / 2, 700, 1.0)
        # raios de luz suaves descendo
        camada = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        dd = ImageDraw.Draw(camada)
        for k in range(5):
            x = 240 + k * 150
            dd.polygon([(x, 0), (x + 40, 0), (x + 220, H), (x + 120, H)], fill=(255, 225, 170, int(18 * luz)))
        base.alpha_composite(camada.filter(ImageFilter.GaussianBlur(30)))
        texto(base, '...à atmosfera do louvor', W / 2, 860, 68, T_LOUVOR, t, cor=(255, 226, 180), dur=0.6,
              caminho=SERIF)
        texto(base, 'no culto de domingo.', W / 2, 1000, 64, T_LOUVOR + 0.5, t, cor=CINZA, caminho=REG, dur=0.6)
        for k, (pi, dx) in enumerate(((5, -260), (0, 260))):
            p = ease_out(prog(lt, 0.6 + k * 0.2, 0.6))
            colar(base, pedal_img(pi), W / 2 + dx, 1440 + (1 - p) * 120, p, 0.62)


def cena_cta(base, t):
    lt = t - T_CTA
    colar(base, brilho(520, AMBAR, 110), W / 2, 760, ease_out(prog(lt, 0, 0.5)))
    texto(base, 'Seu som.', W / 2, 520, 110, T_CTA, t)
    texto(base, 'Sua assinatura.', W / 2, 650, 110, T_CTA + 0.35, t, cor=AMBAR)
    texto(base, 'Encomende seu pedal\npersonalizado', W / 2, 870, 64, T_CTA + 1.0, t, caminho=REG)
    texto(base, 'Produção artesanal em pequena escala:\ngaranta já o seu lugar na fila.', W / 2, 1050, 40,
          T_CTA + 1.6, t, cor=CINZA, caminho=REG)
    # botão "chame no direct" pulsando no tempo
    p = ease_out(prog(lt, 2.2, 0.4))
    if p > 0:
        pulso = 1 + 0.035 * max(0.0, math.cos(2 * math.pi * (lt - 2.2) * 2))
        bw, bh = 760, 150
        botao = Image.new('RGBA', (bw + 40, bh + 40), (0, 0, 0, 0))
        db = ImageDraw.Draw(botao)
        db.rounded_rectangle((20, 20, 20 + bw, 20 + bh), radius=75, fill=AMBAR + (255,))
        f = fonte(BOLD, 60)
        txt = '@targinocustomp'
        db.text((20 + bw / 2 - f.getlength(txt) / 2, 20 + bh / 2 - 38), txt, font=f, fill=(20, 16, 14))
        colar(base, botao, W / 2, 1290, p, pulso * (0.9 + 0.1 * p))
        texto(base, 'Mande uma mensagem no Instagram', W / 2, 1430, 48, T_CTA + 2.5, t, caminho=REG)
    p3 = ease_out(prog(lt, 3.2, 0.6))
    colar(base, texto_img('TARGINO', 70, CREME, SERIF, tracking=4), W / 2, 1640, p3)
    colar(base, texto_img('C U S T O M   P E D A L S', 26, AMBAR, BOLD), W / 2, 1712, p3)


CENAS = [(T_HOOK, T_TENSAO, cena_gancho), (T_TENSAO, T_MARCA, cena_tensao), (T_MARCA, T_PEDAIS, cena_marca),
         (T_PEDAIS, T_ARTE, cena_pedais), (T_ARTE, T_ROCK, cena_arte), (T_ROCK, T_CTA, cena_publicos),
         (T_CTA, TOTAL + 1, cena_cta)]


def quadro(n):
    t = n / FPS
    base = FUNDO_IMG.copy()
    for a, b, fn in CENAS:
        if a <= t < b:
            fn(base, t)
            # transição: escurecimento curto nas trocas de cena
            borda = min(t - a, b - t)
            if borda < 0.08 and a > 0:
                base.alpha_composite(Image.new('RGBA', (W, H), (0, 0, 0, int(255 * (1 - borda / 0.08)))))
            break
    base.alpha_composite(GRAOS[0])  # granulação estática: arquivo leve
    # barra de progresso discreta (estimula assistir até o fim)
    ImageDraw.Draw(base).rectangle((0, H - 8, int(W * t / TOTAL), H), fill=AMBAR + (255,))
    # escurecimento final
    if t > TOTAL - 0.8:
        base.alpha_composite(Image.new('RGBA', (W, H), (0, 0, 0, int(255 * prog(t, TOTAL - 0.8, 0.8)))))
    return base.convert('RGB')


def main():
    trilha, saida = sys.argv[1], sys.argv[2]
    preparar_texturas()
    if len(sys.argv) > 3:  # modo de pré-visualização: salva quadros isolados
        for s in sys.argv[3:]:
            quadro(int(float(s) * FPS)).save(f'{saida}_{s}.png')
        return
    ff = subprocess.Popen(
        ['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
         '-r', str(FPS), '-i', '-', '-i', trilha, '-c:v', 'libx264', '-preset', 'medium', '-crf', '22',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k', '-shortest', '-movflags', '+faststart', saida],
        stdin=subprocess.PIPE)
    total = int(TOTAL * FPS)
    for n in range(total):
        ff.stdin.write(quadro(n).tobytes())
        if n % 150 == 0:
            print(f'{n}/{total}', flush=True)
    ff.stdin.close()
    ff.wait()
    print('ok', saida)


if __name__ == '__main__':
    main()
