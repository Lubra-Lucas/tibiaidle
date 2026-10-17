#!/usr/bin/env python3
"""Completa os efeitos de combate do jogo (tibia-assets/combate15.js, COMB15) com o que faltava do cliente 15.10 e liga a eles o que o Canary usa.

  1. efeitos e missiles do cliente que o COMB15 ainda nao tem -> novos atlas tibia-assets/sprites15/combate_N.png (extrair_cliente.atlas_combate, mesmo formato dos
     atlas existentes: os 194 efeitos e 56 missiles que o COMB15 ja tinha saem pixel a pixel iguais); os que o proprio cliente define TOTALMENTE vazios (sprite 0) nao
     entram nos atlas: ficam registrados em COMB15.vazios (efeitos/tiros), ja que o Tibia real tambem nao desenha nada para eles; nomes do Canary (CONST_ME_*) dos novos
     entram em COMB15.me;
  2. magias de suporte do Canary (util/conjure/...) que ficaram sem 'ef' (a magia so manda o efeito em sendMagicEffect, que o gerador nao lia): ganham o efeito real
     do sucesso (o ultimo CONST_ME nao-POFF do script);
  3. ataques de monstros 'condition' (veneno, etc.) e outros que o gerador converteu sem 'effect'/'shootEffect' (caiam no efeito generico de dano HIT15): recebem os ids
     reais do Canary, casando a entrada pela chance e pelo dano. Vale para os monstros de caçada (cacadas100.js), bosses/minions (chefes.js) e COMB15.monstros.
Idempotente. So mexe nesses campos (cada arquivo e relido logo antes de gravar). Uso:
  efeitos_faltantes.py --dat Tibia.dat --spr Tibia.spr --canary CANARY_DIR [--out tibia-assets] [--dry]"""
import sys, os, re, json, glob, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import extrair_cliente as X

ap = argparse.ArgumentParser(); ap.add_argument('--dat', required=True); ap.add_argument('--spr', required=True); ap.add_argument('--canary', required=True)
ap.add_argument('--out', default='tibia-assets'); ap.add_argument('--dry', action='store_true')
A = ap.parse_args(); CAN = A.canary.rstrip('/') + '/'; OUT = A.out.rstrip('/') + '/'

def carregar(p, var):
    s = open(p, encoding='utf-8').read(); m = 'window.' + var + '='; i = s.index(m) + len(m); o, j = json.JSONDecoder().raw_decode(s[i:]); return s, i, j, o
def gravar(p, var, o, ea):
    s, i, j, _ = carregar(p, var); open(p, 'w', encoding='utf-8').write(s[:i] + json.dumps(o, ensure_ascii=ea, separators=(',', ':')) + s[i + j:])
def enum(prefix):
    o = {}; n = -1
    for l in open(CAN + 'src/utils/utils_definitions.hpp', encoding='utf-8', errors='ignore'):
        m = re.match(r'\s*(' + prefix + r'\w+)\s*(?:=\s*(\d+))?\s*,', l)
        if m: n = int(m.group(2)) if m.group(2) else n + 1; o[m.group(1)] = n
    return o
ME, ANI = enum('CONST_ME_'), enum('CONST_ANI_')

# ---------------------------------------------------------------- 1. atlas
spr = X.Spr(A.spr); dat, _ = X.detectar(A.dat, spr.n)
_, _, _, CB = carregar(OUT + 'combate15.js', 'COMB15')
n0 = 1 + max(int(re.search(r'combate_(\d+)', os.path.basename(f)).group(1)) for f in glob.glob(OUT + 'sprites15/combate_*.png'))
faltam_ef = [i for i in sorted(dat.cats[X.CAT_EFFECT]) if str(i) not in CB['efeitos'] and i not in CB.get('vazios', {}).get('efeitos', [])]
faltam_ti = [i for i in sorted(dat.cats[X.CAT_MISSILE]) if str(i) not in CB['tiros'] and i not in CB.get('vazios', {}).get('tiros', [])]
novos_ef, vazios_ef, novos_ti, vazios_ti = {}, [], {}, []
if faltam_ef or faltam_ti:
    if A.dry: os.makedirs('/tmp/efeitos_faltantes_dry', exist_ok=True)
    dest = '/tmp/efeitos_faltantes_dry' if A.dry else OUT + 'sprites15'
    arqs = []
    if faltam_ef:
        novos_ef, vazios_ef, a = X.atlas_combate(spr, dat, X.CAT_EFFECT, faltam_ef, dest, 'combate', n0); arqs += a
    if faltam_ti:
        n1 = n0 + len(arqs); novos_ti, vazios_ti, a = X.atlas_combate(spr, dat, X.CAT_MISSILE, faltam_ti, dest, 'combate', n1); arqs += a
    print('atlas novos:', arqs)
print('efeitos novos', sorted(novos_ef), '| vazios no cliente (efeitos)', len(vazios_ef), '| missiles novos', sorted(novos_ti), '| vazios (missiles)', vazios_ti)
inv_me = {}
for k, v in ME.items(): inv_me.setdefault(v, k)

# ---------------------------------------------------------------- 2. magias sem 'ef'
spell_files = {}
for f in glob.glob(CAN + 'data/scripts/spells/**/*.lua', recursive=True): spell_files.setdefault(os.path.basename(f), f)
EF = {int(k) for k in CB['efeitos']} | set(novos_ef); TI = {int(k) for k in CB['tiros']} | set(novos_ti)
ef_magias = {}
for m in CB['magias']:
    if m.get('ef') or m.get('runa') or m['arquivo'] not in spell_files: continue
    efs = [ME[e] for e in re.findall(r'CONST_ME_[A-Z_0-9]+', open(spell_files[m['arquivo']], errors='ignore').read()) if e in ME and ME[e] not in (0, 3)]
    if efs and efs[-1] in EF: ef_magias[m['id']] = efs[-1]
print('magias sem ef que ganham o efeito real:', len(ef_magias), ef_magias)

# ---------------------------------------------------------------- 3. ataques de monstros
MON = {}
for f in glob.glob(CAN + 'data-otservbr-global/monster/**/*.lua', recursive=True):
    t = open(f, encoding='utf-8', errors='ignore').read(); nm = re.search(r'Game\.createMonsterType\("([^"]+)"\)', t)
    if nm: MON[nm.group(1).lower()] = t
def bloco(s, nome):
    m = re.search(r'monster\.' + nome + r' = \{\n(.*?)\n\}', s, re.S); return m.group(1) if m else ''
def campos(t): return {k: v.strip('"') for k, v in re.findall(r'(\w+)\s*=\s*("[^"]*"|[-\w\.]+)', t)}
def num(v, d=0):
    try: return int(v)
    except Exception: return d
def canary(t, nome):
    out = []
    for m in re.finditer(r'\{([^{}]*)\}', bloco(t, nome)):
        c = campos(m.group(1))
        if c.get('name') in (None, 'melee') or ('effect' not in c and 'shootEffect' not in c): continue
        iv = num(c.get('interval'), 2000) or 2000; ch = num(c.get('chance'), 100)
        out.append(((ch if ch >= 100 else min(100, round(ch * 2000 / iv))), num(c.get('minDamage')), num(c.get('maxDamage')), ME.get(c.get('effect', ''), 0), ANI.get(c.get('shootEffect', ''), 0)))
    return out
def corrigir(lista, can, aplicar):
    usados = set(); res = []
    for ch, mn, mx, e, a in can:
        for i, x in enumerate(lista):
            if i in usados or x['name'] == 'melee' or (x.get('chance'), x.get('minDamage'), x.get('maxDamage')) != (ch, mn, mx): continue
            usados.add(i)
            if e in EF and not x.get('effect'): res.append((i, 'effect', e)); aplicar and x.__setitem__('effect', e)
            if a in TI and not x.get('shootEffect'): res.append((i, 'shootEffect', a)); aplicar and x.__setitem__('shootEffect', a)
            break
    return res
def ataques(mobs, chaves, nomekey, aplicar):
    rel = {}
    for k, m in mobs.items():
        t = MON.get(m[nomekey].lower())
        if not t: continue
        r = corrigir(m[chaves[0]], canary(t, 'attacks'), aplicar) + [('def',) + x for x in corrigir(m[chaves[1]], canary(t, 'defenses'), aplicar)]
        if r: rel[k] = r
    return rel

# ---------------------------------------------------------------- gravar (cada arquivo relido e mesclado)
rel = {}
for arq, var in (('cacadas100.js', 'CACADAS100'), ('chefes.js', 'CHEFES')):
    _, _, _, O = carregar(OUT + arq, var); r = ataques(O['mobs'], ('atq15', 'def15'), 'n', True); rel.update({(arq, k): v for k, v in r.items()})
    if r and not A.dry: gravar(OUT + arq, var, O, False)
print('monstros com ataque corrigido (cacadas100/chefes):', {k[1]: v for k, v in rel.items()})
_, _, _, CB = carregar(OUT + 'combate15.js', 'COMB15')
rc = ataques(CB['monstros'], ('ataques', 'defesas'), 'nome', True); print('monstros do COMB15 corrigidos:', rc)
if not A.dry:
    CB['efeitos'].update({str(k): v for k, v in novos_ef.items()}); CB['tiros'].update({str(k): v for k, v in novos_ti.items()})
    if vazios_ef or vazios_ti:
        v = CB.setdefault('vazios', {'efeitos': [], 'tiros': []}); v['efeitos'] = sorted(set(v['efeitos']) | set(vazios_ef)); v['tiros'] = sorted(set(v['tiros']) | set(vazios_ti))
    for i in novos_ef:
        nm = inv_me.get(i)
        if nm: CB['me'].setdefault(nm.replace('CONST_ME_', '').lower(), i)
    for m in CB['magias']:
        if m['id'] in ef_magias and not m.get('ef'): m['ef'] = ef_magias[m['id']]
    gravar(OUT + 'combate15.js', 'COMB15', CB, True)
