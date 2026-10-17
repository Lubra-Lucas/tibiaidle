#!/usr/bin/env python3
"""Extrai sprites de itens/objetos de um cliente Tibia (Tibia.dat + Tibia.spr, formato legado
10.x+ com ids de sprite u32 / "extended", como os clientes convertidos para OTClient).

Os arquivos do cliente NAO fazem parte do repositorio (sao enormes) - aponte para eles com
--dat / --spr. So os PNGs gerados e esta ferramenta ficam no repo.

Uso (sempre com -I):
  python3 -I ferramentas/extrair_cliente.py --dat Tibia.dat --spr Tibia.spr --info
  python3 -I ferramentas/extrair_cliente.py --dat ... --spr ... --itens 3031,28552 --saida tibia-assets/sprites15/itens
  python3 -I ferramentas/extrair_cliente.py --dat ... --spr ... --sheet 36040 --saida dir   # fases de animacao em tira horizontal
  python3 -I ferramentas/extrair_cliente.py --dat ... --spr ... --criaturas 21,demon=35:0,0,0,0 --saida dir   # folha de criatura (outfit)
  python3 -I ferramentas/extrair_cliente.py --nomes items.xml --buscar "exercise sword"      # id -> nome (items.xml do Canary)

Formato (variante detectada por tentativa em detectar()):
  dat: u32 assinatura, u16 itens/outfits/efeitos/missiles (ids maximos); por coisa: lista de flags
       (tabela 10.10+, com market 0x22, usable 0x23, wrapable/unwrapable/topeffect 0x24-0x26) ate 0xFF;
       dims w,h,[exactSize se w>1||h>1],camadas,padX,padY,padZ,fases; fases>1 => bloco de animacao
       (async u8, loop i32, inicio i8, min/max u32 por fase); ids de sprite u32.
  spr: u32 assinatura, u32 contagem, u32 offsets[contagem]; cada sprite: 3 bytes chave de cor, u16 tamanho,
       RLE (u16 transparentes, u16 coloridos, pixels RGB ou RGBA).
"""
import argparse
import json
import os
import struct
import sys
import xml.etree.ElementTree as ET

from PIL import Image

CAT_ITEM, CAT_OUTFIT, CAT_EFFECT, CAT_MISSILE = 0, 1, 2, 3
FIRST_ITEM_ID = 100


class Grupo:
    pass


class Coisa:
    def __init__(self, cat, tid):
        self.cat, self.id = cat, tid
        self.flags = {}
        self.market = None
        self.grupos = []


class Dat:
    """Parser do Tibia.dat. Variante: grupos (frame groups em outfits), enh (bloco de animacao avancado),
    ext (sprite ids u32), usable (bytes de payload da flag 0x23)."""

    PAYLOAD = {0x00: 2, 0x08: 2, 0x09: 2, 0x16: 4, 0x19: 4, 0x1A: 2, 0x1D: 2, 0x1E: 2, 0x21: 2}
    SEM_PAYLOAD = set(range(0x01, 0x08)) | set(range(0x0A, 0x16)) | {0x17, 0x18, 0x1B, 0x1C, 0x1F, 0x20,
                                                                      0x24, 0x25, 0x26, 0xFE}
    NOMES = {0x00: "ground", 0x01: "clip", 0x02: "bottom", 0x03: "top", 0x04: "container", 0x05: "stackable",
             0x06: "forceuse", 0x07: "multiuse", 0x08: "writable", 0x09: "writableonce", 0x0A: "fluid",
             0x0B: "splash", 0x0C: "unpass", 0x0D: "unmove", 0x0E: "blockmissile", 0x0F: "blockpath",
             0x10: "nomoveanim", 0x11: "pickupable", 0x12: "hangable", 0x13: "hooksouth", 0x14: "hookeast",
             0x15: "rotatable", 0x16: "light", 0x17: "donthide", 0x18: "translucent", 0x19: "displacement",
             0x1A: "elevation", 0x1B: "lyingcorpse", 0x1C: "animatealways", 0x1D: "minimap", 0x1E: "lenshelp",
             0x1F: "fullground", 0x20: "look", 0x21: "cloth", 0x22: "market", 0x23: "usable", 0x24: "wrapable",
             0x25: "unwrapable", 0x26: "topeffect", 0xFE: "usable"}

    def __init__(self, caminho, grupos=True, enh=True, ext=True, usable=2):
        with open(caminho, "rb") as f:
            self.b = f.read()
        self.grupos, self.enh, self.ext = grupos, enh, ext
        self.payload = dict(self.PAYLOAD)
        self.payload[0x23] = usable
        self.assinatura, = struct.unpack_from("<I", self.b, 0)
        self.n_item, self.n_outfit, self.n_efeito, self.n_missil = struct.unpack_from("<4H", self.b, 4)
        self.cats = [{}, {}, {}, {}]
        self.fim = 0

    def parse(self):
        b, p = self.b, 12
        U16 = struct.Struct("<H").unpack_from
        faixas = [(CAT_ITEM, FIRST_ITEM_ID, self.n_item), (CAT_OUTFIT, 1, self.n_outfit),
                  (CAT_EFFECT, 1, self.n_efeito), (CAT_MISSILE, 1, self.n_missil)]
        for cat, ini, fim in faixas:
            for tid in range(ini, fim + 1):
                t = Coisa(cat, tid)
                while True:
                    f = b[p]
                    p += 1
                    if f == 0xFF:
                        break
                    if f == 0x22:  # market: categoria, comerciar como, mostrar como, nome, profissao, nivel
                        nl = U16(b, p + 6)[0]
                        t.market = (U16(b, p)[0], U16(b, p + 2)[0], U16(b, p + 4)[0],
                                    b[p + 8:p + 8 + nl].decode("latin-1"), U16(b, p + 8 + nl)[0], U16(b, p + 10 + nl)[0])
                        t.flags["market"] = t.market
                        p += 12 + nl
                    elif f in self.payload:
                        n = self.payload[f]
                        t.flags[self.NOMES[f]] = b[p:p + n]
                        p += n
                    elif f in self.SEM_PAYLOAD:
                        t.flags[self.NOMES[f]] = True
                    else:
                        raise ValueError(f"flag desconhecida 0x{f:02X} em cat {cat} id {tid} offset {p - 1}")
                ngrupos = 1
                if cat == CAT_OUTFIT and self.grupos:
                    ngrupos = b[p]
                    p += 1
                for _ in range(ngrupos):
                    tipo = 0
                    if cat == CAT_OUTFIT and self.grupos:
                        tipo = b[p]  # tipo do grupo: 0 = parado, 1 = andando
                        p += 1
                    g = Grupo()
                    g.tipo = tipo
                    g.w, g.h = b[p], b[p + 1]
                    p += 2
                    if g.w > 1 or g.h > 1:
                        p += 1  # exactSize
                    g.layers, g.px, g.py, g.pz, g.fases = b[p:p + 5]
                    p += 5
                    if not (1 <= g.w <= 8 and 1 <= g.h <= 8 and 1 <= g.layers <= 8 and g.px <= 8 and g.py <= 8
                            and g.pz <= 8 and g.fases >= 1):
                        raise ValueError(f"dimensoes absurdas cat {cat} id {tid}")
                    g.dur = None
                    if g.fases > 1 and self.enh:
                        p += 6  # async u8, loopCount i32, startPhase i8
                        g.dur = [struct.unpack_from("<II", b, p + 8 * i) for i in range(g.fases)]
                        p += 8 * g.fases
                    n = g.w * g.h * g.layers * g.px * g.py * g.pz * g.fases
                    fmt, tam = ("I", 4) if self.ext else ("H", 2)
                    g.ids = struct.unpack_from(f"<{n}{fmt}", b, p)
                    p += tam * n
                    t.grupos.append(g)
                self.cats[cat][tid] = t
        self.fim = p
        return self

    def maior_sprite(self):
        return max(max(g.ids) for c in self.cats for t in c.values() for g in t.grupos)


def detectar(caminho, n_sprites=None):
    """Tenta as variantes do formato; devolve (Dat, descricao) da primeira cujo parse termina exatamente
    no fim do arquivo e so referencia sprites existentes."""
    tam = os.path.getsize(caminho)
    for grupos in (True, False):
        for enh in (True, False):
            for ext in (True, False):
                for usable in (2, 0):
                    try:
                        d = Dat(caminho, grupos, enh, ext, usable).parse()
                    except Exception:
                        continue
                    if d.fim == tam and (n_sprites is None or d.maior_sprite() <= n_sprites):
                        return d, (f"frame groups em outfits={grupos}, animacao avancada (duracoes)={enh}, "
                                   f"sprite id u32={ext}, payload da flag usable={usable}")
    raise SystemExit("nenhuma variante do .dat consumiu o arquivo inteiro")


class Spr:
    def __init__(self, caminho):
        self.f = open(caminho, "rb")
        self.assinatura, self.n = struct.unpack("<II", self.f.read(8))
        self.off = struct.unpack(f"<{self.n}I", self.f.read(4 * self.n))
        self.alpha = self._detectar_alpha()
        self.cache = {}

    def _bruto(self, sid):
        o = self.off[sid - 1] if 1 <= sid <= self.n else 0
        if not o:
            return None
        self.f.seek(o + 3)  # 3 bytes de chave de cor
        tam, = struct.unpack("<H", self.f.read(2))
        return self.f.read(tam)

    @staticmethod
    def _rle(dado, bpp):
        """[(indice_pixel, r, g, b, a)] ou None se o RLE nao fecha com bpp bytes/pixel (<=1024 pixels)."""
        p, pix, out, n = 0, 0, [], len(dado)
        while p < n:
            if p + 4 > n:
                return None
            tr, co = struct.unpack_from("<HH", dado, p)
            p += 4
            pix += tr
            if pix + co > 1024 or p + co * bpp > n:
                return None
            for i in range(co):
                q = p + i * bpp
                out.append((pix + i, dado[q], dado[q + 1], dado[q + 2], dado[q + 3] if bpp == 4 else 255))
            pix += co
            p += co * bpp
        return out

    def _detectar_alpha(self):
        rgb = rgba = amostras = 0
        passo = max(1, self.n // 400)
        for sid in range(1, self.n + 1, passo):
            dado = self._bruto(sid)
            if not dado:
                continue
            amostras += 1
            rgb += self._rle(dado, 3) is not None
            rgba += self._rle(dado, 4) is not None
            if amostras >= 300:
                break
        self.stats = (amostras, rgb, rgba)
        return rgba > rgb

    def sprite(self, sid):
        if sid in self.cache:
            return self.cache[sid]
        im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        dado = self._bruto(sid) if sid else None
        if dado:
            pixels = self._rle(dado, 4 if self.alpha else 3)
            if pixels is None:
                raise ValueError(f"sprite {sid} corrompido")
            px = im.load()
            for i, r, g, b, a in pixels:
                px[i % 32, i // 32] = (r, g, b, a)
        self.cache[sid] = im
        return im


def indice(g, frame=0, x=0, y=0, z=0, camada=0, hh=0, ww=0):
    return (((((frame * g.pz + z) * g.py + y) * g.px + x) * g.layers + camada) * g.h + hh) * g.w + ww


def render(spr, t, frame=0, x=0, y=0, z=0, grupo=0):
    """Compoe um frame (todas as camadas) em (32*w)x(32*h). O sprite de indice 0 fica no canto
    inferior direito (ordem de desenho do Tibia)."""
    g = t.grupos[grupo]
    im = Image.new("RGBA", (32 * g.w, 32 * g.h), (0, 0, 0, 0))
    for c in range(g.layers):
        for hh in range(g.h):
            for ww in range(g.w):
                sid = g.ids[indice(g, frame, x, y, z, c, hh, ww)]
                if sid:
                    im.alpha_composite(spr.sprite(sid), (32 * (g.w - ww - 1), 32 * (g.h - hh - 1)))
    return im

def cor_outfit(c):
    """Paleta de 133 cores do Tibia (Outfit::getColor do OTClient), igual a cor15() do index.html -> (r, g, b) 0-255."""
    H, SI = 19, 7
    if c >= H * SI:
        c = 0
    if c % H:
        h = c % H / 18
        s, i = [(.25, 1), (.25, .75), (.5, .75), (.667, .75), (1, 1), (1, .75), (1, .5)][c // H]
    else:
        h, s, i = 0, 0, 1 - c / H / SI
    if not i:
        return (0, 0, 0)
    if not s:
        v = int(i * 255)
        return (v, v, v)
    if h < 1 / 6:
        r = i; b = i * (1 - s); g = b + (i - b) * 6 * h
    elif h < 2 / 6:
        g = i; b = i * (1 - s); r = g - (i - b) * (6 * h - 1)
    elif h < 3 / 6:
        g = i; r = i * (1 - s); b = r + (i - r) * (6 * h - 2)
    elif h < 4 / 6:
        b = i; r = i * (1 - s); g = b - (i - r) * (6 * h - 3)
    elif h < 5 / 6:
        b = i; g = i * (1 - s); r = g + (i - g) * (6 * h - 4)
    else:
        r = i; g = i * (1 - s); b = r - (i - g) * (6 * h - 5)
    return (int(r * 255), int(g * 255), int(b * 255))


def camada_img(spr, g, frame, x, y, camada):
    im = Image.new("RGBA", (32 * g.w, 32 * g.h), (0, 0, 0, 0))
    for hh in range(g.h):
        for ww in range(g.w):
            sid = g.ids[indice(g, frame, x, y, 0, camada, hh, ww)]
            if sid:
                im.alpha_composite(spr.sprite(sid), (32 * (g.w - ww - 1), 32 * (g.h - hh - 1)))
    return im


def celula_outfit(spr, g, frame, direcao, cores, addons):
    """Um quadro de outfit: base (patternY 0) + addons ligados em `addons` (bit 1 = patternY 1, bit 2 = patternY 2);
    se o outfit tem 2 camadas, a 2a e a mascara de cores (amarelo=cabeca, vermelho=corpo, verde=pernas, azul=pes),
    aplicada como no comporOutfit() do index.html (multiplica a base pela cor). direcao: 0=N 1=E 2=S 3=W (patternX)."""
    out = Image.new("RGBA", (32 * g.w, 32 * g.h), (0, 0, 0, 0))
    px = direcao % g.px
    pal = [cor_outfit(c) for c in cores]
    for py in [0] + [k for k in (1, 2) if addons & k and k < g.py]:
        base = camada_img(spr, g, frame, px, py, 0)
        if g.layers > 1:
            mk = camada_img(spr, g, frame, px, py, 1)
            b, m = base.load(), mk.load()
            for yy in range(base.height):
                for xx in range(base.width):
                    r, gg, bb, a = m[xx, yy]
                    if not a:
                        continue
                    q = pal[0] if (r and gg and not bb) else pal[1] if (r and not gg) else pal[2] if (gg and not r) else pal[3] if bb else None
                    if q:
                        v = b[xx, yy]
                        b[xx, yy] = (v[0] * q[0] // 255, v[1] * q[1] // 255, v[2] * q[2] // 255, v[3])
        out.alpha_composite(base)
    return out


def folha_criatura(spr, dat, look, cores=(0, 0, 0, 0), addons=0, ex=False):
    """Folha de criatura no formato do jogo (tibia-assets/sprites15/criaturas): linhas = direcoes N,L,S,O
    (patternX 0..3), colunas = quadros parados + quadros de andar (grupos de quadro 0 e 1 do outfit), celula w x h
    = tamanho do outfit em pixels. Devolve (Image, meta) onde meta e o dict do SPR15.criaturas (sem src/cad).
    ex=True trata `look` como um item (lookTypeEx): um quadro, as 4 direcoes iguais."""
    if ex:
        t = dat.cats[CAT_ITEM][look]
        im = render(spr, t)
        folha = Image.new("RGBA", (im.width, im.height * 4), (0, 0, 0, 0))
        for d in range(4):
            folha.paste(im, (0, d * im.height))
        return folha, {"w": im.width, "h": im.height, "parado": 1, "andar": 0, "ms": [300], "desl": [0, 0]}
    t = dat.cats[CAT_OUTFIT][look]
    gp = [g for g in t.grupos if g.tipo == 0] or t.grupos[:1]
    g0 = gp[0]
    gm = [g for g in t.grupos if g.tipo == 1 and g is not g0]
    gm = gm[0] if gm else None
    quadros = [(g0, f) for f in range(g0.fases)] + ([(gm, f) for f in range(gm.fases)] if gm else [])
    W, H = 32 * max(g.w for g, _ in quadros), 32 * max(g.h for g, _ in quadros)   # grupos de tamanhos diferentes: ancora no canto inferior direito
    folha = Image.new("RGBA", (W * len(quadros), H * 4), (0, 0, 0, 0))
    for col, (g, f) in enumerate(quadros):
        for d in range(4):
            c = celula_outfit(spr, g, f, d, cores, addons)
            folha.paste(c, (col * W + W - c.width, d * H + H - c.height))
    ms = [max(1, g0.dur[i][0]) for i in range(g0.fases)] if g0.dur and g0.fases > 1 else [300]
    dl = t.flags.get("displacement")
    desl = [dl[0] | dl[1] << 8, dl[2] | dl[3] << 8] if dl else [0, 0]
    return folha, {"w": W, "h": H, "parado": g0.fases, "andar": gm.fases if gm else 0, "ms": ms, "desl": desl}


def ler_monstro_lua(caminho):
    """Do .lua de um monstro do Canary: (outfit {lookType|lookTypeEx, lookHead, lookBody, lookLegs, lookFeet, lookAddons}, corpse)."""
    return ler_monstro_lua_txt(open(caminho, encoding="utf-8", errors="ignore").read())


def ler_monstro_lua_txt(s):
    import re
    m = re.search(r"monster\.outfit\s*=\s*\{(.*?)\}", s, re.S)
    o = {k: int(v) for k, v in re.findall(r"(\w+)\s*=\s*(-?\d+)", m.group(1))} if m else {}
    c = re.search(r"monster\.corpse\s*=\s*(\d+)", s)
    return o, int(c.group(1)) if c else None


def carregar_nomes(xml):
    r = {}
    for it in ET.parse(xml).getroot().iter("item"):
        nome = it.get("name")
        if not nome:
            continue
        if it.get("id"):
            r[int(it.get("id"))] = (nome, it.get("article") or "")
        elif it.get("fromid"):
            for i in range(int(it.get("fromid")), int(it.get("toid")) + 1):
                r[i] = (nome, it.get("article") or "")
    return r


def atlas_combate(spr, dat, cat, ids, saida, nome="combate", primeiro=0, src_prefixo="tibia-assets/sprites15/", largura=2048, altura=2048):
    """Empacota efeitos (cat 2) ou missiles (cat 3) em atlas PNG no formato do COMB15 (tibia-assets/combate15.js):
      efeito: tira horizontal de fases (cada fase = 32*w x 32*h, a mesma de render()), meta {x,y,w,h,n,ms,src}; ms = (min+max)//2 de cada fase (100 se parado);
      missil: grade 3x3 de direcoes (coluna 0=oeste..2=leste, linha 0=norte..2=sul), cada celula 32*w x 32*h, meta {x,y,w,h,src}
              (missil com 1 padrao so, sem direcoes, repete o mesmo desenho nas 9 celulas); atlas <nome>_<N>.png (N = primeiro, primeiro+1, ...).
    Coisas totalmente transparentes (efeitos/missiles que o cliente define vazios) nao entram: voltam na lista de vazios.
    Devolve (meta {id: {...}}, vazios [ids], arquivos [caminhos])."""
    pecas = []
    vazios = []
    for i in ids:
        t = dat.cats[cat][i]
        g = t.grupos[0]
        if cat == CAT_EFFECT:
            quadros = [render(spr, t, q) for q in range(g.fases)]
            if not any(q.getbbox() for q in quadros):
                vazios.append(i)
                continue
            W, H = quadros[0].size
            ms = [(d[0] + d[1]) // 2 for d in g.dur] if g.dur else [100]
            pecas.append((i, W * len(quadros), H, quadros, ms))
        else:
            cel = [[render(spr, t, 0, px % g.px, py % g.py) for px in range(3)] for py in range(3)]
            if not any(c.getbbox() for l in cel for c in l):
                vazios.append(i)
                continue
            W, H = cel[0][0].size
            pecas.append((i, 3 * W, 3 * H, cel, None))
    pecas.sort(key=lambda p: (-p[2], p[0]))
    folhas, meta = [], {}
    x = y = linha = 0
    atual = None
    for i, pw, ph, dados, ms in pecas:
        if atual is None or x + pw > largura:
            x, y, linha = 0, y + linha, 0
        if atual is None or y + ph > altura:
            atual = Image.new("RGBA", (largura, altura), (0, 0, 0, 0))
            folhas.append([atual, 0])
            x = y = linha = 0
        linha = max(linha, ph)
        src = f"{src_prefixo}{nome}_{primeiro + len(folhas) - 1}.png"
        if cat == CAT_EFFECT:
            for q, im in enumerate(dados):
                atual.paste(im, (x + q * im.width, y))
            meta[i] = {"x": x, "y": y, "w": dados[0].width, "h": dados[0].height, "n": len(dados), "ms": ms, "src": src}
        else:
            for py in range(3):
                for px in range(3):
                    atual.paste(dados[py][px], (x + px * dados[0][0].width, y + py * dados[0][0].height))
            meta[i] = {"x": x, "y": y, "w": dados[0][0].width, "h": dados[0][0].height, "src": src}
        x += pw
        folhas[-1][1] = max(folhas[-1][1], y + linha)
    arquivos = []
    for n, (im, h) in enumerate(folhas):
        caminho = os.path.join(saida, f"{nome}_{primeiro + n}.png")
        im.crop((0, 0, largura, (h + 31) // 32 * 32)).save(caminho)
        arquivos.append(caminho)
    return meta, vazios, arquivos


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dat")
    ap.add_argument("--spr")
    ap.add_argument("--info", action="store_true", help="mostra a variante detectada e estatisticas")
    ap.add_argument("--itens", help="client ids separados por virgula (ex.: 3031,28552)")
    ap.add_argument("--cat", choices=["item", "outfit", "effect", "missile"], default="item")
    ap.add_argument("--sheet", help="ids cujas fases de animacao viram uma tira horizontal <id>_anim.png")
    ap.add_argument("--criaturas", help="folhas de criatura: lookType[:cabeca,corpo,pernas,pes[:addons]] separados por virgula "
                    "(lookTypeEx com prefixo e, ex.: e3031); grava <id>.png (ou <nome>=<spec> para escolher o nome do arquivo) e imprime o JSON da folha")
    ap.add_argument("--atlas", help="(com --cat effect|missile) ids ou 'todos': empacota em atlas combate_N.png no formato do COMB15 e imprime o JSON")
    ap.add_argument("--atlas-nome", default="combate", help="prefixo dos atlas (padrao combate)")
    ap.add_argument("--atlas-primeiro", type=int, default=0, help="numero do primeiro atlas (padrao 0)")
    ap.add_argument("--saida", default=".")
    ap.add_argument("--nomes", help="items.xml do Canary")
    ap.add_argument("--buscar", help="texto a procurar nos nomes (com --nomes)")
    ap.add_argument("--exato", action="store_true", help="--buscar exige nome identico")
    a = ap.parse_args()

    if a.nomes and a.buscar:
        nomes = carregar_nomes(a.nomes)
        q = a.buscar.lower()
        for i in sorted(nomes):
            n = nomes[i][0].lower()
            if (n == q) if a.exato else (q in n):
                print(i, nomes[i][0])
        return
    if not (a.dat and a.spr):
        ap.error("--dat e --spr sao obrigatorios")
    spr = Spr(a.spr)
    dat, desc = detectar(a.dat, spr.n)
    cat = {"item": 0, "outfit": 1, "effect": 2, "missile": 3}[a.cat]
    if a.info:
        print(f"dat: assinatura 0x{dat.assinatura:08X}; itens {FIRST_ITEM_ID}..{dat.n_item}, outfits {dat.n_outfit}, "
              f"efeitos {dat.n_efeito}, missiles {dat.n_missil}")
        print(f"dat variante: {desc}")
        print(f"spr: assinatura 0x{spr.assinatura:08X}, {spr.n} sprites, "
              f"{'RGBA' if spr.alpha else 'RGB'} (amostra {spr.stats[0]}: RGB ok {spr.stats[1]}, RGBA ok {spr.stats[2]})")
        print(f"maior sprite id referenciado no dat: {dat.maior_sprite()}")
    os.makedirs(a.saida, exist_ok=True)
    for s in (a.itens.split(",") if a.itens else []):
        cid = int(s)
        t = dat.cats[cat][cid]
        im = render(spr, t)
        im.save(os.path.join(a.saida, f"{cid}.png"))
        print(f"{cid}: {t.grupos[0].w}x{t.grupos[0].h} tiles, {t.grupos[0].fases} fases -> {im.size}")
    for s in (a.criaturas.split(",") if a.criaturas else []):
        nome, _, spec = s.rpartition("=")
        nome = nome or spec.split(":")[0]
        pt = spec.split(":")
        ex = pt[0].startswith("e")
        cores = tuple(int(v) for v in pt[1].split(",")) if len(pt) > 1 and pt[1] else (0, 0, 0, 0)
        folha, meta = folha_criatura(spr, dat, int(pt[0].lstrip("e")), cores, int(pt[2]) if len(pt) > 2 else 0, ex)
        folha.save(os.path.join(a.saida, f"{nome}.png"))
        print(nome, json.dumps(meta))
    if a.atlas:
        if cat not in (CAT_EFFECT, CAT_MISSILE):
            ap.error("--atlas precisa de --cat effect ou missile")
        ids = sorted(dat.cats[cat]) if a.atlas == "todos" else [int(v) for v in a.atlas.split(",")]
        meta, vazios, arq = atlas_combate(spr, dat, cat, ids, a.saida, a.atlas_nome, a.atlas_primeiro)
        print(json.dumps({"meta": meta, "vazios": vazios, "arquivos": arq}, separators=(",", ":")))
    for s in (a.sheet.split(",") if a.sheet else []):
        cid = int(s)
        t = dat.cats[cat][cid]
        g = t.grupos[0]
        fr = [render(spr, t, f) for f in range(g.fases)]
        folha = Image.new("RGBA", (fr[0].width * len(fr), fr[0].height), (0, 0, 0, 0))
        for i, im in enumerate(fr):
            folha.paste(im, (i * im.width, 0))
        folha.save(os.path.join(a.saida, f"{cid}_anim.png"))
        print(f"{cid}: {g.fases} fases {fr[0].size}; duracoes {g.dur}")


if __name__ == "__main__":
    sys.exit(main())
