#!/usr/bin/env python3
"""Capricha o entorno de algumas caçadas (tibia-assets/mapas15/cacadas/hNNN.js + hNNN_0.png) depois de refazer_cacadas.py.

O refazer_cacadas.py garante que nada fica preto, mas a massa em volta é uma síntese de textura: em mapas de neve/gelo/caverna vira
uma "chapa" cinza lisa, sem paredes entre o chão e a massa, com fragmentos de prédio/parede soltos. Esta ferramenta refaz só o entorno
(o andável, os spawns e o início não mudam), em 4 passos, tudo aprendido dos mapas ORIGINAIS (recortes reais do Azeroth.otbm):

  1. mantém o que é real e coerente: células bloqueadas reais (do recorte original, com chão opaco ou objeto) até PROF tiles do andável,
     e "buracos" internos (lagos, ilhas) que não se ligam à borda do mapa. O resto (síntese do refazer, fragmentos soltos, vazio) é refeito;
  2. BORDA (autotile): cada célula refeita que encosta no andável recebe a pilha que, nos mapas-fonte do mesmo bioma, aparece numa célula
     bloqueada com a MESMA vizinhança de andável (máscara de 8 vizinhos reduzida: 4 lados + cantos só-diagonal), logo com a orientação,
     os cantos externos e internos certos (parede de gelo, margem de neve, parede de caverna, barranco...). Sprites de outras caçadas são
     copiados para o atlas da própria caçada com ids novos 'hNNN:cK' (o carregador só usa atlas do prefixo do mapa);
  3. MASSA: o resto vira terreno natural: o chão de rocha/gelo/terra/água do bioma em tons (campo de ruído suave + escurecimento com a
     distância, como a penumbra do Tibia) em vez de uma cor lisa; água/mar usam o próprio chão animado do mapa;
  4. DECORAÇÃO esparsa (pedras, cristais, troncos, estalagmites...) tirada de objetos reais do bioma, longe da borda, sem aglomerar.
Valida: sem célula vazia, chão opaco, ids válidos, spawns/início/andável idênticos ao refazer, nada andável perto da borda.

Reprodutível a partir dos originais (commit 648aa79, antes do refazer):
  mkdir /tmp/orig && git archive 648aa79 tibia-assets/mapas15/cacadas | tar -x -C /tmp/orig
  python3 ferramentas/caprichar_cacadas.py --src /tmp/orig/tibia-assets/mapas15/cacadas [h007 h094 ...]
(roda refazer_cacadas.refazer em temporário e grava o resultado final em --dst, padrão o repositório; sem lista, faz todas as de KITS/AUTO;
as demais caçadas ficam como o refazer_cacadas.py deixou)"""
import sys, os, re, json, random, zlib, argparse, hashlib, tempfile, shutil
from collections import Counter, defaultdict
import numpy as np
from PIL import Image
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refazer_cacadas as RF
from refazer_cacadas import ler_js, jdump

N8 = RF.VIZ
MARCA2 = 'entorno capricho por ferramentas/caprichar_cacadas.py'
PROF = 5   # até onde o que é real e perto do andável é mantido


# ------------------------------------------------------------------ utilitários
def hspr(arr, t):
    a = arr[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w'] * t.get('n', 1)]
    return hashlib.md5(a.tobytes() + bytes([t['w'] & 255, t['h'] & 255, t.get('n', 1)])).hexdigest()[:12]

def cheb(W, maxd=60):
    H, Wd = W.shape; dist = np.full((H, Wd), maxd, np.int32); dist[W] = 0; fr = W.copy()
    for r in range(1, maxd):
        m = np.pad(fr, 1); v = np.zeros_like(fr)
        for dy in range(3):
            for dx in range(3): v |= m[dy:dy + H, dx:dx + Wd]
        nw = v & (dist == maxd)
        if not nw.any(): break
        dist[nw] = r; fr = nw
    return dist

def wmask(W, x, y):
    h, w = W.shape; m = 0
    for i, (dx, dy) in enumerate(N8):
        nx, ny = x + dx, y + dy
        if 0 <= nx < w and 0 <= ny < h and W[ny, nx]: m |= 1 << i
    return m

def redkey(m):
    k = m & 0x55   # lados N L S O (bits 0,2,4,6); cantos só contam se nenhum dos dois lados vizinhos é andável
    for i in (1, 3, 5, 7):
        if m >> i & 1 and not (m >> ((i - 1) % 8) & 1) and not (m >> ((i + 1) % 8) & 1): k |= 1 << i
    return k

def kdist(a, b):
    """distância entre chaves: lados diferentes pesam mais que cantos"""
    return 10 * bin((a ^ b) & 0x55).count('1') + bin((a ^ b) & 0xAA).count('1')

def vnoise(H, W, rng, cell, octs=2):
    """ruído de valor suave em [0,1]"""
    out = np.zeros((H, W)); amp = 1.0; tot = 0
    for o in range(octs):
        c = max(2, cell // (2 ** o)); gh, gw = H // c + 3, W // c + 3
        g = np.array([[rng.random() for _ in range(gw)] for _ in range(gh)])
        ys = np.arange(H) / c; xs = np.arange(W) / c
        y0 = ys.astype(int); x0 = xs.astype(int); fy = ys - y0; fx = xs - x0
        fy = fy * fy * (3 - 2 * fy); fx = fx * fx * (3 - 2 * fx)
        a = g[y0][:, x0]; b = g[y0][:, x0 + 1]; c_ = g[y0 + 1][:, x0]; d = g[y0 + 1][:, x0 + 1]
        v = (a * (1 - fx) + b * fx) * (1 - fy)[:, None] + (c_ * (1 - fx) + d * fx) * fy[:, None]
        out += v * amp; tot += amp; amp *= .5
    return out / tot


# ------------------------------------------------------------------ mapa-fonte (original real)
class Fonte:
    _c = {}
    def __init__(self, src, k):
        _, maps, spr = ler_js(f'{src}/{k}.js'); d = maps[k]; self.k = k; self.spr = spr
        self.arr = np.array(Image.open(f'{src}/{k}_0.png').convert('RGBA'))
        self.h = {i: hspr(self.arr, t) for i, t in spr.items()}
        self.id = {}
        for i, h in self.h.items(): self.id.setdefault(h, i)
        self.cov = {h: float((self.arr[spr[i]['y']:spr[i]['y'] + spr[i]['h'], spr[i]['x']:spr[i]['x'] + spr[i]['w'], 3] > 16).mean()) for h, i in self.id.items()}
        self.w, self.hh = d['w'], d['h']; self.walk = np.array(d['walk'], bool).reshape(self.hh, self.w)
        self.st = [[None] * self.w for _ in range(self.hh)]
        for x, y, ids in d['tiles']:
            if ids: self.st[y][x] = tuple(self.h.get(i) for i in ids)
        ow = Counter(); ob = Counter()
        for y in range(self.hh):
            for x in range(self.w):
                s = self.st[y][x]
                if s: [(ow if self.walk[y, x] else ob).update([o]) for o in s[1:] if o]
        self.ow, self.ob = ow, ob
    @classmethod
    def get(cls, src, k):
        if (src, k) not in cls._c: cls._c[(src, k)] = Fonte(src, k)
        return cls._c[(src, k)]
    def opaco(self, h): return h is not None and self.cov.get(h, 0) >= .97
    def pixels(self, h):
        t = self.spr[self.id[h]]
        return self.arr[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w'] * t.get('n', 1)].copy(), t

def aprender_bordas(srcdir, fontes, ok=None, plano=True):
    """chave reduzida da vizinhança de andável -> Counter(pilha de hashes) de células bloqueadas reais encostadas no andável"""
    T = defaultdict(Counter); orig = {}; pm = {}
    for k in fontes:
        f = Fonte.get(srcdir, k)
        nb = Counter(); nw = Counter()
        for y in range(f.hh):
            for x in range(f.w):
                s0 = f.st[y][x]
                if s0 and len(s0) == 1 and f.opaco(s0[0]): (nw if f.walk[y, x] else nb)[s0[0]] += 1
        pm[k] = {g for g, n in nb.items() if n >= 20 and nw[g] < .3 * n}
        for y in range(f.hh):
            for x in range(f.w):
                s = f.st[y][x]
                if f.walk[y, x] or not s or s[0] is None: continue
                if any(o is None for o in s): continue
                if any(f.ow[o] > 0.2 * f.ob[o] for o in s[1:]): continue      # decoração de chão (aparece também no andável), não de borda
                c0 = f.cov.get(s[0], 0)
                if c0 < .97:     # chão vazio/parcial (bordas de gelo, areia...): o chão da massa entra por baixo (None) e o parcial vira camada
                    s = (None,) + ((s[0],) if c0 >= .05 else ()) + s[1:]
                    if len(s) == 1: continue      # só vazio: não é borda
                m = wmask(f.walk, x, y)
                if not m: continue
                if ok and not ok(f, s): continue
                if plano and len(s) == 1 and s[0] in pm[k]: continue    # chão liso de massa não é peça de borda
                T[redkey(m)][s] += 1; orig[s] = k
    return T, orig


# ------------------------------------------------------------------ mapa-alvo
class Alvo:
    def __init__(self, k, cab, d, spr, arr, srcdir):
        self.k, self.cab, self.d, self.spr, self.arr, self.srcdir = k, cab, d, spr, arr, srcdir
        self.h = {i: hspr(arr, t) for i, t in spr.items()}
        self.id = {}
        for i, h in self.h.items(): self.id.setdefault(h, i)
        self.novos = []   # (id, array RGBA, w, h, n)
        self.nid = 0
    def adotar(self, f, h):
        """garante o sprite (hash h, da fonte f) neste atlas e devolve o id"""
        if h in self.id: return self.id[h]
        a, t = f.pixels(h); self.nid += 1; i = f'{self.k}:c{self.nid}'
        self.novos.append((i, a, t['w'], t['h'], t.get('n', 1))); self.id[h] = i
        return i
    def sintetico(self, a):
        """sprite 32x32 gerado (RGBA uint8)"""
        self.nid += 1; i = f'{self.k}:c{self.nid}'; self.novos.append((i, a, 32, 32, 1)); return i
    def gravar_atlas(self, png):
        arr = self.arr; W = arr.shape[1]; y0 = arr.shape[0]; x = 0; y = y0; rowh = 0; place = []
        for i, a, w, h, n in self.novos:
            ww = w * n
            if x + ww > W: x = 0; y += rowh; rowh = 0
            place.append((i, x, y, a, w, h, n)); x += ww; rowh = max(rowh, h)
        H = y + rowh if place else y0
        out = np.zeros((H, W, 4), np.uint8); out[:y0] = arr
        src_atlas = next(iter(self.spr.values()))['src']
        for i, x, y, a, w, h, n in place:
            out[y:y + a.shape[0], x:x + a.shape[1]] = a
            self.spr[i] = {'x': x, 'y': y, 'w': w, 'h': h, 'n': n, 'src': src_atlas}
        Image.fromarray(out).save(png, optimize=True)


def tingir(a, ganho, cor, dessat=.45, rng=None, ruido=0.0, desloca=False):
    """RGBA uint8 -> RGBA uint8 com ganho de luz, cor multiplicadora e dessaturação parcial (alpha intacto)"""
    rgb = a[..., :3].astype(np.float32); lum = rgb.mean(axis=2, keepdims=True)
    rgb = (dessat * lum + (1 - dessat) * rgb) * np.array(cor, np.float32)[None, None, :] * ganho
    if desloca: rgb = np.roll(np.roll(rgb, rng.randrange(a.shape[0]), 0), rng.randrange(a.shape[1]), 1)
    if ruido: rgb = rgb * (1 + np.array([[rng.uniform(-ruido, ruido) for _ in range(a.shape[1])] for _ in range(a.shape[0])], np.float32)[..., None])
    o = a.copy(); o[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8); return o


# ------------------------------------------------------------------ KITS (por caçada)
# edge : mapas-fonte das bordas (autotile); alem dos listados usa o proprio mapa
# massa: 'chao' = (mapa-fonte, hash) base; 'tons' = (claro, escuro, queda por tile, amplitude do ruído); 'cor' multiplicador RGB;
#        'agua' = lista de chãos reais usados sem escurecer
# deco : lista de (mapa-fonte, pilha de hashes dos objetos, peso); dens = densidade
KITS = {}

ROCHA = dict(fontes=['h055', 'h063', 'h077'], chao=['c89c1bb6314a', '5d46120fa132', 'f1ed664d676b', 'fb883ad54028', 'bafccbd4fdef', '4b61773fea23', '631a3cf09ed2', '9b08ad6df3c2'],
             objs=['b0c9125cf4e5', '48cd65e40f8b', 'fe8287748238', '6dfebddc5b73', '566e75796725', 'ec3e25e0d1fa'], ganho=(.62, .36), dens=(.14, .36), amp=.3, queda=.03)
KITS['h042'] = dict(edge=['h042'], massa=dict(ROCHA, cor=(1.0, .82, .66)), prof=5)
KITS['h048'] = dict(edge=['h048'], massa=dict(ROCHA, cor=(.85, .8, 1.0)), prof=5)
KITS['h073'] = dict(edge=['h073'], massa=dict(ROCHA, cor=(.8, .8, .8), ganho=(.5, .3)), prof=5)
KITS['h093'] = dict(edge=['h093'], massa=dict(ROCHA, cor=(1.0, .85, .75)), prof=5)
KITS['h096'] = dict(edge=['h096'], massa=dict(ROCHA, cor=(.85, .9, .7), ganho=(.5, .3)), prof=5)
KITS['h065'] = dict(edge=['h065'], massa=dict(ROCHA, cor=(.95, .95, 1.0)), prof=5)
GELO = dict(ROCHA, cor=(.82, .98, 1.18), dessat=.6, ganho=(.9, .55))
KITS['h007'] = dict(edge=['h028'], massa=GELO, prof=5)
KITS['h053'] = dict(edge=['h094'], edge_ok='solo', massa=GELO, prof=5, ignorar=['e9f98b77be17', '2e44f7f6a256', '9458777cd5c7', '724ef1d8c8ab', '67abf18f4772'])
KITS['h028'] = dict(edge=['h028'], massa=GELO, prof=5)
KITS['h094'] = dict(edge=['h094'], massa=GELO, prof=5)
KITS['h041'] = dict(edge=['h041'], massa=GELO, prof=5)
KITS['h099'] = dict(edge=['h099'], massa=dict(GELO, cor=(.72, 1.0, 1.0)), prof=5)
KITS['h012'] = dict(edge=['h012'], massa=dict(ROCHA, cor=(1.3, .55, .4), dessat=.2, ganho=(.42, .26)), prof=5)
KITS['h033'] = dict(edge=['h033'], massa=dict(ROCHA, cor=(.9, .95, 1.0)), prof=5)
KITS['h039'] = dict(edge=['h039'], massa=dict(ROCHA, cor=(.95, .95, 1.0)), prof=5)
KITS['h049'] = dict(edge=['h049'], massa=dict(ROCHA, cor=(.95, .95, 1.0)), prof=5)
KITS['h052'] = dict(edge=['h052'], massa=dict(ROCHA, cor=(1.1, .95, .7), ganho=(.75, .45)), prof=5)
KITS['h084'] = dict(edge=['h084'], massa=dict(ROCHA, cor=(1.1, 1.0, .8), ganho=(.8, .5)), prof=5)
JUNGLA = dict(fontes=['h004'], chao=['f7c15eb3b9af', 'af1daa3f0e1d', '46005b5ab8df', '2984adcca282', 'b57b7cb57219', '0e0bfb757c05'],
              objs=['bfca498c8a16', 'd658ca0f4c80', '67cad06be27c', 'efe255bd650c', '813b90f9fc02', '61b416cfeddd'], ganho=(.75, .4), dens=(.25, .5), amp=.3, queda=.03, dessat=.1)
KITS['h004'] = dict(edge=['h004'], massa=JUNGLA, prof=5)
KITS['h001'] = dict(edge=['h001'], massa=dict(ROCHA, cor=(1.0, .92, .85), ganho=(.58, .34)), prof=5)
KITS['h031'] = dict(edge=['h031'], massa=dict(ROCHA, cor=(1.12, .95, .72), ganho=(.7, .42)), prof=5)
MAR = dict(agua='auto', fontes=[])
for _k in ('h070', 'h005'): KITS[_k] = dict(edge=['h013', 'h026', 'h015'], edge_ok='solo', massa=MAR, prof=5, piso_morto=False, plano=False)
# cavernas/terra com massa lisa ou fragmentos: borda do próprio mapa + rocha na cor do chão de rocha/terra real encostado no andável
AUTO = '016 017 022 023 029 034 038 046 056 058 059 064 067 071 074 075 076 083 086 089 090 091 100'.split()
def kit_auto(k): return dict(edge=[k], massa=dict(ROCHA, cor='auto'), prof=5)
def lista(): return sorted(set(KITS) | {'h' + n for n in AUTO})


# ------------------------------------------------------------------ geração
def capricho(k, srcdir, tmp, dst_js, dst_png, kit):
    rng = random.Random(zlib.crc32(('c' + k).encode()))
    r1js, r1png = f'{tmp}/{k}.js', f'{tmp}/{k}_0.png'
    RF.refazer(k, f'{srcdir}/{k}.js', f'{srcdir}/{k}_0.png', r1js, r1png, random.Random(zlib.crc32(k.encode())))
    U = dict(RF.ULTIMO)
    cab, maps, spr = ler_js(r1js); d = maps[k]; arr = np.array(Image.open(r1png).convert('RGBA'))
    A = Alvo(k, cab, d, spr, arr, srcdir)
    W_, H_ = d['w'], d['h']
    P = np.array(d['walk'], bool).reshape(H_, W_)
    st = [[None] * W_ for _ in range(H_)]
    for x, y, ids in d['tiles']: st[y][x] = tuple(ids)
    F0 = Fonte.get(srcdir, k)
    nb = Counter(); nw = Counter()
    for y in range(F0.hh):
        for x in range(F0.w):
            s0 = F0.st[y][x]
            if s0 and len(s0) == 1 and F0.opaco(s0[0]): (nw if F0.walk[y, x] else nb)[s0[0]] += 1
    PM = {g for g, n in nb.items() if n >= 20 and nw[g] < .3 * n}                 # chão liso de massa
    PISO = {g for g, n in nw.items() if n >= 10 and n > .5 * nb[g]} if kit.get('piso_morto', True) else set()   # chão de andar: piso solto/inalcançável é fragmento
    # --- células reais do recorte original (chão opaco ou objeto), em coordenadas novas
    cx0, cy0 = U['cx0'], U['cy0']; real = np.zeros((H_, W_), bool)
    for y in range(F0.hh):
        for x in range(F0.w):
            X, Y = x - cx0, y - cy0
            if not (0 <= X < W_ and 0 <= Y < H_) or U['desc'][Y, X]: continue
            s = F0.st[y][x]
            if s and (F0.opaco(s[0]) or len(s) > 1): real[Y, X] = True
            if s and any(h in kit.get('ignorar', ()) for h in s): real[Y, X] = False
            if s and len(s) == 1 and s[0] in PISO and not F0.walk[y, x]: real[Y, X] = False
    # células reais bloqueadas cujo chão original não era opaco (vazio/borda parcial com objeto/parede em cima): o "chão de enchimento" do
    # refazer vira o chão da massa nova, para parede e massa combinarem
    semchao = np.zeros((H_, W_), bool)
    for y in range(F0.hh):
        for x in range(F0.w):
            X, Y = x - cx0, y - cy0
            if 0 <= X < W_ and 0 <= Y < H_ and real[Y, X] and not P[Y, X]:
                s0 = F0.st[y][x]
                if not F0.opaco(s0[0]): semchao[Y, X] = True
    dist = cheb(P)
    prof = kit.get('prof', PROF)
    # --- "longe" ligado à borda do mapa = massa externa (refeita); longe e cercado = buraco interno (mantido)
    far = (~P) & (dist > prof); lab = np.full((H_, W_), -1, np.int32); ext = np.zeros((H_, W_), bool)
    for y in range(H_):
        for x in range(W_):
            if far[y, x] and lab[y, x] < 0:
                comp = [(x, y)]; lab[y, x] = 1; q = [(x, y)]; toca = False
                while q:
                    cx, cy = q.pop()
                    if cx in (0, W_ - 1) or cy in (0, H_ - 1): toca = True
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        nx, ny = cx + dx, cy + dy
                        if 0 <= nx < W_ and 0 <= ny < H_ and far[ny, nx] and lab[ny, nx] < 0: lab[ny, nx] = 1; q.append((nx, ny)); comp.append((nx, ny))
                if toca:
                    for cx, cy in comp: ext[cy, cx] = True
    refazer_ = (~P) & (ext | ~real)
    # "massa lisa" real (chão puro de terra/rocha que quase nunca é andável): a parte ligada ao entorno refeito também é refeita, senão
    # sobra uma placa lisa colada no andável; lagos/ilhas internos (que não se ligam ao entorno por massa lisa) ficam
    if kit.get('plano', True):
        plano = np.zeros((H_, W_), bool)
        for y in range(F0.hh):
            for x in range(F0.w):
                X, Y = x - cx0, y - cy0
                s0 = F0.st[y][x]
                if 0 <= X < W_ and 0 <= Y < H_ and real[Y, X] and not P[Y, X] and s0 and len(s0) == 1 and s0[0] in PM: plano[Y, X] = True
        q = [(x, y) for y in range(H_) for x in range(W_) if refazer_[y, x]]; vis = refazer_.copy()
        while q:
            cx, cy = q.pop()
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = cx + dx, cy + dy
                if 0 <= nx < W_ and 0 <= ny < H_ and not vis[ny, nx] and plano[ny, nx]: vis[ny, nx] = True; q.append((nx, ny))
        refazer_ |= vis & plano
    if kit.get('refazer_tudo_perto'): refazer_ |= (~P) & (dist <= kit['refazer_tudo_perto'])
    # --- bordas aprendidas
    eok = kit.get('edge_ok'); eok = (lambda f, s_: len(s_) == 1 or (s_[0] is None and len(s_) == 2)) if eok == 'solo' else eok
    T, orig = aprender_bordas(srcdir, kit['edge'], eok, kit.get('plano', True))
    # fontes: as pilhas são hashes; cada uma precisa vir da fonte que a contém
    where = {}
    for kk in kit['edge']:
        f = Fonte.get(srcdir, kk)
        for h in f.id: where.setdefault(h, f)
    chaves = list(T)
    def escolher(key):
        if key in T: c = T[key]
        else:
            if not chaves: return None
            best = min(chaves, key=lambda c: (kdist(c, key), -sum(T[c].values())))
            if kdist(best, key) > 10: return None
            c = T[best]
        items = [(s, n) for s, n in c.most_common(4) if n >= 0.35 * c.most_common(1)[0][1]]
        return rng.choices([s for s, _ in items], [n for _, n in items])[0]
    def adotar_pilha(s):
        out = []
        for h in s:
            if h is None: out.append(None); continue
            f = next(f for f in [where.get(h)] + [Fonte.get(srcdir, kk) for kk in kit['edge']] if f is not None and h in f.id)
            out.append(A.adotar(f, h))
        return tuple(out)
    cache_borda = {}
    novo = {}
    n_borda = 0
    for y in range(H_):
        for x in range(W_):
            if not refazer_[y, x]: continue
            m = wmask(P, x, y)
            if m:
                key = redkey(m)
                # variações por chave: sorteia pilha; cache por (chave, índice) para reaproveitar sprites
                s = escolher(key)
                if s is None: continue
                novo[(x, y)] = adotar_pilha(s); n_borda += 1
    # --- massa
    ms = kit['massa']
    if ms.get('cor') == 'auto':      # cor da massa = cor média do chão de rocha/terra real encostado no andável
        acc = []; 
        for y in range(H_):
            for x in range(W_):
                if real[y, x] and not P[y, x] and not refazer_[y, x] and dist[y, x] <= 4:
                    g = st[y][x][0]; t = spr.get(g)
                    if t and t['w'] == 32 and t['h'] == 32 and float((arr[t['y']:t['y'] + 32, t['x']:t['x'] + 32, 3] > 16).mean()) >= .97: acc.append(arr[t['y']:t['y'] + 32, t['x']:t['x'] + 32, :3].reshape(-1, 3).mean(0))
        m = np.mean(acc, 0) if acc else np.array([128., 120., 110.]); c = m / m.mean()
        ms = dict(ms, cor=tuple(float(1 + .55 * (v - 1)) for v in c), dessat=.6)
    noise = vnoise(H_, W_, rng, 6, 3); noise2 = vnoise(H_, W_, rng, 5, 2)
    NL = 6; cache = {}
    def tinto(f, h, lv, tipo):
        key = (h, lv, tipo)
        if key not in cache:
            a, t = f.pixels(h); g = ms['ganho'][0] + (ms['ganho'][1] - ms['ganho'][0]) * lv / (NL - 1)
            a = tingir(a, g, ms.get('cor', (1, 1, 1)), ms.get('dessat', .45), rng, .03 if tipo == 'g' else 0, tipo == 'g')
            A.nid += 1; i = f'{k}:c{A.nid}'; A.novos.append((i, a, t['w'], t['h'], t.get('n', 1))); cache[key] = i
        return cache[key]
    fz = lambda kk: Fonte.get(srcdir, kk)
    def achar(h, fontes):
        for kk in fontes:
            if h in fz(kk).id: return fz(kk)
        raise KeyError(h)
    if 'agua' in ms:
        if ms['agua'] == 'auto':      # chãos azuis (água) mais usados no próprio mapa original
            ca = Counter()
            for y in range(F0.hh):
                for x in range(F0.w):
                    s0 = F0.st[y][x]
                    if s0 and s0[0] and F0.opaco(s0[0]):
                        a_, t_ = F0.pixels(s0[0]); mm = a_[:t_['w'], :t_['w'], :3].reshape(-1, 3).mean(0)
                        if mm[2] > mm[0] + 50 and mm[2] > mm[1] + 20: ca[s0[0]] += 1
            ms = dict(ms, agua=[h for h, n in ca.most_common(3)], fontes=[k])
        agua = [A.adotar(achar(h, ms['fontes']), h) for h in ms['agua']]
    else:
        chaos = [(achar(h, ms['fontes']), h) for h in ms['chao']]; objs = [(achar(h, ms['fontes']), h) for h in ms.get('objs', [])]
    d_perto, d_longe = ms.get('dens', (.0, .0))
    def nivel(x, y):
        tv = (noise[y, x] - .5) * 2 * ms.get('amp', .5) + min(1.0, max(0, dist[y, x] - 2) * ms.get('queda', .05))
        return min(NL - 1, max(0, int(tv * NL + .5)))
    def chao_massa(x, y):
        if 'agua' in ms: return rng.choice(agua)
        f, h = chaos[int((noise2[y, x] * 7.3 + rng.random() * .8) * len(chaos)) % len(chaos)]
        return tinto(f, h, nivel(x, y), 'g')
    for y in range(H_):
        for x in range(W_):
            sc = semchao[y, x] and not refazer_[y, x]
            if (x, y) in novo or not (refazer_[y, x] or sc): continue
            if sc: novo[(x, y)] = (chao_massa(x, y),) + tuple(st[y][x][1:]); continue
            st_ = (chao_massa(x, y),)
            if 'agua' not in ms and objs and dist[y, x] >= 2:
                pr = d_perto + (d_longe - d_perto) * min(1.0, (dist[y, x] - 2) / 8.0)
                if rng.random() < pr * (.5 + noise2[y, x]):
                    f2, h2 = rng.choice(objs); st_ += (tinto(f2, h2, nivel(x, y), 'o'),)
            novo[(x, y)] = st_
    for (x, y), s_ in list(novo.items()):
        if s_[0] is None:      # borda com chão da massa por baixo
            novo[(x, y)] = (chao_massa(x, y),) + s_[1:]
    # --- decoração
    dec = []
    for (kk, s_, pe) in kit.get('deco', []):
        f = Fonte.get(srcdir, kk); dec.append((tuple(A.adotar(f, h) for h in s_), pe))
    if dec:
        ocup = np.zeros((H_, W_), bool); dens = kit.get('dens', .03)
        for y in range(H_):
            for x in range(W_):
                if (x, y) in novo and dist[y, x] >= kit.get('deco_dist', 3) and not ocup[max(0, y - 1):y + 2, max(0, x - 1):x + 2].any():
                    if rng.random() < dens * (0.4 + 1.2 * noise[y, x]):
                        o = rng.choices([s_ for s_, _ in dec], [p for _, p in dec])[0]
                        novo[(x, y)] = novo[(x, y)] + o; ocup[y, x] = True
    # --- aplica e valida
    for (x, y), s in novo.items(): st[y][x] = s
    for y in range(H_):
        for x in range(W_): assert st[y][x] is not None
    A.gravar_atlas(dst_png)
    fin = np.array(Image.open(dst_png).convert('RGBA'))
    cobre = {}
    for y in range(H_):
        for x in range(W_):
            assert st[y][x], (k, x, y)
            g = st[y][x][0]
            if g not in cobre: t = A.spr[g]; cobre[g] = float((fin[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w'], 3] > 16).mean())
            assert cobre[g] >= .97, (k, x, y, g)         # chão sempre opaco: nada de buraco/preto
            for i in st[y][x]: assert i in A.spr, (k, i)
    assert not P[:RF.MARGEM_Y - 1].any() and not P[-RF.MARGEM_Y + 1:].any() and not P[:, :RF.MARGEM_X - 1].any() and not P[:, -RF.MARGEM_X + 1:].any()
    nd = dict(d); nd['tiles'] = [[x, y, list(st[y][x])] for y in range(H_) for x in range(W_)]
    cab2 = cab[:-2].rstrip() + f'; {MARCA2} */' if cab.endswith('*/') else cab
    out = [cab2, 'window.MAPAS=Object.assign(window.MAPAS||{},' + jdump({k: nd}) + ');',
           'window.MAPAS_SPRITES=window.MAPAS_SPRITES||{tiles:{},criaturas:{}};Object.assign(window.MAPAS_SPRITES.tiles,' + jdump(A.spr) + ');']
    open(dst_js, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    return dict(w=W_, h=H_, refeitas=int(refazer_.sum()), bordas=n_borda, novos=len(A.novos))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--src', required=True, help='pasta com os mapas ORIGINAIS (hNNN.js/_0.png)')
    ap.add_argument('--dst'); ap.add_argument('hunts', nargs='*'); a = ap.parse_args()
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tibia-assets', 'mapas15', 'cacadas')
    dst = a.dst or raiz; os.makedirs(dst, exist_ok=True)
    tmp = tempfile.mkdtemp()
    try:
        for k in a.hunts or lista():
            r = capricho(k, a.src, tmp, f'{dst}/{k}.js', f'{dst}/{k}_0.png', KITS.get(k) or kit_auto(k)); print(k, r, flush=True)
    finally: shutil.rmtree(tmp, ignore_errors=True)

if __name__ == '__main__': main()
