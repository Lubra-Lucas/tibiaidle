#!/usr/bin/env python3
"""Monta o fundo da arena do Tibia Royale (royale/arena.png) com tiles reais do mapa de Thais
(tibia-assets/mapas15/thais.js + atlas). Sempre com -I:

  python3 -I ferramentas/gerar_arena_royale.py [--saida royale/arena.png] [--semente 7]

Campo de 18 x 33 tiles (como o Clash Royale, com o rio de 3 tiles no meio) e 2 colunas de mata de cada lado.
Linhas 15-17 = rio (margem de cima, água, margem de baixo); pontes nas colunas 2-4 e 13-15;
trilhas de terra das torres até as pontes. As constantes batem com royale/index.html.
"""
import argparse
import json
import os
import random

from PIL import Image

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
TRILHAS_X = (3, 14)       # trilha de terra no meio de cada ponte, das torres das pontas até o rio


def carregar_thais():
    s = open(os.path.join(RAIZ, "tibia-assets/mapas15/thais.js"), encoding="utf-8").read()
    dec = json.JSONDecoder()
    t = "Object.assign(window.MAPAS_SPRITES.tiles,"
    sp, _ = dec.raw_decode(s[s.find(t) + len(t):])
    return sp


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


if __name__ == "__main__":
    main()
