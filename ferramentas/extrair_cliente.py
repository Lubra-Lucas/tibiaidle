#!/usr/bin/env python3
"""Extrai sprites de itens/objetos de um cliente Tibia (Tibia.dat + Tibia.spr, formato legado
10.x+ com ids de sprite u32 / "extended", como os clientes convertidos para OTClient).

Os arquivos do cliente NAO fazem parte do repositorio (sao enormes) - aponte para eles com
--dat / --spr. So os PNGs gerados e esta ferramenta ficam no repo.

Uso (sempre com -I):
  python3 -I ferramentas/extrair_cliente.py --dat Tibia.dat --spr Tibia.spr --info
  python3 -I ferramentas/extrair_cliente.py --dat ... --spr ... --itens 3031,28552 --saida tibia-assets/sprites15/itens
  python3 -I ferramentas/extrair_cliente.py --dat ... --spr ... --sheet 36040 --saida dir   # fases de animacao em tira horizontal
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
                    if cat == CAT_OUTFIT and self.grupos:
                        p += 1  # tipo do grupo
                    g = Grupo()
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dat")
    ap.add_argument("--spr")
    ap.add_argument("--info", action="store_true", help="mostra a variante detectada e estatisticas")
    ap.add_argument("--itens", help="client ids separados por virgula (ex.: 3031,28552)")
    ap.add_argument("--cat", choices=["item", "outfit", "effect", "missile"], default="item")
    ap.add_argument("--sheet", help="ids cujas fases de animacao viram uma tira horizontal <id>_anim.png")
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
