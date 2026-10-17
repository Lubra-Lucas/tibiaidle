#!/usr/bin/env python3
"""Garante que os materiais de imbuement e as gemas gigantes tenham quem os dropa.
Idempotente: reescreve apenas os arrays de loot dos monstros listados e as entradas de `itens`
(tira a marca naoDropa). Re-le cada arquivo imediatamente antes de gravar.

Materiais de imbuement: cada um tem agora o DONO REAL do Canary (data-otservbr-global/monster, chance/100000) dentro das caçadas
(tabela REAIS, gerada pelas caçadas novas de ferramentas/gerar_cacadas_novas.py): vexclaw, grimeleech, silencer, braindeath,
blood crab / deepsea blood crab, mutated tiger, gloom wolf e grim reaper. O script confere que o dono real esta no jogo e
REMOVE os drops de reserva tematicos (ANTIGOS_FALLBACK) que existiam antes para esse item. Se um dia um item perder o dono real,
ponha-o em FALLBACK (monstro tematico, chance baixa) que o script o recoloca.
Gemas gigantes (Canary: Apocalypse ruby; Abomination/Brain Head amethyst/topaz): ainda sem dono real no jogo -> chefes demoniacos (DROPS 'h').
"""
import json, os, sys
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tibia-assets')
CACADAS, CHEFES = os.path.join(R, 'cacadas100.js'), os.path.join(R, 'chefes.js')

# (arquivo, monstro, item, chance 0-1, maxCount)
DROPS = [   # (arquivo, monstro, item, chance 0-1, maxCount) -- drops de reserva ainda necessarios
 # Gemas gigantes (Canary: Apocalypse ruby 31,5%; Abomination/Brain Head amethyst; Abomination topaz): chefes demoniacos
 ('h', 'ferumbras',            'giant_ruby', 0.15, 1),
 ('h', 'orshabaal',            'giant_ruby', 0.08, 1),
 ('h', 'gazharagoth',          'giant_amethyst', 0.10, 1),
 ('h', 'ghazbaran',            'giant_amethyst', 0.06, 1),
 ('h', 'ghazbaran',            'giant_topaz', 0.10, 1),
 ('h', 'orshabaal',            'giant_topaz', 0.06, 1),
]
# giant_sapphire/emerald ja caem do Scourge.
# donos reais (Canary) dos materiais de imbuement que ja estao nas caçadas: item -> monstros
REAIS = {
 'bloody_pincers': ['blood_crab', 'deepsea_blood_crab'],          # 6,19% / 6,98%  (Blood Crab Shore)
 'piece_of_dead_brain': ['braindeath'],                           # 5,03%          (Braindeath Crypt)
 'silencer_claws': ['silencer'],                                  # 17%            (Demon Rift)
 'some_grimeleech_wings': ['grimeleech'],                         # 19,08%         (Demon Rift)
 'sabretooth': ['mutated_tiger'],                                 # 10,6%          (Mutated Jungle)
 'vexclaw_talon': ['vexclaw'],                                    # 21,5%          (Demon Rift)
 'gloom_wolf_fur': ['gloom_wolf'],                                # 8%             (Mammoth Tundra)
 'mystical_hourglass': ['grim_reaper'],                           # 5,3%           (Grim Reaper Crypt)
}
# drops de reserva (tematicos) que existiam antes dos donos reais: sao removidos se o item tem dono real no jogo
ANTIGOS_FALLBACK = [('crab', 'bloody_pincers'), ('young_sea_serpent', 'bloody_pincers'), ('bonelord', 'piece_of_dead_brain'), ('gazer', 'piece_of_dead_brain'),
 ('hellflayer', 'silencer_claws'), ('brachiodemon', 'silencer_claws'), ('infernal_demon', 'some_grimeleech_wings'), ('fury', 'some_grimeleech_wings'),
 ('tiger', 'sabretooth'), ('sabretooth', 'sabretooth'), ('demon', 'vexclaw_talon'), ('hellflayer', 'vexclaw_talon'), ('winter_wolf', 'gloom_wolf_fur'), ('wolf', 'gloom_wolf_fur'),
 ('guardian_of_tales', 'mystical_hourglass'), ('energuardian_of_tales', 'mystical_hourglass')]
FALLBACK = []   # (monstro, item, chance, maxCount) de itens cujo dono real ainda nao esta no jogo (nenhum no momento)

def load(path, marca):
    txt = open(path, encoding='utf-8').read()
    i = txt.index(marca) + len(marca)
    obj, j = json.JSONDecoder().raw_decode(txt, i)
    return txt, i, j, obj

def dump(o): return json.dumps(o, ensure_ascii=False, separators=(',', ':'))

def process(path, marca, tag, extra_itens):
    txt, i, j, d = load(path, marca)
    mobs = d['mobs']
    if tag == 'c':
        for it, donos in REAIS.items():
            for dono in donos:
                if dono not in mobs or not any(l[0] == it for l in mobs[dono]["loot"]): sys.exit(f"dono real ausente: {dono} -> {it}")
        for m, it in ANTIGOS_FALLBACK:
            if m in mobs and it in REAIS: mobs[m]['loot'] = [l for l in mobs[m]['loot'] if l[0] != it]
        for m, it, ch, mx in FALLBACK:
            loot = mobs[m]['loot']
            for l in loot:
                if l[0] == it: l[1], l[2] = ch, mx; break
            else: loot.append([it, ch, mx])
    for t, m, it, ch, mx in DROPS:
        if t != tag: continue
        if m not in mobs: sys.exit('monstro ausente: ' + m)
        loot = mobs[m]['loot']
        for l in loot:
            if l[0] == it: l[1], l[2] = ch, mx; break
        else: loot.append([it, ch, mx])
    for k in extra_itens:
        if k in d['itens']: d['itens'][k].pop('naoDropa', None)
    # re-le logo antes de gravar para nao pisar em mudancas concorrentes
    txt2, i2, j2, _ = load(path, marca)
    if txt2 != txt: sys.exit('arquivo mudou durante a execucao: ' + path)
    novo = txt[:i] + dump(d) + txt[j:]
    if novo != txt:
        open(path, 'w', encoding='utf-8').write(novo)
        print('atualizado', os.path.basename(path))
    else: print('sem mudancas', os.path.basename(path))

MATS = ['bloody_pincers','piece_of_dead_brain','silencer_claws','some_grimeleech_wings','sabretooth','vexclaw_talon','gloom_wolf_fur','mystical_hourglass']
process(CACADAS, 'window.CACADAS100=', 'c', MATS)
process(CHEFES, 'window.CHEFES=', 'h', [])
