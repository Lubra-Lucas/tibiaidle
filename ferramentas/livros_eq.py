#!/usr/bin/env python3
"""Spellbooks de topo (Lion, Eldritch, Arcanomancer, Arboreal, Cocoa/Creamy, Ancient Arcana, Vigilance, Book of Lies) viram equipamento de verdade do slot escudo
(tibia-assets/chefes.js 'eq') e caem dos bosses. Defesa, +Magic Level (magiclevelpoints), absorções (absorbpercent*; poison = earth) e level vêm do items.xml do Canary;
só mages (vocation do items.xml) podem usar. Os bônus de Magic Level específicos de elemento/cura e o magic shield do Canary não existem no jogo e são ignorados.
Idempotente, relê o arquivo antes de gravar. Ícones: ferramentas/extrair_cliente.py --itens <cid>. Uso: livros_eq.py CANARY_DIR [--out tibia-assets] [--dry]"""
import sys, re, json, argparse
ap = argparse.ArgumentParser(); ap.add_argument('canary'); ap.add_argument('--out', default='tibia-assets'); ap.add_argument('--dry', action='store_true')
A = ap.parse_args(); CAN = A.canary.rstrip('/') + '/'; OUT = A.out.rstrip('/') + '/'
xml = open(CAN + 'data/items/items.xml', encoding='latin-1').read(); X = {}
for m in re.finditer(r'<item id="(\d+)"([^>]*?)(/>|>(.*?)\n\t</item>)', xml, re.S):
    n = re.search(r'name="([^"]*)"', m.group(2))
    if n: X[n.group(1).lower()] = (int(m.group(1)), re.findall(r'<attribute key="([^"]+)" value="([^"]*)"', m.group(4) or ''))
# id, nome Canary, conjunto, level (None = do items.xml), valor NPC estimado (gp), bosses: {boss: chance por rolagem}
LIVROS = [('spellbook_of_vigilance', 'spellbook of vigilance', 'boss', None, 30000, {'orshabaal': .0667}),
          ('spellbook_of_ancient_arcana', 'spellbook of ancient arcana', 'boss', None, 60000, {'orshabaal': .05}),
          ('book_of_lies', 'book of lies', 'boss', 150, 12000, {'orshabaal': .05}),
          ('cocoa_grimoire', 'cocoa grimoire', 'boss', None, 90000, {'ghazbaran': .02}),
          ('creamy_grimoire', 'creamy grimoire', 'boss', None, 90000, {'ghazbaran': .02}),
          ('lion_spellbook', 'lion spellbook', 'lion', None, 120000, {'ghazbaran': .008}),
          ('eldritch_folio', 'eldritch folio', 'eldritch', None, 190000, {'ferumbras': .012}),
          ('eldritch_tome', 'eldritch tome', 'eldritch', None, 190000, {'ferumbras': .012}),
          ('arcanomancer_folio', 'arcanomancer folio', 'arcanomancer', None, 250000, {'gazharagoth': .008}),
          ('arboreal_tome', 'arboreal tome', 'arboreal', None, 250000, {'gazharagoth': .008})]
ELS = {'physical': 'phys', 'fire': 'fire', 'poison': 'earth', 'earth': 'earth', 'energy': 'energy', 'ice': 'ice', 'holy': 'holy', 'death': 'death'}
VOC = {'sorcerer': 'sorcerer', 'master sorcerer': 'sorcerer', 'druid': 'druid', 'elder druid': 'druid'}
def carregar(p):
    s = open(p, encoding='utf-8').read(); i = s.index('window.CHEFES=') + 14; o, j = json.JSONDecoder().raw_decode(s[i:]); return s, i, j, o
s, i, j, CH = carregar(OUT + 'chefes.js'); ids = {e['id'] for e in CH['eq']}; novos = []
for eid, nome, conj, lv, v, bosses in LIVROS:
    if eid in ids: continue
    cid, at = X[nome]; a = {k: val for k, val in at}; ab = {}
    for k, val in at:
        mm = re.match(r'absorbpercent(\w+)$', k)
        if mm and mm.group(1) in ELS: ab[ELS[mm.group(1)]] = ab.get(ELS[mm.group(1)], 0) + int(val)
    voc = sorted({VOC[x.split(';')[0].strip().lower()] for x in a['vocation'].split(',')}) if 'vocation' in a else ['sorcerer', 'druid']
    st = {'def': int(a['defense']), 'libro': 1}; ml = int(a.get('magiclevelpoints', 0))
    if ml: st['sk'] = {'magic': ml}
    if ab: st['abs'] = ab
    e = {'id': eid, 'n': ' '.join(p.capitalize() if p != 'of' else p for p in nome.split()), 'slot': 'shield', 'voc': voc, 'wt': None, 'st': st, 'lv': lv or int(a['level']),
         'w': round(int(a['weight']) / 100, 1), 'v': v, 'icone': f'tibia-assets/sprites15/itens/{cid}.png', 'conj': conj,
         'real': {'cid': cid, 'armor': None, 'defense': a['defense'], 'attack': None}}
    CH['eq'].append(e); novos.append((eid, e['lv'], voc, st))
    for b, ch in bosses.items():
        L = CH['mobs'][b]['loot']
        if not any(x[0] == eid for x in L): L.append([eid, ch, 1])
print(len(novos), 'novos'); [print(*n) for n in novos]
if not A.dry and novos:
    s2, i2, j2, o2 = carregar(OUT + 'chefes.js')   # relê logo antes de gravar
    ids2 = {e['id'] for e in o2['eq']}; o2['eq'] += [e for e in CH['eq'] if e['id'] not in ids2]
    for b in {b for *_, bs in LIVROS for b in bs}:
        for x in CH['mobs'][b]['loot']:
            if not any(y[0] == x[0] for y in o2['mobs'][b]['loot']): o2['mobs'][b]['loot'].append(x)
    open(OUT + 'chefes.js', 'w', encoding='utf-8').write(s2[:i2] + json.dumps(o2, ensure_ascii=False, separators=(',', ':')) + s2[i2 + j2:])
