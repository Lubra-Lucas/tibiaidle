#!/usr/bin/env python3
"""Machados, clavas e espadas de 2 mãos de boss viram equipamento de verdade (tibia-assets/chefes.js 'eq'), agora que o Knight tem Sword/Axe/Club.
1) converte os itens de loot (só venda) do chefes.js listados em CONV para linhas de 'eq' (mesmo id/ícone/preço NPC/peso; atk/level na escala do jogo, ver abaixo);
   a chave de loot nos monstros continua a mesma (o índice resolve para o equipamento, nada muda nas tabelas de drop);
2) acrescenta os irmãos de machado/clava dos conjuntos já existentes (Cobra, Lion, Falcon, Soul, Sanguine): mesma chance de drop do equivalente espada/besta
   em cada boss, mesmo preço e level do conjunto. Ícones reais: ferramentas/extrair_cliente.py --itens <cid> --saida tibia-assets/sprites15/itens.
Escala de ataque: o real do items.xml até 46 (igual às espadas da loja); acima disso 46+(real-46)*2.2, como o warlord/mystic já são inflados; level compactado como as
umbral blades existentes (crude 70, normal 80, master 90). Idempotente, relê o arquivo antes de gravar. Uso: armas_eq.py CANARY_DIR [--out tibia-assets] [--dry]"""
import sys, re, json, argparse
ap = argparse.ArgumentParser(); ap.add_argument('canary'); ap.add_argument('--out', default='tibia-assets'); ap.add_argument('--dry', action='store_true')
A = ap.parse_args(); CAN = A.canary.rstrip('/') + '/'; OUT = A.out.rstrip('/') + '/'
def carregar(p, var):
    s = open(p, encoding='utf-8').read(); i = s.index('window.' + var + '=') + len('window.' + var + '='); o, j = json.JSONDecoder().raw_decode(s[i:]); return s, i, j, o
xml = open(CAN + 'data/items/items.xml', encoding='latin-1').read(); X = {}
for m in re.finditer(r'<item id="(\d+)"([^>]*?)(/>|>(.*?)\n\t</item>)', xml, re.S):
    n = re.search(r'name="([^"]*)"', m.group(2))
    if n: X[n.group(1).lower()] = (int(m.group(1)), dict(re.findall(r'<attribute key="([^"]+)" value="([^"]*)"', m.group(4) or '')))
def esc(real): return round(real if real <= 46 else 46 + (real - 46) * 2.2)
sh, ih, jh, CH = carregar(OUT + 'chefes.js', 'CHEFES'); ids = {e['id'] for e in CH['eq']}
# id de loot -> (atk real do Canary, level no jogo; None = mesmo número do XML), tipo de arma
CONV = {'twin_axe': 50, 'havoc_blade': 70, 'ravenwing': 65, 'ornamented_axe': 50, 'demonwing_axe': 90, 'hellforged_axe': 85, 'skullcrusher': 85, 'thunder_hammer': 85,
        'onyx_flail': 65, 'amber_staff': 40, 'arcane_staff': 75, 'calamity': 85}
UMBRAL = {'crude umbral': (54, 70), 'umbral': (57, 80), 'umbral master': (60, 90)}
for pre, (a, lv) in UMBRAL.items():
    for t, d2 in (('slayer', 1), ('axe', 0), ('chopper', 1), ('hammer', 1), ('mace', 0)):
        CONV[(pre + ' ' + t).replace(' ', '_')] = lv; CONV['@' + (pre + ' ' + t).replace(' ', '_')] = a + d2
TIPO = {'sword': 'sword', 'axe': 'axe', 'club': 'club'}
novos = []
def linha(i, nome, cid, wt, atk, lv, w, v, conj):
    xd = X[nome.lower()][1]
    return {'id': i, 'n': ' '.join(p.capitalize() for p in nome.split()), 'slot': 'weapon', 'voc': ['knight'], 'wt': wt, 'st': {'atk': atk}, 'lv': lv, 'w': w, 'v': v,
            'icone': f'tibia-assets/sprites15/itens/{cid}.png', 'conj': conj, 'real': {'cid': cid, 'armor': None, 'defense': xd.get('defense'), 'attack': xd.get('attack')}}
for k in [k for k in CONV if not k.startswith('@')]:
    it = CH['itens'].get(k)
    if not it or k in ids: continue
    cid, xd = X[it['n'].lower()]; wt = xd.get('weaponType')
    atk = CONV.get('@' + k) or esc(int(xd.get('attack', 0)))
    CH['eq'].append(linha(k, it['n'], cid, wt, atk, CONV[k], it['w'], it['v'], 'boss')); del CH['itens'][k]; novos.append(('conv', k, wt, atk, CONV[k]))
# irmãos dos conjuntos: (conj, nome Canary, tipo, atk, level, equivalente existente (de onde vêm preço e drop))
FAM = [('cobra', 'cobra axe', 'axe', 72, 220, 'cobra_crossbow'), ('cobra', 'cobra club', 'club', 72, 220, 'cobra_crossbow'),
       ('lion', 'lion axe', 'axe', 76, 270, 'lion_longsword'), ('lion', 'lion hammer', 'club', 76, 270, 'lion_longsword'),
       ('falcon', 'falcon battleaxe', 'axe', 78, 300, 'falcon_longsword'), ('falcon', 'falcon mace', 'club', 77, 300, 'falcon_longsword'),
       ('soul', 'soulshredder', 'sword', 87, 400, 'soulcutter'), ('soul', 'soulbiter', 'axe', 84, 400, 'soulcutter'), ('soul', 'souleater', 'axe', 87, 400, 'soulcutter'),
       ('soul', 'soulcrusher', 'club', 84, 400, 'soulcutter'), ('soul', 'soulmaimer', 'club', 87, 400, 'soulcutter'),
       ('sanguine', 'sanguine hatchet', 'axe', 90, 600, 'sanguine_blade'), ('sanguine', 'sanguine cudgel', 'club', 90, 600, 'sanguine_blade'),
       ('sanguine', 'sanguine battleaxe', 'axe', 93, 600, 'sanguine_razor'), ('sanguine', 'sanguine bludgeon', 'club', 93, 600, 'sanguine_razor')]
byid = {e['id']: e for e in CH['eq']}
for conj, nome, wt, atk, lv, ref in FAM:
    i = re.sub(r'[^a-z0-9]+', '_', nome); cid, xd = X[nome]
    if i in byid: continue
    r = byid[ref]; w = round(int(xd['weight']) / 100, 1)
    e = linha(i, nome, cid, wt, atk, lv, w, r['v'], conj); CH['eq'].append(e); byid[i] = e; novos.append(('fam', i, wt, atk, lv))
    for mk, m in CH['mobs'].items():
        for l in list(m['loot']):
            if l[0] == ref and not any(x[0] == i for x in m['loot']): m['loot'].append([i, l[1], l[2]])
print(len(novos), 'novos'); [print(*n) for n in novos]
if not A.dry and novos:
    s2 = open(OUT + 'chefes.js', encoding='utf-8').read(); i2 = s2.index('window.CHEFES=') + 14; o2, j2 = json.JSONDecoder().raw_decode(s2[i2:])   # relê logo antes de gravar
    ids2 = {e['id'] for e in o2['eq']}; o2['eq'] += [e for e in CH['eq'] if e['id'] not in ids2]
    for k in list(o2['itens']):
        if k not in CH['itens']: del o2['itens'][k]
    for k, m in CH['mobs'].items():
        if k in o2['mobs']: o2['mobs'][k]['loot'] = m['loot']
    open(OUT + 'chefes.js', 'w', encoding='utf-8').write(s2[:i2] + json.dumps(o2, ensure_ascii=False, separators=(',', ':')) + s2[i2 + j2:])
