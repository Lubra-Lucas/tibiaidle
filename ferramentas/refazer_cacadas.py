#!/usr/bin/env python3
"""Refaz os mapas das 100 caçadas (tibia-assets/mapas15/cacadas/hNNN.js + hNNN_0.png) para que nenhum tile visível fique vazio/preto.

Causa dos pixels pretos: os mapas originais são recortes retangulares de mapas OTBM reais. O jogo só desenha o que o mapa tem; fora
disso o canvas fica preto: (a) células sem tile, (b) ground null, (c) ground "0" transparente do OTBM (o "vazio" das cavernas),
(d) ground parcialmente transparente (bordas) e, principalmente, (e) tudo além do recorte (46x46 tiles, menor que a tela) assim que
o personagem anda perto de uma borda, além de caminhos andáveis que simplesmente terminam na borda do recorte.

O que esta ferramenta faz em cada mapa (nada é desenhado à mão: tudo é aprendido do próprio mapa):
  1. acha a área alcançável a partir de "inicio" (8 vizinhos, como o jogo anda); o que é andável mas inalcançável vira bloqueado;
  2. amplia o mapa: alcançável + margem (MARGEM_X/MARGEM_Y tiles) maior que o raio visível da câmera;
  3. normaliza cada pilha: ground vazio/null/transparente vira o marcador 'G' (chão sólido a definir); ground parcialmente transparente
     vira objeto sobre um 'G';
  4. descarta o "vazio" colado no andável e tudo fora do recorte e os RECRIA por síntese de textura em grade (Efros-Leung): cada célula
     nova copia a pilha de uma célula bloqueada do mapa cuja vizinhança (8 vizinhos, andável x bloqueado, orientação) combina com a
     vizinhança já conhecida. Resultado: paredes/bordas/margens de água/árvores continuam com a mesma orientação e estilo do mapa;
  5. 'G' recebe o chão de rocha/terra vizinho do próprio mapa ou, sem exemplo, um chão sólido sintético (textura do chão do mapa
     escurecida; novos sprites 'hNNN:fK' no atlas);
  6. valida: nenhuma célula vazia, todo ground opaco, spawns/inicio andáveis e alcançáveis, nada andável perto da borda.
Uso: refazer_cacadas.py [--src DIR_DOS_ORIGINAIS] [--dst DIR] [h001 h002 ...]   (padrão: lê e grava no repositório; recusa o que já foi refeito)"""
import sys, os, re, json, random, argparse, heapq, zlib
from collections import Counter, deque
import numpy as np
from PIL import Image

MARGEM_X, MARGEM_Y = 20, 16      # câmera: até ~±20 tiles (2560px a zoom 2) / ±15 (tablet em pé); folga para não aparecer fora do mapa
MARCA = 'refeitas por ferramentas/refazer_cacadas.py'
VIZ = [(0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]   # N NE L SE S SO O NO
CTX = VIZ + [(dx, dy) for dy in range(-2, 3) for dx in range(-2, 3) if max(abs(dx), abs(dy)) == 2]   # contexto 5x5 (24 vizinhos)
PESO = np.array([3, 2, 3, 2, 3, 2, 3, 2] + [1] * 16, np.float32)

def ler_js(p):
    s = open(p, encoding='utf-8').read()
    k = 'Object.assign(window.MAPAS||{},'
    a = s.index(k) + len(k); j = s.index('window.MAPAS_SPRITES')
    maps = json.loads(s[a:j].rstrip().rstrip(';')[:-1])
    t = re.search(r'Object\.assign\(window\.MAPAS_SPRITES\.tiles,', s)
    spr = json.loads(s[t.end():].rstrip().rstrip(';')[:-1])
    return s.split('\n')[0], maps, spr

def jdump(o): return json.dumps(o, ensure_ascii=False, separators=(',', ':'))

class Atlas:
    def __init__(self, png):
        self.arr = np.array(Image.open(png).convert('RGBA')); self.cache = {}; self.novo = False
    def cov(self, spr, i):
        if i is None or i not in spr: return 0.0
        if i not in self.cache:
            t = spr[i]; a = self.arr[t['y']:t['y'] + t['h'], t['x']:t['x'] + t['w'], 3]
            self.cache[i] = float((a > 16).mean())
        return self.cache[i]

def refazer(k, src_js, src_png, dst_js, dst_png, rng):
    cab, maps, spr = ler_js(src_js)
    if MARCA in cab: raise SystemExit(f'{k}: já refeito (use --src com os originais)')
    d = maps[k]; w0, h0 = d['w'], d['h']; at = Atlas(src_png)
    src_atlas = next(iter(spr.values()))['src']
    GC = lambda i: at.cov(spr, i)
    wk0 = d['walk']
    # --- 1. alcançável a partir do início (8 vizinhos)
    sx, sy = d['inicio']
    if not wk0[sy * w0 + sx]:
        sx, sy = min((abs(x - sx) + abs(y - sy), x, y) for y in range(h0) for x in range(w0) if wk0[y * w0 + x])[1:]
    seen = {(sx, sy)}; q = deque([(sx, sy)])
    while q:
        x, y = q.popleft()
        for dx, dy in VIZ:
            nx, ny = x + dx, y + dy
            if 0 <= nx < w0 and 0 <= ny < h0 and wk0[ny * w0 + nx] and (nx, ny) not in seen: seen.add((nx, ny)); q.append((nx, ny))
    xs = [p[0] for p in seen]; ys = [p[1] for p in seen]
    cx0, cy0 = min(xs) - MARGEM_X, min(ys) - MARGEM_Y
    W, H = max(xs) + MARGEM_X - cx0 + 1, max(ys) + MARGEM_Y - cy0 + 1
    walk = np.zeros((H, W), bool)
    for x, y in seen: walk[y - cy0, x - cx0] = True
    # --- 2/3. pilhas normalizadas: ground 'G' = a definir
    st = [[None] * W for _ in range(H)]; inrect = np.zeros((H, W), bool)
    T0 = {(x, y): ids for x, y, ids in d['tiles']}
    for y in range(h0):
        for x in range(w0):
            X, Y = x - cx0, y - cy0
            if not (0 <= X < W and 0 <= Y < H): continue
            inrect[Y, X] = True; ids = T0.get((x, y))
            if not ids: st[Y][X] = ('G',); continue
            g, objs = ids[0], [o for o in ids[1:] if o in spr]
            c = GC(g)
            if c >= .97: st[Y][X] = (g,) + tuple(objs)
            elif c < .05: st[Y][X] = ('G',) + tuple(objs)
            else: st[Y][X] = ('G', g) + tuple(objs)
    # sprites de objeto que aparecem mais em células andáveis (decoração do chão, escadas...) não servem de "massa"
    ow = Counter(); ob = Counter()
    for y in range(H):
        for x in range(W):
            if st[y][x]:
                for o in st[y][x][1:]: (ow if walk[y, x] else ob)[o] += 1
    ruim = {o for o in ow if ow[o] > ob[o]}
    # distância (Chebyshev) ao andável
    dist = np.full((H, W), 99, np.int32); dist[walk] = 0; fr = walk.copy()
    for r in range(1, 6):
        m = np.pad(fr, 1); viz = np.zeros((H, W), bool)
        for dy in range(3):
            for dx in range(3): viz |= m[dy:dy + H, dx:dx + W]
        novo = viz & (dist == 99); dist[novo] = r; fr = novo
    # --- células a recriar: fora do recorte + "vazio" puro colado no andável
    desc = ~inrect
    for y in range(H):
        for x in range(W):
            if inrect[y, x] and not walk[y, x] and st[y][x] == ('G',) and dist[y, x] <= 1: desc[y, x] = True
    for y in range(H):
        for x in range(W):
            if desc[y, x]: st[y][x] = None
    # --- 4. síntese de textura em grade
    ids_code = {}; code = np.full((H, W), -1, np.int32)
    def cod(s):
        if s not in ids_code: ids_code[s] = len(ids_code) + 1
        return ids_code[s]
    for y in range(H):
        for x in range(W):
            if walk[y, x]: code[y, x] = 0
            elif st[y][x] is not None: code[y, x] = cod(st[y][x])
    def ctx(y, x):
        r = []
        for dx, dy in CTX:
            nx, ny = x + dx, y + dy
            r.append(code[ny, nx] if 0 <= nx < W and 0 <= ny < H else -1)
        return r
    # componentes bloqueados pequenos e cercados de andável (poças, buracos, salas fechadas) não servem de exemplo
    comp = np.full((H, W), -1, np.int32); ncomp = 0; csz = []; ctouch = []
    for y in range(H):
        for x in range(W):
            if walk[y, x] or desc[y, x] or not inrect[y, x] or comp[y, x] >= 0: continue
            comp[y, x] = ncomp; qq = [(x, y)]; n = 0; touch = False
            while qq:
                cx_, cy_ = qq.pop(); n += 1
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = cx_ + dx, cy_ + dy
                    if not (0 <= nx < W and 0 <= ny < H) or not inrect[ny, nx]: touch = True; continue
                    if walk[ny, nx] or desc[ny, nx] or comp[ny, nx] >= 0: continue
                    comp[ny, nx] = ncomp; qq.append((nx, ny))
            csz.append(n); ctouch.append(touch); ncomp += 1
    gw = Counter(); gon = Counter()
    for y in range(H):
        for x in range(W):
            if not inrect[y, x] or desc[y, x]: continue
            g = st[y][x][0]
            if g == 'G': continue
            if walk[y, x]: gw[g] += 1
            elif len(st[y][x]) == 1: gon[g] += 1
    piso = lambda g: g != 'G' and gw[g] > 0.5 * gon[g]          # chão que também é andável (areia, grama, piso)
    def massa_ok(s):
        bloq = any(ob[o] > 2 * ow[o] for o in s[1:])
        if len(s) == 1: return not piso(s[0])
        if bloq: return True
        return s[0] != 'G' and not piso(s[0])
    cand = []; cctx = []; cpos = []
    for y in range(H):
        for x in range(W):
            if walk[y, x] or desc[y, x] or not inrect[y, x]: continue
            if csz[comp[y, x]] < 40 and not ctouch[comp[y, x]]: continue
            s = st[y][x]
            if not massa_ok(s): continue
            c = ctx(y, x)
            if sum(1 for v in c[:8] if v >= 0) < 8 or sum(1 for v in c if v >= 0) < 20: continue
            cand.append(s); cctx.append(c); cpos.append((x, y))
    if not cand:   # mapa sem exemplo de massa: usa o 'vazio' puro
        cand = [('G',)] * 8; cctx = [[cod(('G',))] * 24] * 8; cpos = [(0, 0)] * 8
    cctx = np.array(cctx, np.int32); cpx = np.array([p[0] for p in cpos]); cpy = np.array([p[1] for p in cpos])
    rx0, rx1 = int(np.flatnonzero(inrect.any(0))[0]), int(np.flatnonzero(inrect.any(0))[-1])
    ry0, ry1 = int(np.flatnonzero(inrect.any(1))[0]), int(np.flatnonzero(inrect.any(1))[-1])
    heap = []; cnt = np.zeros((H, W), np.int32)
    def kn(y, x): return sum(1 for v in ctx(y, x) if v >= 0)
    for y in range(H):
        for x in range(W):
            if code[y, x] < 0 and desc[y, x]:
                c = kn(y, x)
                if c: heapq.heappush(heap, (-c, rng.random(), y, x))
    feitos = 0
    while heap:
        nc, _, y, x = heapq.heappop(heap)
        if code[y, x] >= 0: continue
        t = np.array(ctx(y, x), np.int32); c = int((t >= 0).sum())
        if c != -nc:
            heapq.heappush(heap, (-c, rng.random(), y, x)); continue
        m = t >= 0
        match = (cctx == t) & m
        wmis = ((cctx == 0) != (t == 0)) & m
        score = (match * PESO).sum(1) - (wmis * PESO * 3).sum(1)
        best = score.max(); tol = 0.0 if rng.random() > .12 else 2.0
        idx = np.flatnonzero(score >= best - tol)
        # localidade: prefere exemplos perto do ponto do recorte original mais próximo deste (mantém o ambiente: prédio perto de prédio...)
        px_, py_ = min(max(x, rx0), rx1), min(max(y, ry0), ry1)
        dl = np.maximum(np.abs(cpx[idx] - px_), np.abs(cpy[idx] - py_)).astype(np.float64)
        wl = 1.0 / (1.0 + dl / 6.0) ** 2
        s = cand[int(idx[np.searchsorted(np.cumsum(wl), rng.random() * wl.sum())])]
        st[y][x] = s; code[y, x] = cod(s); feitos += 1
        for dx, dy in VIZ:
            nx, ny = x + dx, y + dy
            if 0 <= nx < W and 0 <= ny < H and code[ny, nx] < 0 and desc[ny, nx]: heapq.heappush(heap, (-kn(ny, nx), rng.random(), ny, nx))
    for y in range(H):
        for x in range(W): assert st[y][x] is not None, (k, x, y)
    # --- 5. ground 'G'
    synth = []
    def gsint():
        if synth: return rng.choice(synth)
        cg = Counter(); cw = Counter()
        for y in range(H):
            for x in range(W):
                if not inrect[y, x]: continue
                g = st[y][x][0]
                if g == 'G' or GC(g) < .97: continue
                if walk[y, x]: cw[g] += 1
                elif any(ob[o] > 2 * ow[o] for o in st[y][x][1:]): cg[g] += 1
        cg = Counter({g: n for g, n in cg.items() if not piso(g)})
        base = (cg or cw).most_common(1)[0][0]; t = spr[base]
        a = at.arr[t['y']:t['y'] + 32, t['x']:t['x'] + 32, :3].astype(np.float32)
        a = 0.3 * a + 0.7 * a.mean(axis=2, keepdims=True); a = a * ((72 if d.get('escuro') else 96) / max(1.0, a.mean()))   # textura do chão, dessaturada, na luminosidade de uma rocha escura
        vs = []
        for v in range(6):
            b = np.roll(np.roll(a, rng.randrange(32), 0), rng.randrange(32), 1)
            b = b * (1 + np.array([[rng.uniform(-.05, .05) for _ in range(32)] for _ in range(32)], np.float32)[..., None])
            for _ in range(3):
                px, py = rng.randrange(32), rng.randrange(32)
                for _s in range(rng.randrange(5, 12)):
                    px = (px + rng.choice((-1, 0, 1))) % 32; py = (py + rng.choice((0, 1))) % 32; b[py, px] *= .65
            vs.append(np.clip(b, 0, 255).astype(np.uint8))
        H0 = at.arr.shape[0]; add = np.zeros((32, at.arr.shape[1], 4), np.uint8)
        for v, b in enumerate(vs):
            add[:, v * 32:(v + 1) * 32, :3] = b; add[:, v * 32:(v + 1) * 32, 3] = 255
            nid = f'{k}:f{v}'; spr[nid] = {'x': v * 32, 'y': H0, 'w': 32, 'h': 32, 'n': 1, 'src': src_atlas}; synth.append(nid)
        at.arr = np.concatenate([at.arr, add], 0); at.cache.clear(); at.novo = True
        return rng.choice(synth)
    # chãos de "massa" do próprio mapa: ground puro (sem objeto) em célula bloqueada, que não é também chão de célula andável
    mw = Counter(); mu = Counter()
    for y in range(H):
        for x in range(W):
            if not inrect[y, x] or desc[y, x]: continue
            g = st[y][x][0]
            if g == 'G' or GC(g) < .97: continue
            if walk[y, x]: mu[g] += 1
            elif len(st[y][x]) == 1: mw[g] += 1
    totn = sum(1 for y in range(H) for x in range(W) if inrect[y, x] and not desc[y, x] and not walk[y, x] and st[y][x][0] != 'G')
    massa = {g for g, n in mw.items() if n >= max(25, 0.04 * totn) and not piso(g)}
    mpos = [(y, x, st[y][x][0]) for y in range(H) for x in range(W)
            if inrect[y, x] and not desc[y, x] and not walk[y, x] and len(st[y][x]) == 1 and st[y][x][0] in massa]
    if mpos:
        my = np.array([p[0] for p in mpos]); mx = np.array([p[1] for p in mpos]); mg = [p[2] for p in mpos]
        mglob = Counter(mg).most_common(3)
    def gmassa(y, x):
        if not mpos: return None
        dd = np.maximum(np.abs(my - y), np.abs(mx - x))
        if dd.min() > 14: tops = mglob
        else:
            j = np.flatnonzero(dd <= dd.min() + 1); tops = Counter(mg[i] for i in j).most_common(3)
        return rng.choices([a for a, _ in tops], [n for _, n in tops])[0]
    def vizw(y, x):
        c = Counter()
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and walk[ny, nx] and st[ny][nx][0] != 'G' and GC(st[ny][nx][0]) >= .97: c[st[ny][nx][0]] += 1
        return c
    stats = Counter()
    for y in range(H):
        for x in range(W):
            s = st[y][x]
            if s[0] != 'G': continue
            if walk[y, x]:
                c = vizw(y, x); g = c.most_common(1)[0][0] if c else gsint()
            else:
                g = gmassa(y, x) or gsint(); stats['sint'] += g.startswith(k + ':f')
            st[y][x] = (g,) + s[1:]; stats['G'] += 1
    # --- 6. validação
    for y in range(H):
        for x in range(W):
            s = st[y][x]
            assert GC(s[0]) >= .97, (k, x, y, s)
            for i in s[1:]: assert i in spr, (k, i)
    assert not walk[:MARGEM_Y - 1].any() and not walk[-MARGEM_Y + 1:].any() and not walk[:, :MARGEM_X - 1].any() and not walk[:, -MARGEM_X + 1:].any()
    nd = dict(d); nd['w'], nd['h'] = W, H
    if d.get('origem'): nd['origem'] = [d['origem'][0] + cx0, d['origem'][1] + cy0, d['origem'][2]]
    nd['tiles'] = [[x, y, list(st[y][x])] for y in range(H) for x in range(W)]
    nd['walk'] = [int(v) for v in walk.flatten()]
    nd['spawns'] = [[s[0] - cx0, s[1] - cy0] + list(s[2:]) for s in d['spawns'] if (s[0], s[1]) in seen]
    nd['inicio'] = [sx - cx0, sy - cy0]
    assert walk[nd['inicio'][1], nd['inicio'][0]]
    for s in nd['spawns']: assert walk[s[1], s[0]]
    cab2 = cab[:-2].rstrip() + f'; bordas {MARCA} */' if cab.endswith('*/') else cab
    out = [cab2, 'window.MAPAS=Object.assign(window.MAPAS||{},' + jdump({k: nd}) + ');',
           'window.MAPAS_SPRITES=window.MAPAS_SPRITES||{tiles:{},criaturas:{}};Object.assign(window.MAPAS_SPRITES.tiles,' + jdump(spr) + ');']
    if at.novo: Image.fromarray(at.arr).save(dst_png, optimize=True)
    elif os.path.abspath(src_png) != os.path.abspath(dst_png): open(dst_png, 'wb').write(open(src_png, 'rb').read())
    open(dst_js, 'w', encoding='utf-8').write('\n'.join(out) + '\n')
    return dict(w=W, h=H, ant=(w0, h0), recriadas=int(desc.sum()), G=stats['G'], sint=stats['sint'], cand=len(cand), spawns=len(nd['spawns']), alc=len(seen))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--src'); ap.add_argument('--dst'); ap.add_argument('hunts', nargs='*'); a = ap.parse_args()
    raiz = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tibia-assets', 'mapas15', 'cacadas')
    src = a.src or raiz; dst = a.dst or raiz
    os.makedirs(dst, exist_ok=True)
    for k in a.hunts or ['h%03d' % n for n in range(1, 101)]:
        r = refazer(k, f'{src}/{k}.js', f'{src}/{k}_0.png', f'{dst}/{k}.js', f'{dst}/{k}_0.png', random.Random(zlib.crc32(k.encode())))
        print(k, r, flush=True)
if __name__ == '__main__': main()
