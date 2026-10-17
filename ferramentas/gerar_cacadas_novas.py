#!/usr/bin/env python3
"""Acrescenta ao jogo as caçadas novas (h101+) com criaturas que já tinham sprite mas não apareciam em nenhuma caçada, mais os donos reais dos materiais de imbuement
(vexclaw, grimeleech, silencer, braindeath, mutated tiger, blood crab, gloom wolf, grim reaper).

Fontes (as mesmas de gerar_chefes.py, de onde reaproveita a conversão Canary -> formato do jogo):
  - Canary (clone com data-otservbr-global/monster, data/items/items.xml, npc/*.lua): vida, exp, velocidade, armor/defense, resistências, ataques, defesas,
    invocações, loot (chance/100000), corpse, outfit e Bestiary (marcos, charm, estrelas, classe);
  - cliente Tibia 15.10 (Tibia.dat/.spr; --cliente DIR): folhas de criatura/cadáveres que faltarem (vexclaw, grimeleech, silencer, braindeath, mutated tiger,
    lizard snakecharmer) e ícones dos itens de loot novos (sprites15/itens/<cid>.png; só itens com preço de NPC no Canary).
Mapas: não há OTBM para mapas novos, então cada caçada nova REAPROVEITA o mapa de uma caçada existente do mesmo bioma: hNNN.js novo (chave e prefixo de tiles novos) que
aponta para o MESMO atlas PNG do original (nada de PNG duplicado). Mesmas células andáveis, início e pontos de spawn (sem células pretas, tudo alcançável, como o original);
só o monstro de cada um dos 16 pontos (ordenados do mais afastado) é redistribuído conforme os pesos da caçada.
O level recomendado sai da exp média ponderada dos monstros, interpolada na curva das 100 caçadas originais. As caçadas passam a ser numeradas (num) por level.
Grava: cacadas100.js (hunts, mobs, itens), sprites15.js (criaturas e cadáveres novos) e mapas15/cacadas/hNNN.js. Idempotente.
Depois de rodar: ferramentas/loot_faltante.py (completa o loot com itens sem preço de NPC no Canary) e ferramentas/drops_imbuement.py.
Uso: python3 -I ferramentas/gerar_cacadas_novas.py CANARY_DIR --cliente DIR [--out tibia-assets]   (precisa de Pillow)"""
import sys, os, re, json, bisect, math
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gerar_chefes as G   # lê os argumentos da linha de comando: CANARY_DIR --cliente DIR --out DIR
XC = G.XC; OUT = G.OUT; CD = G.CD

slug = lambda n: re.sub(r'[^a-z0-9]+', '_', n.lower()).strip('_')

# ---------------------------------------------------------------- caçadas novas
# id, nome, mapa de origem (caçada hNNN cujo mapa é reaproveitado), {monstro: peso}, descrição
HUNTS = [
 ('rookgaard_farm', 'Rookgaard Farm', 'h008', {'badger': 6, 'bat': 4, 'skunk': 3, 'rabbit': 2, 'chicken': 2, 'squirrel': 2, 'sheep': 1, 'pig': 1, 'dog': 1, 'cat': 1, 'deer': 1},
  'Uma fazenda tranquila de Rookgaard: texugos, morcegos, coelhos e bichos de curral. Carne e presunto de sobra.'),
 ('swamp_troll_marsh', 'Swamp Troll Marsh', 'h020', {'swamp_troll': 10, 'marsh_stalker': 4, 'swampling': 4, 'toad': 4, 'salamander': 2, 'crimson_frog': 2},
  'Trolls do pântano, sapos e criaturas lodosas num brejo escuro.'),
 ('troll_caves', 'Troll Caves', 'h016', {'troll_guard': 10, 'troll_champion': 8, 'furious_troll': 3},
  'Cavernas de trolls veteranos: guardas, campeões e o temido Furious Troll.'),
 ('chakoya_iceberg', 'Chakoya Iceberg', 'h007', {'chakoya_toolshaper': 8, 'chakoya_tribewarden': 8, 'chakoya_windcaller': 6, 'frost_troll': 5, 'penguin': 2, 'dire_penguin': 2},
  'Um iceberg habitado pelos chakoyas, trolls de gelo e pinguins.'),
 ('goblin_minotaur_camp', 'Goblin & Minotaur Camp', 'h040', {'goblin_leader': 6, 'goblin_assassin': 8, 'minotaur_guard': 8, 'wild_warrior': 4},
  'Um acampamento de goblins chefes e assassinos ao lado de guardas minotauros.'),
 ('dworc_village', 'Dworc Village', 'h011', {'dworc_venomsniper': 8, 'dworc_voodoomaster': 8, 'dworc_fleshhunter': 6, 'orc_rider': 4},
  'A aldeia dos dworcs: atiradores venenosos, mestres do voodoo e cavaleiros orcs.'),
 ('thieves_den', "Thieves' Den", 'h034', {'gang_member': 8, 'grave_robber': 6, 'smuggler': 5, 'crazed_beggar': 4, 'firestarter': 4},
  'Um covil de ladrões, contrabandistas e incendiários escondido no subsolo.'),
 ('abandoned_mine', 'Abandoned Mine', 'h022', {'undead_mine_worker': 10, 'undead_prospector': 8, 'corym_charlatan': 4, 'little_corym_charlatan': 5, 'damaged_worker_golem': 3},
  'Uma mina abandonada onde mineiros mortos-vivos e corym disputam cada túnel.'),
 ('pirate_cove', 'Pirate Cove', 'h032', {'pirate_marauder': 8, 'pirate_skeleton': 8, 'pirate_ghost': 3, 'smuggler': 4},
  'Uma enseada de piratas vivos, esqueletos e fantasmas guardando o tesouro.'),
 ('blood_crab_shore', 'Blood Crab Shore', 'h013', {'blood_crab': 10, 'deepsea_blood_crab': 5, 'seagull': 2, 'flamingo': 1},
  'A praia dos caranguejos de sangue: pinças vermelhas e muita casca.'),
 ('lizard_temple', 'Lizard Temple', 'h036', {'lizard_sentinel': 10, 'lizard_templar': 8, 'lizard_snakecharmer': 4},
  'O templo dos lagartos: sentinelas, templários e encantadores de serpente.'),
 ('witch_grove', 'Witch Grove', 'h060', {'witch': 8, 'elf_arcanist': 6, 'hunter': 5, 'gargoyle': 3},
  'Um bosque de bruxas e arcanistas élficos, com caçadores à espreita.'),
 ('mad_scientist_lab', 'Mad Scientist Lab', 'h046', {'mad_scientist': 8, 'dark_magician': 6, 'novice_of_the_cult': 5},
  'O laboratório de cientistas loucos e magos sombrios do culto.'),
 ('mammoth_tundra', 'Mammoth Tundra', 'h053', {'mammoth': 8, 'gloom_wolf': 8, 'ghost_wolf': 4, 'white_deer': 2},
  'A tundra dos mamutes e dos lobos sombrios, que carregam pelos valiosos.'),
 ('elephant_savanna', 'Elephant Savanna', 'h070', {'elephant': 8, 'water_buffalo': 6, 'scorpion': 5, 'terramite': 4, 'dromedary': 1},
  'A savana dos elefantes e búfalos, com escorpiões e terramites na areia.'),
 ('hound_plains', 'Hound Plains', 'h027', {'gnarlhound': 8, 'boar': 6, 'starving_wolf': 6, 'war_wolf': 4, 'terror_bird': 4},
  'Planícies cheias de cães selvagens, javalis, lobos famintos e terror birds.'),
 ('gargoyle_ruins', 'Gargoyle Ruins', 'h029', {'gargoyle': 10, 'white_shade': 5, 'wisp': 2, 'tainted_soul': 3},
  'Ruínas assombradas por gárgulas de pedra, sombras brancas e almas corrompidas.'),
 ('mole_burrows', 'Mole Burrows', 'h018', {'mole': 8, 'slug': 5, 'insect_swarm': 5, 'leaf_golem': 3, 'spit_nettle': 2},
  'Tocas escuras de toupeiras, lesmas, enxames e golens de folhas.'),
 ('braindeath_crypt', 'Braindeath Crypt', 'h056', {'braindeath': 10, 'bonelord': 3},
  'A cripta dos braindeaths, cérebros flutuantes que invocam vampiros.'),
 ('mutated_jungle', 'Mutated Jungle', 'h035', {'mutated_tiger': 10, 'tiger': 3},
  'Uma selva infestada de tigres mutantes, de dentes de sabre afiados.'),
 ('hellspawn_pit', 'Hellspawn Pit', 'h077', {'destroyer': 8, 'hellspawn': 8},
  'Um fosso de lava onde destroyers e hellspawns despedaçam qualquer um.'),
 ('grim_reaper_crypt', 'Grim Reaper Crypt', 'h082', {'grim_reaper': 10, 'white_shade': 3},
  'Uma cripta funesta guardada pelos Grim Reapers, senhores das ampulhetas do tempo.'),
 ('demon_rift', 'Demon Rift', 'h076', {'vexclaw': 8, 'grimeleech': 8, 'silencer': 6, 'dark_torturer': 3},
  'Uma fenda infernal de vexclaws, grimeleeches, silencers e torturadores sombrios.'),
 ('juggernaut_fortress', 'Juggernaut Fortress', 'h090', {'juggernaut': 10, 'destroyer': 3},
  'A fortaleza dos juggernauts: o fim da linha dos demônios.'),
]
EXISTENTES = {'tiger', 'bonelord', 'dworc_fleshhunter', 'war_wolf', 'terror_bird'}   # já eram monstros das 100 caçadas: não são regerados
# preços 'estimado' que ficaram absurdos (comida/munição/osso valendo milhares) e distorciam o gp/h das caçadas novas: valores de NPC do Tibia real
CORRECOES_PRECO = {'beetroot': 5, 'flaming_arrow': 10, 'big_bone': 28}
# ajustes finos de level depois de medir exp/h numa simulação de 5 min com um knight (vida alta ou exp alta demais para o level da curva)
LV_AJUSTE = {'blood_crab_shore': 42, 'witch_grove': 46, 'grim_reaper_crypt': 430, 'juggernaut_fortress': 720}
PULL = {'cauteloso': {'n': 6, 'k': 1, 'nome': 'Cauteloso'}, 'ousado': {'n': 10, 'k': 2, 'nome': 'Ousado'}, 'agressivo': {'n': 16, 'k': 3, 'nome': 'Agressivo'}}

# ---------------------------------------------------------------- monstros
NOME_REAL = {}   # slug -> nome exato do Canary
for k, s in G.MON.items():
    NOME_REAL.setdefault(slug(k), re.search(r'createMonsterType\("([^"]+)"', s).group(1))

def bestiario(s):
    c = G.campos(re.search(r'monster\.Bestiary = \{(.*?)\n\}', s, re.S).group(1)) if re.search(r'monster\.Bestiary = \{', s) else None
    if not c: return {'best': [25, 250, 500], 'charm': 5, 'est': 1}, 'Elemental'
    return {'best': [G.num(c.get('FirstUnlock'), 25), G.num(c.get('SecondUnlock'), 250), G.num(c.get('toKill'), 500)], 'charm': G.num(c.get('CharmsPoints'), 5),
            'est': G.num(c.get('Stars'), 1)}, c.get('class', 'Elemental')

def exportar_icones(nomes):
    """exporta do cliente os ícones dos itens de loot que o jogo ainda não tem (com preço de NPC no Canary), antes de converter o loot"""
    spr, dat = G.cliente(); feitos = []
    for nm in nomes:
        for e in G.entradas(G.blocos(G.MON[nm.lower()], 'loot')):
            if 'chance' not in e: continue
            d = G.item_do_loot(e)
            if not d: continue
            n, cid = d['name'].lower(), d['id']
            if n in G.ours_by_name or cid in G.ours_by_cid or str(cid) in G.icones_eq: continue
            arq = f'{G.ITENS_DIR}{cid}.png'
            if os.path.exists(arq) or G.SELL.get(cid, 0) <= 0: continue
            os.makedirs(G.ITENS_DIR, exist_ok=True); XC.render(spr, dat.cats[XC.CAT_ITEM][cid]).save(arq); feitos.append(d['name'])
    return feitos

def curva_lv():
    """(log exp média ponderada, level) das 100 caçadas originais, ordenado"""
    nossos = {h[0] for h in HUNTS}
    pts = sorted((math.log(max(1, sum(CD['mobs'][m]['exp'] * w for m, w in h['mobs'].items()) / sum(h['mobs'].values()))), h['lv']) for k, h in CD['hunts'].items() if k not in nossos)
    return [p[0] for p in pts], [p[1] for p in pts]
def lv_da_exp(exp, curva):
    xs, ys = curva; x = math.log(max(1, exp)); i = bisect.bisect_left(xs, x)
    if i == 0: return max(1, ys[0] * x / max(xs[0], 1e-9)) if x > 0 and exp >= 3 else 1
    if i >= len(xs): return ys[-1]
    lo, hi = max(0, i - 4), min(len(xs), i + 4); xx, yy = xs[lo:hi], ys[lo:hi]   # reta de mínimos quadrados local (não segue o ruído de uma caçada isolada)
    mx, my = sum(xx) / len(xx), sum(yy) / len(yy); den = sum((a - mx) ** 2 for a in xx) or 1
    return my + sum((a - mx) * (c - my) for a, c in zip(xx, yy)) / den * (x - mx)

# ---------------------------------------------------------------- mapas
def sorteio_mobs(pesos, n):
    """n pontos de spawn na proporção dos pesos (todo monstro com ao menos um ponto): os primeiros pontos (modo Cauteloso usa 6) levam um de cada monstro, do maior peso
    para o menor, e o resto é intercalado por smooth weighted round robin"""
    ks = sorted(pesos, key=lambda k: -pesos[k]); tot = sum(pesos.values()); cnt = {k: max(1, round(pesos[k] / tot * n)) for k in ks}
    while sum(cnt.values()) > n: cnt[max((k for k in ks if cnt[k] > 1), key=lambda k: cnt[k])] -= 1
    while sum(cnt.values()) < n: cnt[max(ks, key=lambda k: pesos[k] / cnt[k])] += 1
    seq = list(ks[:6])
    for k in seq: cnt[k] -= 1
    cur = {k: 0.0 for k in ks}; rest = sum(cnt.values())
    for _ in range(rest):
        for k in ks: cur[k] += cnt[k]
        b = max((k for k in ks if cnt[k] > 0), key=lambda k: cur[k]); cur[b] -= rest; cnt[b] -= 1; seq.append(b)
    return seq

def copiar_mapa(src, chave, nome, pesos):
    p = f'{OUT}mapas15/cacadas/{src}.js'; s = open(p, encoding='utf-8').read(); pre = 'window.MAPAS=Object.assign(window.MAPAS||{},'
    i = s.index(pre) + len(pre); obj, j = json.JSONDecoder().raw_decode(s, i); m = obj[src]; seq = sorteio_mobs(pesos, len(m['spawns']))
    m['nome'] = nome; m['spawns'] = [[x, y, seq[k], t] for k, (x, y, _, t) in enumerate(m['spawns'])]
    novo = s[:i] + json.dumps({chave: m}, ensure_ascii=False, separators=(",", ":")) + s[j:]
    novo = novo.replace('"' + src + ':', '"' + chave + ':')
    novo = re.sub(r'^/\*.*?\*/', f'/* mapa de {src} reaproveitado para a caçada {nome} por ferramentas/gerar_cacadas_novas.py (mesmo atlas PNG; spawns redistribuídos) */', novo, count=1, flags=re.S)
    open(f'{OUT}mapas15/cacadas/{chave}.js', 'w', encoding='utf-8').write(novo)

def gravar(path, var, mexe):
    """relê o arquivo logo antes de gravar e aplica `mexe(obj)` nele (não pisa em mudanças concorrentes)"""
    s = open(path, encoding='utf-8').read(); m = 'window.' + var + '='; i = s.index(m) + len(m); o, j = json.JSONDecoder().raw_decode(s[i:])
    mexe(o); open(path, 'w', encoding='utf-8').write(s[:i] + json.dumps(o, ensure_ascii=False, separators=(',', ':')) + s[i + j:])

def main():
    usados = []
    for h in HUNTS:
        for m in h[3]:
            if m not in usados: usados.append(m)
    gerar = [m for m in usados if m not in EXISTENTES]
    for m in usados:
        if m not in NOME_REAL and m not in CD['mobs']: sys.exit('monstro sem Canary: ' + m)
    print('monstros a gerar:', len(gerar))
    print('ícones de loot exportados:', exportar_icones([NOME_REAL[m] for m in gerar]))
    mobs = {}; sprites = {}
    for mid in gerar:
        nm = NOME_REAL[mid]; s = G.MON[nm.lower()]; extra, classe = bestiario(s)
        mobs[mid] = G.montar_mob(nm, mid, classe, extra)
    SPR = G.carregar_js(OUT + 'sprites15.js', 'SPR15')
    for mid in gerar:
        meta = SPR['criaturas'].get(mid)
        if meta and os.path.exists(f'{G.CRIA_DIR}{mid}.png'):   # a folha já existe: não mexe nela; só garante o cadáver (meta['cad'])
            if meta.get('cad') is None:
                _, corpo = XC.ler_monstro_lua_txt(G.MON[NOME_REAL[mid].lower()])
                if corpo:
                    spr, dat = G.cliente(); arq = f'{G.CAD_DIR}{corpo}.png'
                    if not os.path.exists(arq): os.makedirs(G.CAD_DIR, exist_ok=True); XC.render(spr, dat.cats[XC.CAT_ITEM][corpo]).save(arq)
                    c = G.Image.open(arq); G.CADAVERES[str(corpo)] = {'w': c.width, 'h': c.height, 'src': f'tibia-assets/sprites15/cadaveres/{corpo}.png'}
                    sprites[mid] = dict(meta, cad=corpo)
            continue
        sprites[mid] = G.folha_criatura(NOME_REAL[mid], mid)
    print('sprites de criatura exportados:', sorted(sprites), '| cadáveres novos:', sorted(G.CADAVERES))
    # caçadas
    curva = curva_lv(); hunts = {}
    for n, (hid, nome, src, pesos, desc) in enumerate(HUNTS):
        sh = next(h for h in CD['hunts'].values() if h['chave'] == src)
        exp_med = sum(mobs[m]['exp'] * w if m in mobs else CD['mobs'][m]['exp'] * w for m, w in pesos.items()) / sum(pesos.values())
        lv = LV_AJUSTE.get(hid) or max(1, round(lv_da_exp(exp_med, curva)))
        chave = f'h{101 + n}'
        copiar_mapa(src, chave, nome, pesos)
        hunts[hid] = {'num': 0, 'n': nome, 'desc': desc, 'lv': lv, 'mobs': pesos, 'principal': max(pesos, key=pesos.get), 'bioma': sh['bioma'], 'mapa': f'tibia-assets/mapas15/cacadas/{chave}.js',
                      'chave': chave, 'pull': PULL, 'sub': sh['sub'], 'origem': f"mapa reaproveitado de {sh['n']} ({src}); exp média {exp_med:.0f}"}
    def mexe_cd(o):
        o['mobs'].update(mobs); o['itens'].update({k: v for k, v in G.NOVOS_ITENS.items() if k not in o['itens']})
        for k, v in CORRECOES_PRECO.items():
            if k in o['itens']: o['itens'][k]['v'] = v
        for k, h in hunts.items(): o['hunts'][k] = h
        for i, (k, h) in enumerate(sorted(o['hunts'].items(), key=lambda kv: (kv[1]['lv'], kv[1]['num'] or 999, kv[0]))): h['num'] = i + 1   # num = posição por level
    gravar(OUT + 'cacadas100.js', 'CACADAS100', mexe_cd)
    def mexe_spr(o):
        o['criaturas'].update(sprites); o['cadaveres'].update({k: v for k, v in G.CADAVERES.items()})
    gravar(OUT + 'sprites15.js', 'SPR15', mexe_spr)
    print('itens novos:', sorted(G.NOVOS_ITENS), '| sem sprite/preço:', sorted(G.SPRITE_FALTA))
    for k, h in sorted(hunts.items(), key=lambda kv: kv[1]['lv']): print(f"{k:22} lv {h['lv']:4} {h['chave']} {h['origem']}")

if __name__ == '__main__':
    main()
