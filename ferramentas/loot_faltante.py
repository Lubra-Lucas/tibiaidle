#!/usr/bin/env python3
"""Completa o loot do jogo com os itens reais do Canary que tinham ficado de fora (sem sprite no cliente antigo) e acrescenta ao loot dos monstros/bosses as
entradas que faltavam (chance e maxCount reais do Canary, chance/100000).

Fontes: Canary (data-otservbr-global/monster/**.lua, data/items/items.xml, data/items/appearances.dat, npc/*.lua) e os ícones reais do cliente 15.10, que este
script NAO extrai: rode antes  ferramentas/extrair_cliente.py --itens <cids> --saida tibia-assets/sprites15/itens  (o script imprime os cids que faltam).
Preço (v): o maior preço de compra de NPC do Canary (npc/*.lua, igual ao appearances.dat); sem comprador de NPC, estimativa marcada com 'estimado' (tabela EST).
Equipamento que o modelo do jogo entende (espada de 1 mão, arco/besta, armadura, bota, escudo) vira item equipável de boss (chefes.js 'eq'); machados, clavas, armas de
2 mãos, anéis etc. entram só como loot para vender (os spellbooks viraram escudos de mage: index.html e livros_eq.py). Idempotente: pode rodar de novo. Uso:
  loot_faltante.py CANARY_DIR [--out tibia-assets]"""
import sys, os, re, json, glob, argparse, struct

ap = argparse.ArgumentParser(); ap.add_argument('canary'); ap.add_argument('--out', default='tibia-assets'); ap.add_argument('--dry', action='store_true'); ap.add_argument('--pular-sem-preco', action='store_true', help='itens sem comprador de NPC nem estimativa (lixo cosmético, comida, troféus...) ficam de fora em vez de abortar')
A = ap.parse_args(); CAN = A.canary.rstrip('/') + '/'; OUT = A.out.rstrip('/') + '/'

def carregar(p, var):
    s = open(p, encoding='utf-8').read(); m = 'window.' + var + '='; i = s.index(m) + len(m); o, j = json.JSONDecoder().raw_decode(s[i:]); return s, i, j, o
def gravar(p, var, s, i, j, o):   # relê o arquivo logo antes de gravar (outros processos mexem nos campos de sprite): só mescla itens novos, eq novos e o loot dos monstros
    s2 = open(p, encoding='utf-8').read(); i2 = s2.index('window.' + var + '=') + len('window.' + var + '='); o2, j2 = json.JSONDecoder().raw_decode(s2[i2:])
    for k, v in o['itens'].items(): o2['itens'].setdefault(k, v)
    for k, m in o['mobs'].items():
        if k in o2['mobs']: o2['mobs'][k]['loot'] = m['loot']
    if 'eq' in o:
        ids = {e['id'] for e in o2['eq']}; o2['eq'] += [e for e in o['eq'] if e['id'] not in ids]
    open(p, 'w', encoding='utf-8').write(s2[:i2] + json.dumps(o2, ensure_ascii=False, separators=(',', ':')) + s2[i2 + j2:])

# ---------------------------------------------------------------- Canary
def items_xml():
    s = open(CAN + 'data/items/items.xml', encoding='latin-1').read(); by_id = {}; by_name = {}
    for m in re.finditer(r'<item (?:id="(\d+)"|fromid="(\d+)" toid="(\d+)")([^>]*?)(/>|>(.*?)</item>)', s, re.S):
        n = re.search(r'name="([^"]*)"', m.group(4))
        if not n: continue
        for i in range(int(m.group(1) or m.group(2)), int(m.group(1) or m.group(3)) + 1):
            d = {'id': i, 'name': n.group(1), 'attr': dict(re.findall(r'<attribute key="([^"]+)" value="([^"]*)"', m.group(6) or ''))}
            by_id[i] = d; by_name.setdefault(d['name'].lower(), d)
    return by_id, by_name
XID, XNAME = items_xml()
def _vi(b, i):
    r = 0; s = 0
    while True:
        c = b[i]; i += 1; r |= (c & 0x7f) << s; s += 7
        if c < 0x80: return r, i
def _campos(b):
    i = 0
    while i < len(b):
        k, i = _vi(b, i); f, t = k >> 3, k & 7
        if t == 0: v, i = _vi(b, i)
        elif t == 2: l, i = _vi(b, i); v = b[i:i + l]; i += l
        elif t == 1: v = b[i:i + 8]; i += 8
        elif t == 5: v = b[i:i + 4]; i += 4
        else: raise ValueError(t)
        yield f, v
def appearances():   # nomes (objetos sem entrada no items.xml, ex.: itens novos) e preço de compra dos NPCs (campo npcsaledata.buy_price)
    o = {}
    for f, v in _campos(open(CAN + 'data/items/appearances.dat', 'rb').read()):
        if f != 1: continue
        d = {'id': 0, 'name': '', 'buy': 0}
        for g, w in _campos(v):
            if g == 1: d['id'] = w
            elif g == 4: d['name'] = w.decode('utf-8', 'replace')
            elif g == 3:
                for h, x in _campos(w):
                    if h == 40:
                        s = dict(_campos(x))
                        if not s.get(5): d['buy'] = max(d['buy'], s.get(4, 0))
        o[d['id']] = d
    return o
APP = appearances(); APP_NAME = {}
for d in APP.values(): APP_NAME.setdefault(d['name'].lower(), d)
SELL = {}
for f in glob.glob(CAN + 'data-otservbr-global/npc/*.lua'):
    for m in re.finditer(r'itemName = "([^"]+)", clientId = (\d+)(?:, buy = \d+)?, sell = (\d+)', open(f, errors='ignore').read()):
        SELL[int(m.group(2))] = max(SELL.get(int(m.group(2)), 0), int(m.group(3)))
SELL_NOME = {}
for i, p in SELL.items():
    nm = (XID.get(i) or {}).get('name') or (APP.get(i) or {}).get('name')
    if nm: SELL_NOME[nm.lower()] = max(SELL_NOME.get(nm.lower(), 0), p)
def campos(t):
    return {k: v.strip('"') for k, v in re.findall(r'(\w+)\s*=\s*("[^"]*"|[-\w\.]+)', t)}
def bloco(s, nome):
    m = re.search(r'monster\.' + nome + r' = \{\n(.*?)\n\}', s, re.S); return m.group(1) if m else ''
MON = {}
for f in glob.glob(CAN + 'data-otservbr-global/monster/**/*.lua', recursive=True):
    s = open(f, encoding='utf-8', errors='ignore').read(); nm = re.search(r'Game\.createMonsterType\("([^"]+)"\)', s)
    if nm: MON[nm.group(1).lower()] = s
def resolver(e):   # entrada de loot -> (id do cliente, nome)
    if 'name' in e:
        n = e['name'].lower(); d = XNAME.get(n)
        if d: return d['id'], d['name']
        d = APP_NAME.get(n); return (d['id'], d['name']) if d else (None, e['name'])
    i = int(e['id']); n = (XID.get(i) or APP.get(i) or {}).get('name'); return (i, n) if n else (None, str(i))

# ---------------------------------------------------------------- estimativas e equipamentos
# preço estimado (gp) dos itens sem comprador de NPC no Canary (marcados 'estimado'): faixas por tipo/raridade, nada que desequilibre a economia do boss
EST = {
  "ferumbras' hat": 3000, "orshabaal's brain": 5000, 'blue tome': 1000, 'calamity': 20000, 'cluster of solace': 1500, 'dream matter': 1000, 'unrealized dream': 2000,
  'demonic tapestry': 5000, 'psychedelic tapestry': 5000, 'nightmare beacon': 3000, 'nightmare horn': 3000, 'eye pod': 2000, 'dream warden mask': 8000,
  'phoenix charm': 2500, 'solitude charm': 2500, 'spiritual charm': 2500, 'twin sun charm': 2500, 'unity charm': 2500, 'infernal bolt': 5,
  'teddy bear': 3000, 'piggy bank': 4000, 'twin axe': 5000, 'ravenwing': 12000, 'skullcrusher': 6000, 'hellforged axe': 15000, 'demonwing axe': 25000, 'havoc blade': 15000,
  'frozen plate': 10000, 'oceanborn leviathan armor': 20000, 'ghazbaran oyoroi': 20000, 'velvet mantle': 15000, 'golden boots': 15000, 'emerald sword': 20000,
  'spellbook of dark mysteries': 12000, 'spellscroll of prophecies': 10000, 'gold token': 1000, 'silver token': 200, 'mysterious remains': 1500, 'library ticket': 500,
  'supreme health potion': 150, 'ultimate spirit potion': 350, 'unstable darklight matter': 2500, 'darklight obsidian axe': 5000,
}
for pre, v in (('crude umbral', 4000), ('umbral master', 40000), ('umbral', 12000)):   # armas umbral por faixa: crude < normal < master
    for t in ('axe', 'blade', 'bow', 'chopper', 'crossbow', 'hammer', 'katar', 'mace', 'slayer', 'spellbook', 'masterblade'):
        n = f'{pre} {t}'.replace('umbral master masterblade', 'umbral masterblade')
        EST.setdefault(n, v)
EST['umbral masterblade'] = 40000
PESO_EST = {'bulltaur horn': 2.5, 'bulltaur hoof': 3.0, 'bulltaur armor scrap': 3.0, 'encrypted notes': .3, 'strange substance': 1.0, 'unstable darklight matter': 1.0, 'darklight obsidian axe': 80.0}
# equipável no modelo do jogo (nome Canary: slot, vocações (None = todas), tipo de arma, estatística, level). arm = armor real+1, def = defense real+2 (como em gerar_chefes.py);
# atk de espada/arco acima do magic longsword (55) e abaixo do warlord (70), acompanhando o ataque real (48-52)
K, P, S, D = ['knight'], ['paladin'], ['sorcerer'], ['druid']
EQ = {
  'crude umbral blade': ('weapon', K, 'sword', {'atk': 54}, 70), 'umbral blade': ('weapon', K, 'sword', {'atk': 57}, 80), 'umbral masterblade': ('weapon', K, 'sword', {'atk': 60}, 90),
  'runed sword': ('weapon', K, 'sword', {'atk': 52}, 60), 'emerald sword': ('weapon', K, 'sword', {'atk': 56}, 75),
  'crude umbral bow': ('weapon', P, 'distance', {'atk': 56}, 75), 'umbral bow': ('weapon', P, 'distance', {'atk': 59}, 85), 'umbral master bow': ('weapon', P, 'distance', {'atk': 62}, 95),
  'crude umbral crossbow': ('weapon', P, 'distance', {'atk': 56}, 75), 'umbral crossbow': ('weapon', P, 'distance', {'atk': 59}, 85), 'umbral master crossbow': ('weapon', P, 'distance', {'atk': 62}, 95),
  'frozen plate': ('armor', K + P, None, {'arm': 14}, 60), 'oceanborn leviathan armor': ('armor', K + P, None, {'arm': 16}, 100), 'ghazbaran oyoroi': ('armor', K + P, None, {'arm': 15}, 110),
  'greenwood coat': ('armor', P + S + D, None, {'arm': 13}, 80), 'velvet mantle': ('armor', S + D, None, {'arm': 13}, 80), 'golden boots': ('boots', None, None, {'arm': 5}, 100),
  'phoenix shield': ('shield', K + P, None, {'def': 36}, 90), 'tempest shield': ('shield', K + P, None, {'def': 38}, 110), 'rift shield': ('shield', K + P, None, {'def': 39}, 125),
}

def titulo(n):
    p = n.split(); return ' '.join(w.capitalize() if i == 0 or w not in ('of', 'the') else w for i, w in enumerate(p))
slug = lambda n: re.sub(r'[^a-z0-9]+', '_', n.lower()).strip('_')

# ---------------------------------------------------------------- dados do jogo
sc, ic, jc, CD = carregar(OUT + 'cacadas100.js', 'CACADAS100'); sh, ih, jh, CH = carregar(OUT + 'chefes.js', 'CHEFES')
MOBS = dict(CD['mobs']); MOBS.update(CH['mobs']); EM_CH = set(CH['mobs'])
ITENS = dict(CD['itens']); ITENS.update(CH['itens'])
por_nome = {v['n'].lower(): k for k, v in ITENS.items()}; por_cid = {v.get('cid'): k for k, v in ITENS.items()}
eq_ids = {e['id']: e for e in CH['eq']}; eq_nome = {e['n'].lower(): e['id'] for e in CH['eq']}
EQ_CID = {int(os.path.basename(v)[:-4]): k for k, v in CD['icones'].items()}   # equipamentos do jogo (ids do HTML) pelo cid do ícone
EQ_JOGO = {}   # nome minúsculo -> id de equipamento/poção definido no index.html: só os que têm ícone conhecido
for cid, k in EQ_CID.items():
    nm = (XID.get(cid) or {}).get('name')
    if nm: EQ_JOGO.setdefault(nm.lower(), k)
sem_icone = set(); novos = []; falta_preco = []

def garantir(cid, nome, mobs_dest):
    """devolve a chave de loot do item (existente ou criado); mobs_dest: 'cd' (item usado por monstro de caçada) ou 'ch'"""
    n = nome.lower()
    if n in por_nome: return por_nome[n]
    if cid in por_cid: return por_cid[cid]
    if n in eq_nome: return eq_nome[n]
    if n in EQ_JOGO: return EQ_JOGO[n]
    if not os.path.exists(f'{OUT}sprites15/itens/{cid}.png'): sem_icone.add((cid, nome)); return None
    xd = XID.get(cid) or {}; w = (int(xd.get('attr', {}).get('weight', 0)) / 100) if xd.get('attr', {}).get('weight') else PESO_EST.get(n, 1.0)
    preco = SELL.get(cid) or SELL_NOME.get(n) or (APP.get(cid) or {}).get('buy') or 0; est = False
    if not preco: preco = EST.get(n, 0); est = True
    if not preco: falta_preco.append(nome); return None
    k = slug(n)
    if n in EQ:
        slot, voc, wt, st, lv = EQ[n]; r = {'id': k, 'n': titulo(n), 'slot': slot, 'wt': wt, 'st': st, 'lv': lv, 'w': round(w, 1), 'v': preco, 'icone': f'tibia-assets/sprites15/itens/{cid}.png', 'conj': 'boss',
                                            'real': {'cid': cid, 'armor': xd.get('attr', {}).get('armor'), 'defense': xd.get('attr', {}).get('defense'), 'attack': xd.get('attr', {}).get('attack')}}
        if voc: r['voc'] = voc
        CH['eq'].append(r); eq_nome[n] = k; novos.append(('eq', nome, preco, est)); return k
    it = {'n': titulo(n), 'w': round(w, 2) if w < 1 else round(w, 1), 'v': preco, 'type': 'loot', 'cid': cid}
    if est: it['estimado'] = True
    it['icone'] = f'tibia-assets/sprites15/itens/{cid}.png'
    (CD if mobs_dest == 'cd' else CH)['itens'][k] = it; por_nome[n] = k; por_cid[cid] = k; novos.append(('item', nome, preco, est)); return k

# ---------------------------------------------------------------- loot dos monstros
adds = {}; tot = 0
for mk, m in MOBS.items():
    s = MON.get(m['n'].lower())
    if not s: continue
    dest = 'ch' if mk in EM_CH else 'cd'; tem = {}
    for k, c, mc in m['loot']: tem[k] = tem.get(k, 0) + 1
    quer = {}
    for e in re.finditer(r'\{([^{}]*)\}', bloco(s, 'loot')):
        c = campos(e.group(1))
        if 'chance' not in c: continue
        cid, nome = resolver(c)
        if cid is None: continue
        k = garantir(cid, nome, dest)
        if not k: continue
        quer.setdefault(k, []).append([k, round(int(c['chance']) / 100000, 5), int(c.get('maxCount', 1))])
    for k, es in quer.items():
        falta = len(es) - tem.get(k, 0)
        # entradas já presentes (mesma chave): só completa o que passa da contagem
        if falta > 0:
            for ent in es[len(es) - falta:]:
                m['loot'].append(ent); adds.setdefault(mk, []).append(ent); tot += 1
print('itens novos:', len(novos), '| entradas de loot novas:', tot, '| mobs alterados:', len(adds))
print('sem ícone (rode o extrator):', sorted(sem_icone)); print('sem preço:', falta_preco)
for t in novos: print(*t)
for mk, l in adds.items(): print(mk, [(x[0], x[1], x[2]) for x in l])
if not A.dry and not sem_icone and (not falta_preco or A.pular_sem_preco):
    gravar(OUT + 'cacadas100.js', 'CACADAS100', sc, ic, jc, CD); gravar(OUT + 'chefes.js', 'CHEFES', sh, ih, jh, CH)
