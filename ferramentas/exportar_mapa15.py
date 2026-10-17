#!/usr/bin/env python3
"""Exporta um mapa OTBM (OpenTibia) para o formato dos mapas do jogo (tibia-assets/mapas15/<chave>.js + atlas PNG),
com sprites do cliente 15.01 (Tibia.dat/.spr via extrair_cliente.py). Sempre com -I:

  python3 -I ferramentas/exportar_mapa15.py --otbm Thaismap.otbm --otb items.otb|- --dat Tibia.dat --spr Tibia.spr \\
      --chave thais --nome Thais --z 7 --caixa 32300,32180,32420,32300 --saida tibia-assets/mapas15 [--inicio x,y,z]
  (--otb - : mapas 12+ cujos ids ja sao client ids)
  python3 -I ferramentas/exportar_mapa15.py ... --info            # versoes, andares e limites do mapa
  python3 -I ferramentas/exportar_mapa15.py ... --achar 3,5       # onde ha estes ids (server ids) no mapa

OTBM: arvore de nos (0xFE inicio, 0xFF fim, 0xFD escape); raiz = versao/largura/altura/versao dos itens (maior,menor);
MAP_DATA -> TILE_AREA (x,y,z base) -> TILE / HOUSETILE (x,y,[casa]) com atributos (ITEM = chao compacto) e filhos ITEM.
Os ids do OTBM sao "server ids"; o items.otb (mesma versao maior; os server ids sao estaveis entre versoes) leva cada
server id ao client id, e o Tibia.dat do cliente 15.01 usa os mesmos client ids dos itens antigos.
"""
import argparse
import collections
import hashlib
import json
import math
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extrair_cliente as EC  # noqa: E402
from PIL import Image  # noqa: E402

# ---------------------------------------------------------------- arvore de nos (OTBM / OTB)
_ESPECIAIS = re.compile(rb"[\xfd\xfe\xff]")
_ESC = re.compile(rb"\xfd(.)", re.S)


def ler_nos(b):
    """b = arquivo sem os 4 bytes de identificacao. Devolve a raiz como [tipo, dados, filhos] (dados sem escape)."""
    pilha, raiz, ini = [], None, 0
    for m in _ESPECIAIS.finditer(b):
        j = m.start()
        if b[j] == 0xFD:
            continue
        k = j - 1
        while k >= 0 and b[k] == 0xFD:
            k -= 1
        if (j - 1 - k) % 2:
            continue  # byte escapado: e dado
        if pilha and j > ini:
            pilha[-1][1].append(b[ini:j])
        if b[j] == 0xFE:
            nd = [None, [], []]
            (pilha[-1][2].append(nd) if pilha else None)
            if not pilha:
                raiz = nd
            pilha.append(nd)
        else:
            fechar(pilha.pop())
        ini = j + 1
    return raiz


def fechar(nd):
    d = _ESC.sub(rb"\1", b"".join(nd[1]))
    nd[0], nd[1] = d[0], d[1:]


# ---------------------------------------------------------------- items.otb
def ler_otb(caminho):
    """-> (versao (maior, menor, build), {server_id: client_id}, {server_id: flags})"""
    b = open(caminho, "rb").read()
    r = ler_nos(b[4:])
    ma, mi, bu = struct.unpack_from("<III", r[1], 7)
    s2c, fl = {}, {}
    for nd in r[2]:
        d = nd[1]
        flags = struct.unpack_from("<I", d, 0)[0]
        p, sid, cid = 4, None, None
        while p + 3 <= len(d):
            t, ln = struct.unpack_from("<BH", d, p)
            v = d[p + 3:p + 3 + ln]
            if t == 0x10:
                sid = struct.unpack_from("<H", v)[0]
            elif t == 0x11:
                cid = struct.unpack_from("<H", v)[0]
            p += 3 + ln
        if sid is not None and cid is not None:
            s2c[sid], fl[sid] = cid, (nd[0], flags)
    return (ma, mi, bu), s2c, fl


# ---------------------------------------------------------------- OTBM
class Mapa:
    pass


def _attrs(d, p, versao):
    """le os atributos de um tile/item a partir de d[p:]; devolve ({tipo: valor}, p)"""
    a = {}
    while p < len(d):
        t = d[p]
        p += 1
        if t in (6, 7, 18) or t == 19 or t == 1 or t == 2:  # strings: texto, descricao, escrito por
            n = struct.unpack_from("<H", d, p)[0]
            a[t] = d[p + 2:p + 2 + n]
            p += 2 + n
        elif t == 3 or t == 16 or t == 18 or t == 20 or t == 21:
            a[t] = struct.unpack_from("<I", d, p)[0]
            p += 4
        elif t in (4, 5, 9, 10, 22):
            a[t] = struct.unpack_from("<H", d, p)[0]
            p += 2
        elif t == 8:
            a[t] = struct.unpack_from("<HHB", d, p)
            p += 5
        elif t in (12, 14, 15, 17):
            a[t] = d[p]
            p += 1
        else:
            raise ValueError(f"atributo OTBM desconhecido {t}")
    return a, p


def ler_otbm(caminho):
    """-> Mapa com .versao, .w, .h, .itens (maior, menor) e .tiles = {(x,y,z): [server ids, chao primeiro]}
    e .info[(x,y,z)] = dict de atributos especiais dos itens (acao, texto, destino de teleporte) por indice."""
    b = open(caminho, "rb").read()
    r = ler_nos(b[4:])
    m = Mapa()
    m.versao, m.w, m.h, m.maior, m.menor = struct.unpack_from("<IHHII", r[1], 0)
    m.tiles, m.attrs, m.casas, m.cidades = {}, {}, {}, []
    for md in r[2]:
        if md[0] != 2:
            continue
        for area in md[2]:
            if area[0] == 12:  # TOWNS: id u32, nome, templo x,y,z
                for t in area[2]:
                    n = struct.unpack_from("<H", t[1], 4)[0]
                    m.cidades.append((t[1][6:6 + n].decode("latin-1"), struct.unpack_from("<HHB", t[1], 6 + n)))
                continue
            if area[0] != 4:
                continue
            bx, by, bz = struct.unpack_from("<HHB", area[1], 0)
            for t in area[2]:
                if t[0] not in (5, 14):
                    continue
                x, y = bx + t[1][0], by + t[1][1]
                p = 2
                if t[0] == 14:
                    m.casas[(x, y, bz)] = struct.unpack_from("<I", t[1], 2)[0]
                    p = 6
                a, _ = _attrs(t[1], p, m.versao)
                pilha = [a[9]] if 9 in a else []
                esp = {}
                for it in t[2]:
                    if it[0] != 6:
                        continue
                    iid = struct.unpack_from("<H", it[1], 0)[0]
                    ia = _attrs(it[1], 2, m.versao)[0] if len(it[1]) > 2 else {}
                    if set(ia) & {4, 5, 6, 7, 8, 10}:
                        esp[len(pilha)] = ia
                    pilha.append(iid)
                m.tiles[(x, y, bz)] = pilha
                if esp:
                    m.attrs[(x, y, bz)] = esp
    return m


# ---------------------------------------------------------------- exportacao
CAT = EC.CAT_ITEM
MAX_FASES = 8          # animacoes: no maximo 8 quadros na tira do atlas
ATLAS_L, ATLAS_A = 2048, 2048


class Cliente:
    """Tibia.dat + Tibia.spr e os atalhos de flags dos itens."""

    def __init__(self, dat, spr):
        self.spr = EC.Spr(spr)
        self.dat, _ = EC.detectar(dat, self.spr.n)
        self.itens = self.dat.cats[CAT]
        self.F = {}

    def fl(self, cid):
        f = self.F.get(cid)
        if f is None:
            t = self.itens.get(cid)
            fl = t.flags if t else {}
            dp, el = fl.get("displacement"), fl.get("elevation")
            f = self.F[cid] = (fl, (dp[0] | dp[1] << 8, dp[2] | dp[3] << 8) if dp else (0, 0), (el[0] | el[1] << 8) if el else 0)
        return f[0]

    def desl(self, cid):
        self.fl(cid)
        return self.F[cid][1]

    def elev(self, cid):
        self.fl(cid)
        return self.F[cid][2]


def ordem_desenho(cl, ids):
    """Ordem do cliente: chao, bordas (clip), bottom, itens comuns (em ordem inversa, como o OTClient), top."""
    F = cl.fl
    g = [i for i in ids if "ground" in F(i)]
    r = [i for i in ids if "ground" not in F(i)]
    cp = [i for i in r if "clip" in F(i)]
    bo = [i for i in r if "bottom" in F(i) and "clip" not in F(i)]
    tp = [i for i in r if "top" in F(i) and "clip" not in F(i) and "bottom" not in F(i)]
    co = [i for i in r if i not in cp and i not in bo and i not in tp]
    return g + cp + bo + co[::-1] + tp


def dividir(cl, ids):
    """(grupo do chao = [chao] + bordas, resto): o chao vai num sprite 32x32 so, o resto num sprite maior ancorado embaixo-direita."""
    k = 1 if ids and "ground" in cl.fl(ids[0]) else 0
    while k < len(ids) and "clip" in cl.fl(ids[k]):
        k += 1
    return ids[:k], ids[k:]


def padrao(cl, i, g, wx, wy):
    """pattern x/y do sprite: posicao absoluta do tile mod padroes (variacao de chao/itens, tambem em empilhaveis)."""
    return wx % g.px, wy % g.py


def compor(cl, ids, wx, wy, chao):
    """Compoe os itens num so sprite (lista de quadros, uma por fase de animacao). Cada item e desenhado ancorado no canto
    inferior direito do tile, deslocado pelo displacement e pela elevacao acumulada; o corte e o retangulo que cobre todos
    os quadros (no minimo o proprio tile); o chao e cortado no tile 32x32."""
    if not ids:
        return None
    ids = ordem_desenho(cl, ids)
    fs = [cl.itens[i].grupos[0].fases for i in ids]
    n = 1
    for f in fs:
        n = n * f // math.gcd(n, f)
    n = min(n, MAX_FASES)
    quadros, bb = [], None
    for q in range(n):
        cv = Image.new("RGBA", (160, 160), (0, 0, 0, 0))
        elev = 0
        for i in ids:
            t = cl.itens[i]
            g = t.grupos[0]
            px, py = padrao(cl, i, g, wx, wy)
            sid = EC.render(cl.spr, t, q % g.fases, px, py)
            dx, dy = cl.desl(i)
            cv.alpha_composite(sid, (128 - sid.width - dx - elev, 128 - sid.height - dy - elev))
            elev = min(elev + cl.elev(i), 24)
        quadros.append(cv)
        b = cv.getbbox()
        if b:
            bb = b if bb is None else (min(bb[0], b[0]), min(bb[1], b[1]), max(bb[2], b[2]), max(bb[3], b[3]))
    if bb is None:
        return None
    caixa = (96, 96, 128, 128) if chao else (min(bb[0], 96), min(bb[1], 96), 128, 128)
    return [c.crop(caixa) for c in quadros]


def andavel(cl, ids, mover_piso=False):
    """Andavel = tem chao e nenhum item (nem o chao) bloqueia (unpass = parede/arvore/agua..., blockpath = fogo/campo)."""
    if not ids or "ground" not in cl.fl(ids[0]):
        return 0
    return 0 if any("unpass" in cl.fl(i) or "blockpath" in cl.fl(i) for i in ids) else 1


def empacotar(sprites, chave, web, fs, largura=ATLAS_L, altura=ATLAS_A):
    """sprites = [(nome, [quadros])]; atlas <chave>_<N>.png (shelf, mais altos primeiro). -> (meta {nome: {...}}, [arquivos])"""
    ordem = sorted(range(len(sprites)), key=lambda i: (-sprites[i][1][0].height, -sprites[i][1][0].width, i))
    paginas, meta = [], {}
    x = y = linha = 0
    pg = None
    for i in ordem:
        nome, q = sprites[i]
        w, h, n = q[0].width, q[0].height, len(q)
        if pg is None or x + w * n > largura:
            x, y, linha = 0, y + linha, 0
        if pg is None or y + h > altura:
            pg = [Image.new("RGBA", (largura, altura), (0, 0, 0, 0)), 0]
            paginas.append(pg)
            x = y = linha = 0
        for k, im in enumerate(q):
            pg[0].paste(im, (x + k * w, y))
        linha = max(linha, h)
        pg[1] = max(pg[1], y + h)
        meta[nome] = {"x": x, "y": y, "w": w, "h": h, "n": n, "src": f"{web}/{chave}_{len(paginas) - 1}.png"}
        x += w * n
    arqs = []
    for k, (im, alt) in enumerate(paginas):
        im = im.crop((0, 0, largura, max(alt, 1)))
        arqs.append(salvar_png(im, os.path.join(fs, f"{chave}_{k}.png")))
    return meta, arqs


def salvar_png(im, caminho):
    """PNG sem perdas: paleta (<=256 cores, com transparencia) quando couber, senao RGBA otimizado."""
    cores = im.getcolors(256)
    if cores is not None:
        pal = im.convert("RGBA").quantize(colors=256, method=Image.FASTOCTREE, dither=Image.NONE)
        if list(pal.convert("RGBA").getdata()) == list(im.getdata()):
            pal.save(caminho, optimize=True)
            return caminho
    im.save(caminho, optimize=True)
    return caminho


def jdump(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def exportar(a):
    cl = Cliente(a.dat, a.spr)
    if a.otb == "-":   # mapas 12+ (SharpMapTracker/Canary): o id do OTBM ja e o client id
        ver, s2c = None, {i: i for i in cl.itens}
    else:
        ver, s2c, otbfl = ler_otb(a.otb)
    m = ler_otbm(a.otbm)
    bloq = {int(v) for v in a.bloquear.split(",")} if a.bloquear else set()
    subst = {int(k): int(v) for k, v in (p.split("=") for p in a.substituir.split(","))} if a.substituir else {}
    x0, y0, x1, y1 = a.caixa
    base = a.otbm_nome or os.path.basename(a.otbm)
    desc = {}
    # pilhas de client ids por tile (so ids conhecidos), na ordem do OTBM
    pil = {}
    desc_miss = collections.Counter()
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            it = m.tiles.get((x, y, a.z))
            if not it:
                continue
            ids = []
            for sid in it:
                sid = subst.get(sid, sid)
                if not sid:
                    continue   # --substituir X=0 remove o item
                c = s2c.get(sid)
                if c is None or c not in cl.itens:
                    desc_miss[sid] += 1
                    continue
                ids.append(c)
            if ids:
                pil[(x, y)] = (ids, it)
    w, h = x1 - x0 + 1, y1 - y0 + 1
    if a.preencher:   # tiles que faltam no OTBM (mapa de tracker incompleto): copia o chao do vizinho mais proximo, nao andavel
        from collections import deque
        q = deque()
        for k, (ids, _) in pil.items():
            g = [i for i in ids if "ground" in cl.fl(i)]
            if g:
                q.append((k, g[0]))
        visto = {k for k, _ in q} | set(pil)
        falta = set()
        while q:
            (x, y), g = q.popleft()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (x + dx, y + dy)
                if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and n not in visto:
                    visto.add(n)
                    falta.add(n)
                    pil[n] = ([g], None)
                    q.append((n, g))
    nomes, imagens, cache, tiles = {}, [], {}, []
    walk = [0] * (w * h)

    def chave(ids, wx, wy, chao):
        ids = ordem_desenho(cl, ids)
        pads = tuple(padrao(cl, i, cl.itens[i].grupos[0], wx, wy) for i in ids)
        return (chao, tuple(ids), pads)

    def sprite(ids, wx, wy, chao):
        if not ids:
            return None
        k = chave(ids, wx, wy, chao)
        if k in cache:
            return cache[k]
        q = compor(cl, ids, wx, wy, chao)
        if q is None:
            cache[k] = None
            return None
        dig = hashlib.md5(b"".join(i.tobytes() for i in q) + bytes(q[0].size) + bytes([len(q)])).hexdigest()
        if dig not in nomes:
            nomes[dig] = f"{a.chave}:{len(nomes)}"
            imagens.append((nomes[dig], q))
        cache[k] = nomes[dig]
        return cache[k]

    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if (x, y) not in pil:
                continue
            ids, it = pil[(x, y)]
            g, resto = dividir(cl, ids)
            st = [sprite(g, x, y, True), sprite(resto, x, y, False)]
            while st and st[-1] is None:
                st.pop()
            if not st:
                continue
            tiles.append([x - x0, y - y0, st])
            walk[(y - y0) * w + (x - x0)] = andavel(cl, ids) if not a.sem_andar and it is not None and not (bloq & set(it)) else 0
    meta, arqs = empacotar(imagens, a.chave, a.saida_web, a.saida, a.largura or ATLAS_L, ATLAS_A)
    ini = a.inicio or (w // 2, h // 2)
    mapa = {"nome": a.nome, "w": w, "h": h, "origem": [x0, y0, a.z], "tiles": tiles, "walk": walk, "spawns": [],
            "inicio": [ini[0], ini[1]], "escuro": False}
    if a.extra:
        mapa.update(json.loads(a.extra))
    js = os.path.join(a.saida, a.chave + ".js")
    with open(js, "w", encoding="utf-8") as f:
        f.write(f"/* gerado por ferramentas/exportar_mapa15.py a partir de {base} (sprites do cliente 15.01) */\n")
        f.write("window.MAPAS=Object.assign(window.MAPAS||{},{" + jdump(a.chave) + ":" + jdump(mapa) + "});\n")
        f.write("window.MAPAS_SPRITES=window.MAPAS_SPRITES||{tiles:{},criaturas:{}};Object.assign(window.MAPAS_SPRITES.tiles," + jdump(meta) + ");\n")
    return {"js": js, "atlas": arqs, "tiles": len(tiles), "sprites": len(imagens), "w": w, "h": h, "sem_id": dict(desc_miss),
            "andaveis": sum(walk), "otb": ver, "otbm": (m.versao, m.maior, m.menor)}


def prever(a, saida_png, esc=1):
    """Renderiza o mapa exportado (js + atlas) em PNG, como o jogo (chao 32x32, itens ancorados embaixo-direita)."""
    s = open(os.path.join(a.saida, a.chave + ".js"), encoding="utf-8").read()
    dec = json.JSONDecoder()
    d, _ = dec.raw_decode(s[s.find('{"' + a.chave + '":') + len('{"' + a.chave + '":'):])
    sp, _ = dec.raw_decode(s[s.find("Object.assign(window.MAPAS_SPRITES.tiles,") + len("Object.assign(window.MAPAS_SPRITES.tiles,"):])
    atl = {}
    im = Image.new("RGBA", (d["w"] * 32, d["h"] * 32), (0, 0, 0, 255))
    for x, y, st in d["tiles"]:
        for j, k in enumerate(st):
            if not k:
                continue
            t = sp[k]
            if t["src"] not in atl:
                atl[t["src"]] = Image.open(os.path.join(a.saida, os.path.basename(t["src"]))).convert("RGBA")
            c = atl[t["src"]].crop((t["x"], t["y"], t["x"] + t["w"], t["y"] + t["h"]))
            if j == 0:
                im.alpha_composite(c, (x * 32, y * 32))
            else:
                im.alpha_composite(c, (x * 32 + 32 - t["w"], y * 32 + 32 - t["h"]))
    if esc != 1:
        im = im.resize((im.width * esc // 32 or 1, im.height * esc // 32 or 1), Image.LANCZOS)
    im.convert("RGB").save(saida_png)


def achar(a):
    """--achar 2589,2590: onde ha estes server ids (andar --z) dentro da caixa (ou do mapa todo)."""
    m = ler_otbm(a.otbm)
    ids = {int(v) for v in a.achar.split(",")}
    for (x, y, z), it in sorted(m.tiles.items(), key=lambda k: (k[0][2], k[0][1], k[0][0])):
        if z == a.z and any(i in ids for i in it):
            if not a.caixa or (a.caixa[0] <= x <= a.caixa[2] and a.caixa[1] <= y <= a.caixa[3]):
                print(x, y, z, [i for i in it if i in ids])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--otbm", required=True)
    ap.add_argument("--otb")
    ap.add_argument("--dat")
    ap.add_argument("--spr")
    ap.add_argument("--chave")
    ap.add_argument("--nome")
    ap.add_argument("--z", type=int)
    ap.add_argument("--caixa", help="x0,y0,x1,y1 (inclusive, coordenadas do OTBM); omitido = todo o andar")
    ap.add_argument("--saida", default="tibia-assets/mapas15", help="pasta onde gravar <chave>.js e <chave>_N.png")
    ap.add_argument("--saida-web", dest="saida_web", help="caminho do atlas visto pelo navegador (padrao = --saida)")
    ap.add_argument("--inicio", help="x,y (relativo ao recorte) onde o jogador nasce; padrao = centro")
    ap.add_argument("--otbm-nome", dest="otbm_nome")
    ap.add_argument("--extra", help="JSON mesclado no mapa (ex.: depots)")
    ap.add_argument("--largura", type=int)
    ap.add_argument("--substituir", help="troca server ids antes de exportar: 11059=424,...")
    ap.add_argument("--preencher", action="store_true", help="preenche tiles ausentes com o chao do vizinho (nao andaveis)")
    ap.add_argument("--bloquear", help="server ids (originais do OTBM) que tornam o tile nao andavel: 919,918")
    ap.add_argument("--sem-andar", dest="sem_andar", action="store_true")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--achar")
    ap.add_argument("--previa", help="grava um PNG do mapa exportado")
    a = ap.parse_args()
    if a.caixa:
        a.caixa = [int(v) for v in a.caixa.split(",")]
    if a.inicio:
        a.inicio = [int(v) for v in a.inicio.split(",")]
    a.saida_web = a.saida_web or a.saida
    if a.info:
        m = ler_otbm(a.otbm)
        zs = collections.Counter(k[2] for k in m.tiles)
        print("OTBM versao", m.versao, "itens", (m.maior, m.menor), "tamanho", (m.w, m.h), "cidades", m.cidades)
        for z in sorted(zs):
            xs = [k[0] for k in m.tiles if k[2] == z]
            ys = [k[1] for k in m.tiles if k[2] == z]
            print("z", z, zs[z], "tiles x", min(xs), max(xs), "y", min(ys), max(ys))
        return
    if a.achar:
        return achar(a)
    for k in ("otb", "dat", "spr", "chave", "nome", "z"):
        if getattr(a, k) is None:
            ap.error("faltou --" + k)
    if not a.caixa:
        m = ler_otbm(a.otbm)
        ks = [k for k in m.tiles if k[2] == a.z]
        a.caixa = [min(k[0] for k in ks), min(k[1] for k in ks), max(k[0] for k in ks), max(k[1] for k in ks)]
    r = exportar(a)
    print(json.dumps(r, ensure_ascii=False))
    if a.previa:
        prever(a, a.previa)


if __name__ == "__main__":
    main()
