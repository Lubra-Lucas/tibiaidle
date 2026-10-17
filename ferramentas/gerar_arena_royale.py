#!/usr/bin/env python3
"""Monta o fundo da arena do Tibia Royale (royale/arena.png) e as torres (royale/torres.png + royale/torres.js)
com tiles reais do mapa de Thais (tibia-assets/mapas15/thais.js + atlas). Sempre com -I:

  python3 -I ferramentas/gerar_arena_royale.py [--saida royale/arena.png] [--semente 7]

Campo de 18 x 33 tiles (como o Clash Royale, com o rio de 3 tiles no meio) e 2 colunas de mata de cada lado.
Linhas 15-17 = rio (margem de cima, água, margem de baixo); pontes nas colunas 2-4 e 13-15;
trilhas de terra das torres até as pontes. As constantes batem com royale/index.html.
Torres: muralha de pedra (parede do forte ao norte de Thais) com piso de madeira e ameias; ruínas com entulho.
"""
import argparse
import json
import os
import random

from PIL import Image, ImageDraw, ImageEnhance

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CAMPO_W, CAMPO_H, MARGEM = 18, 33, 2

# chaves do atlas de Thais (escolhidas olhando o rio ao sul da cidade, x 72-96, y 127-140)
GRAMA = ["4", "5", "7", "1", "11", "90", "91", "15", "28", "22", "17"]
MARGEM_CIMA = ["602", "954", "604"]                        # grama em cima, água embaixo
AGUA = ["586", "585", "587"]
MARGEM_BAIXO = ["2329", "690", "687", "2420", "1087", "1032", "2121"]   # água em cima, grama embaixo
PONTE = {15: ["988", "989", "990"], 16: ["1010", "1011", "1012"], 17: ["1083", "1084", "1085"]}
TERRA = ["116", "117", "59", "55", "165", "166"]
ARVORES = ["764", "2304", "700"]
PEDRAS = ["33", "37", "43", "47", "106", "158", "249", "251"]
PONTES_X = (2, 13)        # primeira coluna de cada ponte (3 de largura)
PAREDE = ["1001", "1002", "1003", "1027", "1028", "1029", "941", "964"]   # face de muralha de pedra
PISO = ["646"]                                                             # piso de madeira do forte
TRILHAS_X = (3, 14)       # trilha de terra no meio de cada ponte, das torres das pontas até o rio


def carregar_thais():
    s = open(os.path.join(RAIZ, "tibia-assets/mapas15/thais.js"), encoding="utf-8").read()
    dec = json.JSONDecoder()
    t = "Object.assign(window.MAPAS_SPRITES.tiles,"
    sp, _ = dec.raw_decode(s[s.find(t) + len(t):])
    return sp


def escurecer(im, f):
    return ImageEnhance.Brightness(im).enhance(f)


def textura(spr, rnd, w, h, keys):
    im = Image.new("RGBA", (w, h))
    for y in range(0, h, 32):
        for x in range(0, w, 32):
            im.alpha_composite(spr(rnd.choice(keys)).crop((0, 0, 32, 32)), (x, y))
    return im


def torre(spr, rnd, n, ruina=False):
    """Torre de n x n tiles vista como no cliente: plataforma em cima e a parede da frente embaixo.
    A base da imagem coincide com a base do quadrado da torre; o topo passa um pouco para cima."""
    W = n * 32
    face = 48 if n == 3 else 56
    topo = W - 12
    H = topo + face + 4   # 4 px de folga em cima para as ameias
    im = Image.new("RGBA", (W, H))
    f = textura(spr, rnd, W, face + 32, PAREDE).crop((0, 0, W, face))
    px = f.load()
    for x in range(W):   # sombreado: laterais e pé da parede mais escuros, como uma torre redonda
        k = 1 - .45 * abs((x - (W - 1) / 2) / (W / 2)) ** 2
        for y in range(face):
            r, g, b, a = px[x, y]
            kk = k * (1 - .25 * y / face)
            px[x, y] = (int(r * kk), int(g * kk), int(b * kk), a)
    pedra = textura(spr, rnd, 64, 64, PAREDE)
    if ruina:   # só o pé da parede quebrado e entulho
        base = escurecer(f, .6).crop((0, face // 2, W, face))
        dr = ImageDraw.Draw(im)
        dr.ellipse((4, H - base.height - W // 3, W - 5, H - 2), fill=(84, 66, 46, 255))
        for x in range(0, W, 6):   # topo serrilhado
            h = rnd.randint(0, base.height // 2)
            im.alpha_composite(base.crop((x, h, min(W, x + 6), base.height)), (x, H - base.height + h))
        for _ in range(n * 7):
            w, h = rnd.randint(7, 13), rnd.randint(5, 9)
            x, y = rnd.randint(4, W - w - 4), rnd.randint(H - base.height - W // 3 + 4, H - h - 2)
            dr.rectangle((x - 1, y - 1, x + w, y + h), fill=(25, 22, 20, 255))
            im.alpha_composite(escurecer(pedra.crop((x % 40, y % 40, x % 40 + w, y % 40 + h)), rnd.uniform(.7, 1.1)), (x, y))
        return im
    im.alpha_composite(f, (0, topo + 4))
    im.alpha_composite(escurecer(textura(spr, rnd, W, topo, PAREDE).crop((0, 0, W, topo)), .85), (0, 4))
    im.alpha_composite(textura(spr, rnd, W, topo, PISO).crop((0, 0, W - 12, topo - 12)), (6, 10))
    ImageDraw.Draw(im).rectangle((6, 10, W - 7, topo - 3), outline=(40, 36, 32, 255))
    for x in range(0, W, 12):   # ameias na frente e atrás
        for yy, hh in ((0, 9), (topo - 9, 11)):
            m = escurecer(pedra.crop((x % 32, yy % 32, x % 32 + 8, yy % 32 + hh)), 1.15 if yy == 0 else 1)
            im.alpha_composite(m, (x + 2, yy + (0 if yy == 0 else 4)))
    for y in range(0, topo, 12):
        for xx in (0, W - 8):
            im.alpha_composite(escurecer(pedra.crop((0, y % 32, 8, y % 32 + 8)), .95), (xx, y + 4))
    return im


def balista(spr):
    """A balista das muralhas ao sul de Thais (x 79-80, y 126-127): três peças em 2 x 2 tiles."""
    im = Image.new("RGBA", (64, 64))
    for k, tx, ty in (("2436", 1, 0), ("2452", 0, 1), ("2454", 1, 1)):
        p = spr(k)
        im.alpha_composite(p, (tx * 32 + 32 - p.width, ty * 32 + 32 - p.height))
    return im


def tumulo():
    """Monte de terra de cova (item 11484) com uma caveira (item 3114) em cima, ampliados."""
    terra = Image.open(os.path.join(RAIZ, "tibia-assets/sprites15/itens/11484.png")).convert("RGBA").resize((64, 64), Image.NEAREST)
    caveira = Image.open(os.path.join(RAIZ, "tibia-assets/sprites15/itens/3114.png")).convert("RGBA").resize((48, 48), Image.NEAREST)
    im = Image.new("RGBA", (64, 64))
    im.alpha_composite(terra, (0, 0))
    im.alpha_composite(caveira, (10, -4))
    return im


def exportar_torres(spr, rnd, pasta):
    pecas = [("princesa", torre(spr, rnd, 3)), ("rei", torre(spr, rnd, 4)),
             ("ruina3", torre(spr, rnd, 3, True)), ("ruina4", torre(spr, rnd, 4, True)),
             ("balista", balista(spr)), ("tumulo", tumulo())]
    W, H = sum(p.width for _, p in pecas) + 2 * len(pecas), max(p.height for _, p in pecas)
    atlas, meta, x = Image.new("RGBA", (W, H)), {}, 0
    for nome, p in pecas:
        atlas.alpha_composite(p, (x, 0))
        meta[nome] = {"x": x, "w": p.width, "h": p.height}
        x += p.width + 2
    atlas.save(os.path.join(pasta, "torres.png"), optimize=True)
    with open(os.path.join(pasta, "torres.js"), "w", encoding="utf-8") as f:
        f.write("/* gerado por ferramentas/gerar_arena_royale.py: torres, ruínas e construções (base da imagem = base do quadrado) */\n")
        f.write("window.TORRES_SPR=" + json.dumps(meta, separators=(",", ":")) + ";\n")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", default=os.path.join(RAIZ, "royale/arena.png"))
    ap.add_argument("--semente", type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.semente)
    sp = carregar_thais()
    atlas = {}

    def spr(k):
        t = sp["thais:" + k]
        if t["src"] not in atlas:
            atlas[t["src"]] = Image.open(os.path.join(RAIZ, t["src"])).convert("RGBA")
        return atlas[t["src"]].crop((t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]))

    W, H = CAMPO_W + 2 * MARGEM, CAMPO_H
    im = Image.new("RGBA", (W * 32, H * 32), (0, 0, 0, 255))

    def chao(x, y, k):
        im.alpha_composite(spr(k), ((x + MARGEM) * 32, y * 32))

    def objeto(x, y, k):
        s = spr(k)
        im.alpha_composite(s, ((x + MARGEM) * 32 + 32 - s.width, y * 32 + 32 - s.height))

    for y in range(H):
        for x in range(-MARGEM, CAMPO_W + MARGEM):
            ponte = y in PONTE and any(px <= x < px + 3 for px in PONTES_X)
            if ponte:
                chao(x, y, PONTE[y][x - (PONTES_X[0] if x < 9 else PONTES_X[1])])
            elif y == 15:
                chao(x, y, rnd.choice(MARGEM_CIMA))
            elif y == 16:
                chao(x, y, rnd.choice(AGUA))
            elif y == 17:
                chao(x, y, rnd.choice(MARGEM_BAIXO))
            elif x in TRILHAS_X and (5 <= y <= 14 or 18 <= y <= 27):
                chao(x, y, rnd.choice(TERRA))
            else:
                chao(x, y, rnd.choice(GRAMA))
    # mata nas laterais (fora do campo), de cima para baixo para as copas se sobreporem direito
    for y in range(H):
        if 15 <= y <= 17:
            continue
        for x in (-1, CAMPO_W + MARGEM - 1):   # objetos de 64 px ancorados embaixo à direita: ocupam só a margem
            r = rnd.random()
            if r < .65:
                objeto(x, y, rnd.choice(ARVORES))
            elif r < .9:
                objeto(x, y, rnd.choice(PEDRAS))
    os.makedirs(os.path.dirname(a.saida), exist_ok=True)
    im.convert("RGB").save(a.saida, optimize=True)
    print(a.saida, im.size)
    print(exportar_torres(spr, random.Random(a.semente), os.path.dirname(a.saida)))


if __name__ == "__main__":
    main()
