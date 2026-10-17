#!/usr/bin/env python3
"""Gera tibia-assets/chefes.js (bosses em grupo, itens de topo e minions) e os sprites novos em tibia-assets/sprites15.

Fontes (nada aqui é inventado à mão além da tabela CONFIG abaixo):
  - Canary (opentibiabr/canary, clone esparso com data-otservbr-global/monster, data/items/items.xml, data-otservbr-global/npc,
    src/utils/utils_definitions.hpp): vida, exp, ataques, defesas, resistências, loot e estatísticas reais dos itens;
  - cliente Tibia 15.10 (Tibia.dat + Tibia.spr, fora do repo; --cliente DIR): folhas de criatura reais (outfit lookType/cores/addons do
    Canary, 4 direções, todos os quadros parado/andar, via ferramentas/extrair_cliente.py) e os sprites dos cadáveres (monster.corpse);
  - ícones dos itens de topo: sprites reais do cliente, extraídos com ferramentas/extrair_cliente.py para
    tibia-assets/sprites15/itens/<cid>.png (o gerador só aponta o caminho; rode o extrator antes).
Uso: gerar_chefes.py CANARY_DIR --cliente DIR_COM_Tibia.dat_e_Tibia.spr [--out tibia-assets]   (precisa de Pillow)"""
import sys, os, re, json, argparse, colorsys
from PIL import Image
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extrair_cliente as XC

ap = argparse.ArgumentParser()
ap.add_argument('canary'); ap.add_argument('--cliente', required=True); ap.add_argument('--out', default='tibia-assets')
A = ap.parse_args()
CAN, CLI, OUT = A.canary.rstrip('/') + '/', A.cliente.rstrip('/') + '/', A.out.rstrip('/') + '/'
ITENS_DIR = OUT + 'sprites15/itens/'; CRIA_DIR = OUT + 'sprites15/criaturas/'

# ---------------------------------------------------------------- dados do jogo atual
def carregar_js(p, var):
    s = open(p, encoding='utf-8').read(); i = s.index('window.' + var + '=') + len('window.' + var + '=')
    return json.JSONDecoder().raw_decode(s[i:])[0]
CD = carregar_js(OUT + 'cacadas100.js', 'CACADAS100')
CB = carregar_js(OUT + 'combate15.js', 'COMB15')
SPR_EXISTE = set(carregar_js(OUT + 'sprites15.js', 'SPR15')['criaturas'])   # criaturas que o jogo já tem folha (não sobrescrever)
ours_by_name = {v['n'].lower(): k for k, v in CD['itens'].items()}
ours_by_cid = {v.get('cid'): k for k, v in CD['itens'].items()}
icones_eq = {os.path.basename(v)[:-4]: k for k, v in CD['icones'].items()}   # cid -> id do equipamento do jogo

# ---------------------------------------------------------------- Canary
def enum(prefix):
    o = {}; n = -1
    for l in open(CAN + 'src/utils/utils_definitions.hpp', encoding='utf-8', errors='ignore'):
        m = re.match(r'\s*(' + prefix + r'\w+)\s*(?:=\s*(\d+))?\s*,', l)
        if m:
            n = int(m.group(2)) if m.group(2) else n + 1; o[m.group(1)] = n
    return o
ME, ANI = enum('CONST_ME_'), enum('CONST_ANI_')
COMBAT = {'PHYSICALDAMAGE': 'phys', 'ENERGYDAMAGE': 'energy', 'EARTHDAMAGE': 'earth', 'FIREDAMAGE': 'fire', 'LIFEDRAIN': 'lifedrain', 'MANADRAIN': 'manadrain',
          'DROWNDAMAGE': 'drown', 'ICEDAMAGE': 'ice', 'HOLYDAMAGE': 'holy', 'DEATHDAMAGE': 'death', 'HEALING': 'healing'}
COND = {'CONDITION_POISON': 'earth', 'CONDITION_FIRE': 'fire', 'CONDITION_ENERGY': 'energy', 'CONDITION_BLEEDING': 'phys', 'CONDITION_CURSED': 'death'}
ELEM = {'PHYSICALDAMAGE': 'phys', 'ENERGYDAMAGE': 'energy', 'EARTHDAMAGE': 'earth', 'FIREDAMAGE': 'fire', 'LIFEDRAIN': 'lifedrain', 'MANADRAIN': 'manadrain',
        'DROWNDAMAGE': 'drown', 'ICEDAMAGE': 'ice', 'HOLYDAMAGE': 'holy', 'DEATHDAMAGE': 'death'}
EF_OK = {int(k) for k in CB['efeitos']}; ANI_OK = {int(k) for k in CB['tiros']}

def items_xml():
    s = open(CAN + 'data/items/items.xml', encoding='latin-1').read(); by_id = {}; by_name = {}
    for m in re.finditer(r'<item id="(\d+)"([^>]*?)(/>|>(.*?)</item>)', s, re.S):
        n = re.search(r'name="([^"]*)"', m.group(2))
        if not n: continue
        d = {'id': int(m.group(1)), 'name': n.group(1), 'attr': dict(re.findall(r'<attribute key="([^"]+)" value="([^"]*)"', m.group(4) or ''))}
        by_id[d['id']] = d; by_name.setdefault(d['name'].lower(), d)
    return by_id, by_name
XML_ID, XML_NAME = items_xml()

def npc_sell():
    import glob; o = {}
    for f in glob.glob(CAN + 'data-otservbr-global/npc/*.lua'):
        for m in re.finditer(r'itemName = "([^"]+)", clientId = (\d+)(?:, buy = \d+)?, sell = (\d+)', open(f, errors='ignore').read()):
            o[int(m.group(2))] = max(o.get(int(m.group(2)), 0), int(m.group(3)))
    return o
SELL = npc_sell()

def monstros():
    import glob; o = {}
    for f in glob.glob(CAN + 'data-otservbr-global/monster/**/*.lua', recursive=True):
        s = open(f, encoding='utf-8', errors='ignore').read(); nm = re.search(r'Game\.createMonsterType\("([^"]+)"\)', s)
        if nm: o[nm.group(1).lower()] = s
    return o
MON = monstros()

def blocos(s, nome):
    m = re.search(r'monster\.' + nome + r' = \{(.*?)\n\}', s, re.S); return m.group(1) if m else ''
def campos(t):
    d = {}
    for k, v in re.findall(r'(\w+)\s*=\s*("[^"]*"|[-\w\.]+)', t): d[k] = v.strip('"')
    return d
def num(v, dflt=0):
    try: return int(v)
    except Exception: return dflt

def converter_ataque(c, defesa=False):
    # o motor do jogo rola todos os ataques a cada 2 s e ignora 'interval': normaliza a chance para a janela de 2 s (interval 1000 e chance 34 = 68% por rolagem)
    iv = num(c.get('interval'), 2000) or 2000; ch = num(c.get('chance'), 100)
    n = c.get('name', ''); o = {'name': n, 'interval': iv, 'chance': ch if ch >= 100 else min(100, round(ch * 2000 / iv))}
    def efs(o):
        e = ME.get(c.get('effect', ''), 0); a = ANI.get(c.get('shootEffect', ''), 0)
        if e in EF_OK: o['effect'] = e
        if a in ANI_OK: o['shootEffect'] = a
    if n == 'melee':
        if 'maxDamage' in c: o['minDamage'] = 0; o['maxDamage'] = num(c['maxDamage'])
        else: o['minDamage'] = 0; o['maxDamage'] = -round(num(c.get('skill')) * num(c.get('attack')) / 28)   # fórmula de melee do Canary (aprox.)
        return o
    if n == 'condition' and c.get('type') in COND and not defesa:
        n = 'combat'; c = dict(c); c['type'] = 'COMBAT_' + {v: k for k, v in ELEM.items()}[COND[c['type']]]
        o['name'] = 'combat'
    if n == 'combat':
        t = (c.get('type') or '').replace('COMBAT_', '')
        if t not in COMBAT: return None
        o['type'] = COMBAT[t]; o['minDamage'] = num(c.get('minDamage')); o['maxDamage'] = num(c.get('maxDamage'))
        for k in ('range', 'radius', 'length', 'spread'):
            if k in c: o[k] = num(c[k])
        efs(o); o['target'] = c.get('target') == 'true'
        if defesa and o['type'] != 'healing': return None
        return o
    if n in ('firefield', 'energyfield', 'poisonfield') and not defesa:
        for k in ('range', 'radius'):
            if k in c: o[k] = num(c[k])
        efs(o); o['target'] = c.get('target') == 'true'; return o
    if n == 'speed':
        o['speedChange'] = num(c.get('speedChange')); o['duration'] = num(c.get('duration'), 5000)
        for k in ('radius',):
            if k in c: o[k] = num(c[k])
        efs(o); o['target'] = c.get('target') == 'true'; return o
    ESP = {"energy strike": ('energy', 1), "gaz'haragoth iceball": ('ice', 7)}   # magias nomeadas do Canary que o motor do jogo não conhece
    if n in ESP and not defesa:
        mn, mx = num(c.get('minDamage')), num(c.get('maxDamage'))
        return {'name': 'combat', 'interval': o['interval'], 'chance': o['chance'], 'type': ESP[n][0], 'minDamage': mn, 'maxDamage': mx, 'range': ESP[n][1], 'target': True,
                'effect': {'ice': ME['CONST_ME_ICEAREA'], 'energy': ME['CONST_ME_ENERGYHIT']}[ESP[n][0]], **({'shootEffect': ANI['CONST_ANI_ICE']} if ESP[n][0] == 'ice' else {})}
    return None

def entradas(txt):
    return [campos(m.group(1)) for m in re.finditer(r'\{([^{}]*)\}', txt)]

def item_do_loot(e):
    nm = e.get('name'); i = num(e.get('id'), 0)
    d = XML_NAME.get(nm.lower()) if nm else XML_ID.get(i)
    return d

SPRITE_FALTA = set()
GEMAS = [('giant ruby', 3030), ('giant sapphire', 3029), ('giant emerald', 3032), ('giant amethyst', 3033), ('giant topaz', 9057)]   # sem sprite 15.01 público: gema pequena ampliada
def gemas_gigantes():
    for nome, base in GEMAS:
        d = XML_NAME[nome]; k = nome.replace(' ', '_'); im = Image.open(f'{ITENS_DIR}{base}.png').convert('RGBA'); bb = im.getbbox(); g = im.crop(bb)
        f = 28 / max(g.size); g = g.resize((max(1, round(g.width * f)), max(1, round(g.height * f))), Image.NEAREST)
        c = Image.new('RGBA', (32, 32), (0, 0, 0, 0)); c.paste(g, ((32 - g.width) // 2, 31 - g.height), g); # (o PNG real vem de ferramentas/extrair_cliente.py; nao e mais derivado)
        NOVOS_ITENS[k] = {'n': d['name'].title(), 'w': num(d['attr'].get('weight')) / 100, 'v': SELL[d['id']], 'type': 'loot', 'cid': d['id'], 'icone': f"tibia-assets/sprites15/itens/{d['id']}.png"}
NOVOS_ITENS = {}   # itens de loot com sprite local que o cacadas100.js não tem
def chave_item(d):
    if d['name'].lower().replace(' ', '_') in NOVOS_ITENS: return d['name'].lower().replace(' ', '_')
    """devolve a chave que o jogo resolve para o item (chave do cacadas100, nome em minúsculas de equipamento do jogo ou item novo) ou None"""
    n = d['name'].lower(); cid = d['id']
    if n in ours_by_name: return ours_by_name[n]
    if cid in ours_by_cid: return ours_by_cid[cid]
    if str(cid) in icones_eq: return n          # equipamento do jogo (resolvido por nome no HTML)
    if not os.path.exists(f'{ITENS_DIR}{cid}.png'): SPRITE_FALTA.add(d['name']); return None
    w = num(d['attr'].get('weight')) / 100; v = SELL.get(cid, 0)
    if v <= 0: SPRITE_FALTA.add(d['name'] + ' (sem preço de NPC)'); return None
    k = re.sub(r'[^a-z0-9]+', '_', n).strip('_')
    NOVOS_ITENS[k] = {'n': d['name'], 'w': w, 'v': v, 'type': 'loot', 'cid': cid, 'icone': f'tibia-assets/sprites15/itens/{cid}.png'}
    return k

def montar_mob(nome_canary, mid, classe, extra=None):
    s = MON[nome_canary.lower()]; g = lambda r, d=0: num((re.search(r, s) or [0, d])[1], d)
    hp = g(r'monster\.health = (\d+)'); exp = g(r'monster\.experience = (\d+)'); vel = g(r'monster\.speed = (\d+)', 100)
    dfs = blocos(s, 'defenses'); armor = num((re.search(r'armor = (\d+)', dfs) or [0, 0])[1]); defn = num((re.search(r'\bdefense = (\d+)', dfs) or [0, 0])[1])
    atq = [x for x in (converter_ataque(c) for c in entradas(blocos(s, 'attacks'))) if x]
    dfa = [x for x in (converter_ataque(c, True) for c in entradas(dfs)) if x]
    el = {k: 0 for k in ELEM.values()}
    for c in entradas(blocos(s, 'elements')):
        t = (c.get('type') or '').replace('COMBAT_', '')
        if t in ELEM: el[ELEM[t]] = num(c.get('percent'))
    inv = []; maxinv = num((re.search(r'maxSummons = (\d+)', blocos(s, 'summon')) or [0, 0])[1])
    for c in entradas(blocos(s, 'summon')):
        if 'name' in c: inv.append({'id': re.sub(r"[^a-z0-9]+", '_', c['name'].lower()).strip('_'), 'chance': num(c.get('chance'), 10)})
    loot = []
    for e in entradas(blocos(s, 'loot')):
        if 'chance' not in e: continue
        d = item_do_loot(e)
        if not d: continue
        k = chave_item(d)
        if k: loot.append([k, round(num(e['chance']) / 100000, 5), num(e.get('maxCount'), 1)])
    hit = max([abs(a.get('maxDamage', 0)) for a in atq if a['name'] == 'melee'] or [0])
    m = {'n': nome_canary, 'hp': hp, 'exp': exp, 'vel': vel, 'arm': armor, 'def': defn, 'el': el, 'hit': hit, 'atq15': atq, 'def15': dfa, 'invoca': inv, 'maxInv': maxinv,
         'best': [1, 3, 5], 'charm': 0, 'est': 5, 'classe': classe, 'invocado': False, 'loot': loot}
    if extra: m.update(extra)
    return m

# ---------------------------------------------------------------- sprites de criatura do cliente
_CLI = {}
def cliente():
    if not _CLI:
        spr = XC.Spr(CLI + 'Tibia.spr'); dat, _ = XC.detectar(CLI + 'Tibia.dat', spr.n); _CLI.update(spr=spr, dat=dat)
    return _CLI['spr'], _CLI['dat']
CAD_DIR = OUT + 'sprites15/cadaveres/'; CADAVERES = {}   # cadáveres (id do item -> {w,h,src}) que o sprites15.js pode ainda não ter
def folha_criatura(nome, mid):
    """folha real do cliente para o monstro do Canary `nome` (outfit + cores + addons); o cadáver vem de monster.corpse (0 = não deixa cadáver)"""
    spr, dat = cliente(); look, corpo = XC.ler_monstro_lua_txt(MON[nome.lower()])
    if look.get('lookTypeEx'): im, meta = XC.folha_criatura(spr, dat, look['lookTypeEx'], ex=True)
    else: im, meta = XC.folha_criatura(spr, dat, look['lookType'], tuple(look.get(k, 0) for k in ('lookHead', 'lookBody', 'lookLegs', 'lookFeet')), look.get('lookAddons', 0))
    os.makedirs(CRIA_DIR, exist_ok=True); im.save(f'{CRIA_DIR}{mid}.png'); meta['src'] = f'tibia-assets/sprites15/criaturas/{mid}.png'
    if corpo:
        meta['cad'] = corpo; arq = f'{CAD_DIR}{corpo}.png'
        if not os.path.exists(arq):
            os.makedirs(CAD_DIR, exist_ok=True); XC.render(spr, dat.cats[XC.CAT_ITEM][corpo]).save(arq)
        c = Image.open(arq); CADAVERES[str(corpo)] = {'w': c.width, 'h': c.height, 'src': f'tibia-assets/sprites15/cadaveres/{corpo}.png'}
    return meta

# ---------------------------------------------------------------- CONFIG: bosses e minions
MINIONS = {   # id do jogo: (nome Canary, GIF, classe); os que já existem no jogo (CD.mobs / COMB15.monstros) não entram aqui
    'hellhound': ('Hellhound', 'creatures/Hellhound.gif', 'Magical'),
    'demon_skeleton': ('Demon Skeleton', 'creatures/Demon_Skeleton.gif', 'Undead'),
    'deathslicer': ('Deathslicer', 'creatures/Deathslicer.gif', 'Undead'),
    'charger': ('Charger', 'creatures/Charger.gif', 'Extra Dimensional'),
    'spark_of_destruction': ('Spark of Destruction', 'creatures/Spark_of_Destruction.gif', 'Extra Dimensional'),
    'minion_of_gazharagoth': ("Minion of Gaz'haragoth", "creatures/Minion_of_Gaz'haragoth.gif", 'Demon'),
    'nightmare_of_gazharagoth': ("Nightmare of Gaz'haragoth", "creatures/Nightmare_of_Gaz'haragoth.gif", 'Demon'),
}
BOSSES = [   # id, nome Canary, GIF, classe, nível recomendado, mapa (caçada cujo mapa é reaproveitado), minions {id: peso}, descrição
    dict(id='orshabaal', nome='Orshabaal', gif='bosses/Orshabaal.gif', classe='Demon', lv=150, mapa='hellgore', hpMul=4, danoMul=1, minions={'demon': 3, 'hellhound': 2, 'fire_elemental': 1},
         desc='Um dos Ruthless Seven. Invoca demons, drena mana e queima tudo ao redor.'),
    dict(id='ghazbaran', nome='Ghazbaran', gif='bosses/Ghazbaran.gif', classe='Demon', lv=250, mapa='infernal_throne', hpMul=.3, danoMul=1.5, minions={'deathslicer': 3, 'demon_skeleton': 2},
         desc='O Ruthless Seven da perdição: leva uma party inteira à beira da morte.'),
    dict(id='ferumbras', nome='Ferumbras', gif='bosses/Ferumbras.gif', classe='Demon', lv=350, mapa='lich_crypt', hpMul=5, danoMul=2, minions={'demon': 3, 'demon_skeleton': 2},
         desc='O arquimago renegado. Fogo, energia e veneno em área; cai com os melhores itens do jogo.'),
    dict(id='gazharagoth', nome="Gaz'Haragoth", gif="bosses/Gaz'haragoth.gif", classe='Demon', lv=500, mapa='hellflayer_pit', hpMul=1.2, danoMul=1, minions={'minion_of_gazharagoth': 3, 'nightmare_of_gazharagoth': 1}, invoca=[{'id': 'minion_of_gazharagoth', 'chance': 15}], maxinv=6,
         desc='O Lord of Demons. Dano devastador de fogo e gelo e uma multidão de minions.'),
    dict(id='scourge_of_oblivion', nome='The Scourge of Oblivion', gif='bosses/The_Scourge_of_Oblivion.gif', classe='Extra Dimensional', lv=800, mapa='darklight_core', hpMul=2, danoMul=1.2,
         minions={'charger': 3, 'spark_of_destruction': 3}, desc='O flagelo do esquecimento: 800 mil de vida e dano físico em toda a sala.'),
]

# Itens de topo. (id, nome Canary, slot, voc, tipo de arma, estatística no modelo do jogo, level, conjunto, base do ícone (cid))
# Estatísticas reais do items.xml (armor, defense, attack, bônus de skill e elemental) viram o modelo do jogo (arm/def/atk, min/max/mana de wand/rod):
# arm = armor real + 1 (bônus de skill/absorção que o jogo não tem), def = defense real + 2, atk = escala própria por tier acima do warlord_sword (70);
# wands/rods: dano acima do Everblazing/Glacial (160-200). Veja EQUIP abaixo.
T = lambda *a: a
K, P, S, D = ['knight'], ['paladin'], ['sorcerer'], ['druid']
EQUIP = [
  # conjunto, nome, slot, vocações, wt, stats, level, cid base do ícone
  ('gnome', 'gnome helmet', 'helmet', S + D, None, {'arm': 9}, 200, 3392),
  ('gnome', 'gnome armor', 'armor', P, None, {'arm': 18}, 200, 3360),
  ('gnome', 'gnome legs', 'legs', S + D, None, {'arm': 10}, 200, 3364),
  ('gnome', 'gnome shield', 'shield', K + P, None, {'def': 40}, 200, 3414),
  ('gnome', 'gnome sword', 'weapon', K, 'sword', {'atk': 74}, 250, 3278),
  ('cobra', 'cobra hood', 'helmet', K, None, {'arm': 10}, 270, 3391),
  ('cobra', 'cobra boots', 'boots', K, None, {'arm': 4}, 220, 3556),
  ('cobra', 'cobra crossbow', 'weapon', P, 'distance', {'atk': 72}, 220, 3349),
  ('cobra', 'cobra wand', 'weapon', S, 'wand', {'min': 175, 'max': 215, 'mana': 22}, 270, 16115),
  ('cobra', 'cobra rod', 'weapon', D, 'rod', {'min': 175, 'max': 215, 'mana': 22}, 220, 16118),
  ('lion', 'lion spangenhelm', 'helmet', P, None, {'arm': 9}, 230, 3392),
  ('lion', 'lion plate', 'armor', K, None, {'arm': 19}, 270, 3366),
  ('lion', 'lion shield', 'shield', K, None, {'def': 41}, 250, 3420),
  ('lion', 'lion longsword', 'weapon', K, 'sword', {'atk': 76}, 270, 3281),
  ('lion', 'lion longbow', 'weapon', P, 'distance', {'atk': 75}, 270, 8026),
  ('eldritch', 'eldritch cowl', 'helmet', S, None, {'arm': 8}, 250, 3351),
  ('eldritch', 'eldritch hood', 'helmet', D, None, {'arm': 8}, 250, 3351),
  ('eldritch', 'eldritch cuirass', 'armor', K, None, {'arm': 18}, 250, 3366),
  ('eldritch', 'eldritch breeches', 'legs', P, None, {'arm': 10}, 250, 3371),
  ('eldritch', 'eldritch shield', 'shield', K, None, {'def': 41}, 270, 3414),
  ('falcon', 'falcon coif', 'helmet', K + P, None, {'arm': 11}, 300, 3392),
  ('falcon', 'falcon plate', 'armor', K, None, {'arm': 20}, 300, 3366),
  ('falcon', 'falcon greaves', 'legs', K + P, None, {'arm': 11}, 300, 3364),
  ('falcon', 'falcon shield', 'shield', K + P, None, {'def': 41}, 300, 3422),
  ('falcon', 'falcon escutcheon', 'shield', K + P, None, {'def': 42}, 300, 3414),
  ('falcon', 'falcon longsword', 'weapon', K, 'sword', {'atk': 78}, 300, 3296),
  ('falcon', 'falcon bow', 'weapon', P, 'distance', {'atk': 77}, 300, 36664),
  ('falcon', 'falcon wand', 'weapon', S, 'wand', {'min': 205, 'max': 250, 'mana': 26}, 300, 16115),
  ('falcon', 'falcon rod', 'weapon', D, 'rod', {'min': 205, 'max': 250, 'mana': 26}, 300, 16118),
  ('soul', 'soulshell', 'armor', P, None, {'arm': 20}, 400, 8057),
  ('soul', 'soulmantle', 'armor', S, None, {'arm': 19}, 400, 3360),
  ('soul', 'soulshanks', 'legs', S, None, {'arm': 11}, 400, 3371),
  ('soul', 'soulstrider', 'legs', D, None, {'arm': 11}, 400, 3371),
  ('soul', 'pair of soulwalkers', 'boots', K, None, {'arm': 5}, 400, 3554),
  ('soul', 'soulcutter', 'weapon', K, 'sword', {'atk': 84}, 400, 7384),
  ('soul', 'soulbleeder', 'weapon', P, 'distance', {'atk': 83}, 400, 36664),
  ('soul', 'soulpiercer', 'weapon', P, 'distance', {'atk': 85}, 400, 5803),
  ('soul', 'soulhexer', 'weapon', D, 'rod', {'min': 235, 'max': 285, 'mana': 30}, 400, 8084),
  ('spiritthorn', 'spiritthorn helmet', 'helmet', K, None, {'arm': 13}, 400, 3356),
  ('spiritthorn', 'spiritthorn armor', 'armor', K, None, {'arm': 22}, 400, 8057),
  ('alicorn', 'alicorn headguard', 'helmet', P, None, {'arm': 12}, 400, 3391),
  ('arcanomancer', 'arcanomancer regalia', 'helmet', S, None, {'arm': 10}, 400, 3392),
  ('arboreal', 'arboreal crown', 'helmet', D, None, {'arm': 10}, 400, 3392),
  ('sanguine', 'sanguine legs', 'legs', K, None, {'arm': 13}, 500, 3364),
  ('sanguine', 'sanguine greaves', 'legs', P, None, {'arm': 12}, 500, 3363),
  ('sanguine', 'sanguine boots', 'boots', S, None, {'arm': 4}, 500, 3079),
  ('sanguine', 'sanguine galoshes', 'boots', D, None, {'arm': 4}, 500, 3079),
  ('sanguine', 'sanguine blade', 'weapon', K, 'sword', {'atk': 90}, 600, 7384),
  ('sanguine', 'sanguine razor', 'weapon', K, 'sword', {'atk': 93}, 600, 3281),
  ('sanguine', 'sanguine bow', 'weapon', P, 'distance', {'atk': 90}, 600, 8026),
  ('sanguine', 'sanguine crossbow', 'weapon', P, 'distance', {'atk': 92}, 600, 3349),
  ('sanguine', 'sanguine coil', 'weapon', S, 'wand', {'min': 275, 'max': 335, 'mana': 34}, 600, 16115),
  ('sanguine', 'sanguine rod', 'weapon', D, 'rod', {'min': 275, 'max': 335, 'mana': 34}, 600, 16118),
]
# cor do conjunto: (matiz 0-360, saturação mínima, multiplicador de saturação, multiplicador de brilho)
PALETA = {'gnome': (285, .45, 1.0, .95), 'cobra': (135, .55, 1.1, .95), 'lion': (38, .65, 1.1, 1.0), 'eldritch': (250, .5, 1.0, .9), 'falcon': (205, .5, 1.0, 1.05),
          'soul': (165, .5, 1.0, .95), 'spiritthorn': (95, .5, 1.0, .85), 'alicorn': (190, .3, .9, 1.1), 'arcanomancer': (305, .5, 1.0, .95), 'arboreal': (80, .55, 1.0, .85),
          'sanguine': (356, .7, 1.2, .85)}
# peso mínimo de dificuldade -> valor NPC (gp) por conjunto: peça 'padrão'; armas valem mais
VALOR = {'gnome': 60000, 'cobra': 80000, 'lion': 110000, 'eldritch': 150000, 'falcon': 280000, 'soul': 450000, 'spiritthorn': 380000, 'alicorn': 350000,
         'arcanomancer': 350000, 'arboreal': 350000, 'sanguine': 900000}
# onde cada conjunto cai: boss -> {item: chance por rolagem}
DROPS = {
  'ghazbaran': [('gnome', .012), ('cobra', .010), ('lion', .008)],
  'ferumbras': [('eldritch', .012), ('falcon', .010)],
  'gazharagoth': [('soul', .010), ('spiritthorn', .008), ('alicorn', .008), ('arcanomancer', .008), ('arboreal', .008)],
  'scourge_of_oblivion': [('sanguine', .012), ('soul', .008)],
}

def tingir(base, conj, dst):
    h, smin, sm, vm = PALETA[conj]; im = Image.open(f'{ITENS_DIR}{base}.png').convert('RGBA'); px = im.load()
    for y in range(im.height):
        for x in range(im.width):
            r, g, b, a = px[x, y]
            if a < 8: continue
            hh, ss, vv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if vv > .12:   # contorno escuro fica como está; o resto troca de matiz e ganha a saturação do conjunto
                hh = h / 360; ss = min(1, max(ss * sm, smin * (.35 + .65 * min(1, vv * 1.3)))); vv = min(1, vv * vm)
            r, g, b = colorsys.hsv_to_rgb(hh, ss, vv); px[x, y] = (int(r * 255), int(g * 255), int(b * 255), a)
    im.save(dst)

def build():
    gemas_gigantes(); equip = []; ids = {}
    for conj, nome, slot, voc, wt, st, lv, base in EQUIP:
        d = XML_NAME[nome]; eid = re.sub(r'[^a-z0-9]+', '_', nome).strip('_')
        w = round(num(d['attr'].get('weight')) / 100, 1); mult = 1.6 if slot == 'weapon' else 1.0
        v = int(VALOR[conj] * mult * (1.3 if slot in ('armor', 'shield') else 1.0) / 1000 + .5) * 1000
        ic = f"sprites15/itens/{d['id']}.png"   # sprite real extraido do cliente (extrair_cliente.py --itens <cid>)
        row = {'id': eid, 'n': ' '.join(x.capitalize() if x not in ('of', 'the') else x for x in nome.replace("'", "'").split()), 'slot': slot, 'voc': voc, 'wt': wt, 'st': st, 'lv': lv,
               'w': w, 'v': v, 'icone': 'tibia-assets/' + ic, 'conj': conj, 'real': {'cid': d['id'], 'armor': d['attr'].get('armor'), 'defense': d['attr'].get('defense'), 'attack': d['attr'].get('attack')}}
        equip.append(row); ids.setdefault(conj, []).append(eid)
    mobs = {}; sprites = {}
    for mid, (nome, gif, classe) in MINIONS.items():
        mobs[mid] = montar_mob(nome, mid, classe, {'invocado': True})
        if mid not in SPR_EXISTE: sprites[mid] = folha_criatura(nome, mid)
    chefes = {}
    for b in BOSSES:
        m = montar_mob(b['nome'], b['id'], b['classe'], {'chefe': True})
        if b.get('invoca'): m['invoca'] = b['invoca']; m['maxInv'] = b['maxinv']
        m['hpMul'] = b['hpMul']; m['danoMul'] = b['danoMul']   # balanceamento contra o dano de uma party de 4 no nível recomendado (ver README do script)
        for conj, ch in DROPS.get(b['id'], []):
            for eid in ids[conj]:
                r = next(e for e in equip if e['id'] == eid); m['loot'].append([eid, round(ch * (.6 if r['slot'] == 'weapon' else 1), 5), 1])
        mobs[b['id']] = m; sprites[b['id']] = folha_criatura(b['nome'], b['id'])
        chefes['boss_' + b['id']] = {'n': b['nome'], 'mob': b['id'], 'lv': b['lv'], 'mapa': b['mapa'], 'minions': b['minions'], 'desc': b['desc'], 'min': 2, 'rec': 3}
    # minions que o jogo já tem mas o jogo nunca precisou de loot de: ok. Remove loot repetido por nome e ordena por chance
    return {'v': 1, 'itens': NOVOS_ITENS, 'eq': equip, 'mobs': mobs, 'chefes': chefes, 'sprites': sprites, 'cadaveres': CADAVERES}

if __name__ == '__main__':
    D = build()
    cab = '/* gerado por ferramentas/gerar_chefes.py: bosses em grupo, minions, itens de topo (Canary) e folhas de criatura reais do cliente 15.10. Não editar à mão. */\n'
    js = 'window.CHEFES=' + json.dumps({k: v for k, v in D.items() if k not in ('sprites', 'cadaveres')}, ensure_ascii=False, separators=(',', ':')) + ';\n'
    js += '(function(){var S=window.SPR15;if(!S)return;var o=' + json.dumps(D['sprites'], separators=(',', ':')) + ';for(var k in o)S.criaturas[k]=o[k];var c=' + json.dumps(D['cadaveres'], separators=(',', ':')) + ';for(var k in c)if(!S.cadaveres[k])S.cadaveres[k]=c[k];})();\n'
    open(OUT + 'chefes.js', 'w', encoding='utf-8').write(cab + js)
    print('equip', len(D['eq']), 'mobs', len(D['mobs']), 'itens novos', len(D['itens']), 'sem sprite:', sorted(SPRITE_FALTA)[:40])
