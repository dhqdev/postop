"""Roteiro da animação 2D: normaliza o que a IA escreveu, catálogo enxuto para o prompt e roteiro sem IA.

A IA recebe só nomes curtos (cenários, personagens, objetos, ações, efeitos) e devolve um JSON pequeno:
elenco fixo (`cast`) + cenas (`scenes`). Aqui tudo é conferido: nomes em português ou inglês viram os
nomes internos, valores inválidos são descartados e, se faltar algo, a cena é deduzida da narração.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..render3d.spec import _index, lookup, parse_color, plain, scan
from .anim import CHAR_ACTIONS, NATURAL
from .characters import CHARACTER_TYPES, CRITTERS, HAIRS, HOLD_ITEMS, SKINS, make_look
from .places import PLACES
from .props import PROPS
from .scene import CAMERAS, FX, POS, Element2D, SceneSpec2D

CHAR_WORDS = {
    "person": "pessoa,personagem,humano,gente,alguem,character,individuo",
    "man": "homem,rapaz,moco,pai,marido,irmao,tio,cara,guy,sujeito,senhor,ele",
    "woman": "mulher,moca,mae,esposa,irma,tia,senhora,lady,garota adulta,ela",
    "boy": "menino,garoto,filho,crianca,kid,neto,aluno pequeno",
    "girl": "menina,filha,neta,garotinha",
    "baby": "bebe,nene,recem nascido,baby,menino jesus",
    "old_man": "idoso,velho,avo,vovo,velhinho,anciao,grandpa",
    "old_woman": "idosa,velha,vovozinha,velhinha,grandma",
    "king": "rei,imperador,monarca,nabucodonosor,herodes,davi,salomao,sultao,king",
    "queen": "rainha,imperatriz,ester,queen",
    "prince": "principe,prince",
    "princess": "princesa,princess,fada",
    "prophet": "profeta,daniel,moises,elias,abraao,noe,sabio,ancião sabio,prophet",
    "shepherd": "pastor,pastores,pastorzinho,shepherd,jose",
    "disciple": "discipulo,apostolo,pedro,joao,tiago,andre,discipulos,apostolos,sidrac,misac,abdenago,hebreu",
    "jesus": "jesus,cristo,messias,senhor jesus",
    "mary": "maria,nossa senhora,virgem maria",
    "biblical_man": "israelita,judeu,homem da biblia",
    "biblical_woman": "mulher da biblia,israelita mulher,marta,rute,sara,ana",
    "angel": "anjo,anjos,gabriel,miguel,angel",
    "priest": "padre,sacerdote,pastor de igreja,priest",
    "pharaoh": "farao,pharaoh",
    "soldier": "soldado,soldados,guerreiro,centuriao,soldier,warrior,exercito",
    "guard": "guarda,guardas,sentinela,guard",
    "knight": "cavaleiro,knight,heroi medieval",
    "roman": "romano,senador,cesar,romans",
    "viking": "viking,vikings,nordico",
    "scientist": "cientista,inventor,pesquisador,scientist,einstein",
    "doctor": "medico,medica,doutor,doctor,cirurgiao",
    "nurse": "enfermeira,enfermeiro,nurse",
    "teacher": "professor,professora,teacher,mestre",
    "student": "estudante,aluno,aluna,student",
    "police": "policial,policia,policiais,guarda municipal,police,cop,xerife",
    "detective": "detetive,investigador,detective,sherlock",
    "agent": "agente,agentes,seguranca,guarda costas,espiao,fbi,governo,homens de preto,agent",
    "businessman": "empresario,executivo,chefe,gerente,ceo,advogado,politico,businessman,milionario",
    "reporter": "reporter,jornalista,apresentador,ancora,noticia,reporter de tv",
    "chef": "chef,cozinheiro,cozinheira,padeiro",
    "farmer": "fazendeiro,agricultor,caipira,campones,farmer,sitiante",
    "worker": "operario,pedreiro,construtor,trabalhador,engenheiro,mecanico,worker",
    "astronaut": "astronauta,cosmonauta,astronaut",
    "pilot": "piloto,aviador,pilot",
    "firefighter": "bombeiro,bombeiros,firefighter",
    "athlete": "atleta,jogador,corredor,esportista,lutador,athlete",
    "superhero": "super heroi,superheroi,heroi,superhero",
    "ninja": "ninja,samurai",
    "pirate": "pirata,pirate,capitao pirata",
    "cowboy": "cowboy,vaqueiro,peao",
    "explorer": "explorador,aventureiro,arqueologo,turista,viajante,explorer",
    "wizard": "mago,feiticeiro,bruxo,merlin,wizard",
    "witch": "bruxa,feiticeira,witch,cuca",
    "vampire": "vampiro,dracula,vampire",
    "zombie": "zumbi,zombie,morto vivo",
    "ghost": "fantasma,espirito,assombracao,alma penada,ghost",
    "robot": "robo,robot,androide,maquina,ia,inteligencia artificial",
    "alien": "alien,alienigena,et,extraterrestre,marciano",
    "caveman": "homem das cavernas,caveman,primitivo",
    "musician": "musico,cantor,cantora,guitarrista,rockstar,dj,musician",
    "influencer": "influencer,youtuber,tiktoker,blogueira,blogueiro,celebridade,famoso",
    "mermaid": "sereia,iara,mermaid",
    "saci": "saci,saci perere",
    "curupira": "curupira",
    "cat": "gato,gata,gatinho,cat", "dog": "cachorro,cao,cachorrinho,dog,filhote", "fox": "raposa,fox",
    "lion": "leao,leoa,lion", "tiger": "tigre,onca,jaguar,tiger", "bear": "urso,ursinho,bear",
    "panda": "panda", "rabbit": "coelho,coelhinho,rabbit", "mouse": "rato,ratinho,camundongo,mouse",
    "sheep": "ovelha,ovelhas,cordeiro,carneiro,sheep,lamb", "cow": "vaca,boi,touro,bezerro,cow",
    "pig": "porco,porquinho,pig", "horse": "cavalo,egua,potro,horse", "unicorn": "unicornio,unicorn",
    "donkey": "burro,jumento,jumentinho,donkey", "camel": "camelo,dromedario,camel",
    "elephant": "elefante,elephant", "monkey": "macaco,mico,gorila,monkey", "capybara": "capivara,capybara",
    "frog": "sapo,ra,perereca,frog", "dinosaur": "dinossauro,dino,tiranossauro,dinosaur", "dragon": "dragao,dragon",
    "wolf": "lobo,loba,wolf", "deer": "veado,cervo,rena,deer", "goat": "cabra,bode,goat", "squirrel": "esquilo,squirrel",
    "koala": "coala,koala", "bird": "passaro,passarinho,ave,bird", "dove": "pomba,pombinha,dove",
    "chicken": "galinha,galo,chicken", "chick": "pintinho,chick", "duck": "pato,patinho,duck",
    "owl": "coruja,owl", "parrot": "papagaio,arara,parrot", "penguin": "pinguim,penguin", "eagle": "aguia,falcao,eagle",
    "flamingo": "flamingo", "toucan": "tucano,toucan", "crow": "corvo,urubu,crow", "bat": "morcego,bat",
    "fish": "peixe,peixes,peixinho,fish", "goldfish": "peixe dourado,goldfish", "shark": "tubarao,shark",
    "whale": "baleia,whale", "dolphin": "golfinho,boto,dolphin", "turtle": "tartaruga,jabuti,turtle",
    "snake": "cobra,serpente,snake", "butterfly": "borboleta,butterfly", "bee": "abelha,bee",
    "ladybug": "joaninha,ladybug", "octopus": "polvo,octopus", "crab": "caranguejo,siri,crab", "spider": "aranha,spider",
}  # fmt: skip

PROP_WORDS = {
    "tree": "arvore,arvores,tree", "pine": "pinheiro,pine,arvore de natal", "palm": "palmeira,coqueiro,palm",
    "bush": "arbusto,moita,bush", "flower": "flor,flores,rosa,girassol,flower", "rock": "pedra,rocha,rock",
    "cactus": "cacto,cactus", "mushroom": "cogumelo,mushroom", "grass": "grama,capim,grass",
    "dead_tree": "arvore seca,galho seco,dead tree", "mountain": "montanha,monte,morro,mountain",
    "volcano": "vulcao,volcano", "cloud": "nuvem,nuvens,cloud", "sun": "sol,sun", "moon": "lua,moon",
    "star": "estrela,estrelas,star", "rainbow": "arco iris,rainbow", "house": "casa,casinha,lar,house,home",
    "building": "predio,edificio,arranha ceu,building", "church": "igreja,capela,church",
    "castle": "castelo,castle", "tower": "torre,tower,torre de babel", "pyramid": "piramide,pyramid",
    "temple": "templo,temple,santuario", "tent": "tenda,barraca,tent", "hut": "cabana,oca,hut",
    "barn": "celeiro,estabulo vermelho,barn", "statue": "estatua,estatua de ouro,idolo,imagem de ouro,statue,idol",
    "throne": "trono,throne", "furnace": "fornalha,forno,fornalha ardente,furnace,oven",
    "well": "poco,well", "manger": "manjedoura,berco de palha,manger", "stable": "estabulo,presepio,stable",
    "column": "coluna,pilar,column", "fence": "cerca,fence", "lamp_post": "poste,lamp post",
    "tombstone": "tumulo,lapide,tumba,tombstone", "cross": "cruz,crucifixo,cross", "sign": "placa,letreiro,sign",
    "door": "porta,portao,door", "table": "mesa,table", "chair": "cadeira,chair", "bed": "cama,bed",
    "sofa": "sofa,couch", "tv": "televisao,tv,televisor,jornal da tv,noticiario", "computer": "computador,pc,computer",
    "laptop": "notebook,laptop", "car": "carro,carros,car", "police_car": "viatura,carro de policia,police car",
    "taxi": "taxi", "bus": "onibus,bus", "truck": "caminhao,truck", "boat": "barco,canoa,boat",
    "ship": "navio,arca,arca de noe,ship", "chest": "bau,cofre,chest", "treasure": "tesouro,treasure",
    "box": "caixa,caixote,box,pacote", "gift": "presente,presentes,gift", "candle": "vela,velas,candle",
    "advent_wreath": "coroa do advento,advent wreath", "campfire": "fogueira,campfire", "bench": "banco,bench",
    "snowman": "boneco de neve,snowman", "rocket": "foguete,nave,rocket", "airplane": "aviao,airplane,plane",
    "trophy": "trofeu,taca,trophy", "globe": "globo terrestre,globe", "heart": "coracao,coracoes,amor,heart,love",
    "broken_heart": "coracao partido,broken heart", "coin": "moeda,moedas,coin", "money": "dinheiro,nota,grana,money,cash",
    "money_bag": "saco de dinheiro,money bag,fortuna", "gem": "joia,diamante,gem,diamond",
    "crown": "coroa,crown", "ring": "anel,alianca,ring", "ring_box": "caixinha de anel,pedido de casamento,ring box",
    "phone": "celular,telefone,smartphone,mensagens,phone", "book": "livro,livros,caderno,book",
    "bible": "biblia,escrituras,bible", "scroll": "pergaminho,rolo,scroll", "tablets": "tabuas da lei,mandamentos,tablets",
    "letter": "carta,envelope,convite,convites,letter", "newspaper": "jornal,newspaper", "lightbulb": "lampada,ideia,lightbulb,idea",
    "question": "pergunta,interrogacao,question", "exclamation": "exclamacao,alerta,exclamation",
    "check": "certo,correto,check,visto", "x_mark": "errado,x,proibido,wrong", "clock": "relogio,clock,hora",
    "hourglass": "ampulheta,hourglass,tempo", "calendar": "calendario,data,calendar", "magnifier": "lupa,magnifier",
    "key": "chave,key", "lock": "cadeado,lock", "dna": "dna,genetica,gene", "atom": "atomo,atom",
    "flask": "frasco,tubo de ensaio,pocao,flask,potion", "pill": "remedio,pilula,comprimido,pill",
    "brain": "cerebro,mente,brain", "camera": "camera,foto,camera fotografica", "microphone": "microfone,microphone,mic",
    "megaphone": "megafone,megaphone", "music_note": "nota musical,musica,music note", "medal": "medalha,medal",
    "bomb": "bomba,bomb", "fire": "fogo,chamas,fire,flames", "lightning": "raio,relampago,lightning",
    "explosion": "explosao,boom,explosion", "skull": "caveira,cranio,skull", "pin": "alfinete,localizacao,mapa,pin",
    "target": "alvo,meta,target", "gear": "engrenagem,gear", "shield": "escudo,shield", "sword": "espada,sword",
    "cup": "calice,copo,cup", "bread": "pao,paes,bread", "apple": "maca,fruta,apple", "pizza": "pizza",
    "burger": "hamburguer,lanche,burger", "cake": "bolo,cake", "coffee": "cafe,coffee", "balloon": "balao,baloes,balloon",
    "ball": "bola,ball", "earth": "terra,planeta terra,mundo,earth,world", "planet": "planeta,planetas,saturno,marte,planet",
    "comet": "cometa,asteroide,meteoro,comet", "ufo": "ovni,disco voador,ufo", "eye": "olho,olhos,eye",
    "thumbs_up": "curtida,like,joinha,thumbs up", "chat": "conversa,chat,mensagem,balao de conversa", "arrow": "seta,arrow",
}  # fmt: skip

PLACE_WORDS = {
    "plain": "fundo liso,fundo,plain,abstrato,estudio", "room": "sala,casa por dentro,interior,room",
    "bedroom": "quarto,dormitorio,bedroom", "living_room": "sala de estar,living room", "office": "escritorio,empresa,office",
    "classroom": "sala de aula,escola,classroom,school", "lab": "laboratorio,hospital,clinica,lab",
    "church": "igreja,capela,church,missa", "palace": "palacio,sala do trono,corte,palace,throne room",
    "street": "rua,bairro,vizinhanca,street", "city": "cidade,centro,metropole,city",
    "ancient_city": "cidade antiga,babilonia,jerusalem,nazare,belem,roma antiga,ancient city",
    "desert": "deserto,sertao,desert", "egypt": "egito,egypt", "village": "vila,aldeia,povoado,village",
    "farm": "fazenda,sitio,roca,farm", "forest": "floresta,bosque,mata,forest", "park": "parque,praca,jardim,park",
    "hills": "campo,colinas,morros,pasto,campo verde,hills,field", "beach": "praia,litoral,mar,beach,ocean",
    "underwater": "fundo do mar,oceano profundo,debaixo d agua,underwater", "space": "espaco,universo,cosmos,space",
    "sky": "ceu,paraiso,nuvens,heaven,sky", "night_city": "cidade a noite,noite na cidade,night city",
    "graveyard": "cemiterio,graveyard", "cave": "caverna,gruta,cave", "mountains": "montanhas,serra,mountains",
    "snow": "neve,gelo,polo,snow", "fire": "fornalha,dentro do fogo,inferno,fire", "stage": "palco,show,teatro,estudio de tv,stage",
    "stable": "estabulo,presepio,manjedoura,stable", "temple": "templo,grecia,olimpo,temple",
    "castle": "castelo,reino,castle", "jungle": "selva,amazonia,jungle",
}  # fmt: skip

ACTION_WORDS_2D = {
    "idle": "parado,idle,esperar,ficar", "talk": "falar,fala,falando,conversar,explicar,contar,dizer,talk,speak",
    "walk_in": "entrar,entra,chegar,chega,aparece andando,walk in,enter,arrive",
    "walk_out": "sair,sai,ir embora,vai embora,partir,walk out,leave,exit",
    "walk": "andar,anda,caminhar,caminha,andando,walk", "run": "correr,corre,correndo,fugir,foge,run,escape",
    "jump": "pular,pula,saltar,pulo,jump", "wave": "acenar,acena,tchau,oi,wave",
    "point": "apontar,aponta,mostrar para,indicar,point", "cheer": "comemorar,comemora,celebrar,vibrar,festejar,cheer",
    "clap": "aplaudir,palmas,clap", "think": "pensar,pensa,pensando,duvida,imaginar,think",
    "surprised": "surpreso,surpresa,espantado,chocado,susto,surprised,shocked",
    "scared": "medo,assustado,com medo,apavorado,tremer,scared,afraid", "sad": "triste,tristeza,desanimado,sad",
    "cry": "chorar,chora,chorando,lagrimas,cry", "angry": "bravo,raiva,irritado,furioso,angry,mad",
    "laugh": "rir,ri,gargalhar,risada,laugh", "bow": "curvar,reverencia,bow", "kneel": "ajoelhar,ajoelha,prostrar,ir ao chao,kneel",
    "pray": "orar,ora,rezar,reza,oracao,pray", "sit": "sentar,senta,sentado,sit", "sleep": "dormir,dorme,dormindo,sleep",
    "lie": "deitar,deita,deitado,lie down", "fall": "cair,cai,tropecar,desmaiar,fall",
    "dance": "dancar,danca,dance", "look": "olhar,procurar,observar,look,search", "nod": "concordar,sim,acenar com a cabeca,nod",
    "shake_head": "discordar,nao,negar,shake head", "shrug": "dar de ombros,sei la,shrug",
    "hold_up": "mostrar,erguer,segurar,levantar,hold up,show", "spin": "girar,gira,rodopiar,spin",
    "float": "flutuar,flutua,pairar,float,hover", "fly": "voar,voa,voando,fly", "appear": "aparecer,aparece,surgir,appear",
    "vanish": "sumir,some,desaparecer,vanish,disappear", "eat": "comer,come,beber,eat", "hop": "saltitar,hop",
    "swim": "nadar,nada,swim", "pop": "pop,brotar", "drop": "cair do ceu,despencar,drop", "fly_in": "entrar voando,fly in",
    "fly_out": "sair voando,fly out", "rise": "subir,sobe,decolar,levantar voo,rise,launch", "shake": "sacudir,vibrar,shake",
    "pulse": "pulsar,pulse,batida", "grow": "crescer,cresce,aumentar,grow", "shrink": "encolher,diminuir,shrink",
    "glow": "brilhar,brilha,iluminar,glow,shine", "burn": "queimar,pegar fogo,arder,burn", "ring": "tocar,toca,ligar,chamar,ring",
    "bounce": "quicar,bounce", "slide": "deslizar,passar,slide,drive", "open": "abrir,abre,open",
    "orbit": "orbitar,girar em volta,orbit", "sway": "balancar,sway", "spin_loop": "rodar sem parar,spin loop",
}  # fmt: skip

FX_WORDS = {
    "confetti": "confete,festa,confetti,party", "hearts": "coracoes,amor,apaixonado,hearts,love",
    "notes": "musica,notas musicais,notes,music", "stars": "estrelas,stars", "sparkles": "brilho,brilhos,magia,sparkles,magic",
    "money": "chuva de dinheiro,dinheiro,money", "coins": "moedas,coins", "rain": "chuva,chovendo,rain",
    "snow": "neve,nevando,snow", "leaves": "folhas,outono,leaves", "bubbles": "bolhas,bubbles", "embers": "brasas,faiscas,embers",
    "fire": "fogo,chamas,fire", "smoke": "fumaca,smoke", "zzz": "dormindo,zzz,sono", "question": "duvida,interrogacao,question",
    "lightning": "raio,trovao,tempestade,lightning,storm", "rays": "raios de luz,luz divina,gloria,rays,light",
    "spotlight": "holofote,destaque,celebridade,spotlight", "flash": "flash,clarao", "shake": "tremor,terremoto,shake",
}  # fmt: skip

CAMERA_WORDS_2D = {"zoom_in": "aproximar,zoom,zoom in,close", "zoom_out": "afastar,zoom out", "pan_left": "pan left,esquerda",
                   "pan_right": "panoramica,pan,pan right,direita", "static": "parada,fixa,static",
                   "punch": "impacto,punch", "shake": "tremida,shake"}  # fmt: skip
POS_WORDS_2D = {"center": "centro,meio,center", "left": "esquerda,left", "right": "direita,right",
                "far_left": "canto esquerdo,far left", "far_right": "canto direito,far right", "back": "fundo,atras,back",
                "back_left": "fundo esquerda,back left", "back_right": "fundo direita,back right",
                "front": "frente,front", "sky": "ceu,alto,sky,top", "above": "acima,em cima,sobre,above"}  # fmt: skip

CHAR_INDEX = _index(CHAR_WORDS)
PROP_INDEX = _index(PROP_WORDS)
PLACE_INDEX = _index(PLACE_WORDS)
ACTION_INDEX = _index(ACTION_WORDS_2D)
FX_INDEX = _index(FX_WORDS)
CAM_INDEX = _index(CAMERA_WORDS_2D)
POS_INDEX = _index(POS_WORDS_2D)
VALID_ACTIONS = set(NATURAL) | set(CHAR_ACTIONS)
VALID_POS = set(POS) | {"above"}
MAX_INSTANCES = 24


@dataclass
class Story:
    title: str = ""
    caption: str = ""
    hashtags: list = field(default_factory=list)
    cast: dict = field(default_factory=dict)  # id -> Element2D modelo (tipo + aparência + nome)
    scenes: list = field(default_factory=list)  # SceneSpec2D
    raw_scenes: list = field(default_factory=list)


def _str(v, limit: int) -> str:
    if v is None or v is False:
        return ""
    s = re.sub(r"\s+", " ", str(v)).strip().strip('"')
    return s[:limit]


def _num(v, default: float, lo: float, hi: float) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return default if x != x else min(max(x, lo), hi)


def _size(v) -> float:
    if isinstance(v, str):
        p = plain(v)
        if p in ("big", "grande", "enorme", "huge", "large", "gigante"):
            return 1.5
        if p in ("small", "pequeno", "pequena", "tiny", "mini"):
            return 0.7
    return _num(v, 1.0, 0.4, 2.5)


def char_type(value) -> str:
    v = plain(value).replace(" ", "_")
    if v in CHARACTER_TYPES or v in CRITTERS:
        return v
    return lookup(value, CHAR_INDEX) or ""


def prop_type(value) -> str:
    v = plain(value).replace(" ", "_")
    if v in PROPS:
        return v
    return lookup(value, PROP_INDEX) or ""


def actions(value, kind: str = "char") -> list[str]:
    if isinstance(value, str):
        items = re.split(r"[,;/>|]|\bthen\b|\bdepois\b|\be\b|\band\b", value)
    elif isinstance(value, (list, tuple)):
        items = [str(x) for x in value]
    else:
        items = []
    out: list[str] = []
    for it in items:
        k = plain(it).replace(" ", "_")
        a = k if k in VALID_ACTIONS else lookup(it, ACTION_INDEX)
        if a and (not out or out[-1] != a):
            out.append(a)
    return out[:3]


def _look_extra(raw: dict) -> dict:
    extra: dict = {}
    hold = plain(raw.get("hold", "")).replace(" ", "_")
    if hold in HOLD_ITEMS:
        extra["hold"] = hold
    beard = plain(raw.get("beard", ""))
    if beard in ("full", "short", "mustache", "goatee"):
        extra["beard"] = beard
    elif beard in ("true", "yes", "sim", "1"):
        extra["beard"] = "short"
    if str(raw.get("glasses", "")).lower() in ("true", "1", "sim", "yes"):
        extra["extras"] = ("glasses",)
    return extra


def build_cast(raw_cast) -> dict:
    cast: dict = {}
    if isinstance(raw_cast, dict):
        raw_cast = [{"id": k, **(v if isinstance(v, dict) else {"type": v})} for k, v in raw_cast.items()]
    for i, c in enumerate(raw_cast if isinstance(raw_cast, list) else []):
        if isinstance(c, str):
            c = {"id": c, "type": c}
        if not isinstance(c, dict):
            continue
        cid = plain(c.get("id") or c.get("name") or f"p{i}").replace(" ", "_")[:24] or f"p{i}"
        kind = char_type(c.get("type") or c.get("kind") or "") or char_type(c.get("name") or "") or "person"
        color = parse_color(c.get("color"))
        skin = c.get("skin") if plain(c.get("skin", "")) in SKINS else None
        hair = c.get("hair") if plain(c.get("hair", "")) in HAIRS else None
        look = make_look(kind, cid, color, skin, hair, _look_extra(c))
        name = _str(c.get("name"), 28)
        cast[cid] = Element2D("char", kind, cid, look, label=name, color=color)
        if len(cast) >= 8:
            break
    return cast


def _element(raw, cast: dict, scene_i: int, j: int) -> Element2D | None:
    if isinstance(raw, str):
        key = plain(raw).replace(" ", "_")
        raw = {"id": key} if key in cast else {"type": raw}
    if not isinstance(raw, dict):
        return None
    ref = plain(raw.get("id") or raw.get("who") or "").replace(" ", "_")
    if ref and ref in cast:
        base = cast[ref]
        el = Element2D("char", base.type, ref, base.look, color=base.color)
    else:
        name = raw.get("prop") or raw.get("object") or ""
        ptype = prop_type(name) if name else ""
        ctype = "" if ptype else char_type(raw.get("type") or raw.get("who") or raw.get("id") or "")
        if not ptype and not ctype:
            ptype = prop_type(raw.get("type") or raw.get("id") or "")
        if ctype:
            color = parse_color(raw.get("color"))
            el = Element2D(
                "char",
                ctype,
                "",
                make_look(ctype, f"{scene_i}-{j}", color, extra=_look_extra(raw)),
                color=color,
            )
        elif ptype:
            el = Element2D("prop", ptype, color=parse_color(raw.get("color")))
        else:
            return None
    el.count = int(_num(raw.get("count", 1), 1, 1, 12))
    el.actions = actions(raw.get("do") or raw.get("action") or raw.get("actions") or "", el.kind) or ["idle"]
    at = plain(raw.get("at") or raw.get("position") or "").replace(" ", "_")
    el.at = at if at in VALID_POS else (lookup(raw.get("at") or raw.get("position") or "", POS_INDEX) or "")
    el.size = _size(raw.get("size", 1.0))
    lab = raw.get("label")
    if lab is True and el.ref:
        el.label = cast[el.ref].label
    elif isinstance(lab, str) and lab.strip().lower() not in ("true", "false", ""):
        el.label = _str(lab, 26)
    el.say = _str(raw.get("say"), 70)
    f = plain(raw.get("facing", ""))
    el.facing = f if f in ("left", "right", "camera", "front", "center") else ""
    return el


def normalize_story(raw, n_scenes: int = 6, theme_place: str = "plain", theme_actor: str = "person",
                    banner_color: int = 0, tag: str = "") -> Story:  # fmt: skip
    """Transforma o JSON da IA (ou do roteiro automático) numa história pronta para o motor 2D."""
    raw = raw if isinstance(raw, dict) else {}
    cast = build_cast(raw.get("cast") or raw.get("characters") or [])
    raw_scenes = [s for s in (raw.get("scenes") or []) if isinstance(s, dict)][: max(1, n_scenes)]
    story = Story(
        title=_str(raw.get("title"), 200),
        caption=_str(raw.get("caption"), 500),
        cast=cast,
        raw_scenes=raw_scenes,
    )
    tags = raw.get("hashtags") or []
    story.hashtags = tags.split() if isinstance(tags, str) else [str(t) for t in tags if t][:10]
    prev_place, prev_time = theme_place if theme_place in PLACES else "plain", "day"
    prev_ids: set[str] = set()
    for i, s in enumerate(raw_scenes):
        narr = _str(s.get("narration") or s.get("text") or s.get("caption"), 400)
        place = plain(s.get("place") or s.get("setting") or "").replace(" ", "_")
        if place not in PLACES:
            place = lookup(s.get("place") or s.get("setting") or "", PLACE_INDEX) or ""
        place = place or (scan(narr, PLACE_INDEX, None, 1) or [""])[0] or prev_place
        time = plain(s.get("time") or "")
        time = time if time in ("day", "sunset", "night", "dawn") else {"noite": "night", "dia": "day",
                                                                         "por do sol": "sunset", "amanhecer": "dawn"}.get(time, prev_time)  # fmt: skip
        show = s.get("show") or s.get("elements") or s.get("actors") or []
        if isinstance(show, (dict, str)):
            show = [show]
        els = [e for e in (_element(x, cast, i, j) for j, x in enumerate(show[:5])) if e is not None]
        if not els:
            els = _infer_elements(narr, cast, theme_actor, i)
        total = 0
        for e in els:
            e.count = max(1, min(e.count, MAX_INSTANCES - total))
            total += e.count
        items = s.get("list") or s.get("items") or []
        if isinstance(items, str):
            items = [x.strip() for x in re.split(r"[;\n]", items) if x.strip()]
        fx = plain(s.get("fx") or s.get("effect") or "")
        fx = fx if fx in FX or fx == "shake" else (lookup(s.get("fx") or "", FX_INDEX) or "")
        cam = plain(s.get("camera") or "").replace(" ", "_")
        cam = cam if cam in CAMERAS else (lookup(s.get("camera") or "", CAM_INDEX) or "")
        chart = plain(s.get("chart") or "")
        spec = SceneSpec2D(
            place=place,
            time=time,
            elements=els,
            banner=_str(s.get("banner") or s.get("title"), 48),
            card=_str(s.get("card") or s.get("subtitle"), 60),
            tag=_str(s.get("tag"), 28) or (tag if i == 0 else ""),
            sticker=_str(s.get("sticker"), 32),
            items=[_str(x, 60) for x in items if str(x).strip()][:5],
            items_title=_str(s.get("list_title"), 30),
            number=_str(s.get("number"), 40),
            chart=chart if chart in ("up", "down", "wave") else "",
            fx=fx,
            camera=cam,
            color=parse_color(s.get("color")),
            banner_color=banner_color,
            narration=narr,
            keep=sorted(prev_ids & {e.ref for e in els if e.ref}),
        )
        story.scenes.append(spec)
        prev_place, prev_time = place, time
        prev_ids = {e.ref for e in els if e.ref}
    return story


def _infer_elements(text: str, cast: dict, default_actor: str, i: int) -> list[Element2D]:
    els: list[Element2D] = []
    words = plain(text)
    for cid, c in cast.items():
        if cid.replace("_", " ") in words or (c.label and plain(c.label) in words):
            els.append(Element2D("char", c.type, cid, c.look, actions=["talk"], color=c.color))
    for t in scan(text, CHAR_INDEX, None, 2):
        if not any(e.type == t for e in els):
            els.append(Element2D("char", t, "", make_look(t, f"inf{i}{t}"), actions=["idle"]))
    for t in scan(text, PROP_INDEX, None, 2):
        els.append(Element2D("prop", t, actions=["pop"]))
    if not any(e.kind == "char" for e in els):
        if cast:
            cid, c = next(iter(cast.items()))
            els.insert(0, Element2D("char", c.type, cid, c.look, actions=["talk"], color=c.color))
        elif not els:
            els.append(
                Element2D("char", default_actor, "", make_look(default_actor, "main"), actions=["talk"])
            )
    return els[:4]


# ------------------------------------------------------------------ catálogo para a IA
def catalog_text() -> str:
    people = [k for k in CHARACTER_TYPES if k not in ("person",)]
    animals = sorted(CRITTERS)
    char_acts = ("talk, walk_in, walk_out, walk, run, jump, wave, point, cheer, clap, think, surprised, scared, sad, cry, "
                 "angry, laugh, bow, kneel, pray, sit, sleep, fall, dance, look, nod, shake_head, shrug, hold_up, float, "
                 "fly, appear, vanish")  # fmt: skip
    prop_acts = "pop, drop, fly_in, fly_out, rise, float, spin, shake, pulse, grow, shrink, vanish, glow, burn, ring, bounce, open"
    return f"""CATÁLOGO 2D (use SOMENTE estes nomes, em inglês):
- place: {", ".join(PLACES)}
- time: day, sunset, night
- type (personagens): {", ".join(people)}
- animais: {", ".join(animals)}
- prop (objetos): {", ".join(PROPS)}
- do (personagem): {char_acts}
- do (objeto): {prop_acts}
- at: center, left, right, far_left, far_right, back, back_left, back_right, front, sky, above
- fx: {", ".join(FX)}
- camera: zoom_in, zoom_out, pan_left, pan_right, static, punch, shake
- hold (objeto na mão, opcional no cast): {", ".join(HOLD_ITEMS)}"""


# ------------------------------------------------------------------ roteiro sem IA
PLAN = [
    (["walk_in", "wave"], "", "zoom_in"),
    (["talk"], "", "static"),
    (["think"], "question", "pan_right"),
    (["point"], "", "punch"),
    (["surprised"], "sparkles", "zoom_out"),
    (["talk"], "", "static"),
    (["cheer"], "confetti", "zoom_in"),
    (["nod"], "", "pan_left"),
]


def offline_story(prompt: str, n: int, theme_place: str = "plain", theme_actor: str = "person",
                  hashtags=(), words: int = 14) -> dict:  # fmt: skip
    """Roteiro sem IA: personagens, objetos e lugar achados no texto, com ações e efeitos variando por cena."""
    chars = scan(prompt, CHAR_INDEX, None, 3)
    props = scan(prompt, PROP_INDEX, None, 4)
    place = (scan(prompt, PLACE_INDEX, None, 1) or [theme_place])[0]
    main = (chars or [theme_actor])[0]
    others = chars[1:]
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", str(prompt).strip()) if x.strip()]
    tokens = str(prompt).split()
    if len(sentences) >= n:
        chunks = sentences[:n]
    else:
        per = max(3, min(words, -(-len(tokens) // max(n, 1))))
        chunks = [" ".join(tokens[i : i + per]) for i in range(0, len(tokens), per)]
    title_words = " ".join(tokens[:4]).upper()
    scenes = []
    for i in range(max(1, n)):
        acts, fx, cam = PLAN[i % len(PLAN)]
        show = [{"id": "main", "do": acts, "at": "center" if not others else "left"}]
        if others:
            show.append({"type": others[i % len(others)], "do": ["talk" if i % 2 else "nod"], "at": "right"})
        if props:
            show.append({"prop": props[i % len(props)], "do": ["pop"]})
        scenes.append({
            "narration": chunks[i] if i < len(chunks) else "",
            "place": place,
            "banner": title_words if i == 0 else "",
            "show": show,
            "fx": fx,
            "camera": cam,
        })  # fmt: skip
    return {
        "title": str(prompt)[:90],
        "caption": str(prompt)[:200],
        "hashtags": list(hashtags),
        "cast": [{"id": "main", "type": main}],
        "scenes": scenes,
    }
