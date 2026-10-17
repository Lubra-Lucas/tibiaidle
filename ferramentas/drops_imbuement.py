#!/usr/bin/env python3
"""Garante que os materiais de imbuement e as gemas gigantes tenham quem os dropa.
Idempotente: reescreve apenas os arrays de loot dos monstros listados e as entradas de `itens`
(tira a marca naoDropa). Re-le cada arquivo imediatamente antes de gravar.

Pesquisa no Canary (data-otservbr-global/monster, chance/100000): NENHUM dos monstros/chefes do jogo dropa
estes itens no Canary (os donos reais - blood crab, braindeath, silencer, grimeleech, vexclaw, mutated tiger,
gloom wolf, grim reaper, apocalypse, abomination, brain head... - nao estao nas 100 cacadas nem nos chefes).
Por isso cada item vai para o monstro tematicamente mais proximo, com chance baixa (comentario em cada linha).
"""
import json, os, sys
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tibia-assets')
CACADAS, CHEFES = os.path.join(R, 'cacadas100.js'), os.path.join(R, 'chefes.js')

# (arquivo, monstro, item, chance 0-1, maxCount)
DROPS = [
 # Bloody Pincers (blood crab 6,19% / deepsea blood crab 6,98% / thanatursus 4,2%): caranguejo e serpente marinha
 ('c', 'crab',                 'bloody_pincers', 0.04, 1),
 ('c', 'young_sea_serpent',    'bloody_pincers', 0.03, 1),
 # Piece of Dead Brain (braindeath 5,03%, rage squid 4,9%, squid warden 10%): bonelords (cerebro/olho)
 ('c', 'bonelord',             'piece_of_dead_brain', 0.05, 1),
 ('c', 'gazer',                'piece_of_dead_brain', 0.02, 1),
 # Silencer Claws (silencer 17%, enfeebled silencer 4%): demonios de garras do fim do jogo
 ('c', 'hellflayer',           'silencer_claws', 0.08, 1),
 ('c', 'brachiodemon',         'silencer_claws', 0.08, 1),
 # Some Grimeleech Wings (grimeleech 19,08%): demonios alados / vampiros
 ('c', 'infernal_demon',       'some_grimeleech_wings', 0.05, 1),
 ('c', 'fury',                 'some_grimeleech_wings', 0.04, 1),
 # Sabretooth (mutated tiger 10,6%): felinos
 ('c', 'tiger',                'sabretooth', 0.08, 1),
 ('c', 'sabretooth',           'sabretooth', 0.15, 1),
 # Vexclaw Talon (vexclaw 21,5%): demonios
 ('c', 'demon',                'vexclaw_talon', 0.05, 1),
 ('c', 'hellflayer',           'vexclaw_talon', 0.04, 1),
 # Gloom Wolf Fur (gloom wolf 8%): lobos
 ('c', 'winter_wolf',          'gloom_wolf_fur', 0.10, 1),
 ('c', 'wolf',                 'gloom_wolf_fur', 0.05, 1),
 # Mystical Hourglass (grim reaper 5,3%, last lore keeper 1%): guardioes da biblioteca (tempo/lore)
 ('c', 'guardian_of_tales',    'mystical_hourglass', 0.02, 1),
 ('c', 'energuardian_of_tales','mystical_hourglass', 0.02, 1),
 # Gemas gigantes (Canary: Apocalypse ruby 31,5%; Abomination/Brain Head amethyst; Abomination topaz): chefes demoniacos
 ('h', 'ferumbras',            'giant_ruby', 0.15, 1),
 ('h', 'orshabaal',            'giant_ruby', 0.08, 1),
 ('h', 'gazharagoth',          'giant_amethyst', 0.10, 1),
 ('h', 'ghazbaran',            'giant_amethyst', 0.06, 1),
 ('h', 'ghazbaran',            'giant_topaz', 0.10, 1),
 ('h', 'orshabaal',            'giant_topaz', 0.06, 1),
]
# sabretooth (monstro) nao dropa o item no Canary; mantido por tema (hunt 94). giant_sapphire/emerald ja caem do Scourge.

def load(path, marca):
    txt = open(path, encoding='utf-8').read()
    i = txt.index(marca) + len(marca)
    obj, j = json.JSONDecoder().raw_decode(txt, i)
    return txt, i, j, obj

def dump(o): return json.dumps(o, ensure_ascii=False, separators=(',', ':'))

def process(path, marca, tag, extra_itens):
    txt, i, j, d = load(path, marca)
    mobs = d['mobs']
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
