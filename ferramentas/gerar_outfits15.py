#!/usr/bin/env python3
"""Gera as folhas de outfits (tibia-assets/sprites15/outfits/<look>.png + <look>m.png montado) e montarias
(tibia-assets/sprites15/montarias/<clientid>.png) do cliente Tibia 15.x e os mapas tibia-assets/outfits15.js
(window.OUTFITS15) e tibia-assets/montarias15.js (window.MONTARIAS15).

Uso (sempre com -I):
  python3 -I ferramentas/gerar_outfits15.py --dat Tibia.dat --spr Tibia.spr --outfits outfits.xml --montarias mounts.xml [--so 136,137] [--saida dir]

Folha de outfit: colunas = quadros parados + quadros de andar (64x64 por celula, canto inferior direito), linhas em blocos
de 8 por padrao de addon (0 = base, 1 e 2 = addons): 4 linhas (N,L,S,O) da camada base e 4 da MASCARA de cores
(amarelo=cabeca, vermelho=corpo, verde=pernas, azul=pes); comporOutfit() do index.html pinta a mascara.
<look>m.png: a mesma folha na pose montada (patternZ 1). Sem addons os blocos 1 e 2 ficam vazios (altura fixa de 24 linhas)."""
import argparse, json, os, re, sys
import xml.etree.ElementTree as ET
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extrair_cliente import Spr, detectar, camada_img, CAT_OUTFIT
from PIL import Image


def salvar(im, caminho):
    """PNG sem perdas; com ate 256 cores (RGBA exato) grava em paleta + tRNS (bem menor), senao RGBA otimizado."""
    cores = im.getcolors(256)
    if cores:
        pal = [c for _, c in cores]
        idx = {c: i for i, c in enumerate(pal)}
        p = Image.new("P", im.size)
        p.putpalette([v for c in pal for v in c[:3]])
        p.putdata([idx[c] for c in zip(*[iter(im.tobytes())] * 4)])
        p.info["transparency"] = bytes(c[3] for c in pal)
        assert p.convert("RGBA").tobytes() == im.tobytes()
        p.save(caminho, optimize=True, transparency=p.info["transparency"])
    else:
        im.save(caminho, optimize=True)


def grupos(t):
    gp = [g for g in t.grupos if g.tipo == 0] or t.grupos[:1]
    g0 = gp[0]
    gm = [g for g in t.grupos if g.tipo == 1 and g is not g0]
    return g0, (gm[0] if gm else None)


def folha(spr, t, z=0, addons=True, preencher=True):
    """(Image, meta, tem_addons) ou None se a pose nao existe."""
    g0, gm = grupos(t)
    if z >= g0.pz:
        return None
    quadros = [(g0, f) for f in range(g0.fases)] + ([(gm, f) for f in range(gm.fases)] if gm else [])
    W, H = 32 * max(g.w for g, _ in quadros), 32 * max(g.h for g, _ in quadros)
    npy = max(1, min(3, g0.py))
    blocos = []
    for py in range(npy):
        im = Image.new("RGBA", (W * len(quadros), H * 8), (0, 0, 0, 0))
        for col, (g, f) in enumerate(quadros):
            if py >= g.py or z >= g.pz:
                continue
            for d in range(4):
                for cam in range(min(2, g.layers)):
                    c = camada_img(spr, g, f, d % g.px, py, cam) if z == 0 else camada_z(spr, g, f, d % g.px, py, cam, z)
                    im.paste(c, (col * W + W - c.width, (cam * 4 + d) * H + H - c.height))
        blocos.append(im)
    tem = addons and npy > 1 and any(b.getbbox() for b in blocos[1:])
    if not tem:
        blocos = blocos[:1]
    out = Image.new("RGBA", (blocos[0].width, blocos[0].height * (3 if preencher else len(blocos))), (0, 0, 0, 0))   # outfits: sempre 3 blocos (a folha original tem altura fixa)
    for i, b in enumerate(blocos):
        out.paste(b, (0, i * b.height))
    ms = [max(1, g0.dur[i][0]) for i in range(g0.fases)] if g0.dur and g0.fases > 1 else [300]
    dl = t.flags.get("displacement")
    desl = [dl[0] | dl[1] << 8, dl[2] | dl[3] << 8] if dl else [0, 0]
    return out, {"w": W, "h": H, "parado": g0.fases, "andar": gm.fases if gm else 0, "ms": ms, "desl": desl}, bool(tem)


def camada_z(spr, g, frame, x, y, camada, z):
    from extrair_cliente import indice
    im = Image.new("RGBA", (32 * g.w, 32 * g.h), (0, 0, 0, 0))
    for hh in range(g.h):
        for ww in range(g.w):
            sid = g.ids[indice(g, frame, x, y, z, camada, hh, ww)]
            if sid:
                im.alpha_composite(spr.sprite(sid), (32 * (g.w - ww - 1), 32 * (g.h - hh - 1)))
    return im


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dat", required=True); ap.add_argument("--spr", required=True)
    ap.add_argument("--outfits", help="outfits.xml do Canary"); ap.add_argument("--montarias", help="mounts.xml do Canary")
    ap.add_argument("--so", help="lookTypes separados por virgula (so esses; nao reescreve os .js)")
    ap.add_argument("--saida", default="tibia-assets")
    a = ap.parse_args()
    spr = Spr(a.spr)
    dat, _ = detectar(a.dat, spr.n)
    so = {int(v) for v in a.so.split(",")} if a.so else None
    od, md = os.path.join(a.saida, "sprites15/outfits"), os.path.join(a.saida, "sprites15/montarias")
    os.makedirs(od, exist_ok=True); os.makedirs(md, exist_ok=True)
    if a.outfits:
        res = {}
        for o in ET.parse(a.outfits).getroot().iter("outfit"):
            look, sexo = int(o.get("looktype")), "f" if o.get("type") == "0" else "m"
            t = dat.cats[CAT_OUTFIT].get(look)
            if not t or (so and look not in so):
                continue
            r = folha(spr, t, 0)
            if not r:
                continue
            im, meta, tem = r
            salvar(im, os.path.join(od, f"{look}.png"))
            e = {"nome": o.get("name"), "sexo": sexo, "src": f"tibia-assets/sprites15/outfits/{look}.png", **meta, "addons": tem}
            rm = folha(spr, t, 1)
            if rm and rm[0].getbbox():
                salvar(rm[0], os.path.join(od, f"{look}m.png"))
                e["srcm"] = f"tibia-assets/sprites15/outfits/{look}m.png"
            res[str(look)] = e
        if not so:
            with open(os.path.join(a.saida, "outfits15.js"), "w") as f:
                f.write("/* gerado por ferramentas/gerar_outfits15.py (outfits do cliente 15.x com máscara de cores, addons e pose montada srcm) */\nwindow.OUTFITS15=" + json.dumps(res, ensure_ascii=False, separators=(",", ":")) + ";\n")
        print(len(res), "outfits")
    if a.montarias:
        res = {}
        for m in ET.parse(a.montarias).getroot().iter("mount"):
            cid = int(m.get("clientid"))
            t = dat.cats[CAT_OUTFIT].get(cid)
            if not t or (so and cid not in so):
                continue
            r = folha(spr, t, 0, False, False)
            if not r:
                continue
            im, meta, _ = r
            salvar(im, os.path.join(md, f"{cid}.png"))
            res[m.get("id")] = {"nome": m.get("name"), "look": cid, "vel": int(m.get("speed")), "prem": m.get("premium") == "yes", "tipo": m.get("type"), "src": f"tibia-assets/sprites15/montarias/{cid}.png", **meta}
        if not so:
            with open(os.path.join(a.saida, "montarias15.js"), "w") as f:
                f.write("/* gerado por ferramentas/gerar_outfits15.py (montarias do cliente 15.x; mounts.xml do Canary) */\nwindow.MONTARIAS15=" + json.dumps(res, ensure_ascii=False, separators=(",", ":")) + ";\n")
        print(len(res), "montarias")


if __name__ == "__main__":
    sys.exit(main())
